# ui/reminder_popup.py
# Reminder popup CTkToplevel — separate from main panel.
#
# MUST be called from the tkinter child process only (via tk_process._poll).
# All enqueue() calls here route to the main process for store updates + badge changes.
import os
import random
import customtkinter as ctk
from PIL import Image
from AppKit import NSScreen

from ui.styles import (
    SAGE_BG, CAT_PINK, SAGE_BUTTON, BUTTON_HOVER, DARK_TEXT, BORDER_COLOR, SAGE_CARD,
)

POPUP_W, POPUP_H = 300, 370
POPUP_H_GOAL = 450   # taller popup for weekly/quarterly tasks (adds progress input row)
_NAG_INTERVAL_MS = 5 * 60 * 1000  # re-nag after 5 minutes of inaction

_NAG_MESSAGES = [
    "*taps you on the shoulder* Still waiting on this one...",
    "Ahem. Your cat is still here. Judging. 🐱",
    "*knocks your water glass off the desk* REMEMBER THIS??",
    "Your cat has been sitting here for FIVE MINUTES. 😾",
    "*sits directly on your keyboard* DO THE THING",
    "This reminder has been open longer than your attention span.",
]

_CAT_MESSAGES = [
    "Your cat says it's time!",
    "*paws at you insistently*",
    "Meow! Don't forget this one.",
    "*sits on your keyboard*",
    "Pspsps... this won't do itself.",
    "Your reminder is here, human.",
    "Time to chase this one down!",
    "*stares at you until you do it*",
]

_HARSH_MESSAGES = [
    "Your cat is judging you. 😾\n{name}: {actual}/{target} done. Expected: {expected}.\nGet on it.",
    "Unacceptable. 😾\n{name}: only {actual}/{target}. You should be at {expected}.\nFix this.",
    "*slow blink of disappointment* 😾\n{name}: {actual}/{target}. Target was {expected}.\nDo better.",
]

_FRIENDLY_MESSAGES = [
    "*purrs approvingly* 🐾\n{name}: {actual}/{target} done. You're on track!\nKeep it up, human.",
    "Good human! 🐾\n{name}: {actual}/{target}. Right where you need to be.\nStay the course!",
    "*headbutts you affectionately* 🐾\n{name}: {actual}/{target}. On track!\nThe cat approves.",
]


def _get_tone_message(task: dict, today=None) -> str:
    """Return formatted tone message for a goal-type task."""
    from datetime import date as _date  # noqa: PLC0415
    from store import weekly_expected_fraction, quarterly_expected_fraction  # noqa: PLC0415

    if today is None:
        today = _date.today()
    name = task.get("name", "this task")

    if task["type"] == "weekly":
        target = task.get("weekly_target", 1)
        actual = task.get("completed_count", 0)
        expected = round(weekly_expected_fraction(today) * target)
        fmt = {"name": name, "actual": actual, "target": target, "expected": expected}
        # Inline behind check: use same logic as is_behind() weekly branch
        behind = actual < weekly_expected_fraction(today) * target
        pool = _HARSH_MESSAGES if behind else _FRIENDLY_MESSAGES

    elif task["type"] == "quarterly":
        actual = task.get("progress", 0)          # 0-100 %
        expected = round(quarterly_expected_fraction(today) * 100)
        fmt = {"name": name, "actual": actual, "target": 100, "expected": expected}
        # Inline quarterly behind check (uses progress, not completed_count)
        behind = actual < quarterly_expected_fraction(today) * 100
        pool = _HARSH_MESSAGES if behind else _FRIENDLY_MESSAGES

    else:
        return random.choice(_CAT_MESSAGES)

    return random.choice(pool).format(**fmt)

_CATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cats")
_CAT_FILES = sorted(f for f in os.listdir(_CATS_DIR) if f.lower().endswith(".png"))

_pending_queue: list[str] = []
_popup: ctk.CTkToplevel | None = None
_store = None


def _get_store():
    global _store
    if _store is None:
        from store import TaskStore  # noqa: PLC0415
        _store = TaskStore()
    return _store


def show_reminder(task_id: str) -> None:
    """Add task_id to pending queue and open popup if none currently showing."""
    _pending_queue.append(task_id)
    if _popup is None or not _popup.winfo_exists():
        _show_next()


