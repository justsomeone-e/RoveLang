# -*- coding: utf-8 -*-
"""
Tour of Nyx - Modern Terminal UI Engine
Provides high-fidelity ANSI truecolor formatting, unicode borders,
progress gauges, and elegant diagnostics cards.
"""

import os
import sys
import shutil

# Check if ANSI color is supported
SUPPORTS_COLOR = sys.platform != "win32" or "ANSICON" in os.environ or "WT_SESSION" in os.environ or os.environ.get("TERM_PROGRAM") is not None or True

# Enable VT100 on Windows console if possible
if sys.platform == "win32":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        hOut = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(hOut, ctypes.byref(mode))
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(hOut, mode.value | 0x0004)
    except Exception:
        pass

# Color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# Standard 16 colors
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_CYAN = "\033[96m"
BRIGHT_WHITE = "\033[97m"

BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_BLUE = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_DARK = "\033[48;5;236m"


def rgb(r: int, g: int, b: int) -> str:
    """Return ANSI 24-bit truecolor escape sequence."""
    return f"\033[38;2;{r};{g};{b}m"


def bg_rgb(r: int, g: int, b: int) -> str:
    """Return ANSI 24-bit background escape sequence."""
    return f"\033[48;2;{r};{g};{b}m"


# Nyx Brand Palette
COLOR_NYX_PURPLE = rgb(155, 89, 182)
COLOR_NYX_VIOLET = rgb(186, 85, 211)
COLOR_NYX_CYAN   = rgb(0, 220, 255)
COLOR_NYX_GOLD   = rgb(255, 204, 0)
COLOR_NYX_GREEN  = rgb(46, 204, 113)
COLOR_NYX_RED    = rgb(231, 76, 60)
COLOR_NYX_GRAY   = rgb(127, 140, 141)
COLOR_NYX_MUTED  = rgb(90, 105, 120)


def get_terminal_width() -> int:
    """Return current terminal column width, clamped to a sensible range."""
    try:
        width = shutil.get_terminal_size((80, 24)).columns
        return max(70, min(width - 2, 100))
    except Exception:
        return 80


def gradient_text(text: str, start_rgb=(170, 75, 255), end_rgb=(0, 220, 255)) -> str:
    """Interpolate truecolor RGB across characters of a single line string."""
    n = len(text)
    if n <= 1:
        return f"{rgb(*start_rgb)}{text}{RESET}"
    out = []
    r1, g1, b1 = start_rgb
    r2, g2, b2 = end_rgb
    for i, ch in enumerate(text):
        ratio = i / (n - 1)
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        out.append(f"{rgb(r, g, b)}{ch}")
    return "".join(out) + RESET


def render_banner() -> str:
    """Generate the glowing ASCII gradient banner for Tour of Nyx."""
    raw_lines = [
        r"  ████████╗ ██████╗ ██╗   ██╗██████╗      ██████╗ ███████╗    ███╗   ██╗██╗   ██╗██╗  ██╗",
        r"  ╚══██╔══╝██╔═══██╗██║   ██║██╔══██╗    ██╔═══██╗██╔════╝    ████╗  ██║╚██╗ ██╔╝╚██╗██╔╝",
        r"     ██║   ██║   ██║██║   ██║██████╔╝    ██║   ██║█████╗      ██╔██╗ ██║ ╚████╔╝  ╚███╔╝ ",
        r"     ██║   ██║   ██║██║   ██║██╔══██╗    ██║   ██║██╔══╝      ██║╚██╗██║  ╚██╔╝   ██╔██╗ ",
        r"     ██║   ╚██████╔╝╚██████╔╝██║  ██║    ╚██████╔╝██║         ██║ ╚████║   ██║   ██╔╝ ██╗",
        r"     ╚═╝    ╚═════╝  ╚═════╝ ╚═╝  ╚═╝     ╚═════╝ ╚═╝         ╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝",
    ]
    formatted = []
    total = len(raw_lines)
    for idx, line in enumerate(raw_lines):
        # Vertical gradient shift from violet to cyan
        ratio = idx / max(1, total - 1)
        r = int(186 - (186 - 0) * ratio)
        g = int(85 + (220 - 85) * ratio)
        b = int(211 + (255 - 211) * ratio)
        formatted.append(f"{rgb(r, g, b)}{line}{RESET}")

    subtitle = "      ✦  Interactive Guided Tour of the Nyx Programming Language  ✦      "
    bar = "―" * (len(subtitle) - 4)
    formatted.append(f"{DIM}{COLOR_NYX_MUTED}    {bar}{RESET}")
    formatted.append(f"{BOLD}{gradient_text(subtitle, (220, 100, 255), (0, 230, 230))}{RESET}")
    formatted.append(f"{DIM}{COLOR_NYX_MUTED}    {bar}{RESET}")
    return "\n".join(formatted)


