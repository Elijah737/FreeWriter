#!/usr/bin/env python3
"""
nu_notes — hierarchical notebook/note TUI
Storage: ~/nu_notes/  (folders = notebooks, .txt files = notes)

Navigation
  Tab            switch focus: list ↔ editor
  ↑ / ↓          move selection (list) or cursor (editor)
  → / ←          enter notebook / open note  |  go up a level  (list)
                 move cursor left/right (editor)
  Ctrl+Q         save & quit
  Ctrl+S         save current note

Global commands (work from any pane)
  Ctrl+N         new note in current directory
  Ctrl+B         new notebook in current directory
  Ctrl+D         delete selected item
  Ctrl+C         copy selected item

Custom markup (rendered in editor; stored as-is in .txt files)
  ##word##       phosphor green bold
  ###word###     cyan
  ##!!word##     phosphor green bold  (!! inside ## = bold + colour)
  ###!!word###   cyan bold
  !!word!!       bold (default colour)
"""

import curses
import os
import re
import shutil
import textwrap

ROOT = os.path.expanduser("~/nu_notes")

PANE_LIST   = 0
PANE_EDITOR = 1

_PHOSPHOR_ATTR = curses.A_BOLD   # set properly after color init


# ── Filesystem helpers ────────────────────────────────────────────────────────

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def list_dir(path):
    """Notebooks (dirs) first, then notes (.txt files), both sorted."""
    try:
        entries = os.listdir(path)
    except OSError:
        return []
    notebooks = sorted(e for e in entries
                       if os.path.isdir(os.path.join(path, e))
                       and not e.startswith("."))
    notes     = sorted(e[:-4] for e in entries
                       if e.endswith(".txt")
                       and os.path.isfile(os.path.join(path, e)))
    return [(n, True) for n in notebooks] + [(n, False) for n in notes]

def note_path(directory, name):
    return os.path.join(directory, name + ".txt")

def read_note(directory, name):
    try:
        with open(note_path(directory, name), "r") as f:
            return f.read()
    except OSError:
        return ""

def write_note(directory, name, content):
    with open(note_path(directory, name), "w") as f:
        f.write(content)

def safe_name(s):
    return s.replace("/", "_").replace("\\", "_").strip()


# ── Word-wrap helpers ─────────────────────────────────────────────────────────

def strip_markup(text):
    """Remove ##...## and !!...!! markers for layout/wrap calculations."""
    text = re.sub(r'##(.+?)##', r'\1', text)
    text = re.sub(r'!!(.+?)!!', r'\1', text)
    return text

def _build_maps(raw_line):
    """
    Walk raw_line once and build two lookup tables:

      raw_to_plain[r]  — for raw index r, the plain (screen) column.
                         Token characters map to the plain col of the
                         nearest following visible character (or the
                         final plain length if at end).
      plain_to_raw[p]  — for plain index p, the raw index of that
                         visible character.

    "Token characters" are the markup syntax chars (##, ###, !!) that
    are not rendered on screen.  Visible characters are everything else.

    Both arrays have length len(raw_line)+1 so index [len] is valid and
    gives the "one past end" position.
    """
    n = len(raw_line)
    # is_token[i] = True if raw_line[i] is a markup syntax character
    is_token = [False] * n
    for m in _MARKUP_RE.finditer(raw_line):
        # Use regex group spans — reliable even if inner text appears in prefix
        inner_grp = next((g for g in (2, 4, 6, 8, 10) if m.group(g) is not None), None)
        if inner_grp:
            inner_start, inner_end = m.start(inner_grp), m.end(inner_grp)
        else:
            inner_start, inner_end = m.start(), m.end()
        # everything in the match except the inner text is a token char
        for i in range(m.start(), m.end()):
            is_token[i] = not (inner_start <= i < inner_end)

    # Build plain_to_raw: list of raw indices for each plain char
    plain_to_raw = []
    for i in range(n):
        if not is_token[i]:
            plain_to_raw.append(i)
    plain_len = len(plain_to_raw)

    # Build raw_to_plain: for each raw index, its plain column.
    # Token chars are mapped to the plain col of the next visible char
    # (so the cursor snaps forward past the token, not backwards).
    raw_to_plain = [0] * (n + 1)
    # fill forwards for visible chars
    p = 0
    for i in range(n):
        if not is_token[i]:
            raw_to_plain[i] = p
            p += 1
        # token chars will be fixed in the backwards pass below
    raw_to_plain[n] = plain_len   # sentinel

    # Backwards pass: token chars get the plain col of the next visible char
    last_plain = plain_len
    for i in range(n - 1, -1, -1):
        if is_token[i]:
            raw_to_plain[i] = last_plain
        else:
            last_plain = raw_to_plain[i]

    return raw_to_plain, plain_to_raw


