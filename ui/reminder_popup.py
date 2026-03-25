# ui/reminder_popup.py
# Reminder popup CTkToplevel — separate from main panel.
# Source: Phase 2 Research — Pattern 5; Phase 2 UI-SPEC Component Inventory.
#
# MUST be called from the tkinter child process only (via tk_process._poll).
# All enqueue() calls here route to the main process for store updates + badge changes.
import customtkinter as ctk
from AppKit import NSScreen

from ui.styles import (
    SAGE_BG, CAT_PINK, SAGE_BUTTON, BUTTON_HOVER, DARK_TEXT, BORDER_COLOR, SAGE_CARD,
)

POPUP_W, POPUP_H = 300, 220

_pending_queue: list[str] = []   # task_ids waiting to show
_popup: ctk.CTkToplevel | None = None
_store = None   # Set on first call via _get_store()


def _get_store():
    """Lazily import TaskStore to avoid module-level import issues."""
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
    # Update badge: if queue now empty, clear dot
    if not _pending_queue:
        enqueue("badge", state="idle")
    _show_next()


def handle_snooze(task_id: str, minutes: int) -> None:
    """Called from _poll when 'snooze' IPC arrives. Schedules re-fire and advances queue."""
    from datetime import datetime, timedelta  # noqa: PLC0415
    from ui.tk_host import enqueue  # noqa: PLC0415
    until = datetime.now() + timedelta(minutes=minutes)
    _get_store().update_snooze(task_id, until)
    # Tell scheduler to register the snooze DateTrigger job
    # (Scheduler listens via main-process-side 'schedule_snooze' handling in Plan 04)
    enqueue("schedule_snooze", task_id=task_id, minutes=minutes)
    _close_popup()
    # Badge: stays pending if queue has more items or this task will re-fire
    if not _pending_queue:
        # Still pending because snooze will re-fire — keep dot
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
    message = f"Time to check in on {task_name}."

    x, y = _calc_position()

    win = ctk.CTkToplevel(root)
    win.title("")
    win.geometry(f"{POPUP_W}x{POPUP_H}+{x}+{y}")
    win.configure(fg_color=SAGE_BG)
    win.resizable(False, False)
    win.attributes("-topmost", True)
    # Prevent closing via the window chrome — user must use Done or Snooze
    win.protocol("WM_DELETE_WINDOW", lambda: None)

    # 1. CAT_PINK accent strip at top
    ctk.CTkFrame(win, height=8, fg_color=CAT_PINK, corner_radius=0).pack(fill="x")

    # 2. Task name
    ctk.CTkLabel(
        win,
        text=task_name,
        font=TITLE_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
        wraplength=260,
    ).pack(pady=(16, 0), padx=16)

    # 3. Reminder message
    ctk.CTkLabel(
        win,
        text=message,
        font=BODY_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
        wraplength=260,
    ).pack(pady=(8, 0), padx=16)

    # 4. Button row — Done + Snooze duration picker
    btn_frame = ctk.CTkFrame(win, fg_color="transparent")
    btn_frame.pack(pady=(24, 0))

    ctk.CTkButton(
        btn_frame,
        text="Mark Done",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=12,
        width=120,
        command=lambda: enqueue("done", task_id=task_id),
    ).pack(side="left", padx=(0, 4))

    snooze_var = ctk.StringVar(value="15 min")
    snooze_menu = ctk.CTkOptionMenu(
        btn_frame,
        values=["5 min", "15 min", "30 min", "1 hr"],
        variable=snooze_var,
        fg_color=SAGE_CARD,
        button_color=SAGE_BUTTON,
        button_hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        width=140,
        command=lambda choice: _on_snooze_select(task_id, choice),
    )
    snooze_menu.pack(side="left")

    win.deiconify()
    win.after(100, win.lift)
    return win


_SNOOZE_MINUTES = {"5 min": 5, "15 min": 15, "30 min": 30, "1 hr": 60}


def _on_snooze_select(task_id: str, choice: str) -> None:
    """CTkOptionMenu command — fires when user selects a snooze duration."""
    from ui.tk_host import enqueue  # noqa: PLC0415
    minutes = _SNOOZE_MINUTES.get(choice, 15)
    enqueue("snooze", task_id=task_id, minutes=minutes)