def render_progress(completed: int, total: int, width: int = 30) -> str:
    """Return a styled unicode progress meter."""
    pct = (completed / total * 100) if total > 0 else 0
    filled = int(width * completed / total) if total > 0 else 0
    empty = width - filled

    bar = f"{COLOR_NYX_CYAN}{'▰' * filled}{DIM}{COLOR_NYX_MUTED}{'▱' * empty}{RESET}"
    percent_str = f"{BOLD}{COLOR_NYX_GOLD}{pct:5.1f}%{RESET}"
    count_str = f"{DIM}({completed}/{total} Completed){RESET}"
    return f"{bar} {percent_str} {count_str}"


def box(title: str, content: str, color_seq: str = COLOR_NYX_CYAN, min_width: int = 76) -> str:
    """Render a modern rounded border card with title and multiline content."""
    width = max(min_width, get_terminal_width())
    lines = content.splitlines()
    if not lines:
        lines = [""]

    top_border_len = width - len(title) - 4
    if top_border_len < 2:
        top_border_len = 2
    top = f"{color_seq}╭─ {BOLD}{title}{RESET}{color_seq} {'─' * top_border_len}╮{RESET}"

    body_lines = []
    for line in lines:
        clean = line.rstrip("\r\n")
        body_lines.append(f"{color_seq}│{RESET} {clean}")

    bot = f"{color_seq}╰{'─' * (width - 1)}╯{RESET}"
    return "\n".join([top] + body_lines + [bot])


def format_error_card(exercise_path: str, raw_error: str) -> str:
    """Format compiler error diagnostics into an attractive boxed error panel."""
    lines = []
    lines.append(f"{BOLD}{BRIGHT_RED}COMPILATION / VERIFICATION FAILED{RESET}")
    lines.append(f"{DIM}File: {COLOR_NYX_CYAN}{exercise_path}{RESET}")
    lines.append("")

    # Clean and indent error lines
    err_lines = [l for l in raw_error.strip().splitlines() if l.strip()]
    if not err_lines:
        lines.append(f"  {RED}(No compiler diagnostic message returned){RESET}")
    else:
        for l in err_lines:
            if "NYX_TYPE_ERROR:" in l or "NYX_PARSER_ERROR:" in l or "NYX_HIR_ERROR:" in l:
                lines.append(f"  {BOLD}{BRIGHT_RED}► {l}{RESET}")
            elif "AssertionError:" in l or "FAILED" in l:
                lines.append(f"  {BOLD}{BRIGHT_RED}✗ {l}{RESET}")
            elif "line " in l or ".nyx:" in l:
                lines.append(f"  {COLOR_NYX_GOLD}{l}{RESET}")
            elif l.startswith("-->") or l.startswith(" |"):
                lines.append(f"  {DIM}{l}{RESET}")
            else:
                lines.append(f"  {WHITE}{l}{RESET}")

    lines.append("")
    lines.append(f"{DIM}Tip: Edit {BOLD}{exercise_path}{RESET}{DIM} in your editor and save to re-test.{RESET}")
    return box("Diagnostics", "\n".join(lines), color_seq=BRIGHT_RED)


