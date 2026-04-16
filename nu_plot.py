#!/usr/bin/env python3
"""
nu_plot — story plotting tool for the Freewriter ecosystem

Layout
  60 cards (default) split 1/4 · 1/2 · 1/4 across three acts.
  Any total card count works — the split is always 25% / 50% / 25%.

Screens
  Project list  →  Act selector  →  Card grid  →  Card editor

Controls (global)
  Ctrl+Q        save and quit
  Esc           go back one screen

Project list
  ↑ ↓           select project
  Enter         open project
  Ctrl+N        new project

Act selector
  ← →           select act
  Enter         open act card grid

Card grid
  ↑ ↓ ← →      navigate cards
  Enter         open card editor

Card editor
  (type freely)
  Tab           switch between title field and content
  Ctrl+S        save card
  Esc           back to grid

Storage: ~/nu_plots/<project>.json
"""

import curses
import os
import json
import math
import re
import textwrap

PLOTS_DIR = os.path.expanduser("~/nu_plots")

# ── Colour pairs ──────────────────────────────────────────────────────────────
CP_PHO    = 1   # phosphor green on black
CP_SEL    = 2   # black on phosphor — selected
CP_DIM    = 3   # dim
CP_ACT1   = 4   # act 1 accent
CP_ACT2   = 5   # act 2 accent
CP_ACT3   = 6   # act 3 accent
CP_FILLED = 7   # card has content
CP_CYAN   = 8   # ###...### cyan highlight

ACT_NAMES  = ["Act I", "Act II", "Act III"]
ACT_COLORS = [CP_ACT1, CP_ACT2, CP_ACT3]

_PHO_ATTR = curses.A_BOLD

# ── Filesystem helpers ────────────────────────────────────────────────────────

def ensure_dir():
    os.makedirs(PLOTS_DIR, exist_ok=True)

def list_projects():
    try:
        return sorted(f[:-5] for f in os.listdir(PLOTS_DIR)
                      if f.endswith(".json"))
    except OSError:
        return []

def project_path(name):
    return os.path.join(PLOTS_DIR, name + ".json")

def load_project(name):
    try:
        with open(project_path(name)) as f:
            data = json.load(f)
        n     = data.get("total_cards", 60)
        cards = data.get("cards", [])
        while len(cards) < n:
            cards.append({"title": "", "content": ""})
        data["cards"] = cards[:n]
        data.setdefault("show_prompts", True)
        return data
    except (OSError, json.JSONDecodeError):
        return None

def save_project(data):
    with open(project_path(data["title"]), "w") as f:
        json.dump(data, f, indent=2)

def new_project(name, total_cards):
    data = {
        "title":        name,
        "total_cards":  total_cards,
        "show_prompts": True,
        "cards":        [{"title": "", "content": ""}
                         for _ in range(total_cards)],
    }
    save_project(data)
    return data

def act_ranges(total):
    a1 = max(1, round(total * 0.25))
    a3 = max(1, round(total * 0.25))
    a2 = total - a1 - a3
    return [(0, a1), (a1, a1 + a2), (a1 + a2, total)]


# ── Hero's Journey stage map ──────────────────────────────────────────────────
# Each entry: (pct_start, pct_end, stage_name, writing_prompt)
# pct values are 0–100 of the total story.  A card's stage is found by
# where its index falls in that range.

