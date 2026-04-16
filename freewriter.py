#!/usr/bin/env python3
"""
freewriter — a dedicated writing environment launcher
Phosphor green. Keyboard only.

Place this file in the same directory as:
  nu_notes.py       — hierarchical note taking
  nu_draft.py       — word processor / drafting
  nu_flow.py        — focused single-line writing mode (terminal emulator)
  nu_flow_tty.py    — focused single-line writing mode (raw TTY)
  nu_plot.py        — story plotting tool (Hero's Journey card grid)

Run with:   python3 freewriter.py
"""

import curses
import os
import sys
import subprocess
import random
import json
import textwrap
import datetime

HERE       = os.path.dirname(os.path.abspath(__file__))
DRAFTS_DIR = os.path.expanduser("~/nu_drafts")
NOTES_DIR  = os.path.expanduser("~/nu_notes")
DATA_DIR      = os.path.expanduser("~/.freewriter")
TODO_FILE     = os.path.join(DATA_DIR, "todo.json")
SESSION_FILE  = os.path.join(DATA_DIR, "sessions.json")

# ── ASCII art title ───────────────────────────────────────────────────────────

TITLE = [
r"    ░▒▓████████▓▒░▒▓███████▓▒░░▒▓████████▓▒░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓███████▓▒░░▒▓█▓▒░▒▓████████▓▒░▒▓████████▓▒░▒▓███████▓▒░  ",
r"    ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░ ",
r"    ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░ ",
r"    ░▒▓██████▓▒░ ░▒▓███████▓▒░░▒▓██████▓▒░ ░▒▓██████▓▒░ ░▒▓█▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓███████▓▒░░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓██████▓▒░ ░▒▓███████▓▒░  ",
r"    ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░ ",
r"    ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░ ",
r"    ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░▒▓████████▓▒░░▒▓█████████████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░ ",
]

# ── Writing prompts ───────────────────────────────────────────────────────────

PROMPTS = [
    "A letter never sent, found decades later in a coat pocket.",
    "The last person on earth who remembers how to do one specific thing.",
    "Two strangers share an umbrella. Neither speaks the other's language.",
    "A map that leads somewhere its maker never intended.",
    "Something ordinary becomes strange after midnight.",
    "The first sentence of a novel you will never finish writing.",
    "A conversation overheard that changes everything.",
    "Someone returns to a place they swore they'd never go back to.",
    "The thing left unsaid at the end of an argument.",
    "A door that should not exist at the end of a familiar hallway.",
    "Write from the perspective of the last light in a room.",
    "An apology that arrives twenty years too late.",
    "The moment just before something irreversible happens.",
    "A character who collects one very specific, useless thing.",
    "Two people who know each other only by the sound of their footsteps.",
    "The weather on the day everything changed.",
    "A story that begins with the words: I should have known.",
    "Something that can only be described by what it is not.",
    "The smell of a place you cannot name but recognise completely.",
    "Write the obituary of an idea.",
    "A conversation between two people who are both lying.",
    "The first day of a job no one else wanted.",
    "What the animals knew that the people did not.",
    "A photograph with a stranger in the background every single time.",
    "The last page of a book that does not exist.",
    "Someone practices a speech they will never give.",
    "A town where one small rule has enormous consequences.",
    "The weight of an object that means nothing to anyone else.",
    "Write about a colour that has no name.",
    "A friendship that exists only in one specific place.",
]


# ── Data helpers ──────────────────────────────────────────────────────────────

def ensure_dirs():
    for d in [DRAFTS_DIR, NOTES_DIR, DATA_DIR]:
        os.makedirs(d, exist_ok=True)

def count_drafts():
    try:
        return len([f for f in os.listdir(DRAFTS_DIR) if f.endswith(".txt")])
    except OSError:
        return 0

def count_notes_recursive(path):
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file() and entry.name.endswith(".txt"):
                total += 1
            elif entry.is_dir():
                total += count_notes_recursive(entry.path)
    except OSError:
        pass
    return total

