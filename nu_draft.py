#!/usr/bin/env python3
"""
nu_draft — a simple drafting word processor
Spiritual sibling of nu_notes. Phosphor green. Keyboard only.
Drafts stored as .txt files in ~/nu_drafts/

Layout (normal mode)
  ┌─────────────────────────────────┐
  │ [title]          words / chars  │  ← header bar
  ├─────────────────────────────────┤
  │                                 │
  │         writing area            │
  │                                 │
  ├─────────────────────────────────┤
  │  [D]rafts  [N]ew  [R]ename      │  ← action bar
  │  [X]Delete [C]opy  [Q]uit       │
  └─────────────────────────────────┘

Focus mode (Ctrl+F)
  Full-screen writing area, current paragraph highlighted,
  all other text dimmed. Status bar hidden.

Typewriter scroll (Ctrl+T)
  Cursor is kept vertically centered on screen at all times.

Navigation
  Arrow keys      move cursor
  Home / End      start / end of visual line
  PgUp / PgDn     scroll one screen
  Tab             cycle: editor → actions → drafts list
  Ctrl+F          toggle focus mode
  Ctrl+T          toggle typewriter scroll
  Ctrl+S          save
  Ctrl+Q          save & quit
  Esc             close drafts list / cancel dialog
"""

import curses
import os
import shutil
import textwrap

DRAFTS_DIR = os.path.expanduser("~/nu_drafts")

PANE_EDITOR  = 0
PANE_ACTIONS = 1
PANE_LIST    = 2   # overlay

_PHOSPHOR_ATTR = curses.A_BOLD   # overridden after color init


# ── Filesystem ────────────────────────────────────────────────────────────────

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def get_drafts():
    try:
        return sorted(f[:-4] for f in os.listdir(DRAFTS_DIR)
                      if f.endswith(".txt") and
                      os.path.isfile(os.path.join(DRAFTS_DIR, f)))
    except OSError:
        return []

def draft_path(name):
    return os.path.join(DRAFTS_DIR, name + ".txt")

def read_draft(name):
    try:
        with open(draft_path(name), "r") as f:
            return f.read()
    except OSError:
        return ""

def write_draft(name, content):
    with open(draft_path(name), "w") as f:
        f.write(content)

def safe_name(s):
    return s.replace("/", "_").replace("\\", "_").strip()


# ── Word-wrap ─────────────────────────────────────────────────────────────────

def wrap_lines(logical_lines, width):
    visual_rows, row_map = [], []
    for li, line in enumerate(logical_lines):
        if not line:
            visual_rows.append("")
            row_map.append((li, 0))
        else:
            segs = textwrap.wrap(line, width,
                                 drop_whitespace=False,
                                 break_long_words=True,
                                 break_on_hyphens=False) or [""]
            col = 0
            for seg in segs:
                visual_rows.append(seg)
                row_map.append((li, col))
                col += len(seg)
    return visual_rows, row_map

def logical_to_visual(lrow, lcol, row_map):
    best = 0
    for vr, (li, cs) in enumerate(row_map):
        if li == lrow and cs <= lcol:
            best = vr
    li, cs = row_map[best]
    return best, lcol - cs


# ── Stats ─────────────────────────────────────────────────────────────────────

def count_stats(lines):
    full = "\n".join(lines)
    words = len(full.split()) if full.strip() else 0
    chars = sum(len(l) for l in lines)
    return words, chars


# ── UI helpers ────────────────────────────────────────────────────────────────

def draw_border(win, title="", active=False):
    global _PHOSPHOR_ATTR
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
            win.addstr(1, 2, prompt[:bw - 4], _PHOSPHOR_ATTR)
            win.addstr(2, 2, "─" * (bw - 4), curses.A_DIM)
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
        elif ch in (27, 17):
            curses.curs_set(0)
            return None
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            text = text[:-1]
        elif 32 <= ch <= 126 and len(text) < max_len:
            text += chr(ch)