def handle_done(task_id: str) -> None:
    """Called from _poll when 'done' IPC arrives. Updates store and advances queue."""
    from ui.tk_host import send_to_main  # noqa: PLC0415
    send_to_main("mark_done", task_id=task_id)
    _close_popup()
    if not _pending_queue:
        send_to_main("badge_clear")
    _show_next()


def handle_snooze(task_id: str, minutes: int) -> None:
    """Called from _poll when 'snooze' IPC arrives. Schedules re-fire and advances queue."""
    from datetime import datetime, timedelta  # noqa: PLC0415
    from ui.tk_host import enqueue, send_to_main  # noqa: PLC0415
    until = datetime.now() + timedelta(minutes=minutes)
    _get_store().update_snooze(task_id, until)
    enqueue("schedule_snooze", task_id=task_id, minutes=minutes)
    _close_popup()
    if not _pending_queue:
        send_to_main("badge_clear")
    _show_next()


def _close_popup() -> None:
    global _popup
    if _popup is not None and _popup.winfo_exists():
        _popup.destroy()
    _popup = None


def _snooze_tomorrow_minutes(task: dict) -> int:
    """Minutes from now until tomorrow at the task's scheduled hour:minute."""
    from datetime import datetime as _dt, timedelta as _td  # noqa: PLC0415
    now = _dt.now()
    tomorrow = now.date() + _td(days=1)
    target = _dt(tomorrow.year, tomorrow.month, tomorrow.day,
                 task.get("hour", 9), task.get("minute", 0))
    return max(1, int((target - now).total_seconds() / 60))


def _auto_nag(win: "ctk.CTkToplevel", msg_label: "ctk.CTkLabel") -> None:
    """Re-nag after inaction: update cat message and re-lift popup."""
    if win is None or not win.winfo_exists():
        return
    msg_label.configure(text=random.choice(_NAG_MESSAGES))
    win.lift()
    win.focus_force()
    try:
        from AppKit import NSApplication  # noqa: PLC0415
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass
    win.after(_NAG_INTERVAL_MS, lambda: _auto_nag(win, msg_label))


def _show_next() -> None:
    global _popup
    if not _pending_queue:
        return
    task_id = _pending_queue.pop(0)
    task = _get_store().get_task(task_id)
    if task is None:
        _show_next()  # skip deleted tasks
        return
    if task.get("is_rock_report"):
        _popup = _build_rock_report_popup(task)
    else:
        _popup = _build_popup(task)


def _calc_position() -> tuple[int, int]:
    """Top-right positioning matching panel.py logic."""
    from ui.tk_host import get_root  # noqa: PLC0415
    root = get_root()
    visible = NSScreen.mainScreen().visibleFrame()
    total_h = root.winfo_screenheight()
    menu_bar_h = total_h - int(visible.size.height) - int(visible.origin.y)
    margin = 8
    x = int(visible.origin.x + visible.size.width) - POPUP_W - margin
    y = menu_bar_h + margin
    return x, y


