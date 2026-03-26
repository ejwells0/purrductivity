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

POPUP_W, POPUP_H = 300, 310
POPUP_H_GOAL = 374   # taller popup for weekly/quarterly tasks (adds progress input row)

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
    from ui.tk_host import enqueue  # noqa: PLC0415
    _get_store().mark_done(task_id)
    _close_popup()
    if not _pending_queue:
        enqueue("badge", state="idle")
    _show_next()


def handle_snooze(task_id: str, minutes: int) -> None:
    """Called from _poll when 'snooze' IPC arrives. Schedules re-fire and advances queue."""
    from datetime import datetime, timedelta  # noqa: PLC0415
    from ui.tk_host import enqueue  # noqa: PLC0415
    until = datetime.now() + timedelta(minutes=minutes)
    _get_store().update_snooze(task_id, until)
    enqueue("schedule_snooze", task_id=task_id, minutes=minutes)
    _close_popup()
    if not _pending_queue:
        enqueue("badge", state="pending")
    _show_next()


def _close_popup() -> None:
    global _popup
    if _popup is not None and _popup.winfo_exists():
        _popup.destroy()
    _popup = None


def _show_next() -> None:
    global _popup
    if not _pending_queue:
        return
    task_id = _pending_queue.pop(0)
    task = _get_store().get_task(task_id)
    if task is None:
        _show_next()  # skip deleted tasks
        return
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
    message = _get_tone_message(task) if is_goal else random.choice(_CAT_MESSAGES)

    x, y = _calc_position()

    popup_h = POPUP_H_GOAL if is_goal else POPUP_H
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

    # 4b. Progress input row (goal tasks only)
    if is_goal:
        task_type = task.get("type")
        current_progress = (
            task.get("completed_count", 0) if task_type == "weekly"
            else task.get("progress", 0)
        )
        weekly_target = task.get("weekly_target", 1) if task_type == "weekly" else None
        unit_text = f"/ {weekly_target}" if task_type == "weekly" else "%"

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
                             _type=task_type, _target=weekly_target):
            try:
                new_val = int(_entry.get())
            except ValueError:
                return  # silently ignore non-numeric input
            if _type == "weekly":
                new_val = max(0, min(new_val, _target))
                _get_store().update_task(_task["id"], completed_count=new_val)
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

    # 5. Done button — primary action
    ctk.CTkButton(
        win,
        text="Done!",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=12,
        height=38,
        font=BODY_FONT,
        command=lambda: enqueue("done", task_id=task_id),
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
    snooze_frame.pack(fill="x", padx=16, pady=(0, 10))

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
            command=lambda m=minutes: enqueue("snooze", task_id=task_id, minutes=m),
        ).pack(side="left", expand=True, fill="x", padx=(0 if i == 0 else 4, 0))

    win.deiconify()
    win.after(100, win.lift)
    return win
