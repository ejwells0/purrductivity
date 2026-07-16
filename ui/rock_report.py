# ui/rock_report.py
# Template-based Rock Report generator for quarterly work tasks.
# No API key needed — derives progress lines and action items from task data.
from __future__ import annotations

import math
from datetime import date


# ── Report data helpers ───────────────────────────────────────────────────────

def _quarter_end(due_quarter: str) -> date | None:
    """Parse 'Q2 2026' → June 30, 2026."""
    try:
        q_str, year_str = due_quarter.split()
        q_num = int(q_str[1])
        year = int(year_str)
        month, day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[q_num]
        return date(year, month, day)
    except Exception:
        return None


def _weeks_remaining(due_quarter: str) -> float:
    end = _quarter_end(due_quarter)
    if end is None:
        return 1.0
    days = (end - date.today()).days
    return max(1.0, days / 7.0)


def _progress_line(rock: dict) -> str:
    name = rock.get("name", "Unnamed")
    progress = rock.get("progress", 0)
    p_type = rock.get("progress_type", "percent")

    if progress >= 100:
        return f"Completed {name}."
    if p_type == "count":
        count = rock.get("progress_count", 0)
        target = rock.get("progress_target", 0)
        return f"{count}/{target} complete — {name}."
    return f"{name}: {progress}% complete."


def _action_item(rock: dict) -> tuple[float, str]:
    """Return (urgency_score, action_text). Higher score = listed first."""
    name = rock.get("name", "Unnamed")
    progress = rock.get("progress", 0)
    p_type = rock.get("progress_type", "percent")
    due_quarter = rock.get("due_quarter", "")
    weeks_left = _weeks_remaining(due_quarter)

    if p_type == "count":
        count = rock.get("progress_count", 0)
        target = rock.get("progress_target", 0)
        remaining = max(0, target - count)
        if remaining == 0:
            return (0.0, f"Finalize and close out {name}.")
        per_week = math.ceil(remaining / weeks_left)
        urgency = remaining / max(1, target)
        return (urgency, f"Complete {per_week} more on {name} to stay on track.")
    else:
        from store import quarterly_expected_fraction  # noqa: PLC0415
        expected_pct = quarterly_expected_fraction(date.today()) * 100
        gap = expected_pct - progress
        if gap <= 0:
            return (0.0, f"Maintain pace on {name}.")
        target_pct = min(100, math.ceil(expected_pct + (100 - expected_pct) / max(1, weeks_left)))
        return (gap / 100.0, f"Advance {name} to {target_pct}%.")


# ── Report text generation ────────────────────────────────────────────────────

_SEP = "─" * 36


def generate_report_text(tasks: list[dict]) -> str:
    rocks = [
        t for t in tasks
        if t.get("category") == "work" and (
            t.get("is_rock")
            or t.get("type") == "quarterly"  # backwards compat for existing quarterly tasks
        )
    ]

    if not rocks:
        return (
            f"What progress did you make last week on your rock(s)?\n\n"
            f"(No quarterly work tasks found — add some in the Work tab.)\n\n"
            f"{_SEP}\n\n"
            f"What are the top 3 things to do this week to get/stay on track?\n\n"
            f"1.\n2.\n3.\n\n"
            f"{_SEP}\n\n"
            f"Is anything blocking your progress?\n\n"
            f"—"
        )

    progress_lines = "\n".join(f"• {_progress_line(r)}" for r in rocks)

    incomplete = [r for r in rocks if r.get("progress", 0) < 100]
    scored = sorted((_action_item(r) for r in incomplete), key=lambda x: -x[0])
    top3 = [text for _, text in scored[:3]]
    while len(top3) < 3:
        top3.append("")
    action_lines = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(top3))

    return (
        f"What progress did you make last week on your rock(s)?\n\n"
        f"{progress_lines}\n\n"
        f"{_SEP}\n\n"
        f"What are the top 3 things to do this week to get/stay on track?\n\n"
        f"{action_lines}\n\n"
        f"{_SEP}\n\n"
        f"Is anything blocking your progress?\n\n"
        f"—"
    )


# ── Dialog ────────────────────────────────────────────────────────────────────

def open_rock_report(store) -> None:
    """Open the rock report dialog. Must be called from the tkinter child process."""
    import customtkinter as ctk  # noqa: PLC0415
    from ui.tk_host import get_root  # noqa: PLC0415
    from ui.styles import (  # noqa: PLC0415
        SAGE_BG, DARK_TEXT, SAGE_BUTTON, BUTTON_HOVER, BORDER_COLOR,
        BODY_FONT, TITLE_FONT, SMALL_FONT, SAGE_CARD, CAT_PINK,
    )

    tasks = store.get_all_tasks()

    root = get_root()
    dlg = ctk.CTkToplevel(root)
    dlg.title("Rock Report")
    dlg.geometry("460x560")
    dlg.configure(fg_color=SAGE_BG)
    dlg.resizable(False, True)
    dlg.attributes("-topmost", True)

    ctk.CTkFrame(dlg, height=8, fg_color=CAT_PINK, corner_radius=0).pack(fill="x")
    ctk.CTkLabel(
        dlg, text="Rock Report",
        font=TITLE_FONT, text_color=DARK_TEXT, fg_color="transparent",
    ).pack(pady=(12, 2))
    ctk.CTkLabel(
        dlg, text="Edit below, then copy to Slack.",
        font=SMALL_FONT, text_color=DARK_TEXT, fg_color="transparent",
    ).pack(pady=(0, 8))

    text_box = ctk.CTkTextbox(
        dlg,
        fg_color=SAGE_CARD,
        text_color=DARK_TEXT,
        border_color=BORDER_COLOR,
        border_width=1,
        wrap="word",
        font=BODY_FONT,
    )
    text_box.pack(fill="both", expand=True, padx=16, pady=(0, 8))
    text_box.insert("1.0", generate_report_text(tasks))

    btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_row.pack(fill="x", padx=16, pady=(0, 14))

    copy_btn = ctk.CTkButton(
        btn_row,
        text="Copy to Clipboard",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=10,
        height=34,
        font=BODY_FONT,
    )
    copy_btn.configure(command=lambda: _do_copy(dlg, text_box, copy_btn))
    copy_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))

    ctk.CTkButton(
        btn_row,
        text="Regenerate",
        fg_color=SAGE_CARD,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        border_color=BORDER_COLOR,
        border_width=1,
        corner_radius=10,
        height=34,
        font=BODY_FONT,
        command=lambda: _do_regen(text_box, store),
    ).pack(side="right")

    dlg.after(100, lambda: (dlg.lift(), dlg.focus_force()))


def _do_copy(dlg: "ctk.CTkToplevel", text_box, btn) -> None:
    content = text_box.get("1.0", "end-1c")
    dlg.clipboard_clear()
    dlg.clipboard_append(content)
    btn.configure(text="Copied!")
    dlg.after(1500, lambda: btn.configure(text="Copy to Clipboard"))


def _do_regen(text_box, store) -> None:
    text_box.delete("1.0", "end")
    text_box.insert("1.0", generate_report_text(store.get_all_tasks()))