def _build_popup(task: dict) -> ctk.CTkToplevel:
    from ui.tk_host import get_root, enqueue  # noqa: PLC0415
    from ui.styles import TITLE_FONT, BODY_FONT, SMALL_FONT  # noqa: PLC0415

    root = get_root()
    task_id = task["id"]
    task_name = task["name"]
    is_goal = task.get("type") in ("weekly", "quarterly")
    # Binary weekly tasks (weekly_target == 1) are done/not-done — no progress input needed
    is_binary_weekly = task.get("type") == "weekly" and task.get("weekly_target", 1) == 1
    show_progress_input = is_goal and not is_binary_weekly
    message = _get_tone_message(task) if is_goal else random.choice(_CAT_MESSAGES)

    x, y = _calc_position()

    popup_h = POPUP_H_GOAL if show_progress_input else POPUP_H
    win = ctk.CTkToplevel(root)
    win.title("")
    win.geometry(f"{POPUP_W}x{popup_h}+{x}+{y}")
    win.configure(fg_color=SAGE_BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    # Prevent closing via window chrome — user must use Done or a snooze button
    win.protocol("WM_DELETE_WINDOW", lambda: None)

    # 1. CAT_PINK accent strip
    ctk.CTkFrame(win, height=8, fg_color=CAT_PINK, corner_radius=0).pack(fill="x")

    # 2. Cat image (random)
    cat_path = os.path.join(_CATS_DIR, random.choice(_CAT_FILES))
    cat_pil = Image.open(cat_path).convert("RGBA")
    cat_img = ctk.CTkImage(light_image=cat_pil, dark_image=cat_pil, size=(80, 80))
    ctk.CTkLabel(win, image=cat_img, text="", fg_color="transparent").pack(pady=(10, 0))

    # 3. Personality message
    msg_label = ctk.CTkLabel(
        win,
        text=message,
        font=SMALL_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
        wraplength=260,
    )
    msg_label.pack(pady=(4, 0), padx=16)

    # 4. Task name
    ctk.CTkLabel(
        win,
        text=task_name,
        font=TITLE_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
        wraplength=260,
    ).pack(pady=(4, 0), padx=16)

    # 4b. Progress input row (goal tasks with weekly_target > 1 or quarterly)
    if show_progress_input:
        task_type = task.get("type")
        is_count_quarterly = (
            task_type == "quarterly" and task.get("progress_type") == "count"
        )
        if task_type == "weekly":
            current_progress = task.get("completed_count", 0)
            cap = task.get("weekly_target", 1)
            unit_text = f"/ {cap}"
        elif is_count_quarterly:
            current_progress = task.get("progress_count", 0)
            cap = task.get("progress_target", 100)
            unit_text = f"/ {cap}"
        else:
            current_progress = task.get("progress", 0)
            cap = 100
            unit_text = "%"

        prog_label = ctk.CTkLabel(
            win,
            text="Update progress:",
            font=SMALL_FONT,
            text_color=DARK_TEXT,
            fg_color="transparent",
            anchor="w",
        )
        prog_label.pack(fill="x", padx=16, pady=(10, 0))

        prog_row = ctk.CTkFrame(win, fg_color="transparent")
        prog_row.pack(fill="x", padx=16, pady=(2, 0))

        progress_entry = ctk.CTkEntry(
            prog_row,
            width=52,
            fg_color=SAGE_CARD,
            border_color=BORDER_COLOR,
            text_color=DARK_TEXT,
        )
        progress_entry.insert(0, str(current_progress))
        progress_entry.pack(side="left")

        ctk.CTkLabel(
            prog_row,
            text=unit_text,
            font=SMALL_FONT,
            text_color=DARK_TEXT,
            fg_color="transparent",
        ).pack(side="left", padx=(6, 0))

        def _on_update_click(_entry=progress_entry, _task=task, _label=msg_label,
                             _type=task_type, _cap=cap, _is_count_q=is_count_quarterly):
            try:
                new_val = int(_entry.get())
            except ValueError:
                return  # silently ignore non-numeric input
            if _type == "weekly":
                new_val = max(0, min(new_val, _cap))
                _get_store().update_task(_task["id"], completed_count=new_val)
            elif _is_count_q:
                new_val = max(0, min(new_val, _cap))
                new_pct = int(new_val / _cap * 100) if _cap else 0
                _get_store().update_task(_task["id"], progress_count=new_val, progress=new_pct)
            else:
                new_val = max(0, min(new_val, 100))
                _get_store().update_task(_task["id"], progress=new_val)
            # Refresh task from store and update message label in-place (no popup close)
            refreshed = _get_store().get_task(_task["id"])
            if refreshed:
                _label.configure(text=_get_tone_message(refreshed))

        ctk.CTkButton(
            prog_row,
            text="Update",
            fg_color=SAGE_BUTTON,
            hover_color=BUTTON_HOVER,
            text_color=DARK_TEXT,
            corner_radius=10,
            height=30,
            width=70,
            command=_on_update_click,
        ).pack(side="right")

    # 5. Done button — primary action (direct call avoids IPC roundtrip)
    ctk.CTkButton(
        win,
        text="Done!",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=12,
        height=38,
        font=BODY_FONT,
        command=lambda: handle_done(task_id),
    ).pack(fill="x", padx=16, pady=(14, 0))

    # 6. Snooze section — "on my way" framing
    ctk.CTkLabel(
        win,
        text="On my way in...",
        font=SMALL_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
    ).pack(pady=(10, 4))

    snooze_frame = ctk.CTkFrame(win, fg_color="transparent")
    snooze_frame.pack(fill="x", padx=16, pady=(0, 4))

    for i, (label, minutes) in enumerate([("15 min", 15), ("30 min", 30), ("1 hr", 60)]):
        ctk.CTkButton(
            snooze_frame,
            text=label,
            fg_color=SAGE_CARD,
            hover_color=BUTTON_HOVER,
            text_color=DARK_TEXT,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_COLOR,
            height=30,
            font=SMALL_FONT,
            command=lambda m=minutes: handle_snooze(task_id, m),
        ).pack(side="left", expand=True, fill="x", padx=(0 if i == 0 else 4, 0))

    ctk.CTkButton(
        win,
        text="Tomorrow",
        fg_color=SAGE_CARD,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=10,
        border_width=1,
        border_color=BORDER_COLOR,
        height=30,
        font=SMALL_FONT,
        command=lambda: handle_snooze(task_id, _snooze_tomorrow_minutes(task)),
    ).pack(fill="x", padx=16, pady=(4, 12))

    win.after(_NAG_INTERVAL_MS, lambda: _auto_nag(win, msg_label))

    win.deiconify()
    try:
        from AppKit import NSApplication  # noqa: PLC0415
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass
    win.after(100, lambda: (win.lift(), win.focus_force()))
    return win


def _build_rock_report_popup(task: dict) -> ctk.CTkToplevel:
    """Popup variant for Rock Report tasks — shows generated report + copy button."""
    from ui.tk_host import get_root, enqueue  # noqa: PLC0415
    from ui.styles import TITLE_FONT, BODY_FONT, SMALL_FONT  # noqa: PLC0415
    from ui.rock_report import generate_report_text  # noqa: PLC0415

    root = get_root()
    task_id = task["id"]

    x, y = _calc_position()

    win = ctk.CTkToplevel(root)
    win.title("")
    win.geometry(f"360x580+{x}+{y}")
    win.configure(fg_color=SAGE_BG)
    win.resizable(False, True)
    win.attributes("-topmost", True)
    win.protocol("WM_DELETE_WINDOW", lambda: None)

    # Accent strip
    ctk.CTkFrame(win, height=8, fg_color=CAT_PINK, corner_radius=0).pack(fill="x")

    # Header
    ctk.CTkLabel(
        win, text="Rock Report",
        font=TITLE_FONT, text_color=DARK_TEXT, fg_color="transparent",
    ).pack(pady=(10, 0))
    ctk.CTkLabel(
        win, text="Edit below, then copy to Slack.",
        font=SMALL_FONT, text_color=DARK_TEXT, fg_color="transparent",
    ).pack(pady=(2, 6))

    # Report text area
    report_text = generate_report_text(_get_store().get_all_tasks())
    text_box = ctk.CTkTextbox(
        win,
        fg_color=SAGE_CARD,
        text_color=DARK_TEXT,
        border_color=BORDER_COLOR,
        border_width=1,
        wrap="word",
        font=BODY_FONT,
    )
    text_box.pack(fill="both", expand=True, padx=14, pady=(0, 6))
    text_box.insert("1.0", report_text)

    # Copy button
    copy_btn = ctk.CTkButton(
        win,
        text="Copy to Clipboard",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=10,
        height=34,
        font=BODY_FONT,
    )

    def _copy():
        content = text_box.get("1.0", "end-1c")
        win.clipboard_clear()
        win.clipboard_append(content)
        copy_btn.configure(text="Copied!")
        win.after(1500, lambda: copy_btn.configure(text="Copy to Clipboard"))

    copy_btn.configure(command=_copy)
    copy_btn.pack(fill="x", padx=14, pady=(0, 4))

    # Done + snooze row
    action_row = ctk.CTkFrame(win, fg_color="transparent")
    action_row.pack(fill="x", padx=14, pady=(0, 6))

    ctk.CTkButton(
        action_row,
        text="Done",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=10,
        height=30,
        font=BODY_FONT,
        command=lambda: handle_done(task_id),
    ).pack(side="left", expand=True, fill="x", padx=(0, 4))

    for label, minutes in [("15 min", 15), ("1 hr", 60)]:
        ctk.CTkButton(
            action_row,
            text=label,
            fg_color=SAGE_CARD,
            hover_color=BUTTON_HOVER,
            text_color=DARK_TEXT,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_COLOR,
            height=30,
            font=SMALL_FONT,
            command=lambda m=minutes: handle_snooze(task_id, m),
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    win.after(_NAG_INTERVAL_MS, lambda: _auto_nag(win, ctk.CTkLabel(win, text="")))
    win.deiconify()
    try:
        from AppKit import NSApplication  # noqa: PLC0415
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass
    win.after(100, lambda: (win.lift(), win.focus_force()))
    return win