HERO_STAGES = [
    (  0,  8,
     "Ordinary World",
     "Introduce your main character and show their life before the adventure. "
     "Lead with lack — what is missing, what is the wound, what is the lie "
     "they believe about themselves or the world?"),
    (  8, 12,
     "Call to Adventure",
     "Something disrupts the ordinary world. A problem, a challenge, an "
     "invitation, a threat. The hero is presented with a choice or a change "
     "they did not ask for."),
    ( 12, 20,
     "Refusal of the Call",
     "The hero hesitates, doubts, or outright refuses. Show the fear, "
     "the comfort of the known, the cost of saying yes. This reluctance "
     "makes the eventual commitment meaningful."),
    ( 20, 25,
     "Meeting the Mentor",
     "A guide appears — a person, a book, a memory, a moment of clarity. "
     "The mentor gives the hero something: a gift, a lesson, a push, "
     "a piece of the truth they need to begin."),
    ( 25, 40,
     "Crossing the Threshold",
     "The hero commits and enters the special world. Everything is new, "
     "unfamiliar, and ruled by different rules. There is no easy way back. "
     "Show the cost and the wonder of this crossing."),
    ( 40, 50,
     "Tests, Allies & Enemies",
     "The hero is tested. Alliances are formed, rivals emerge, the rules of "
     "the new world are learned the hard way. Each test reveals character "
     "and raises the stakes."),
    ( 50, 55,
     "Approach to the Inmost Cave",
     "The hero moves toward the heart of the conflict — the place of greatest "
     "danger or deepest fear. Preparation, tension, and the shadow of what "
     "is to come. Something must be left behind."),
    ( 55, 62,
     "The Ordeal",
     "The darkest moment. The hero faces their greatest fear, a death "
     "(literal or symbolic). Everything is lost — or seems to be. "
     "This is the crucible from which the transformed hero will emerge."),
    ( 62, 70,
     "The Reward",
     "Having survived the ordeal, the hero seizes the reward: a sword, "
     "a secret, a truth, a love, a new understanding of self. "
     "Show what was won and what it cost."),
    ( 70, 80,
     "The Road Back",
     "The hero turns toward home, but the journey is not over. The forces "
     "set in motion pursue or complicate. Commitment to the return — "
     "to completing the transformation — must be renewed."),
    ( 80, 90,
     "The Resurrection",
     "A final, supreme ordeal. The hero is tested one last time and must "
     "use everything they have learned. The old self dies completely. "
     "The hero emerges changed — proven, transformed, worthy."),
    ( 90, 100,
     "Return with the Elixir",
     "The hero returns to the ordinary world carrying something of value "
     "for others: a solution, a story, wisdom, healing, hope. "
     "Show the world changed — or show the hero changed within an unchanged world."),
]


def get_stage(card_index, total_cards):
    """Return the Hero's Journey stage for a card at card_index (0-based)."""
    pct = (card_index / max(1, total_cards - 1)) * 100
    for s, e, name, prompt in HERO_STAGES:
        if pct <= e or s == HERO_STAGES[-1][0]:
            return name, prompt
    return HERO_STAGES[-1][2], HERO_STAGES[-1][3]


# ── Markup engine (shared with nu_notes) ──────────────────────────────────────
# Syntax:
#   ##word##      phosphor green bold
#   ###word###    cyan
#   ##!!word##    phosphor green bold + emphasis
#   ###!!word###  cyan bold
#   !!word!!      bold (default colour)

_MARKUP_RE = re.compile(
    r'(###!!(.+?)###)'
    r'|(##!!(.+?)##)'
    r'|(###(.+?)###)'
    r'|(##(.+?)##)'
    r'|(!!(.+?)!!)'
)


def _build_maps(raw_line):
    """Build raw→plain and plain→raw index lookup tables for a line."""
    n        = len(raw_line)
    is_token = [False] * n
    for m in _MARKUP_RE.finditer(raw_line):
        inner_grp = next(
            (g for g in (2, 4, 6, 8, 10) if m.group(g) is not None), None)
        if inner_grp:
            inner_start, inner_end = m.start(inner_grp), m.end(inner_grp)
        else:
            inner_start, inner_end = m.start(), m.end()
        for i in range(m.start(), m.end()):
            is_token[i] = not (inner_start <= i < inner_end)

    plain_to_raw = [i for i in range(n) if not is_token[i]]
    plain_len    = len(plain_to_raw)

    raw_to_plain = [0] * (n + 1)
    p = 0
    for i in range(n):
        if not is_token[i]:
            raw_to_plain[i] = p
            p += 1
    raw_to_plain[n] = plain_len
    last_plain = plain_len
    for i in range(n - 1, -1, -1):
        if is_token[i]:
            raw_to_plain[i] = last_plain
        else:
            last_plain = raw_to_plain[i]

    return raw_to_plain, plain_to_raw


def strip_markup(text):
    return _MARKUP_RE.sub(
        lambda m: (m.group(2) or m.group(4) or m.group(6)
                   or m.group(8) or m.group(10) or ''),
        text
    )


def raw_col_to_plain(raw_line, raw_col):
    raw_to_plain, _ = _build_maps(raw_line)
    return raw_to_plain[max(0, min(raw_col, len(raw_line)))]


def plain_col_to_raw(raw_line, plain_col):
    _, plain_to_raw = _build_maps(raw_line)
    plain_col = max(0, min(plain_col, len(plain_to_raw)))
    return plain_to_raw[plain_col] if plain_col < len(plain_to_raw) else len(raw_line)