def raw_col_to_plain(raw_line, raw_col):
    """Return the plain (screen) column for a raw index."""
    raw_to_plain, _ = _build_maps(raw_line)
    raw_col = max(0, min(raw_col, len(raw_line)))
    return raw_to_plain[raw_col]


def plain_col_to_raw(raw_line, plain_col):
    """Return the raw index for a plain (screen) column."""
    _, plain_to_raw = _build_maps(raw_line)
    plain_col = max(0, min(plain_col, len(plain_to_raw)))
    if plain_col >= len(plain_to_raw):
        # past end of visible text — return raw end position
        return len(raw_line)
    return plain_to_raw[plain_col]


def wrap_lines(logical_lines, width):
    """
    Wrap logical lines to visual rows.
    Wrapping is done on stripped text (correct screen widths).
    row_map stores (logical_line_index, plain_col_start) — plain offsets,
    so they can be compared against raw_col_to_plain() results.
    visual_rows stores the plain-text segment for length reference.
    """
    visual_rows, row_map = [], []
    for li, line in enumerate(logical_lines):
        plain = strip_markup(line)
        if not plain:
            visual_rows.append("")
            row_map.append((li, 0))
        else:
            segs = textwrap.wrap(plain, width,
                                 drop_whitespace=False,
                                 break_long_words=True,
                                 break_on_hyphens=False) or [""]
            col = 0
            for seg in segs:
                visual_rows.append(seg)
                row_map.append((li, col))   # col is plain-text offset
                col += len(seg)
    return visual_rows, row_map


def logical_to_visual(lrow, lcol, row_map, editor_lines):
    """
    Convert (logical_row, raw_col) to (visual_row, screen_x).
    lcol is a raw index; we convert it to plain space for comparison.
    """
    raw_line   = editor_lines[lrow]
    plain_lcol = raw_col_to_plain(raw_line, lcol)
    best = 0
    for vr, (li, cs) in enumerate(row_map):
        if li == lrow and cs <= plain_lcol:
            best = vr
    li, cs = row_map[best]
    return best, plain_lcol - cs


# ── Markup renderer ───────────────────────────────────────────────────────────
#
# Syntax (stored verbatim in .txt; rendered on display only):
#   ##word##      phosphor green bold
#   ###word###    cyan
#   ##!!word##    phosphor green bold  (!! inside ## = bold + colour)
#   ###!!word###  cyan bold
#   !!word!!      bold (default terminal colour)
#
# Plain text uses A_NORMAL so it doesn't compete with highlights.
# Match ###...### before ##...## (longer token must come first in alternation).

_MARKUP_RE = re.compile(
    r'(###!!(.+?)###)'    # group 1/2: cyan bold
    r'|(##!!(.+?)##)'     # group 3/4: phosphor bold
    r'|(###(.+?)###)'     # group 5/6: cyan
    r'|(##(.+?)##)'       # group 7/8: phosphor bold
    r'|(!!(.+?)!!)'       # group 9/10: plain bold
)

def _parse_spans(raw_text, attrs):
    """Return [(visible_text, curses_attr), ...] for raw_text."""
    spans = []
    pos   = 0
    for m in _MARKUP_RE.finditer(raw_text):
        if m.start() > pos:
            spans.append((raw_text[pos:m.start()], attrs['default']))
        if m.group(2) is not None:
            spans.append((m.group(2), attrs['cyanbold']))
        elif m.group(4) is not None:
            spans.append((m.group(4), attrs['phobold']))
        elif m.group(6) is not None:
            spans.append((m.group(6), attrs['cyan']))
        elif m.group(8) is not None:
            spans.append((m.group(8), attrs['phobold']))
        elif m.group(10) is not None:
            spans.append((m.group(10), attrs['bold']))
        pos = m.end()
    if pos < len(raw_text):
        spans.append((raw_text[pos:], attrs['default']))
    return spans or [(raw_text, attrs['default'])]