def show_message(stdscr, msg):
    sh, sw = stdscr.getmaxyx()
    bw = min(len(msg) + 6, sw - 4)
    win = curses.newwin(3, bw, (sh - 3) // 2, (sw - bw) // 2)
    win.border()
    try:
        win.addstr(1, 3, msg[:bw - 6], curses.color_pair(3))
    except curses.error:
        pass
    win.refresh()
    win.getch()


# ── Main ──────────────────────────────────────────────────────────────────────

def main(stdscr):
    global _PHOSPHOR_ATTR
    ensure_dir(DRAFTS_DIR)
    curses.raw()
    curses.noecho()
    stdscr.keypad(True)
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()

    if curses.can_change_color() and curses.COLORS >= 16:
        curses.init_color(10, 200, 1000, 200)
        PHOSPHOR = 10
    else:
        PHOSPHOR = curses.COLOR_GREEN

    curses.init_pair(1, PHOSPHOR,          -1)   # phosphor on black
    curses.init_pair(2, curses.COLOR_BLACK, PHOSPHOR)  # highlight (black on phosphor)
    curses.init_pair(3, curses.COLOR_RED,   -1)   # error
    curses.init_pair(4, PHOSPHOR,           -1)   # dim text (used with A_DIM)
    curses.init_pair(5, curses.COLOR_BLACK, PHOSPHOR)  # action highlight

    PHO           = curses.color_pair(1) | curses.A_BOLD
    _PHOSPHOR_ATTR = PHO

    # ── App state ─────────────────────────────────────────────────────────
    drafts          = get_drafts()
    current_draft   = drafts[0] if drafts else None
    active_pane     = PANE_EDITOR
    selected_action = 0
    show_list       = False    # drafts list overlay
    list_sel        = 0

    focus_mode      = False    # Ctrl+F
    typewriter      = False    # Ctrl+T

    editor_lines    = [""]
    editor_row      = 0
    editor_col      = 0
    editor_vscroll  = 0

    ACTIONS     = ["[D] Drafts", "[N] New", "[R] Rename",
                   "[X] Delete", "[C] Copy", "[Q] Quit"]
    ACTION_KEYS = ['d', 'n', 'r', 'x', 'c', 'q']

    # ── Helpers ───────────────────────────────────────────────────────────

    def load_draft(name):
        nonlocal editor_lines, editor_row, editor_col, editor_vscroll
        content = read_draft(name) if name else ""
        editor_lines   = content.split("\n") if content else [""]
        editor_lines   = editor_lines or [""]
        editor_row     = len(editor_lines) - 1
        editor_col     = len(editor_lines[editor_row])
        editor_vscroll = 0

    def autosave():
        if current_draft:
            write_draft(current_draft, "\n".join(editor_lines))

    def switch_draft(name):
        nonlocal current_draft
        autosave()
        current_draft = name
        load_draft(name)

    if current_draft:
        load_draft(current_draft)

    # ── Main loop ─────────────────────────────────────────────────────────

    while True:
        sh, sw = stdscr.getmaxyx()
        if sh < 6 or sw < 30:
            stdscr.erase()
            try:
                stdscr.addstr(0, 0, "Terminal too small.")
            except curses.error:
                pass
            stdscr.refresh()
            stdscr.getch()
            continue

        HEADER_H = 1
        ACTION_H = 2
        if focus_mode:
            # Full screen: no header, no action bar
            edit_y      = 0
            edit_h      = sh
            edit_x      = max(0, (sw - min(sw, 80)) // 2)
            edit_w      = min(sw, 80)
        else:
            edit_y      = HEADER_H + 1       # +1 for top border row of header
            edit_h      = sh - HEADER_H - 1 - ACTION_H - 1
            edit_x      = 0
            edit_w      = sw

        # Inner writing area
        margin      = 4   # left/right padding inside editor
        write_w     = max(10, edit_w - margin * 2)
        write_x     = edit_x + margin    # absolute x of text start
        write_inner = edit_h - 2         # rows between borders

        visual_rows, row_map = wrap_lines(editor_lines, write_w)
        total_vrows = len(visual_rows)
        vis_cursor_row, vis_cursor_x = logical_to_visual(
            editor_row, editor_col, row_map)

        # Scroll: typewriter centres cursor, normal keeps it in view
        if typewriter and not focus_mode:
            centre     = write_inner // 2
            editor_vscroll = max(0, vis_cursor_row - centre)
        else:
            if vis_cursor_row < editor_vscroll:
                editor_vscroll = vis_cursor_row
            elif vis_cursor_row >= editor_vscroll + write_inner:
                editor_vscroll = vis_cursor_row - write_inner + 1

        words, chars = count_stats(editor_lines)

        stdscr.erase()
        stdscr.noutrefresh()

        # ── Header bar ───────────────────────────────────────────────────
        if not focus_mode:
            hdr = curses.newwin(HEADER_H + 1, sw, 0, 0)
            draw_border(hdr, current_draft or "nu_draft",
                        active=(active_pane == PANE_EDITOR))
            stat = f" {words}w  {chars}c "
            flags = ""
            if typewriter:
                flags += " [TW]"
            if flags:
                stat = flags + "  " + stat
            try:
                hdr.addstr(0, sw - len(stat) - 2, stat, PHO)
            except curses.error:
                pass
            hdr.noutrefresh()

        # ── Writing area ──────────────────────────────────────────────────
        edit_win = curses.newwin(edit_h, edit_w, edit_y, edit_x)
        edit_win.keypad(True)

        if focus_mode:
            # No border in focus mode — pure text
            # Find the logical paragraph (line) the cursor is on
            focus_para = editor_row
            for screen_row in range(edit_h):
                vrow = screen_row + editor_vscroll
                if vrow >= total_vrows:
                    break
                li, cs = row_map[vrow]
                text   = visual_rows[vrow]
                y_pos  = screen_row
                x_pos  = margin
                if li == focus_para:
                    attr = curses.color_pair(1) | curses.A_BOLD
                else:
                    attr = curses.A_DIM
                try:
                    edit_win.addstr(y_pos, x_pos, text[:write_w], attr)
                except curses.error:
                    pass
        else:
            # Normal mode: draw all visible rows
            for screen_row in range(write_inner):
                vrow = screen_row + editor_vscroll
                if vrow >= total_vrows:
                    break
                text = visual_rows[vrow]
                try:
                    edit_win.addstr(screen_row + 1, margin, text[:write_w])
                except curses.error:
                    pass

        edit_win.noutrefresh()

        # ── Action bar ────────────────────────────────────────────────────
        if not focus_mode:
            act_y   = sh - ACTION_H
            act_win = curses.newwin(ACTION_H, sw, act_y, 0)
            act_win.keypad(True)
            draw_border(act_win, "", active=(active_pane == PANE_ACTIONS))
            x_off = 2
            for i, action in enumerate(ACTIONS):
                attr = (curses.color_pair(5) | curses.A_BOLD
                        if active_pane == PANE_ACTIONS and i == selected_action
                        else curses.A_NORMAL)
                label = f" {action} "
                if x_off + len(label) < sw - 2:
                    try:
                        act_win.addstr(0, x_off, label, attr)
                    except curses.error:
                        pass
                    x_off += len(label) + 1
            act_win.noutrefresh()

        # ── Drafts list overlay ───────────────────────────────────────────
        if show_list:
            drafts = get_drafts()
            list_sel = max(0, min(list_sel, len(drafts) - 1))
            ov_w    = min(40, sw - 4)
            ov_h    = min(len(drafts) + 2, sh - 4, 20)
            ov_y    = (sh - ov_h) // 2
            ov_x    = (sw - ov_w) // 2
            ov      = curses.newwin(ov_h, ov_w, ov_y, ov_x)
            ov.keypad(True)
            draw_border(ov, "Drafts", active=True)
            inner_h = ov_h - 2
            scroll  = max(0, list_sel - inner_h + 1) if list_sel >= inner_h else 0
            for i in range(inner_h):
                idx = i + scroll
                if idx >= len(drafts):
                    break
                name = drafts[idx]
                disp = name[:ov_w - 4]
                try:
                    if idx == list_sel:
                        ov.addstr(i + 1, 1, f" {disp:<{ov_w-4}} ",
                                  curses.color_pair(2) | curses.A_BOLD)
                    else:
                        ov.addstr(i + 1, 1, f" {disp:<{ov_w-4}} ")
                except curses.error:
                    pass
            if not drafts:
                try:
                    ov.addstr(1, 2, "(no drafts yet)")
                except curses.error:
                    pass
            ov.noutrefresh()

        # ── Cursor ────────────────────────────────────────────────────────
        if not show_list and current_draft:
            curses.curs_set(2)
            if focus_mode:
                scr_y = vis_cursor_row - editor_vscroll
                scr_x = vis_cursor_x + margin
                scr_y = max(0, min(scr_y, edit_h - 1))
                scr_x = max(margin, min(scr_x, edit_w - 1))
            else:
                scr_y = vis_cursor_row - editor_vscroll + 1
                scr_x = vis_cursor_x + margin
                scr_y = max(1, min(scr_y, write_inner))
                scr_x = max(margin, min(scr_x, edit_w - margin - 1))

            vrow_idx = vis_cursor_row
            if vrow_idx < len(visual_rows):
                row_text     = visual_rows[vrow_idx]
                char_at      = row_text[vis_cursor_x] if vis_cursor_x < len(row_text) else " "
            else:
                char_at = " "
            try:
                edit_win.addstr(scr_y, scr_x, char_at,
                                curses.color_pair(2) | curses.A_BOLD)
                edit_win.move(scr_y, scr_x)
            except curses.error:
                pass
            edit_win.noutrefresh()
        else:
            curses.curs_set(0)
            edit_win.noutrefresh()

        curses.doupdate()

        # ── Input ─────────────────────────────────────────────────────────
        if show_list:
            ch = ov.getch()
        elif active_pane == PANE_ACTIONS:
            ch = act_win.getch()
        else:
            ch = edit_win.getch()

        # ── Global keys ───────────────────────────────────────────────────

        if ch == 17:          # Ctrl+Q
            autosave()
            break

        if ch == 19:          # Ctrl+S
            autosave()
            continue

        if ch == 6:           # Ctrl+F  toggle focus mode
            focus_mode = not focus_mode
            continue

        if ch == 20:          # Ctrl+T  toggle typewriter scroll
            typewriter = not typewriter
            continue

        if ch == 9:           # Tab
            if show_list:
                show_list = False
            elif focus_mode:
                focus_mode = False
            else:
                active_pane = (active_pane + 1) % 2   # editor ↔ actions
            continue

        if ch == 27:          # Esc
            if show_list:
                show_list = False
            elif focus_mode:
                focus_mode = False
            continue

        # ── Drafts list overlay keys ──────────────────────────────────────
        if show_list:
            if ch == curses.KEY_UP:
                list_sel = max(0, list_sel - 1)
            elif ch == curses.KEY_DOWN:
                list_sel = min(len(drafts) - 1, list_sel + 1)
            elif ch in (curses.KEY_ENTER, 10, 13, curses.KEY_RIGHT):
                if drafts:
                    switch_draft(drafts[list_sel])
                    show_list    = False
                    active_pane  = PANE_EDITOR
            continue

        # ── Editor ───────────────────────────────────────────────────────
        if active_pane == PANE_EDITOR and current_draft:
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
                li, cs = row_map[vis_cursor_row]
                editor_col = cs

            elif ch == curses.KEY_END:
                li, cs = row_map[vis_cursor_row]
                editor_col = cs + len(visual_rows[vis_cursor_row])

            elif ch == curses.KEY_PPAGE:   # Page Up
                target = max(0, vis_cursor_row - write_inner)
                li, cs = row_map[target]
                editor_row = li
                editor_col = cs

            elif ch == curses.KEY_NPAGE:   # Page Down
                target = min(total_vrows - 1, vis_cursor_row + write_inner)
                li, cs = row_map[target]
                editor_row = li
                editor_col = cs

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
                    editor_lines[editor_row] = cur_line + editor_lines[editor_row + 1]
                    editor_lines.pop(editor_row + 1)
                autosave()

            elif ch in (curses.KEY_ENTER, 10, 13):
                tail = cur_line[editor_col:]
                editor_lines[editor_row] = cur_line[:editor_col]
                editor_row += 1
                editor_lines.insert(editor_row, tail)
                editor_col = 0
                autosave()

            elif 32 <= ch <= 126:
                editor_lines[editor_row] = (cur_line[:editor_col]
                                            + chr(ch)
                                            + cur_line[editor_col:])
                editor_col += 1
                autosave()

        # ── Actions bar ───────────────────────────────────────────────────
        elif active_pane == PANE_ACTIONS:
            if ch == curses.KEY_LEFT:
                selected_action = (selected_action - 1) % len(ACTIONS)
            elif ch == curses.KEY_RIGHT:
                selected_action = (selected_action + 1) % len(ACTIONS)
            elif ch in (curses.KEY_ENTER, 10, 13) or (
                    32 <= ch <= 126 and chr(ch).lower() in ACTION_KEYS):

                idx = (ACTION_KEYS.index(chr(ch).lower())
                       if 32 <= ch <= 126 and chr(ch).lower() in ACTION_KEYS
                       else selected_action)

                if idx == 0:    # Drafts list
                    drafts   = get_drafts()
                    list_sel = drafts.index(current_draft) if current_draft in drafts else 0
                    show_list = True

                elif idx == 1:  # New
                    name = prompt_input(stdscr, "New draft name:")
                    if name:
                        s = safe_name(name)
                        if os.path.exists(draft_path(s)):
                            show_message(stdscr, f"'{s}' already exists!")
                        else:
                            write_draft(s, "")
                            switch_draft(s)
                            active_pane = PANE_EDITOR

                elif idx == 2:  # Rename
                    if current_draft:
                        new_name = prompt_input(
                            stdscr, f"Rename '{current_draft}' to:")
                        if new_name:
                            s = safe_name(new_name)
                            if os.path.exists(draft_path(s)):
                                show_message(stdscr, f"'{s}' already exists!")
                            else:
                                autosave()
                                os.rename(draft_path(current_draft),
                                          draft_path(s))
                                current_draft = s

                elif idx == 3:  # Delete
                    if current_draft:
                        confirm = prompt_input(
                            stdscr, f"Delete '{current_draft}'? Type YES:")
                        if confirm and confirm.upper() == "YES":
                            os.remove(draft_path(current_draft))
                            drafts = get_drafts()
                            if drafts:
                                switch_draft(drafts[0])
                            else:
                                current_draft = None
                                editor_lines  = [""]
                                editor_row    = 0
                                editor_col    = 0

                elif idx == 4:  # Copy
                    if current_draft:
                        new_name = prompt_input(
                            stdscr, f"Copy '{current_draft}' to:")
                        if new_name:
                            s = safe_name(new_name)
                            if os.path.exists(draft_path(s)):
                                show_message(stdscr, f"'{s}' already exists!")
                            else:
                                autosave()
                                shutil.copy2(draft_path(current_draft),
                                             draft_path(s))
                                switch_draft(s)
                                active_pane = PANE_EDITOR

                elif idx == 5:  # Quit
                    autosave()
                    break


def run():
    ensure_dir(DRAFTS_DIR)
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    print("nu_draft closed. Drafts saved in ~/nu_drafts/")


if __name__ == "__main__":
    run()