def total_draft_words():
    total = 0
    try:
        for f in os.listdir(DRAFTS_DIR):
            if f.endswith(".txt"):
                try:
                    text = open(os.path.join(DRAFTS_DIR, f)).read()
                    total += len(text.split())
                except OSError:
                    pass
    except OSError:
        pass
    return total

def load_todos():
    """Load todos. On each load, purge any completed from a previous session."""
    try:
        with open(TODO_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    today = datetime.date.today().isoformat()
    # Keep items that are either not done, or were completed today
    kept = [t for t in data
            if not t.get("done") or t.get("done_date") == today]
    return kept

def save_todos(todos):
    with open(TODO_FILE, "w") as f:
        json.dump(todos, f, indent=2)


# ── UI helpers ────────────────────────────────────────────────────────────────

_PHOSPHOR_ATTR = curses.A_BOLD

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

def safe_addstr(win, y, x, text, attr=0):
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


# ── Sub-screens ───────────────────────────────────────────────────────────────

def screen_thesaurus(stdscr, PHO, HL):
    """Thesaurus lookup using the `dict` command with dict.org."""
    sh, sw = stdscr.getmaxyx()

    def lookup(word):
        try:
            result = subprocess.run(
                ["dict", "-d", "moby-thesaurus", word],
                capture_output=True, text=True, timeout=8
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            # Fallback: try any database
            result = subprocess.run(
                ["dict", word],
                capture_output=True, text=True, timeout=8
            )
            return result.stdout.strip() if result.stdout.strip() else None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def format_output(raw, width):
        """Turn raw dict output into clean readable lines."""
        lines = []
        for line in raw.splitlines():
            line = line.rstrip()
            if not line:
                lines.append("")
                continue
            # Wrap long lines
            if len(line) > width:
                wrapped = textwrap.wrap(line, width,
                                        break_long_words=False,
                                        break_on_hyphens=False)
                lines.extend(wrapped or [line])
            else:
                lines.append(line)
        return lines

    word        = ""
    result_lines = []
    scroll      = 0
    message     = ""
    searching   = False

    while True:
        sh, sw = stdscr.getmaxyx()
        inner_w = sw - 6
        stdscr.erase()

        # Title
        safe_addstr(stdscr, 1, 2, " THESAURUS ", PHO)
        safe_addstr(stdscr, 1, sw - 20, " Ctrl+Q: back ", curses.A_DIM)

        # Input box
        safe_addstr(stdscr, 3, 2, "Word: ", PHO)
        box_w = min(40, sw - 12)
        safe_addstr(stdscr, 3, 8, f"[{word:<{box_w}}]", PHO)

        if message:
            safe_addstr(stdscr, 3, sw - len(message) - 3, message, curses.A_DIM)

        # Divider
        safe_addstr(stdscr, 5, 2, "─" * (sw - 4), curses.A_DIM)

        # Results
        view_h = sh - 8
        for i in range(view_h):
            idx = i + scroll
            if idx >= len(result_lines):
                break
            line = result_lines[idx]
            # Highlight section headers (lines starting with a digit or "From")
            if line and (line[0].isdigit() or line.startswith("From")):
                safe_addstr(stdscr, 6 + i, 2, line[:sw - 4], PHO)
            else:
                safe_addstr(stdscr, 6 + i, 2, line[:sw - 4])

        # Scroll hint
        if len(result_lines) > view_h:
            pct = int((scroll / max(1, len(result_lines) - view_h)) * 100)
            safe_addstr(stdscr, sh - 2, sw - 8, f" {pct:3d}% ", curses.A_DIM)

        # Position cursor in input
        curses.curs_set(1)
        try:
            stdscr.move(3, 8 + len(word))
        except curses.error:
            pass
        stdscr.refresh()

        ch = stdscr.getch()

        if ch == 17:                        # Ctrl+Q — back
            curses.curs_set(0)
            return

        elif ch in (curses.KEY_ENTER, 10, 13):
            if word.strip():
                curses.curs_set(0)
                message = "searching..."
                stdscr.refresh()
                raw = lookup(word.strip())
                if raw:
                    result_lines = format_output(raw, inner_w)
                    scroll       = 0
                    message      = f"{len(result_lines)} lines"
                else:
                    result_lines = [f"  No results for '{word}'.  ",
                                    "",
                                    "  Is 'dict' installed?",
                                    "  sudo apt install dict dict-moby-thesaurus"]
                    scroll   = 0
                    message  = "not found"

        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            word = word[:-1]
            result_lines = []
            scroll = 0
            message = ""

        elif ch == curses.KEY_UP:
            scroll = max(0, scroll - 1)

        elif ch == curses.KEY_DOWN:
            scroll = min(max(0, len(result_lines) - (sh - 8)), scroll + 1)

        elif ch == curses.KEY_PPAGE:
            scroll = max(0, scroll - (sh - 8))

        elif ch == curses.KEY_NPAGE:
            scroll = min(max(0, len(result_lines) - (sh - 8)), scroll + (sh - 8))

        elif 32 <= ch <= 126:
            word += chr(ch)
            result_lines = []
            scroll = 0
            message = ""


def screen_prompts(stdscr, PHO, HL):
    """Show a random writing prompt. Space or Enter for a new one."""
    prompt = random.choice(PROMPTS)
    while True:
        sh, sw = stdscr.getmaxyx()
        stdscr.erase()

        safe_addstr(stdscr, 1, 2, " WRITING PROMPT ", PHO)
        safe_addstr(stdscr, 1, sw - 30, " Space/Enter: new  Ctrl+Q: back ", curses.A_DIM)

        # Draw prompt centered in the middle third of the screen
        wrap_w   = min(60, sw - 8)
        wrapped  = textwrap.wrap(prompt, wrap_w) or [prompt]
        start_y  = (sh - len(wrapped)) // 2
        for i, line in enumerate(wrapped):
            x = (sw - len(line)) // 2
            safe_addstr(stdscr, start_y + i, x, line, PHO | curses.A_BOLD)

        stdscr.refresh()
        ch = stdscr.getch()

        if ch == 17:                            # Ctrl+Q
            return
        elif ch in (ord(" "), 10, 13):
            prompt = random.choice(PROMPTS)


def screen_todo(stdscr, PHO, HL):
    """Simple weekly to-do list. Completed items vanish on next launch."""
    todos = load_todos()
    sel   = 0

    while True:
        sh, sw = stdscr.getmaxyx()
        stdscr.erase()

        safe_addstr(stdscr, 1, 2, " WEEKLY TO-DO ", PHO)
        safe_addstr(stdscr, 1, sw - 46,
                    " A: add  D: delete  Space: check  Ctrl+Q: back ",
                    curses.A_DIM)
        safe_addstr(stdscr, 2, 2, "─" * (sw - 4), curses.A_DIM)

        if not todos:
            msg = "No tasks yet. Press A to add one."
            safe_addstr(stdscr, sh // 2, (sw - len(msg)) // 2, msg, curses.A_DIM)
        else:
            sel = max(0, min(sel, len(todos) - 1))
            for i, task in enumerate(todos):
                y    = 3 + i
                if y >= sh - 2:
                    break
                done = task.get("done", False)
                box  = "[x]" if done else "[ ]"
                text = task.get("text", "")
                disp = f"  {box} {text}"[:sw - 4]
                if i == sel:
                    attr = HL
                elif done:
                    attr = curses.A_DIM
                else:
                    attr = curses.A_NORMAL
                safe_addstr(stdscr, y, 2, f"{disp:<{sw-4}}", attr)

        safe_addstr(stdscr, sh - 1, 2,
                    f" {sum(1 for t in todos if t.get('done'))} of {len(todos)} done ",
                    curses.A_DIM)

        stdscr.refresh()
        ch = stdscr.getch()

        if ch == 17:                            # Ctrl+Q — back
            save_todos(todos)
            return

        elif ch in (ord('a'), ord('A')):        # Add task
            curses.curs_set(1)
            # Inline input at bottom
            safe_addstr(stdscr, sh - 2, 2, "New task: " + " " * (sw - 14), PHO)
            stdscr.refresh()
            text = ""
            while True:
                safe_addstr(stdscr, sh - 2, 12, text + " ", PHO)
                try:
                    stdscr.move(sh - 2, 12 + len(text))
                except curses.error:
                    pass
                stdscr.refresh()
                c = stdscr.getch()
                if c in (curses.KEY_ENTER, 10, 13):
                    break
                elif c == 27:
                    text = ""
                    break
                elif c in (curses.KEY_BACKSPACE, 127, 8):
                    text = text[:-1]
                elif 32 <= c <= 126 and len(text) < sw - 14:
                    text += chr(c)
            curses.curs_set(0)
            if text.strip():
                todos.append({"text": text.strip(), "done": False})
                sel = len(todos) - 1
                save_todos(todos)

        elif ch in (ord('d'), ord('D')):        # Delete selected
            if todos:
                todos.pop(sel)
                sel = max(0, sel - 1)
                save_todos(todos)

        elif ch == ord(' '):                    # Toggle done
            if todos:
                task = todos[sel]
                task["done"] = not task.get("done", False)
                task["done_date"] = (datetime.date.today().isoformat()
                                     if task["done"] else None)
                save_todos(todos)

        elif ch == curses.KEY_UP:
            sel = max(0, sel - 1)

        elif ch == curses.KEY_DOWN:
            sel = min(len(todos) - 1, sel + 1)



# ── Session journal helpers ───────────────────────────────────────────────────

def load_sessions():
    """Return dict of {'YYYY-MM-DD': word_count} for all recorded days."""
    try:
        with open(SESSION_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

def save_sessions(sessions):
    with open(SESSION_FILE, "w") as f:
        json.dump(sessions, f, indent=2)

def count_all_draft_words():
    """Total words across all files in ~/nu_drafts/."""
    total = 0
    try:
        for fname in os.listdir(DRAFTS_DIR):
            if fname.endswith(".txt"):
                try:
                    text = open(os.path.join(DRAFTS_DIR, fname)).read()
                    total += len(text.split())
                except OSError:
                    pass
    except OSError:
        pass
    return total

def record_session_words(sessions, words_before):
    """
    Called whenever we return from a writing app.
    Computes words written this sitting and adds them to today's tally.
    words_before: word count snapshot taken before launching the app.
    """
    today      = datetime.date.today().isoformat()
    words_now  = count_all_draft_words()
    delta      = max(0, words_now - words_before)
    if delta > 0:
        sessions[today] = sessions.get(today, 0) + delta
        save_sessions(sessions)
    return words_now   # return new baseline

def get_week_log(sessions):
    """
    Return list of (date_str, display_str, word_count) for the last 7 days,
    oldest first, newest (today) last.
    """
    today = datetime.date.today()
    rows  = []
    for offset in range(6, -1, -1):
        d     = today - datetime.timedelta(days=offset)
        iso   = d.isoformat()
        count = sessions.get(iso, 0)
        # Display: "Mon Apr 10" style, "Today" for today
        if offset == 0:
            label = "Today      "
        else:
            label = d.strftime("%a %b %d ")
        rows.append((iso, label, count))
    return rows


def launch_app(name, *args):
    """Suspend curses, run a sibling script, resume on return."""
    script = os.path.join(HERE, name)
    cmd    = [sys.executable, script] + list(args)
    curses.endwin()
    try:
        subprocess.run(cmd)
    except FileNotFoundError:
        pass
    # curses.wrapper will re-init on next call; we need stdscr refresh
    # The caller does stdscr.clear() + stdscr.refresh() after we return.


# ── Main launcher ─────────────────────────────────────────────────────────────

def main(stdscr):
    global _PHOSPHOR_ATTR
    ensure_dirs()

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

    curses.init_pair(1, PHOSPHOR,           -1)
    curses.init_pair(2, curses.COLOR_BLACK,  PHOSPHOR)
    curses.init_pair(3, curses.COLOR_RED,    -1)

    PHO = curses.color_pair(1) | curses.A_BOLD
    HL  = curses.color_pair(2) | curses.A_BOLD
    DIM = curses.A_DIM
    _PHOSPHOR_ATTR = PHO

    # Menu — Writing Prompt and To-Do now live inline on the home screen
    MENU = [
        ("Drafts",     "nu_flow.py",  "Long-form focused writing"),
        ("Notes",      "nu_notes.py", "Hierarchical notebook & notes"),
        ("Plot",       "nu_plot.py",  "Story plotting — Hero's Journey cards"),
        ("Thesaurus",  None,          "Look up synonyms via dict"),
        ("Quit",       None,          "Exit Freewriter"),
    ]

    # Pick a prompt once per session — shown at the bottom like a daily quote
    daily_prompt = random.choice(PROMPTS)

    # Two focusable panels on the home screen
    FOCUS_MENU = 0
    FOCUS_TODO = 1
    focus    = FOCUS_MENU
    menu_sel = 0

    # To-do list lives inline — load once, save on change
    todos    = load_todos()
    todo_sel = 0

    # Session journal — initialise before the draw loop
    sessions     = load_sessions()
    words_before = count_all_draft_words()

    def reinit():
        """Re-arm curses after returning from a child process."""
        curses.raw()
        curses.noecho()
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.clear()

    def add_todo_inline(sh, sw, right_x, right_w):
        """Inline task-entry field drawn in the to-do panel."""
        curses.curs_set(1)
        prompt_str = "New task: "
        input_x    = right_x + 1 + len(prompt_str)
        input_y    = sh - 4            # just above the prompt strip
        input_w    = right_w - len(prompt_str) - 2
        safe_addstr(stdscr, input_y, right_x + 1,
                    prompt_str + " " * input_w, PHO)
        stdscr.refresh()
        text = ""
        while True:
            safe_addstr(stdscr, input_y, input_x,
                        (text + " ")[:input_w], PHO)
            try:
                stdscr.move(input_y, input_x + len(text))
            except curses.error:
                pass
            stdscr.refresh()
            c = stdscr.getch()
            if c in (curses.KEY_ENTER, 10, 13):
                break
            elif c == 27:
                text = ""
                break
            elif c in (curses.KEY_BACKSPACE, 127, 8):
                text = text[:-1]
            elif 32 <= c <= 126 and len(text) < input_w - 1:
                text += chr(c)
        curses.curs_set(0)
        return text.strip()

    while True:
        sh, sw = stdscr.getmaxyx()
        stdscr.erase()

        # ── Layout maths ──────────────────────────────────────────────────
        TITLE_H      = len(TITLE)
        TITLE_W      = max(len(l) for l in TITLE)
        FOOTER_H     = 1
        PROMPT_H     = 2
        DIVIDER_H    = 1
        bottom_strip = FOOTER_H + DIVIDER_H + PROMPT_H

        # Vertical split — title lives in the left 2/3, right panel is full height
        mid      = (sw * 2) // 3
        left_w   = mid - 1
        right_x  = mid + 1
        right_w  = sw - right_x - 1

        # Title spans the full screen width, centred.
        # Both panels start below it.  The divider starts at title_y + TITLE_H.
        title_x   = max(0, (sw - TITLE_W) // 2)
        title_y   = 1

        # Both panels start immediately below the title
        content_y   = title_y + TITLE_H
        right_top   = content_y
        content_bot = max(content_y + 4, sh - bottom_strip - 1)
        content_h   = content_bot - content_y
        right_bot   = sh - bottom_strip - 1

        # ── ASCII title (full width, centred) ─────────────────────────────
        for i, line in enumerate(TITLE):
            safe_addstr(stdscr, title_y + i, title_x, line[:sw], PHO)

        # ── Vertical centre divider (below title) ─────────────────────────
        for y in range(content_y, sh - 1):
            safe_addstr(stdscr, y, mid, "│", DIM)

        # ── Left panel: Menu ──────────────────────────────────────────────
        panel_label = "MENU" if focus == FOCUS_MENU else "menu"
        safe_addstr(stdscr, content_y, 2, f" {panel_label} ",
                    PHO if focus == FOCUS_MENU else DIM)

        for i, (label, _, desc) in enumerate(MENU):
            row = content_y + 2 + i
            if row >= content_bot:
                break
            is_sel = (focus == FOCUS_MENU and i == menu_sel)
            if is_sel:
                bar = f"  >  {label:<14}  {desc}"
                safe_addstr(stdscr, row, 2,
                            f"{bar:<{left_w - 2}}", HL)
            else:
                safe_addstr(stdscr, row, 5, f"{label:<16}",
                            PHO if focus == FOCUS_MENU else DIM)
                safe_addstr(stdscr, row, 21, desc[:left_w - 22], DIM)

        # ── Right panel: Session Journal ──────────────────────────────────
        safe_addstr(stdscr, right_top, right_x + 1, " THIS WEEK ", PHO)

        week_log   = get_week_log(sessions)
        week_total = sum(c for _, _, c in week_log)
        JOURNAL_ROWS = 7

        for ji, (iso, label, count) in enumerate(week_log):
            jy       = right_top + 1 + ji
            if jy >= content_bot:
                break
            is_today = (ji == 6)
            count_str = f"{count:>6,}" if count else "      —"
            row_str   = f" {label}{count_str}"
            attr      = PHO if is_today else (curses.A_NORMAL if count else DIM)
            safe_addstr(stdscr, jy, right_x + 1, row_str[:right_w - 1], attr)

        # Rule + 7-day total
        total_rule_y = right_top + 1 + JOURNAL_ROWS
        total_val_y  = total_rule_y + 1
        if total_rule_y < right_bot:
            safe_addstr(stdscr, total_rule_y, right_x + 1,
                        "─" * (right_w - 1), DIM)
        if total_val_y < right_bot:
            tw_str  = f"{week_total:>6,}"
            lbl_w   = max(0, right_w - 2 - len(tw_str) - 1)
            safe_addstr(stdscr, total_val_y, right_x + 1,
                        f" {'7-day total':<{lbl_w}}{tw_str}",
                        PHO)

        # Divider between journal and to-do
        divider_y  = total_val_y + 1
        if divider_y < right_bot:
            safe_addstr(stdscr, divider_y, right_x + 1,
                        "─" * (right_w - 1), DIM)

        # ── Right panel: To-Do ────────────────────────────────────────────
        todo_top   = divider_y + 1
        todo_label = "TO-DO" if focus == FOCUS_TODO else "to-do"
        if todo_top < right_bot:
            safe_addstr(stdscr, todo_top, right_x + 1, f" {todo_label} ",
                        PHO if focus == FOCUS_TODO else DIM)

        todo_start = todo_top + 1

        # Clamp selection
        if todos:
            todo_sel = max(0, min(todo_sel, len(todos) - 1))

        if not todos:
            if todo_start < right_bot:
                safe_addstr(stdscr, todo_start,
                            right_x + 2, "No tasks yet.", DIM)
            if focus == FOCUS_TODO and todo_start + 1 < right_bot:
                safe_addstr(stdscr, todo_start + 1,
                            right_x + 2, "Press A to add one.", DIM)
        else:
            max_visible = max(1, right_bot - todo_start - 1)
            for i, task in enumerate(todos[:max_visible]):
                row  = todo_start + i
                if row >= right_bot:
                    break
                done = task.get("done", False)
                box  = "[x]" if done else "[ ]"
                text = task.get("text", "")
                disp = f" {box} {text}"[:right_w - 1]
                is_sel = (focus == FOCUS_TODO and i == todo_sel)
                if is_sel:
                    safe_addstr(stdscr, row, right_x + 1,
                                f"{disp:<{right_w - 1}}", HL)
                elif done:
                    safe_addstr(stdscr, row, right_x + 1, disp, DIM)
                else:
                    safe_addstr(stdscr, row, right_x + 1, disp,
                                PHO if focus == FOCUS_TODO else curses.A_NORMAL)

        # Controls hint inside to-do panel when focused
        if focus == FOCUS_TODO:
            hint = "A:add  D:del  Spc:check"
            safe_addstr(stdscr, right_bot,
                        right_x + max(0, (right_w - len(hint)) // 2),
                        hint[:right_w], DIM)

        # ── Prompt of the day strip ───────────────────────────────────────
        rule_y    = sh - bottom_strip
        prompt_y  = rule_y + 1
        footer_y  = sh - 1

        safe_addstr(stdscr, rule_y, 1, "─" * (sw - 2), DIM)

        wrap_w   = max(10, sw - 6)
        wrapped  = textwrap.wrap(daily_prompt, wrap_w) or [daily_prompt]
        for li, pline in enumerate(wrapped[:PROMPT_H]):
            safe_addstr(stdscr, prompt_y + li,
                        max(1, (sw - len(pline)) // 2),
                        pline[:sw - 2], DIM)

        # ── Footer ────────────────────────────────────────────────────────
        footer = " Tab: switch   ↑↓: navigate   Enter: open   Ctrl+Q: quit "
        safe_addstr(stdscr, footer_y,
                    max(0, (sw - len(footer)) // 2),
                    footer[:sw], DIM)

        stdscr.refresh()

        # ── Input ─────────────────────────────────────────────────────────
        ch = stdscr.getch()

        if ch == 17:                            # Ctrl+Q — always quits
            save_todos(todos)
            break

        elif ch == 9:                           # Tab — switch focus
            focus = FOCUS_TODO if focus == FOCUS_MENU else FOCUS_MENU

        # ── Menu panel ───────────────────────────────────────────────────
        elif focus == FOCUS_MENU:
            if ch == curses.KEY_UP:
                menu_sel = (menu_sel - 1) % len(MENU)
            elif ch == curses.KEY_DOWN:
                menu_sel = (menu_sel + 1) % len(MENU)
            elif ch in (curses.KEY_ENTER, 10, 13):
                label, script, _ = MENU[menu_sel]
                if label == "Quit":
                    save_todos(todos)
                    break
                elif script:
                    launch_app(script)
                    reinit()
                    # Record words written during that app session
                    words_before = record_session_words(sessions, words_before)
                    sessions.update(load_sessions())
                elif label == "Thesaurus":
                    screen_thesaurus(stdscr, PHO, HL)

        # ── To-Do panel ───────────────────────────────────────────────────
        elif focus == FOCUS_TODO:
            if ch == curses.KEY_UP:
                todo_sel = max(0, todo_sel - 1)
            elif ch == curses.KEY_DOWN:
                if todos:
                    todo_sel = min(len(todos) - 1, todo_sel + 1)

            elif ch in (ord('a'), ord('A')):
                new_text = add_todo_inline(sh, sw, right_x, right_w)
                if new_text:
                    todos.append({"text": new_text, "done": False})
                    todo_sel = len(todos) - 1
                    save_todos(todos)

            elif ch in (ord('d'), ord('D')):
                if todos:
                    todos.pop(todo_sel)
                    todo_sel = max(0, todo_sel - 1)
                    save_todos(todos)

            elif ch == ord(' '):
                if todos:
                    task = todos[todo_sel]
                    task["done"] = not task.get("done", False)
                    task["done_date"] = (datetime.date.today().isoformat()
                                         if task["done"] else None)
                    save_todos(todos)


def run():
    ensure_dirs()
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    print("Freewriter closed.")


if __name__ == "__main__":
    run()