def strip_markup(text):
    """Remove all markup tokens, leaving only visible characters."""
    return _MARKUP_RE.sub(
        lambda m: (m.group(2) or m.group(4) or m.group(6)
                   or m.group(8) or m.group(10) or ''),
        text
    )

def render_markup_segment(win, y, x, raw_line, col_start, seg_len, max_w, attrs):
    """
    Render exactly `seg_len` visible characters of `raw_line` starting at
    plain-text offset `col_start`.

    col_start and seg_len are in *plain* (stripped) space.
    We walk the markup spans, counting only visible characters,
    and emit only those that fall within [col_start, col_start+seg_len).
    """
    spans      = _parse_spans(raw_line, attrs)
    plain_pos  = 0   # plain-char counter through the whole line
    cx         = x
    drawn      = 0

    for text, attr in spans:
        span_plain_end = plain_pos + len(text)
        ov_start = max(plain_pos, col_start)
        ov_end   = min(span_plain_end, col_start + seg_len)

        if ov_start < ov_end:
            chunk = text[ov_start - plain_pos : ov_end - plain_pos]
            chunk = chunk[:max_w - drawn]
            if chunk:
                try:
                    win.addstr(y, cx, chunk, attr)
                except curses.error:
                    pass
                cx    += len(chunk)
                drawn += len(chunk)

        plain_pos = span_plain_end
        if drawn >= seg_len or drawn >= max_w:
            break


# ── UI helpers ────────────────────────────────────────────────────────────────

def draw_border(win, title="", active=False):
    h, w = win.getmaxyx()
    attr = _PHOSPHOR_ATTR if active else curses.A_DIM
    win.attron(attr)
    try:
        win.border()
    except curses.error:
        pass
    if title:
        try:
            win.addstr(0, 2, f" {title} "[:w - 4], attr)
        except curses.error:
            pass
    win.attroff(attr)