def format_success_card(exercise_name: str, exercise_path: str, output: str) -> str:
    """Format a successful exercise completion panel."""
    lines = []
    lines.append(f"{BOLD}{BRIGHT_GREEN}✨ EXERCISE SOLVED! {COLOR_NYX_CYAN}{exercise_name}{RESET}")
    lines.append(f"{DIM}Source: {exercise_path}{RESET}")
    lines.append("")
    if output.strip():
        lines.append(f"{BOLD}{COLOR_NYX_VIOLET}Output:{RESET}")
        for l in output.strip().splitlines():
            lines.append(f"  {COLOR_NYX_GREEN}✔ {WHITE}{l}{RESET}")
        lines.append("")
    lines.append(f"{BOLD}{COLOR_NYX_GOLD}Great job!{RESET} Press {BOLD}{BRIGHT_CYAN}[n]{RESET} to continue to the next exercise,")
    lines.append(f"or continue modifying {exercise_path} to experiment further.")
    return box("Success", "\n".join(lines), color_seq=BRIGHT_GREEN)


def format_info_card(topic: str, path: str, description: str, hint_level: int = 0,
                     lesson: dict = None) -> str:
    """Format the current exercise info banner."""
    lines = [
        f"{BOLD}{WHITE}Topic:       {COLOR_NYX_VIOLET}{topic}{RESET}",
        f"{BOLD}{WHITE}File:        {COLOR_NYX_CYAN}{path}{RESET}",
        f"{BOLD}{WHITE}Objective:   {description}{RESET}",
    ]
    if lesson:
        lines.extend([
            "",
            f"{BOLD}{COLOR_NYX_GOLD}Why:        {RESET}{lesson['why']}",
            f"{BOLD}{COLOR_NYX_CYAN}Learn:      {RESET}{lesson['learn']}",
            f"{BOLD}{COLOR_NYX_GREEN}Task:       {RESET}{lesson['task']}",
            f"{BOLD}{WHITE}Expected:   {RESET}{lesson['expected']}",
        ])
    if hint_level > 0:
        lines.append(f"{DIM}Hints viewed: {hint_level}{RESET}")
    return box("Current Lesson", "\n".join(lines), color_seq=COLOR_NYX_PURPLE)


def format_hint_card(hint_text: str, hint_num: int, total_hints: int) -> str:
    """Format a hint display card."""
    lines = [
        f"{BOLD}{COLOR_NYX_GOLD}💡 Hint ({hint_num}/{total_hints}):{RESET}",
        "",
        f"  {hint_text}",
        "",
        f"{DIM}(Press [h] again for more hints if available, or [s] for full solution){RESET}"
    ]
    return box("Hint", "\n".join(lines), color_seq=COLOR_NYX_GOLD)


def format_controls() -> str:
    """Render the bottom interactive key control bar."""
    keys = [
        f"{BOLD}{BRIGHT_CYAN}[o]{RESET} Edit",
        f"{BOLD}{BRIGHT_CYAN}[e]{RESET} Folder",
        f"{BOLD}{BRIGHT_CYAN}[n]{RESET} Next",
        f"{BOLD}{BRIGHT_CYAN}[p]{RESET} Prev",
        f"{BOLD}{BRIGHT_CYAN}[h]{RESET} Hint",
        f"{BOLD}{BRIGHT_CYAN}[r]{RESET} Re-run",
        f"{BOLD}{BRIGHT_CYAN}[l]{RESET} List",
        f"{BOLD}{BRIGHT_CYAN}[s]{RESET} Solution",
        f"{BOLD}{BRIGHT_CYAN}[q]{RESET} Quit",
    ]
    return f"  {' │ '.join(keys)}"


def clear_screen():
    """Clear terminal screen cleanly."""
    if sys.platform == "win32":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