def _parse_spans(raw_text, attrs):
    spans, pos = [], 0
    for m in _MARKUP_RE.finditer(raw_text):
        if m.start() > pos:
            spans.append((raw_text[pos:m.start()], attrs['default']))
        if   m.group(2):  spans.append((m.group(2),  attrs['cyanbold']))
        elif m.group(4):  spans.append((m.group(4),  attrs['phobold']))
        elif m.group(6):  spans.append((m.group(6),  attrs['cyan']))
        elif m.group(8):  spans.append((m.group(8),  attrs['phobold']))
        elif m.group(10): spans.append((m.group(10), attrs['bold']))
        pos = m.end()
    if pos < len(raw_text):
        spans.append((raw_text[pos:], attrs['default']))
    return spans or [(raw_text, attrs['default'])]


def render_markup_segment(win, y, x, raw_line, col_start, seg_len, max_w, attrs):
    """Render seg_len visible chars of raw_line from plain offset col_start."""
    spans, plain_pos, cx, drawn = _parse_spans(raw_line, attrs), 0, x, 0
    for text, attr in spans:
        span_end = plain_pos + len(text)
        ov_start = max(plain_pos, col_start)
        ov_end   = min(span_end, col_start + seg_len)
        if ov_start < ov_end:
            chunk = text[ov_start - plain_pos : ov_end - plain_pos][:max_w - drawn]
            if chunk:
                try:
                    win.addstr(y, cx, chunk, attr)
                except curses.error:
                    pass
                cx += len(chunk); drawn += len(chunk)
        plain_pos = span_end
        if drawn >= seg_len or drawn >= max_w:
            break

# ── UI primitives ─────────────────────────────────────────────────────────────

def init_colors():
    global _PHO_ATTR
    curses.start_color()
    curses.use_default_colors()
    if curses.can_change_color() and curses.COLORS >= 256:
        curses.init_color(10, 200, 1000, 200)
        PHOSPHOR = 10
        curses.init_color(11, 400, 700, 1000)
        curses.init_color(12, 1000, 750, 100)
        curses.init_color(13, 200, 1000, 200)
        A1, A2, A3 = 11, 12, 13
    else:
        PHOSPHOR = curses.COLOR_GREEN
        A1 = curses.COLOR_CYAN
        A2 = curses.COLOR_YELLOW
        A3 = curses.COLOR_GREEN

    curses.init_pair(CP_PHO,    PHOSPHOR,           -1)
    curses.init_pair(CP_SEL,    curses.COLOR_BLACK,  PHOSPHOR)
    curses.init_pair(CP_DIM,    curses.COLOR_WHITE,  -1)
    curses.init_pair(CP_ACT1,   A1,                  -1)
    curses.init_pair(CP_ACT2,   A2,                  -1)
    curses.init_pair(CP_ACT3,   A3,                  -1)
    curses.init_pair(CP_FILLED, PHOSPHOR,            -1)
    curses.init_pair(CP_CYAN,   curses.COLOR_CYAN,   -1)
    _PHO_ATTR = curses.color_pair(CP_PHO) | curses.A_BOLD

def safe_add(win, y, x, text, attr=0):
    try:
        h, w = win.getmaxyx()
        if 0 <= y < h and 0 <= x < w:
            win.addstr(y, x, str(text)[:max(0, w - x - 1)], attr)
    except curses.error:
        pass

def panel_add(win, y, px, panel_w, x_offset, text, attr=0):
    """
    Write text inside a panel whose left edge is px and width is panel_w.
    x_offset is relative to px (0 = first char after left border).
    Text is hard-clipped so it never crosses the right border.
    """
    abs_x   = px + x_offset
    # interior runs from px+1 to px+panel_w-2 inclusive
    clip_w  = max(0, (px + panel_w - 1) - abs_x - 1)
    safe_add(win, y, abs_x, str(text)[:clip_w], attr)

def draw_box(win, y, x, h, w, attr=0):
    try:
        wh, ww = win.getmaxyx()
        if y < 0 or x < 0 or y + h > wh or x + w > ww or h < 2 or w < 2:
            return
        win.attron(attr)
        win.addch(y,     x,     curses.ACS_ULCORNER)
        win.addch(y,     x+w-1, curses.ACS_URCORNER)
        win.addch(y+h-1, x,     curses.ACS_LLCORNER)
        win.hline(y,     x+1,   curses.ACS_HLINE, w-2)
        win.hline(y+h-1, x+1,   curses.ACS_HLINE, w-2)
        win.vline(y+1,   x,     curses.ACS_VLINE, h-2)
        win.vline(y+1,   x+w-1, curses.ACS_VLINE, h-2)
        # Bottom-right corner: addch raises an error at the last cell of a
        # window (curses quirk), so we catch it separately.
        try:
            win.addch(y+h-1, x+w-1, curses.ACS_LRCORNER)
        except curses.error:
            pass
        win.attroff(attr)
    except curses.error:
        pass