def prompt_input(stdscr, prompt, max_len=60):
    sh, sw = stdscr.getmaxyx()
    bw = min(max(len(prompt) + 6, 34), sw - 4)
    bh = 5
    win = curses.newwin(bh, bw, (sh - bh) // 2, (sw - bw) // 2)
    win.keypad(True)
    curses.curs_set(1)
    text = ""
    while True:
        win.erase()
        win.border()
        try:
            win.addstr(1, 2, prompt[:bw - 4])
            win.addstr(2, 2, "─" * (bw - 4))
            disp = text[-(bw - 6):]
            win.addstr(3, 2, disp)
            win.move(3, 2 + len(disp))
        except curses.error:
            pass
        win.refresh()
        ch = win.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            curses.curs_set(0)
            return text.strip() or None
        elif ch == 27:
            curses.curs_set(0)
            return None
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            text = text[:-1]
        elif 32 <= ch <= 126 and len(text) < max_len:
            text += chr(ch)

def show_message(stdscr, msg, color_pair=3):
    sh, sw = stdscr.getmaxyx()
    bw = min(len(msg) + 6, sw - 4)
    win = curses.newwin(3, bw, (sh - 3) // 2, (sw - bw) // 2)
    win.border()
    try:
        win.addstr(1, 3, msg[:bw - 6], curses.color_pair(color_pair))
    except curses.error:
        pass
    win.refresh()
    win.getch()


# ── Main ──────────────────────────────────────────────────────────────────────

def main(stdscr):
    global _PHOSPHOR_ATTR
    ensure_dir(ROOT)
    curses.raw()
    curses.noecho()
    stdscr.keypad(True)
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    # Phosphor palette
    if curses.can_change_color() and curses.COLORS >= 16:
        curses.init_color(10, 200, 1000, 200)   # ≈ #33FF33
        PHOSPHOR = 10
    else:
        PHOSPHOR = curses.COLOR_GREEN

    curses.init_pair(1, PHOSPHOR,            -1)              # phosphor text
    curses.init_pair(2, curses.COLOR_BLACK,   PHOSPHOR)       # selected / HL bar
    curses.init_pair(3, curses.COLOR_RED,     -1)             # error
    curses.init_pair(4, PHOSPHOR,             -1)             # notebook label
    curses.init_pair(5, curses.COLOR_CYAN,    -1)             # ### cyan
    curses.init_pair(6, curses.COLOR_BLACK,   PHOSPHOR)       # cursor cell

    PHO        = curses.color_pair(1) | curses.A_BOLD
    SEL        = curses.color_pair(2) | curses.A_BOLD
    NB_ATTR    = curses.color_pair(4) | curses.A_BOLD
    _PHOSPHOR_ATTR = PHO

    # Markup attribute table — default is A_NORMAL so plain text is uncoloured
    MARKUP_ATTRS = {
        'default':  curses.A_NORMAL,
        'phobold':  curses.color_pair(1) | curses.A_BOLD,        # ##...##
        'cyan':     curses.color_pair(5),                         # ###...###
        'cyanbold': curses.color_pair(5) | curses.A_BOLD,        # ###!!...###
        'bold':     curses.A_BOLD,                                # !!...!!
    }

    # ── Navigation state ──────────────────────────────────────────────────
    cwd_stack   = []
    current_dir = ROOT
    items       = list_dir(current_dir)
    sel         = 0
    active_pane = PANE_LIST

    # ── Editor state ──────────────────────────────────────────────────────
    open_note_name = None
    open_note_dir  = None
    editor_lines   = [""]
    editor_row     = 0
    editor_col     = 0
    editor_vscroll = 0

    # ── Inner helpers ─────────────────────────────────────────────────────

    def refresh_items():
        nonlocal items, sel
        items = list_dir(current_dir)
        sel   = max(0, min(sel, len(items) - 1))

    def do_open_note(directory, name):
        nonlocal open_note_name, open_note_dir
        nonlocal editor_lines, editor_row, editor_col, editor_vscroll
        autosave()
        open_note_name = name
        open_note_dir  = directory
        content        = read_note(directory, name)
        editor_lines   = content.split("\n") if content else [""]
        editor_lines   = editor_lines or [""]
        editor_row     = len(editor_lines) - 1
        editor_col     = len(editor_lines[editor_row])
        editor_vscroll = 0

    def autosave():
        if open_note_name and open_note_dir:
            write_note(open_note_dir, open_note_name, "\n".join(editor_lines))

    # ── Global actions (Ctrl chords, active from any pane) ────────────────

    def action_new_note():
        nonlocal active_pane
        name = prompt_input(stdscr, "New note name:")
        if name:
            s = safe_name(name)
            if os.path.exists(note_path(current_dir, s)):
                show_message(stdscr, f"'{s}' already exists!")
            else:
                write_note(current_dir, s, "")
                refresh_items()
                for i, (n, nb) in enumerate(items):
                    if n == s and not nb:
                        sel_val = i
                        break
                else:
                    sel_val = sel
                nonlocal_set_sel(sel_val)
                do_open_note(current_dir, s)
                active_pane = PANE_EDITOR

    def action_new_notebook():
        name = prompt_input(stdscr, "New notebook name:")
        if name:
            s       = safe_name(name)
            nb_path = os.path.join(current_dir, s)
            if os.path.exists(nb_path):
                show_message(stdscr, f"'{s}' already exists!")
            else:
                ensure_dir(nb_path)
                refresh_items()
                for i, (n, nb) in enumerate(items):
                    if n == s and nb:
                        nonlocal_set_sel(i)
                        break

    def action_delete():
        nonlocal open_note_name, open_note_dir, editor_lines, editor_row, editor_col
        if not items:
            return
        name, is_nb = items[sel]
        kind        = "notebook" if is_nb else "note"
        confirm     = prompt_input(stdscr, f"Delete {kind} '{name}'? Type YES:")
        if confirm and confirm.upper() == "YES":
            target = (os.path.join(current_dir, name)
                      if is_nb else note_path(current_dir, name))
            if is_nb:
                shutil.rmtree(target, ignore_errors=True)
            else:
                os.remove(target)
            if (not is_nb and open_note_name == name
                    and open_note_dir == current_dir):
                open_note_name = None
                open_note_dir  = None
                editor_lines   = [""]
                editor_row     = 0
                editor_col     = 0
            refresh_items()

    def action_copy():
        if not items:
            return
        name, is_nb = items[sel]
        new_name    = prompt_input(stdscr, f"Copy '{name}' to:")
        if new_name:
            s = safe_name(new_name)
            if is_nb:
                dst = os.path.join(current_dir, s)
                if os.path.exists(dst):
                    show_message(stdscr, f"'{s}' already exists!")
                else:
                    shutil.copytree(os.path.join(current_dir, name), dst)
                    refresh_items()
            else:
                if os.path.exists(note_path(current_dir, s)):
                    show_message(stdscr, f"'{s}' already exists!")
                else:
                    shutil.copy2(note_path(current_dir, name),
                                 note_path(current_dir, s))
                    refresh_items()

    # nonlocal helper so lambdas can mutate sel
    def nonlocal_set_sel(v):
        nonlocal sel
        sel = v

    # ── Main loop ─────────────────────────────────────────────────────────

    while True:
        sh, sw = stdscr.getmaxyx()
        if sh < 8 or sw < 40:
            stdscr.erase()
            try:
                stdscr.addstr(0, 0, "Terminal too small — please resize.")
            except curses.error:
                pass
            stdscr.refresh()
            stdscr.getch()
            continue

        # Layout: sidebar ≈ 20% of width, minimum 16, maximum 28
        LIST_W   = max(16, min(28, sw // 5))
        EDITOR_W = sw - LIST_W

        edit_inner_h = sh - 2
        edit_inner_w = EDITOR_W - 3

        # Build wrapped view for editor
        visual_rows, row_map = wrap_lines(editor_lines, edit_inner_w)
        total_vrows          = len(visual_rows)
        vis_cursor_row, vis_cursor_x = logical_to_visual(
            editor_row, editor_col, row_map, editor_lines)

        if vis_cursor_row < editor_vscroll:
            editor_vscroll = vis_cursor_row
        elif vis_cursor_row >= editor_vscroll + edit_inner_h:
            editor_vscroll = vis_cursor_row - edit_inner_h + 1

        stdscr.erase()
        stdscr.noutrefresh()

        # ── Left pane: file tree ───────────────────────────────────────────
        list_win = curses.newwin(sh, LIST_W, 0, 0)
        list_win.keypad(True)

        rel   = os.path.relpath(current_dir, ROOT)
        crumb = "Notes" if rel == "." else rel.replace(os.sep, "/")
        draw_border(list_win, crumb, active=(active_pane == PANE_LIST))

        # Reserve bottom rows for the hint block: divider + 5 hint lines
        HINT_LINES   = 5
        HINT_H       = HINT_LINES + 1          # +1 for the divider row
        list_inner_h = max(1, sh - 2 - HINT_H)
        list_scroll  = max(0, sel - list_inner_h + 1) if sel >= list_inner_h else 0

        for i in range(list_inner_h):
            idx = i + list_scroll
            if idx >= len(items):
                break
            name, is_nb = items[idx]
            prefix = " + " if is_nb else "   "
            disp   = (prefix + name)[:LIST_W - 3]
            try:
                if idx == sel:
                    list_win.addstr(i + 1, 1,
                                    f"{disp:<{LIST_W - 3}}",
                                    SEL)
                elif is_nb:
                    list_win.addstr(i + 1, 1, disp, NB_ATTR)
                else:
                    list_win.addstr(i + 1, 1, disp, curses.color_pair(1))
            except curses.error:
                pass

        if not items:
            try:
                list_win.addstr(1, 2, "(empty)", curses.A_DIM)
            except curses.error:
                pass

        # ── Hint block ────────────────────────────────────────────────────
        divider_y = sh - HINT_H - 1
        hints = [
            ("^N", "new note"),
            ("^B", "new book"),
            ("^D", "delete"),
            ("^C", "copy"),
            ("^S", "save"),
        ]
        try:
            list_win.hline(divider_y, 1, curses.ACS_HLINE, LIST_W - 2,
                           curses.A_DIM)
        except curses.error:
            pass
        for hi, (key, label) in enumerate(hints):
            y = divider_y + 1 + hi
            if y >= sh - 1:
                break
            key_w = len(key)
            try:
                list_win.addstr(y, 1, key,
                                curses.color_pair(1) | curses.A_BOLD)
                list_win.addstr(y, 1 + key_w + 1,
                                label[:LIST_W - key_w - 4],
                                curses.A_DIM)
            except curses.error:
                pass

        list_win.noutrefresh()

        # ── Right pane: editor ────────────────────────────────────────────
        edit_win = curses.newwin(sh, EDITOR_W, 0, LIST_W)
        edit_win.keypad(True)

        note_title = open_note_name or "No note open"
        if open_note_dir and open_note_dir != ROOT:
            rel_dir    = os.path.relpath(open_note_dir, ROOT)
            note_title = rel_dir.replace(os.sep, "/") + "/" + note_title
        draw_border(edit_win, note_title, active=(active_pane == PANE_EDITOR))

        # Render each visible visual row with markup.
        # row_map[vrow] = (logical_line_index, col_start_in_plain_text)
        # visual_rows[vrow] is the plain segment — we use its length to know
        # exactly how many plain chars to draw, starting at col_start.
        for screen_row in range(edit_inner_h):
            vrow = screen_row + editor_vscroll
            if vrow >= total_vrows:
                break
            li, col_start = row_map[vrow]
            raw           = editor_lines[li]          # full raw logical line
            seg_plain     = visual_rows[vrow]         # plain-text segment
            render_markup_segment(edit_win,
                                  screen_row + 1, 2,
                                  raw,
                                  col_start,
                                  len(seg_plain),
                                  edit_inner_w,
                                  MARKUP_ATTRS)

        edit_win.noutrefresh()

        # ── Cursor ────────────────────────────────────────────────────────
        if active_pane == PANE_EDITOR and open_note_name:
            curses.curs_set(2)
            scr_y = max(1, min(vis_cursor_row - editor_vscroll + 1, edit_inner_h))
            scr_x = max(2, min(vis_cursor_x + 2, EDITOR_W - 2))
            # Highlight cursor cell
            vrow_idx  = vis_cursor_row
            plain_seg = visual_rows[vrow_idx] if vrow_idx < len(visual_rows) else ""
            char_here = plain_seg[vis_cursor_x] if vis_cursor_x < len(plain_seg) else " "
            try:
                edit_win.addstr(scr_y, scr_x, char_here, curses.color_pair(6) | curses.A_BOLD)
                edit_win.move(scr_y, scr_x)
            except curses.error:
                pass
            edit_win.noutrefresh()
        else:
            curses.curs_set(0)
            edit_win.noutrefresh()

        curses.doupdate()

        # ── Input — always read from stdscr so Ctrl chords are universal ──
        # We use stdscr.getch() rather than pane-specific windows so that
        # global Ctrl commands fire regardless of which pane is focused.
        ch = stdscr.getch()

        # ── Global Ctrl commands ───────────────────────────────────────────
        if ch == 17:            # Ctrl+Q — save & quit
            autosave()
            break

        if ch == 19:            # Ctrl+S — save
            autosave()
            continue

        if ch == 9:             # Tab — toggle between list and editor only
            active_pane = PANE_EDITOR if active_pane == PANE_LIST else PANE_LIST
            continue

        if ch == 14:            # Ctrl+N — new note
            action_new_note()
            continue

        if ch == 2:             # Ctrl+B — new notebook
            action_new_notebook()
            continue

        if ch == 4:             # Ctrl+D — delete selected
            action_delete()
            continue

        if ch == 3:             # Ctrl+C — copy selected
            action_copy()
            continue

        # ── List pane keys ────────────────────────────────────────────────
        if active_pane == PANE_LIST:

            if ch == curses.KEY_UP:
                sel = max(0, sel - 1)

            elif ch == curses.KEY_DOWN:
                sel = min(len(items) - 1, sel + 1) if items else 0

            elif ch == curses.KEY_RIGHT and items:
                name, is_nb = items[sel]
                if is_nb:
                    cwd_stack.append((current_dir, sel))
                    current_dir = os.path.join(current_dir, name)
                    ensure_dir(current_dir)
                    items = list_dir(current_dir)
                    sel   = 0
                else:
                    do_open_note(current_dir, name)
                    active_pane = PANE_EDITOR

            elif ch == curses.KEY_LEFT:
                if cwd_stack:
                    current_dir, sel = cwd_stack.pop()
                    items = list_dir(current_dir)

            elif ch in (curses.KEY_ENTER, 10, 13) and items:
                name, is_nb = items[sel]
                if is_nb:
                    cwd_stack.append((current_dir, sel))
                    current_dir = os.path.join(current_dir, name)
                    ensure_dir(current_dir)
                    items = list_dir(current_dir)
                    sel   = 0
                else:
                    do_open_note(current_dir, name)
                    active_pane = PANE_EDITOR

        # ── Editor pane keys ──────────────────────────────────────────────
        elif active_pane == PANE_EDITOR and open_note_name:
            cur_line = editor_lines[editor_row]

            if ch == curses.KEY_UP:
                if vis_cursor_row > 0:
                    pv = vis_cursor_row - 1
                    li, cs = row_map[pv]
                    editor_row = li
                    editor_col = min(cs + vis_cursor_x,
                                     cs + len(visual_rows[pv]),
                                     len(editor_lines[li]))

            elif ch == curses.KEY_DOWN:
                if vis_cursor_row < total_vrows - 1:
                    nv = vis_cursor_row + 1
                    li, cs = row_map[nv]
                    editor_row = li
                    editor_col = min(cs + vis_cursor_x,
                                     cs + len(visual_rows[nv]),
                                     len(editor_lines[li]))

            elif ch == curses.KEY_LEFT:
                if editor_col > 0:
                    editor_col -= 1
                elif editor_row > 0:
                    editor_row -= 1
                    editor_col = len(editor_lines[editor_row])

            elif ch == curses.KEY_RIGHT:
                if editor_col < len(cur_line):
                    editor_col += 1
                elif editor_row < len(editor_lines) - 1:
                    editor_row += 1
                    editor_col = 0

            elif ch == curses.KEY_HOME:
                li, cs     = row_map[vis_cursor_row]
                editor_col = cs

            elif ch == curses.KEY_END:
                li, cs     = row_map[vis_cursor_row]
                editor_col = cs + len(visual_rows[vis_cursor_row])

            elif ch == curses.KEY_PPAGE:   # Page Up
                for _ in range(edit_inner_h - 1):
                    if vis_cursor_row > 0:
                        pv = vis_cursor_row - 1
                        li, cs = row_map[pv]
                        editor_row = li
                        editor_col = min(cs + vis_cursor_x,
                                         cs + len(visual_rows[pv]),
                                         len(editor_lines[li]))
                        vis_cursor_row, vis_cursor_x = logical_to_visual(
                            editor_row, editor_col, row_map)

            elif ch == curses.KEY_NPAGE:   # Page Down
                for _ in range(edit_inner_h - 1):
                    if vis_cursor_row < total_vrows - 1:
                        nv = vis_cursor_row + 1
                        li, cs = row_map[nv]
                        editor_row = li
                        editor_col = min(cs + vis_cursor_x,
                                         cs + len(visual_rows[nv]),
                                         len(editor_lines[li]))
                        vis_cursor_row, vis_cursor_x = logical_to_visual(
                            editor_row, editor_col, row_map)

            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if editor_col > 0:
                    editor_lines[editor_row] = (cur_line[:editor_col - 1]
                                                + cur_line[editor_col:])
                    editor_col -= 1
                elif editor_row > 0:
                    prev       = editor_lines[editor_row - 1]
                    editor_col = len(prev)
                    editor_lines[editor_row - 1] = prev + cur_line
                    editor_lines.pop(editor_row)
                    editor_row -= 1
                autosave()

            elif ch == curses.KEY_DC:
                if editor_col < len(cur_line):
                    editor_lines[editor_row] = (cur_line[:editor_col]
                                                + cur_line[editor_col + 1:])
                elif editor_row < len(editor_lines) - 1:
                    editor_lines[editor_row] = (cur_line
                                                + editor_lines[editor_row + 1])
                    editor_lines.pop(editor_row + 1)
                autosave()

            elif ch in (curses.KEY_ENTER, 10, 13):
                tail                      = cur_line[editor_col:]
                editor_lines[editor_row]  = cur_line[:editor_col]
                editor_row               += 1
                editor_lines.insert(editor_row, tail)
                editor_col               = 0
                autosave()

            elif 32 <= ch <= 126:
                editor_lines[editor_row] = (cur_line[:editor_col]
                                            + chr(ch)
                                            + cur_line[editor_col:])
                editor_col += 1
                autosave()


def run():
    ensure_dir(ROOT)
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    print("Thanks for using nu_notes!  Notes saved in ~/nu_notes/")


if __name__ == "__main__":
    run()