def prompt_input(stdscr, question, default=""):
    sh, sw = stdscr.getmaxyx()
    bw  = min(max(len(question) + 8, 44), sw - 4)
    bh  = 5
    win = curses.newwin(bh, bw, (sh - bh) // 2, (sw - bw) // 2)
    win.keypad(True)
    curses.curs_set(1)
    text = default
    while True:
        win.erase()
        win.border()
        safe_add(win, 1, 2, question[:bw - 4], _PHO_ATTR)
        win.hline(2, 1, curses.ACS_HLINE, bw - 2, curses.A_DIM)
        disp = text[-(bw - 6):]
        safe_add(win, 3, 2, disp + " ", curses.color_pair(CP_PHO))
        try:
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
        elif 32 <= ch <= 126 and len(text) < 100:
            text += chr(ch)


# ── Screen 1: Project list ────────────────────────────────────────────────────

def screen_projects(stdscr):
    sel = 0
    while True:
        sh, sw    = stdscr.getmaxyx()
        projects  = list_projects()
        sel       = max(0, min(sel, len(projects) - 1)) if projects else 0
        stdscr.erase()

        title = "nu_plot  —  story plotter"
        safe_add(stdscr, 1, (sw - len(title)) // 2, title, _PHO_ATTR)
        stdscr.hline(2, 0, curses.ACS_HLINE, sw, curses.A_DIM)

        if not projects:
            msg = "No projects yet.  Press Ctrl+N to create one."
            safe_add(stdscr, sh // 2, (sw - len(msg)) // 2, msg, curses.A_DIM)
        else:
            for i, name in enumerate(projects):
                y = 4 + i
                if y >= sh - 2:
                    break
                data   = load_project(name)
                n      = data["total_cards"] if data else 0
                filled = (sum(1 for c in data["cards"]
                              if c["title"] or c["content"])
                          if data else 0)
                label  = f"  {name:<30}  {n} cards  ·  {filled} filled"
                attr   = (curses.color_pair(CP_SEL) | curses.A_BOLD
                          if i == sel else curses.color_pair(CP_PHO))
                safe_add(stdscr, y, 0, f"{label:<{sw}}", attr)

        footer = " ↑↓: select   Enter: open   ^N: new   ^D: delete   ^Q: quit "
        safe_add(stdscr, sh - 1, max(0, (sw - len(footer)) // 2),
                 footer, curses.A_DIM)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == 17:
            return None
        elif ch == 14:                  # Ctrl+N
            name = prompt_input(stdscr, "Project title:")
            if name:
                raw = prompt_input(stdscr, "Total cards (default 60):", "60")
                try:
                    n = int(raw) if raw else 60
                    n = max(4, min(n, 360))
                except ValueError:
                    n = 60
                return new_project(name, n)
        elif ch == 4 and projects:      # Ctrl+D — delete project
            name    = projects[sel]
            confirm = prompt_input(stdscr, f"Delete '{name}'?  Type YES:")
            if confirm and confirm.upper() == "YES":
                try:
                    os.remove(project_path(name))
                except OSError:
                    pass
                sel = max(0, sel - 1)
        elif ch == curses.KEY_UP:
            sel = max(0, sel - 1)
        elif ch == curses.KEY_DOWN:
            sel = min(len(projects) - 1, sel + 1) if projects else 0
        elif ch in (curses.KEY_ENTER, 10, 13) and projects:
            data = load_project(projects[sel])
            if data:
                return data


# ── Screen 2: Act selector ────────────────────────────────────────────────────

def screen_acts(stdscr, data):
    sel    = 0
    ranges = act_ranges(data["total_cards"])
    cards  = data["cards"]

    while True:
        sh, sw   = stdscr.getmaxyx()
        stdscr.erase()

        hdr = f"  {data['title']}  ·  {data['total_cards']} cards"
        safe_add(stdscr, 0, 0, hdr, _PHO_ATTR)
        stdscr.hline(1, 0, curses.ACS_HLINE, sw, curses.A_DIM)

        panel_w = max(20, (sw - 4) // 3)
        panel_h = sh - 4

        for ai in range(3):
            px        = 1 + ai * (panel_w + 1)
            s, e      = ranges[ai]
            count     = e - s
            filled    = sum(1 for c in cards[s:e]
                            if c["title"] or c["content"])
            is_sel    = (ai == sel)
            aattr     = curses.color_pair(ACT_COLORS[ai]) | curses.A_BOLD
            box_attr  = aattr if is_sel else curses.A_DIM

            draw_box(stdscr, 2, px, panel_h, panel_w, box_attr)

            # Act label — centred, clipped to interior
            label   = ACT_NAMES[ai]
            inner_w = panel_w - 2          # interior width between borders
            lx      = max(1, (inner_w - len(label)) // 2 + 1)
            panel_add(stdscr, 2, px, panel_w, lx, label, aattr)

            # Stats line
            stats   = f"{count} cards · {filled} filled"
            sx      = max(1, (inner_w - len(stats)) // 2 + 1)
            panel_add(stdscr, 4, px, panel_w, sx,
                      stats, aattr if is_sel else curses.A_DIM)

            # Preview: first filled card titles, strictly inside the panel
            py    = 6
            shown = 0
            max_preview = min(panel_h - 7, sh - py - 3)
            for ci in range(s, e):
                if shown >= max_preview:
                    break
                t = cards[ci]["title"].strip()
                c = cards[ci]["content"].strip()
                if t or c:
                    num   = f"{ci - s + 1:>2}. "
                    # clip snippet so num+snip fits in interior minus 1 margin
                    avail = inner_w - len(num) - 1
                    snip  = (t or c)[:max(0, avail)]
                    panel_add(stdscr, py + shown, px, panel_w,
                              1, num + snip,
                              curses.color_pair(CP_FILLED) if is_sel
                              else curses.A_DIM)
                    shown += 1

            if shown == 0:
                empty = "(empty)"
                ex    = max(1, (inner_w - len(empty)) // 2 + 1)
                panel_add(stdscr, py, px, panel_w, ex, empty, curses.A_DIM)

        # Selection indicator arrow below selected panel
        arrow_y = sh - 3
        if 0 <= arrow_y < sh:
            for ai in range(3):
                if ai == sel:
                    px = 1 + ai * (panel_w + 1)
                    safe_add(stdscr, arrow_y,
                             px + (panel_w - 8) // 2,
                             "[ Enter ]",
                             curses.color_pair(ACT_COLORS[ai]) | curses.A_BOLD)

        footer = " ←→: choose act   Enter: open   Esc: back   ^Q: quit "
        safe_add(stdscr, sh - 1, max(0, (sw - len(footer)) // 2),
                 footer, curses.A_DIM)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == 17 or ch == 27:
            return None
        elif ch in (curses.KEY_LEFT, ord('h')):
            sel = (sel - 1) % 3
        elif ch in (curses.KEY_RIGHT, ord('l')):
            sel = (sel + 1) % 3
        elif ch in (curses.KEY_ENTER, 10, 13):
            return sel


# ── Screen 3: Card grid ───────────────────────────────────────────────────────

def screen_grid(stdscr, data, act_idx):
    ranges     = act_ranges(data["total_cards"])
    start, end = ranges[act_idx]
    cards      = data["cards"]
    act_count  = end - start
    sel        = 0
    page       = 0          # which page of 15 we are on

    while True:
        sh, sw = stdscr.getmaxyx()

        # ── Layout: fit exactly 15 tiles per page ─────────────────────────
        # We want COLS × ROWS == 15 with tiles as large as possible.
        # Try column counts from 5 down to 1; pick the one where the
        # resulting tile dimensions are most square / readable.
        HDR_H     = 2
        FTR_H     = 1
        grid_h    = sh - HDR_H - FTR_H - 1   # usable rows for tiles
        grid_w    = sw - 2                    # usable cols for tiles

        TILES_PER_PAGE = 15
        best_cols, best_rows, best_tw, best_th = 5, 3, 1, 1
        for try_cols in range(5, 0, -1):
            try_rows = math.ceil(TILES_PER_PAGE / try_cols)
            # tile dimensions including 1-char gap between tiles
            tw = (grid_w - (try_cols - 1)) // try_cols
            th = (grid_h - (try_rows - 1)) // try_rows
            if tw >= 12 and th >= 4:
                best_cols, best_rows = try_cols, try_rows
                best_tw,   best_th   = tw, th
                break

        COLS   = best_cols
        ROWS   = best_rows
        TILE_W = best_tw
        TILE_H = best_th

        total_pages = max(1, math.ceil(act_count / TILES_PER_PAGE))
        page        = max(0, min(page, total_pages - 1))
        page_start  = page * TILES_PER_PAGE
        page_end    = min(act_count, page_start + TILES_PER_PAGE)
        page_count  = page_end - page_start

        sel = max(0, min(sel, act_count - 1))
        # If sel is not on this page, move page to match
        if sel < page_start or sel >= page_end:
            page       = sel // TILES_PER_PAGE
            page_start = page * TILES_PER_PAGE
            page_end   = min(act_count, page_start + TILES_PER_PAGE)
            page_count = page_end - page_start

        sel_on_page = sel - page_start   # 0-based index within current page

        stdscr.erase()

        aattr = curses.color_pair(ACT_COLORS[act_idx]) | curses.A_BOLD
        hdr   = f"  {ACT_NAMES[act_idx]}  ·  cards {page_start+1}–{page_end} of {act_count}"
        safe_add(stdscr, 0, 0, hdr, aattr)
        if total_pages > 1:
            pg_label = f"  page {page+1}/{total_pages}  ←→ PgUp/PgDn "
            safe_add(stdscr, 0, sw - len(pg_label) - 1, pg_label, curses.A_DIM)
        stdscr.hline(1, 0, curses.ACS_HLINE, sw, curses.A_DIM)

        for tile_i in range(page_count):
            local_idx  = page_start + tile_i
            global_idx = start + local_idx
            card       = cards[global_idx]

            row = tile_i // COLS
            col = tile_i  % COLS
            ty  = HDR_H + row * (TILE_H + 1)
            tx  = 1     + col * (TILE_W + 1)

            is_sel    = (local_idx == sel)
            has       = bool(card["title"].strip() or card["content"].strip())

            box_attr  = (aattr if is_sel else
                         curses.color_pair(CP_FILLED) | curses.A_DIM if has
                         else curses.A_DIM)
            text_attr = (curses.color_pair(CP_SEL) | curses.A_BOLD if is_sel
                         else curses.color_pair(CP_PHO) if has
                         else curses.A_DIM)

            draw_box(stdscr, ty, tx, TILE_H, TILE_W, box_attr)

            # Card number in top border
            num = f" {local_idx + 1} "
            safe_add(stdscr, ty, tx + 1, num,
                     aattr if is_sel else curses.A_DIM)

            # Title line (line 1 inside box)
            t = (card["title"].strip() or "")[:TILE_W - 2]
            safe_add(stdscr, ty + 1, tx + 1,
                     f"{t:<{TILE_W - 2}}", text_attr)

            # Content lines (remaining interior rows)
            content_lines = (card["content"].strip().split("\n")
                             if card["content"].strip() else [])
            for ci in range(TILE_H - 3):   # rows between title and bottom border
                row_y = ty + 2 + ci
                ctxt  = content_lines[ci][:TILE_W - 2] if ci < len(content_lines) else ""
                safe_add(stdscr, row_y, tx + 1,
                         f"{ctxt:<{TILE_W - 2}}",
                         text_attr if is_sel else (
                             curses.color_pair(CP_FILLED) | curses.A_DIM
                             if has else curses.A_DIM))

        if total_pages > 1:
            footer = " ↑↓←→: navigate   PgUp/PgDn: page   Enter: edit   Esc: back "
        else:
            footer = " ↑↓←→: navigate   Enter: edit   Esc: back   ^Q: quit "
        safe_add(stdscr, sh - 1, max(0, (sw - len(footer)) // 2),
                 footer, curses.A_DIM)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == 17:
            save_project(data)
            return "quit"
        elif ch == 27:
            save_project(data)
            return None
        elif ch == curses.KEY_UP:
            sel = max(0, sel - COLS)
        elif ch == curses.KEY_DOWN:
            sel = min(act_count - 1, sel + COLS)
        elif ch == curses.KEY_LEFT:
            sel = max(0, sel - 1)
        elif ch == curses.KEY_RIGHT:
            sel = min(act_count - 1, sel + 1)
        elif ch in (curses.KEY_PPAGE,):   # Page Up
            page = max(0, page - 1)
            sel  = page * TILES_PER_PAGE
        elif ch in (curses.KEY_NPAGE,):   # Page Down
            page = min(total_pages - 1, page + 1)
            sel  = page * TILES_PER_PAGE
        elif ch in (curses.KEY_ENTER, 10, 13):
            result = screen_card(stdscr, data, start + sel,
                                 act_idx, sel, act_count)
            if result == "quit":
                return "quit"


# ── Screen 4: Card editor ─────────────────────────────────────────────────────

def screen_card(stdscr, data, global_idx, act_idx, local_idx, act_count):
    card     = data["cards"][global_idx]
    title    = card["title"]
    lines    = card["content"].split("\n") if card["content"] else [""]
    erow     = len(lines) - 1
    ecol     = len(lines[erow])
    vscroll  = 0
    in_title = not bool(title)

    aattr = curses.color_pair(ACT_COLORS[act_idx]) | curses.A_BOLD

    # Markup attribute table for render_markup_segment
    markup_attrs = {
        "default":  curses.A_NORMAL,
        "phobold":  curses.color_pair(CP_PHO)  | curses.A_BOLD,
        "cyan":     curses.color_pair(CP_CYAN),
        "cyanbold": curses.color_pair(CP_CYAN)  | curses.A_BOLD,
        "bold":     curses.A_BOLD,
    }

    def save():
        card["title"]   = title
        card["content"] = "\n".join(lines)
        save_project(data)

    def wrap_raw(raw_lines, width):
        """Wrap raw lines, returning (visual_rows_plain, row_map)."""
        vis, rmap = [], []
        for li, line in enumerate(raw_lines):
            plain = strip_markup(line)
            if not plain:
                vis.append(""); rmap.append((li, 0))
            else:
                segs = textwrap.wrap(plain, width,
                                     drop_whitespace=False,
                                     break_long_words=True,
                                     break_on_hyphens=False) or [""]
                col = 0
                for seg in segs:
                    vis.append(seg); rmap.append((li, col))
                    col += len(seg)
        return vis, rmap

    while True:
        sh, sw = stdscr.getmaxyx()
        stdscr.erase()

        # ── Header ────────────────────────────────────────────────────────
        stage_name, _ = get_stage(global_idx, data["total_cards"])
        show_p = data.get("show_prompts", True)
        hdr_l  = f"  {ACT_NAMES[act_idx]}  ·  Card {local_idx + 1}/{act_count}  ·  {stage_name}"
        hdr_r  = f"  ^H: prompts {'ON ' if show_p else 'OFF'}  ^S: save  Esc: back  "
        safe_add(stdscr, 0, 0, hdr_l[:sw - len(hdr_r) - 1], aattr)
        safe_add(stdscr, 0, sw - len(hdr_r), hdr_r, curses.A_DIM)
        stdscr.hline(1, 0, curses.ACS_HLINE, sw, curses.A_DIM)

        # ── Hero's Journey prompt banner (optional) ────────────────────────
        prompt_rows = 0
        if show_p:
            _, stage_prompt = get_stage(global_idx, data["total_cards"])
            prompt_w   = sw - 4
            # Wrap the prompt text to fit
            p_plain    = stage_prompt
            p_wrapped  = textwrap.wrap(p_plain, prompt_w) if prompt_w > 10 else [p_plain]
            prompt_rows = len(p_wrapped)
            for pi, pline in enumerate(p_wrapped):
                safe_add(stdscr, 2 + pi, 2, pline[:sw - 4],
                         curses.color_pair(CP_CYAN) | curses.A_DIM)
            stdscr.hline(2 + prompt_rows, 0, curses.ACS_HLINE, sw, curses.A_DIM)

        # ── Title field ───────────────────────────────────────────────────
        title_y = 3 + prompt_rows
        tlabel  = " Title: "
        safe_add(stdscr, title_y, 0, tlabel, curses.A_DIM)
        tx      = len(tlabel)
        tw      = sw - tx - 1
        tdisp   = title[:tw]
        tattr   = (curses.color_pair(CP_SEL) | curses.A_BOLD
                   if in_title else _PHO_ATTR)
        safe_add(stdscr, title_y, tx, f"{tdisp:<{tw}}", tattr)
        stdscr.hline(title_y + 1, 0, curses.ACS_HLINE, sw, curses.A_DIM)

        # ── Content editor ────────────────────────────────────────────────
        edit_y = title_y + 2
        edit_h = max(2, sh - edit_y - 2)
        edit_w = sw - 2

        wrapped, row_map = wrap_raw(lines, edit_w)
        total_vrows = len(wrapped)

        # ecol is a raw index; convert to plain for visual row/x lookup
        _plain_ecol = raw_col_to_plain(lines[erow], ecol)
        vis_row, vis_x = 0, _plain_ecol
        for vr, (li, cs) in enumerate(row_map):
            if li == erow and cs <= _plain_ecol:
                vis_row = vr
                vis_x   = _plain_ecol - cs

        if vis_row < vscroll:
            vscroll = vis_row
        elif vis_row >= vscroll + edit_h:
            vscroll = vis_row - edit_h + 1

        for sr in range(edit_h):
            vr = sr + vscroll
            if vr >= total_vrows:
                break
            li, col_start = row_map[vr]
            seg_plain     = wrapped[vr]
            render_markup_segment(stdscr,
                                  edit_y + sr, 1,
                                  lines[li],
                                  col_start, len(seg_plain),
                                  edit_w, markup_attrs)

        if total_vrows > edit_h:
            pct = int(vscroll / max(1, total_vrows - edit_h) * 100)
            safe_add(stdscr, sh - 2, sw - 7, f" {pct:3d}% ", curses.A_DIM)

        # ── Footer + cursor (cursor LAST) ─────────────────────────────────
        footer = " Tab: title↔content   ^H: prompts   ^S: save   Esc: back "
        safe_add(stdscr, sh - 1, max(0, (sw - len(footer)) // 2),
                 footer, curses.A_DIM)

        curses.curs_set(1)
        if in_title:
            try:
                stdscr.move(title_y, min(tx + len(tdisp), sw - 2))
            except curses.error:
                pass
        else:
            cy = edit_y + vis_row - vscroll
            cx = 1 + vis_x
            cy = max(edit_y, min(cy, sh - 3))
            cx = max(1,      min(cx, sw - 2))
            seg       = wrapped[vis_row] if 0 <= vis_row < len(wrapped) else ""
            char_here = seg[vis_x] if vis_x < len(seg) else " "
            try:
                stdscr.addstr(cy, cx, char_here,
                              curses.color_pair(CP_SEL) | curses.A_BOLD)
                stdscr.move(cy, cx)
            except curses.error:
                pass

        stdscr.refresh()
        ch = stdscr.getch()

        if ch == 17:            # Ctrl+Q
            save(); return "quit"
        elif ch == 27:          # Esc
            save(); return None
        elif ch == 19:          # Ctrl+S
            save(); continue
        elif ch == 8:           # Ctrl+H — toggle prompts
            data["show_prompts"] = not data.get("show_prompts", True)
            save_project(data); continue
        elif ch == 9:           # Tab
            in_title = not in_title; continue

        if in_title:
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                title = title[:-1]
            elif ch in (curses.KEY_ENTER, 10, 13):
                in_title = False
            elif 32 <= ch <= 126 and len(title) < 120:
                title += chr(ch)
        else:
            cur = lines[erow]
            if ch == curses.KEY_UP:
                if vis_row > 0:
                    pv = vis_row - 1
                    li, cs = row_map[pv]
                    target_plain = min(cs + vis_x, cs + len(wrapped[pv]))
                    erow = li
                    ecol = plain_col_to_raw(lines[li], target_plain)
            elif ch == curses.KEY_DOWN:
                if vis_row < total_vrows - 1:
                    nv = vis_row + 1
                    li, cs = row_map[nv]
                    target_plain = min(cs + vis_x, cs + len(wrapped[nv]))
                    erow = li
                    ecol = plain_col_to_raw(lines[li], target_plain)
            elif ch == curses.KEY_LEFT:
                if ecol > 0:
                    ecol -= 1
                elif erow > 0:
                    erow -= 1
                    ecol  = len(lines[erow])
            elif ch == curses.KEY_RIGHT:
                if ecol < len(cur):
                    ecol += 1
                elif erow < len(lines) - 1:
                    erow += 1
                    ecol  = 0
            elif ch == curses.KEY_HOME:
                li, cs = row_map[vis_row]
                ecol   = plain_col_to_raw(lines[li], cs)
            elif ch == curses.KEY_END:
                li, cs = row_map[vis_row]
                ecol   = plain_col_to_raw(lines[li], cs + len(wrapped[vis_row]))
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                if ecol > 0:
                    lines[erow] = cur[:ecol - 1] + cur[ecol:]
                    ecol -= 1
                elif erow > 0:
                    prev  = lines[erow - 1]
                    ecol  = len(prev)
                    lines[erow - 1] = prev + cur
                    lines.pop(erow)
                    erow -= 1
            elif ch == curses.KEY_DC:
                if ecol < len(cur):
                    lines[erow] = cur[:ecol] + cur[ecol + 1:]
                elif erow < len(lines) - 1:
                    lines[erow] = cur + lines[erow + 1]
                    lines.pop(erow + 1)
            elif ch in (curses.KEY_ENTER, 10, 13):
                tail = cur[ecol:]
                lines[erow] = cur[:ecol]
                erow += 1
                lines.insert(erow, tail)
                ecol = 0
            elif 32 <= ch <= 126:
                lines[erow] = cur[:ecol] + chr(ch) + cur[ecol:]
                ecol += 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main(stdscr):
    global _PHO_ATTR
    ensure_dir()
    curses.raw()
    curses.noecho()
    stdscr.keypad(True)
    curses.curs_set(0)
    init_colors()

    while True:
        data = screen_projects(stdscr)
        if data is None:
            break
        while True:
            act_idx = screen_acts(stdscr, data)
            if act_idx is None:
                break
            result = screen_grid(stdscr, data, act_idx)
            if result == "quit":
                return


def run():
    ensure_dir()
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    print("nu_plot closed.  Plots saved in ~/nu_plots/")


if __name__ == "__main__":
    run()
