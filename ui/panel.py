# ui/panel.py
# Main panel — CTkToplevel with task list and inline creation form.
# Positioned top-right below menu bar.
# MUST be called from the tkinter thread (via enqueue). Never call directly from
# app.py or scheduler.py.
#
# Views:
#   LIST_VIEW — scrollable task list + Add Task button (or empty state)
#   FORM_VIEW — inline task creation form with per-type fields
#
# NOTE: TITLE_FONT, BODY_FONT, SMALL_FONT are NOT imported at module level —
# they are lazy CTkFont objects that require a tk root to exist. Import them
# inside functions only.
import os
import random
from datetime import datetime, date as _date

import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
from AppKit import NSScreen

from ui.styles import (
    SAGE_BG, SAGE_CARD, DARK_TEXT, SAGE_BUTTON, BUTTON_HOVER,
    BORDER_COLOR, CAT_PINK, MUTED_TEXT, DESTRUCTIVE, WORK_ACCENT,
)

PANEL_WIDTH  = 340
PANEL_HEIGHT = 570

_CATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cats")
_CAT_FILES = sorted(
    f for f in os.listdir(_CATS_DIR) if f.lower().endswith(".png")
)

_panel: ctk.CTkToplevel | None = None
_active_tab: str = "personal"
_active_filter: str = "today"   # "all" | "today" | "week" | "month"
_expanded_row: list = []   # at most one expanded row card at a time
_cal_month_offset: int = 0   # months from today for calendar month view

# Lazy store access — populated on first call, mirrors reminder_popup.py pattern
_store = None


def _get_store():
    """Return module-level TaskStore, creating it on first call."""
    global _store
    if _store is None:
        from store import TaskStore  # noqa: PLC0415
        _store = TaskStore()
    return _store


def _hide_panel() -> None:
    """Hide the panel without destroying it."""
    if _panel is not None and _panel.winfo_exists():
        _panel.withdraw()


def _load_cat_image(size: int = 160) -> ctk.CTkImage:
    """Pick a random cat and return a CTkImage scaled to size×size."""
    path = os.path.join(_CATS_DIR, random.choice(_CAT_FILES))
    img = Image.open(path).convert("RGBA")
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def _draw_cats_on_canvas(canvas: tk.Canvas) -> None:
    """Clear and redraw a fresh random set of cats on the strip canvas."""
    canvas.delete("all")
    cat_size  = 44
    y_offsets = [10,  4, 14,  6,  8,  2, 12,  5, 10,  4]
    step = cat_size + 2
    positions = list(range(-20, PANEL_WIDTH + cat_size, step))
    canvas._cat_photos = []
    for i, x in enumerate(positions):
        y = y_offsets[i % len(y_offsets)]
        path = os.path.join(_CATS_DIR, random.choice(_CAT_FILES))
        pil_img = Image.open(path).convert("RGBA").resize((cat_size, cat_size), Image.LANCZOS)
        photo = ImageTk.PhotoImage(pil_img)
        canvas._cat_photos.append(photo)
        canvas.create_image(x, y, image=photo, anchor="nw")


def _add_cat_strip(win: ctk.CTkToplevel) -> tk.Canvas:
    """Add a decorative row of cats at the bottom. Returns the canvas."""
    canvas = tk.Canvas(win, height=58, bg=SAGE_BG, highlightthickness=0, bd=0)
    canvas.pack(fill="x", side="bottom")
    _draw_cats_on_canvas(canvas)
    return canvas


# ── Day-of-week helpers ────────────────────────────────────────────────────────

_DOW_ABBR = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_DOW_NAME = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

# Half-hour time slots for dropdown (6:00 AM to 11:30 PM)
_TIME_SLOTS = [
    "6:00 AM", "6:30 AM", "7:00 AM", "7:30 AM",
    "8:00 AM", "8:30 AM", "9:00 AM", "9:30 AM",
    "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM",
    "12:00 PM", "12:30 PM", "1:00 PM", "1:30 PM",
    "2:00 PM", "2:30 PM", "3:00 PM", "3:30 PM",
    "4:00 PM", "4:30 PM", "5:00 PM", "5:30 PM",
    "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM",
    "8:00 PM", "8:30 PM", "9:00 PM", "9:30 PM",
    "10:00 PM", "10:30 PM", "11:00 PM", "11:30 PM",
]

_DOW_OPTIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _quarter_options(n: int = 8) -> list:
    """Return next n quarter labels starting from current quarter, e.g. ['Q2 2026', ...]."""
    from datetime import date  # noqa: PLC0415
    today = date.today()
    q = (today.month - 1) // 3 + 1
    year = today.year
    result = []
    for _ in range(n):
        result.append(f"Q{q} {year}")
        q += 1
        if q > 4:
            q = 1
            year += 1
    return result


def _parse_dow(val: str) -> int | None:
    """Parse "Mon"/"Tue"/... to 0-6. Returns None on failure."""
    return _DOW_ABBR.get(val.strip().lower()[:3])


def _format_time(hour: int, minute: int) -> str:
    """Convert hour/minute to '9:00 AM' slot string."""
    return datetime(2000, 1, 1, hour, minute).strftime("%-I:%M %p")


def _parse_time(val: str) -> tuple[int, int] | None:
    """Parse '9:00 AM' or '09:00' to (hour, minute). Returns None on failure."""
    val = val.strip()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            dt = datetime.strptime(val, fmt)
            return dt.hour, dt.minute
        except ValueError:
            continue
    return None


def _next_fire_label(task: dict) -> tuple[str, str]:
    """Return (label_text, text_color) describing next fire or snooze state."""
    if task.get("snoozed_until"):
        try:
            from datetime import timedelta  # noqa: PLC0415
            until = datetime.fromisoformat(task["snoozed_until"])
            time_str = until.strftime("%-I:%M %p")
            today = _date.today()
            if until.date() == today:
                return f"Snoozed until {time_str}", CAT_PINK
            elif until.date() == today + timedelta(days=1):
                return f"Snoozed until tomorrow at {time_str}", CAT_PINK
            else:
                day_str = until.strftime("%A")
                return f"Snoozed until {day_str} at {time_str}", CAT_PINK
        except (ValueError, TypeError):
            return "Snoozed", CAT_PINK

    t = task.get("type", "")
    hour = task.get("hour", 9)
    minute = task.get("minute", 0)
    time_str = datetime(2000, 1, 1, hour, minute).strftime("%-I:%M %p")

    if t == "scheduled":
        dow_name = _DOW_NAME.get(task.get("day_of_week", 0), "?")
        return f"Next: {dow_name}", DARK_TEXT
    elif t == "daily":
        return f"Daily at {time_str}", DARK_TEXT
    elif t == "weekly":
        dow_name = _DOW_NAME.get(task.get("day_of_week", 0), "?")
        return f"Every {dow_name} at {time_str}", DARK_TEXT
    elif t == "monthly":
        dom = task.get("day_of_month", "?")
        return f"Monthly on {dom}", DARK_TEXT
    elif t == "quarterly":
        due = task.get("due_quarter", "")
        return f"Due {due}" if due else "Quarterly", DARK_TEXT
    elif t == "one_time":
        due = task.get("due_date", "")
        try:
            d = _date.fromisoformat(due)
            today_d = _date.today()
            delta = (d - today_d).days
            if delta == 0:
                label = "Due today"
            elif delta == 1:
                label = "Due tomorrow"
            elif 2 <= delta <= 6:
                label = f"Due {d.strftime('%A')}"
            elif delta < 0:
                label = f"Was due {d.strftime('%a %-m/%-d')}"
            else:
                label = f"Due {d.strftime('%a %-m/%-d')}"
            return label, DARK_TEXT
        except (ValueError, TypeError):
            return "One-time", DARK_TEXT
    return "", DARK_TEXT


def _badge_colors(task_type: str) -> tuple[str, str]:
    """Return (border_color, text_color) for a type badge."""
    if task_type == "daily":
        return CAT_PINK, CAT_PINK
    return BORDER_COLOR, DARK_TEXT


_BADGE_LABELS = {
    "scheduled": "Recurring", "daily": "Recurring", "weekly": "Recurring",
    "quarterly": "Recurring", "one_time": "One-time", "monthly": "Recurring",
}

def _badge_label(task_type: str) -> str:
    return _BADGE_LABELS.get(task_type, task_type.capitalize())


# ── Filter helpers ────────────────────────────────────────────────────────────

def _fires_today(task: dict, today: _date) -> bool:
    t = task.get("type", "")
    dow = today.weekday()
    start_str = task.get("start_date")
    end_str = task.get("end_date")
    if start_str:
        try:
            if today < _date.fromisoformat(start_str):
                return False
        except (ValueError, TypeError):
            pass
    if end_str:
        try:
            if today > _date.fromisoformat(end_str):
                return False
        except (ValueError, TypeError):
            pass
    if t == "daily":
        return True
    if t in ("scheduled", "weekly"):
        return task.get("day_of_week") == dow
    if t == "monthly":
        return task.get("day_of_month") == today.day
    if t == "quarterly":
        return task.get("check_in_enabled", False) and task.get("check_in_dow") == dow
    if t == "one_time":
        due = task.get("due_date")
        try:
            return _date.fromisoformat(due) == today if due else False
        except (ValueError, TypeError):
            return False
    return False


def _fires_this_week(task: dict, today: _date) -> bool:
    from datetime import timedelta as _td  # noqa: PLC0415
    t = task.get("type", "")
    if t == "daily":
        return True
    if t in ("scheduled", "weekly"):
        dow = task.get("day_of_week")
        if dow is None:
            return False
        week_start = today - _td(days=today.weekday())
        task_date = week_start + _td(days=dow)
        start_str = task.get("start_date")
        if start_str:
            try:
                return task_date >= _date.fromisoformat(start_str)
            except (ValueError, TypeError):
                pass
        return True
    if t == "monthly":
        from datetime import timedelta as _td  # noqa: PLC0415
        dom = task.get("day_of_month")
        if dom is None:
            return False
        week_start = today - _td(days=today.weekday())
        # Check if any date in this week has that day_of_month
        for offset in range(7):
            d = week_start + _td(days=offset)
            if d.day == dom:
                return True
        return False
    if t == "quarterly":
        return task.get("check_in_enabled", False)
    if t == "one_time":
        from datetime import timedelta as _td  # noqa: PLC0415
        due = task.get("due_date")
        try:
            d = _date.fromisoformat(due) if due else None
            if d is None:
                return False
            week_start = today - _td(days=today.weekday())
            return week_start <= d <= week_start + _td(days=6)
        except (ValueError, TypeError):
            return False
    return False


def _done_today(task: dict, today: _date) -> bool:
    last_done = task.get("last_done")
    if not last_done:
        return False
    try:
        return datetime.fromisoformat(last_done).date() == today
    except (ValueError, TypeError):
        return False


def _done_this_week(task: dict, today: _date) -> bool:
    from datetime import timedelta as _td  # noqa: PLC0415
    last_done = task.get("last_done")
    if not last_done:
        return False
    try:
        last_date = datetime.fromisoformat(last_done).date()
        week_start = today - _td(days=today.weekday())  # Monday
        return last_date >= week_start
    except (ValueError, TypeError):
        return False


def _type_group(task: dict) -> int:
    """Return section group: 0=daily, 1=scheduled/monthly/weekly-binary/one_time, 2=goals."""
    t = task.get("type", "")
    if t == "daily":
        return 0
    if t == "monthly":
        return 1
    if t == "quarterly" or (t == "weekly" and task.get("weekly_target", 1) > 1):
        return 2
    return 1


_GROUP_LABELS = {0: "Daily", 1: "Scheduled", 2: "Goals"}


def _refresh_list(parent: ctk.CTkFrame, category: str = "personal") -> None:
    """Route to the correct view based on _active_tab and _active_filter."""
    if category == "calendar":
        _show_cal_month_view(parent)
    elif _active_filter == "week":
        _show_week_view(parent, category)
    else:
        _show_list_view(parent, category)


# ── List View ─────────────────────────────────────────────────────────────────

def _delete_task(task_id: str, parent: ctk.CTkFrame, category: str) -> None:
    """Delete a task from store, cancel its scheduler job, refresh list."""
    from ui.tk_host import send_to_main  # noqa: PLC0415
    _get_store().delete_task(task_id)
    send_to_main("cancel_job", task_id=task_id)
    _refresh_list(parent, category=category)


def _draw_progress_bar(parent: ctk.CTkFrame, fraction: float, fill_color: str,
                       width: int = 200) -> None:
    """Draw a thin read-only progress bar. fraction is 0.0–1.0."""
    bar_bg = ctk.CTkFrame(parent, fg_color=BORDER_COLOR, corner_radius=4,
                          width=width, height=8)
    bar_bg.pack_propagate(False)
    bar_bg.pack(fill="x", pady=(2, 0))
    fill_w = max(4, int(fraction * width))
    bar_fill = ctk.CTkFrame(bar_bg, fg_color=fill_color, corner_radius=4,
                             width=fill_w, height=8)
    bar_fill.pack_propagate(False)
    bar_fill.place(x=0, y=0)


def _pause_task(task_id: str, parent: ctk.CTkFrame, category: str) -> None:
    """Write paused=True to store, cancel APScheduler job, refresh list."""
    from ui.tk_host import send_to_main  # noqa: PLC0415
    _get_store().update_task(task_id, paused=True)
    send_to_main("cancel_job", task_id=task_id)
    _refresh_list(parent, category=category)


def _resume_task(task_id: str, parent: ctk.CTkFrame, category: str) -> None:
    """Write paused=False to store, re-register APScheduler job, refresh list."""
    from ui.tk_host import send_to_main  # noqa: PLC0415
    _get_store().update_task(task_id, paused=False)
    send_to_main("reschedule_task", task_id=task_id)
    _refresh_list(parent, category=category)


def _confirm_delete(task_id: str, task_name: str, parent: ctk.CTkFrame,
                    category: str) -> None:
    """Show CTkToplevel confirm dialog before deleting."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415
    from ui.tk_host import get_root  # noqa: PLC0415
    dlg = ctk.CTkToplevel(get_root())
    dlg.title("")
    dlg.configure(fg_color=SAGE_BG)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)
    ctk.CTkLabel(
        dlg,
        text=f"Delete {task_name}?\nThis can't be undone.",
        font=BODY_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
        wraplength=240,
        justify="center",
    ).pack(pady=(20, 12), padx=16)
    btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
    btn_frame.pack(fill="x", padx=16)
    ctk.CTkButton(
        btn_frame,
        text="Delete",
        fg_color=DESTRUCTIVE,
        hover_color="#A93226",
        text_color="#FFFFFF",
        corner_radius=10,
        height=32,
        command=lambda: [dlg.destroy(), _delete_task(task_id, parent, category)],
    ).pack(side="left", expand=True, fill="x", padx=(0, 4))
    ctk.CTkButton(
        btn_frame,
        text="Cancel",
        fg_color=SAGE_CARD,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=10,
        height=32,
        command=dlg.destroy,
    ).pack(side="left", expand=True, fill="x")
    dlg.deiconify()
    def _center_dlg():
        dlg.update_idletasks()
        pw = _panel.winfo_x() if _panel else dlg.winfo_screenwidth() // 2
        ph = _panel.winfo_y() if _panel else dlg.winfo_screenheight() // 2
        pw_w = _panel.winfo_width() if _panel else 0
        pw_h = _panel.winfo_height() if _panel else 0
        dw, dh = 280, 140
        x = pw + (pw_w - dw) // 2
        y = ph + (pw_h - dh) // 2
        dlg.geometry(f"{dw}x{dh}+{x}+{y}")
        dlg.lift()
    dlg.after(50, _center_dlg)


def _toggle_expand(action_frame: ctk.CTkFrame) -> None:
    """Expand action_frame for the clicked row; collapse any previously open row."""
    global _expanded_row
    if _expanded_row and _expanded_row[0] is not action_frame:
        _expanded_row[0].pack_forget()
        _expanded_row.clear()
    if action_frame.winfo_ismapped():
        action_frame.pack_forget()
        _expanded_row.clear()
    else:
        action_frame.pack(fill="x", padx=8, pady=(0, 6))
        _expanded_row[:] = [action_frame]


def _show_list_view(parent: ctk.CTkFrame, category: str = "personal") -> None:
    """Populate parent with enriched scrollable task list + Add Task button."""
    from ui.styles import BODY_FONT, SMALL_FONT, TITLE_FONT  # noqa: PLC0415
    from store import is_behind  # noqa: PLC0415

    global _expanded_row
    _expanded_row.clear()

    for widget in parent.winfo_children():
        widget.destroy()

    today = _date.today()
    # Use get_all_tasks() — paused tasks must appear (dimmed) so user can resume
    all_tasks = _get_store().get_all_tasks()
    tasks = [t for t in all_tasks if t.get("category", "personal") == category]

    if _active_filter == "today":
        tasks = [t for t in tasks if t.get("paused") or _fires_today(t, today)]
        tasks = [t for t in tasks if t.get("paused") or not _done_today(t, today)]

    # In "all" view: split done-today tasks into a separate collapsible section
    _is_recurring = lambda t: t.get("type") in ("daily", "scheduled", "weekly", "quarterly")
    if _active_filter == "all":
        done_section_tasks = [t for t in tasks if not t.get("paused") and _done_today(t, today)]
        main_tasks         = [t for t in tasks if t not in done_section_tasks]
    else:
        done_section_tasks = []
        main_tasks         = tasks

    if not main_tasks and not done_section_tasks:
        if _active_filter == "today":
            empty_title = "All done for today!"
            empty_body = "Nothing left on your plate.\nYour cat is impressed. 🐾"
        else:
            empty_title = "No tasks yet"
            empty_body = (
                "No work tasks yet.\nHit '+ Add Task' to start."
                if category == "work"
                else "You haven't added anything to chase yet.\nHit '+ Add Task' to start."
            )
        ctk.CTkLabel(
            parent, text=empty_title, font=TITLE_FONT,
            text_color=DARK_TEXT, fg_color="transparent",
        ).pack(pady=(4, 2))
        ctk.CTkLabel(
            parent, text=empty_body, font=BODY_FONT,
            text_color=DARK_TEXT, fg_color="transparent", justify="center",
        ).pack(pady=(2, 16))

    else:
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color=SAGE_BG, width=PANEL_WIDTH - 32,
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=(8, 4))

        def _render_card(target, task, in_done_section: bool = False) -> None:
            is_paused = task.get("paused", False)
            done = _done_today(task, today)
            task_type = task.get("type", "")
            is_goal = task_type in ("weekly", "quarterly")

            # Done-section cards are always greyed out
            card_color = SAGE_BG if (is_paused or in_done_section) else SAGE_CARD
            name_color = MUTED_TEXT if (is_paused or in_done_section) else DARK_TEXT

            row_card = ctk.CTkFrame(target, fg_color=card_color, corner_radius=8)
            row_card.pack(fill="x", padx=0, pady=3)

            info_row = ctk.CTkFrame(row_card, fg_color="transparent")
            info_row.pack(fill="x", padx=8, pady=(8, 4))
            info_row.grid_columnconfigure(0, weight=1)
            info_row.grid_columnconfigure(1, weight=0)

            left = ctk.CTkFrame(info_row, fg_color="transparent")
            left.grid(row=0, column=0, sticky="nsew")

            _inner_widgets: list = []

            _name_lbl = ctk.CTkLabel(
                left, text=task.get("name", "Unnamed"), font=BODY_FONT,
                text_color=name_color, fg_color="transparent", anchor="w",
            )
            _name_lbl.pack(fill="x")
            _inner_widgets.append(_name_lbl)

            # Status subtitle
            if in_done_section:
                if _is_recurring(task):
                    status_text, status_color = "Recurring", MUTED_TEXT
                else:
                    try:
                        done_date = datetime.fromisoformat(task["last_done"]).date()
                        status_text = f"Done {done_date.strftime('%-m/%-d')}"
                    except Exception:
                        status_text = "Done"
                    status_color = MUTED_TEXT
            elif is_paused:
                status_text, status_color = "Paused", MUTED_TEXT
            elif is_goal:
                behind = is_behind(task, today)
                if behind:
                    status_text, status_color = "Behind", DESTRUCTIVE
                else:
                    status_text, status_color = "On Track", SAGE_BUTTON
            else:
                status_text, status_color = _next_fire_label(task)

            if status_text:
                _status_lbl = ctk.CTkLabel(
                    left, text=status_text, font=SMALL_FONT,
                    text_color=status_color, fg_color="transparent", anchor="w",
                )
                _status_lbl.pack(fill="x")
                _inner_widgets.append(_status_lbl)

            # Progress bar for goal tasks (not paused, not in done section)
            if is_goal and not is_paused and not in_done_section:
                if task_type == "weekly":
                    target = task.get("weekly_target", 1)
                    actual = task.get("completed_count", 0)
                    fraction = min(actual / target, 1.0) if target else 0.0
                elif task.get("progress_type") == "count":
                    q_target = task.get("progress_target") or 1
                    q_count = task.get("progress_count", 0)
                    fraction = min(q_count / q_target, 1.0)
                    _count_lbl = ctk.CTkLabel(
                        left, text=f"{q_count} / {q_target}",
                        font=SMALL_FONT, text_color=MUTED_TEXT,
                        fg_color="transparent", anchor="w",
                    )
                    _count_lbl.pack(fill="x")
                    _inner_widgets.append(_count_lbl)
                else:
                    fraction = min(task.get("progress", 0) / 100, 1.0)
                fill_col = DESTRUCTIVE if is_behind(task, today) else SAGE_BUTTON
                _draw_progress_bar(left, fraction, fill_col, width=180)

            border_c, text_c = _badge_colors(task_type)
            badge_frame = ctk.CTkFrame(
                info_row, fg_color=SAGE_CARD, border_width=1,
                border_color=border_c, corner_radius=4,
            )
            badge_frame.grid(row=0, column=1, sticky="ne", padx=(4, 0))
            _badge_lbl = ctk.CTkLabel(
                badge_frame, text=_badge_label(task_type), font=SMALL_FONT,
                text_color=MUTED_TEXT if in_done_section else text_c, fg_color="transparent",
            )
            _badge_lbl.pack(padx=6, pady=2)
            _inner_widgets.append(_badge_lbl)

            action_frame = ctk.CTkFrame(row_card, fg_color="transparent")

            _task_snap = task
            _tid = task["id"]
            _tname = task.get("name", "this task")

            _toggle_cmd = lambda e, af=action_frame: _toggle_expand(af)
            info_row.bind("<Button-1>", _toggle_cmd)
            left.bind("<Button-1>", _toggle_cmd)
            badge_frame.bind("<Button-1>", _toggle_cmd)
            for _w in _inner_widgets:
                _w.bind("<Button-1>", _toggle_cmd)

            btn_row = ctk.CTkFrame(action_frame, fg_color="transparent")
            btn_row.pack(fill="x", pady=(0, 2))

            ctk.CTkButton(
                btn_row, text="✏ Edit", fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
                text_color=DARK_TEXT, corner_radius=8, height=28,
                command=lambda t=_task_snap: _show_edit_view(parent, t, category),
            ).pack(side="left", expand=True, fill="x", padx=(0, 3))

            ctk.CTkButton(
                btn_row, text="Delete", fg_color=SAGE_CARD, hover_color=BUTTON_HOVER,
                text_color=DESTRUCTIVE, corner_radius=8, height=28,
                border_width=1, border_color=DESTRUCTIVE,
                command=lambda tid=_tid, tn=_tname: _confirm_delete(tid, tn, parent, category),
            ).pack(side="left", expand=True, fill="x", padx=(3, 3))

            if is_paused:
                ctk.CTkButton(
                    btn_row, text="Resume", fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
                    text_color=DARK_TEXT, corner_radius=8, height=28,
                    command=lambda tid=_tid: _resume_task(tid, parent, category),
                ).pack(side="left", expand=True, fill="x", padx=(3, 0))
            else:
                ctk.CTkButton(
                    btn_row, text="Pause", fg_color=SAGE_CARD, hover_color=BUTTON_HOVER,
                    text_color=DARK_TEXT, corner_radius=8, height=28,
                    border_width=1, border_color=BORDER_COLOR,
                    command=lambda tid=_tid: _pause_task(tid, parent, category),
                ).pack(side="left", expand=True, fill="x", padx=(3, 0))

        # ── Active tasks ─────────────────────────────────────────────
        _current_group: list[int] = [-1]
        for task in sorted(main_tasks, key=lambda t: (_type_group(t), t.get("name", "").lower())):
            group = _type_group(task)
            if group != _current_group[0]:
                _current_group[0] = group
                ctk.CTkLabel(
                    scroll, text=_GROUP_LABELS[group],
                    font=SMALL_FONT, text_color=MUTED_TEXT,
                    fg_color="transparent", anchor="w",
                ).pack(fill="x", padx=4, pady=(10 if group > 0 else 4, 2))
            _render_card(scroll, task)

        # ── Collapsible Done section (all filter only) ────────────────
        if done_section_tasks:
            _done_exp = [True]

            done_hdr = ctk.CTkFrame(scroll, fg_color="transparent")
            done_hdr.pack(fill="x", padx=4, pady=(12, 0))

            done_container = ctk.CTkFrame(scroll, fg_color="transparent")
            done_container.pack(fill="x")
            for task in sorted(done_section_tasks, key=lambda t: t.get("name", "").lower()):
                _render_card(done_container, task, in_done_section=True)

            def _toggle_done(btn_ref: list) -> None:
                _done_exp[0] = not _done_exp[0]
                if _done_exp[0]:
                    done_container.pack(fill="x")
                    btn_ref[0].configure(text=f"▼  Done  ({len(done_section_tasks)})")
                else:
                    done_container.pack_forget()
                    btn_ref[0].configure(text=f"▶  Done  ({len(done_section_tasks)})")

            _btn_ref: list = [None]
            _btn = ctk.CTkButton(
                done_hdr,
                text=f"▼  Done  ({len(done_section_tasks)})",
                fg_color="transparent", hover_color=SAGE_CARD,
                text_color=MUTED_TEXT, corner_radius=6, height=24,
                font=SMALL_FONT, anchor="w",
                command=lambda: _toggle_done(_btn_ref),
            )
            _btn.pack(side="left")
            _btn_ref[0] = _btn

    # ── Add Task button (always shown) ────────────────────────────────
    ctk.CTkButton(
        parent, text="+ Add Task", fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT, corner_radius=12,
        command=lambda: _show_form_view(parent, category=category),
    ).pack(fill="x", padx=16, pady=(4, 8))


def _render_week_card(scroll: ctk.CTkScrollableFrame, task: dict, done: bool,
                      BODY_FONT, SMALL_FONT) -> None:
    """Render a compact task card in the week calendar view."""
    task_type = task.get("type", "")
    hour = task.get("hour", 9)
    minute = task.get("minute", 0)
    time_str = datetime(2000, 1, 1, hour, minute).strftime("%-I:%M %p")
    name_color = MUTED_TEXT if done else DARK_TEXT
    card_color = SAGE_BG if done else SAGE_CARD

    row = ctk.CTkFrame(scroll, fg_color=card_color, corner_radius=8)
    row.pack(fill="x", padx=0, pady=2)
    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(fill="x", padx=8, pady=(6, 6))
    inner.grid_columnconfigure(0, weight=1)
    inner.grid_columnconfigure(1, weight=0)

    left = ctk.CTkFrame(inner, fg_color="transparent")
    left.grid(row=0, column=0, sticky="nsew")
    name_text = ("✓  " if done else "") + task.get("name", "Unnamed")
    ctk.CTkLabel(
        left, text=name_text, font=BODY_FONT, text_color=name_color,
        fg_color="transparent", anchor="w",
    ).pack(fill="x")
    ctk.CTkLabel(
        left, text=time_str, font=SMALL_FONT, text_color=MUTED_TEXT,
        fg_color="transparent", anchor="w",
    ).pack(fill="x")

    border_c, text_c = _badge_colors(task_type)
    badge = ctk.CTkFrame(inner, fg_color=SAGE_CARD, border_width=1,
                         border_color=border_c, corner_radius=4)
    badge.grid(row=0, column=1, sticky="ne", padx=(4, 0))
    ctk.CTkLabel(
        badge, text=_badge_label(task_type), font=SMALL_FONT,
        text_color=MUTED_TEXT if done else text_c, fg_color="transparent",
    ).pack(padx=6, pady=2)


def _render_week_goal_card(scroll: ctk.CTkScrollableFrame, task: dict,
                           today: _date, BODY_FONT, SMALL_FONT) -> None:
    """Render a goal progress card in the week calendar view."""
    from store import is_behind  # noqa: PLC0415
    task_type = task.get("type", "")

    row = ctk.CTkFrame(scroll, fg_color=SAGE_CARD, corner_radius=8)
    row.pack(fill="x", padx=0, pady=2)
    inner = ctk.CTkFrame(row, fg_color="transparent")
    inner.pack(fill="x", padx=8, pady=(6, 6))

    ctk.CTkLabel(
        inner, text=task.get("name", "Unnamed"), font=BODY_FONT,
        text_color=DARK_TEXT, fg_color="transparent", anchor="w",
    ).pack(fill="x")

    if task_type == "weekly":
        target = task.get("weekly_target", 1)
        actual = task.get("completed_count", 0)
        fraction = min(actual / target, 1.0) if target else 0.0
        status = f"{actual} / {target} this week"
    elif task.get("progress_type") == "count":
        q_target = task.get("progress_target") or 1
        q_count = task.get("progress_count", 0)
        fraction = min(q_count / q_target, 1.0)
        status = f"{q_count} / {q_target}"
    else:
        fraction = min(task.get("progress", 0) / 100, 1.0)
        status = f"{task.get('progress', 0)}%"

    behind = is_behind(task, today)
    fill_col = DESTRUCTIVE if behind else SAGE_BUTTON
    ctk.CTkLabel(
        inner, text=status, font=SMALL_FONT, text_color=fill_col,
        fg_color="transparent", anchor="w",
    ).pack(fill="x")
    _draw_progress_bar(inner, fraction, fill_col, width=PANEL_WIDTH - 80)


def _show_week_view(parent: ctk.CTkFrame, category: str = "personal") -> None:
    """Day-by-day calendar view for the current Mon–Sun week."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415
    from datetime import timedelta as _td  # noqa: PLC0415

    global _expanded_row
    _expanded_row.clear()

    for widget in parent.winfo_children():
        widget.destroy()

    today = _date.today()
    week_start = today - _td(days=today.weekday())  # Monday

    all_tasks = _get_store().get_all_tasks()
    tasks = [t for t in all_tasks
             if t.get("category", "personal") == category and not t.get("paused")]

    scroll = ctk.CTkScrollableFrame(parent, fg_color=SAGE_BG, width=PANEL_WIDTH - 32)
    scroll.pack(fill="both", expand=True, padx=0, pady=(8, 4))

    _DOW_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    any_content = False

    # ── Mon–Sun sections ──────────────────────────────────────────────
    for offset in range(7):
        day_date = week_start + _td(days=offset)
        day_tasks = sorted(
            [t for t in tasks
             if (t.get("type") in ("scheduled", "weekly")
                 and t.get("day_of_week") == offset
                 and _fires_this_week(t, today))
             or (t.get("type") == "one_time"
                 and t.get("due_date") == day_date.isoformat())],
            key=lambda t: (t.get("hour", 9), t.get("minute", 0)),
        )
        if not day_tasks:
            continue

        any_content = True
        is_past = day_date < today
        is_today_day = day_date == today

        date_str = day_date.strftime("%-m/%-d")
        day_label = f"{_DOW_FULL[offset]} {date_str}"
        if is_today_day:
            day_label += " — Today"

        header_color = "#B86478" if is_today_day else (MUTED_TEXT if is_past else DARK_TEXT)
        ctk.CTkLabel(
            scroll, text=day_label, font=SMALL_FONT, text_color=header_color,
            fg_color="transparent", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))

        for task in day_tasks:
            done = _done_this_week(task, today)
            _render_week_card(scroll, task, done, BODY_FONT, SMALL_FONT)

    # ── Every day (daily tasks) ───────────────────────────────────────
    daily_tasks = sorted(
        [t for t in tasks if t.get("type") == "daily"],
        key=lambda t: (t.get("hour", 9), t.get("minute", 0)),
    )
    if daily_tasks:
        any_content = True
        ctk.CTkLabel(
            scroll, text="Every day", font=SMALL_FONT, text_color=DARK_TEXT,
            fg_color="transparent", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))
        for task in daily_tasks:
            done = _done_today(task, today)
            _render_week_card(scroll, task, done, BODY_FONT, SMALL_FONT)

    # ── Goals ─────────────────────────────────────────────────────────
    goal_tasks = sorted(
        [t for t in tasks
         if t.get("type") == "quarterly"
         or (t.get("type") == "weekly" and t.get("weekly_target", 1) > 1)],
        key=lambda t: t.get("name", "").lower(),
    )
    if goal_tasks:
        any_content = True
        ctk.CTkLabel(
            scroll, text="Goals", font=SMALL_FONT, text_color=DARK_TEXT,
            fg_color="transparent", anchor="w",
        ).pack(fill="x", padx=4, pady=(10, 2))
        for task in goal_tasks:
            _render_week_goal_card(scroll, task, today, BODY_FONT, SMALL_FONT)

    if not any_content:
        ctk.CTkLabel(
            scroll, text="Nothing scheduled this week.",
            font=BODY_FONT, text_color=MUTED_TEXT, fg_color="transparent",
        ).pack(pady=20)

    ctk.CTkButton(
        parent, text="+ Add Task", fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT, corner_radius=12,
        command=lambda: _show_form_view(parent, category=category),
    ).pack(fill="x", padx=16, pady=(4, 8))


# ── Calendar Tab Views ────────────────────────────────────────────────────────

def _task_fires_on_date(task: dict, d: _date) -> bool:
    """Return True if task fires on the given calendar date."""
    t = task.get("type", "")
    # Respect start_date and end_date for all recurring types
    start_str = task.get("start_date")
    end_str = task.get("end_date")
    if start_str:
        try:
            if d < _date.fromisoformat(start_str):
                return False
        except (ValueError, TypeError):
            pass
    if end_str:
        try:
            if d > _date.fromisoformat(end_str):
                return False
        except (ValueError, TypeError):
            pass
    if t == "daily":
        return True
    if t in ("scheduled", "weekly"):
        return task.get("day_of_week") == d.weekday()
    if t == "monthly":
        return task.get("day_of_month") == d.day
    if t == "quarterly":
        return task.get("check_in_enabled", False) and task.get("check_in_dow") == d.weekday()
    if t == "one_time":
        due = task.get("due_date")
        try:
            return _date.fromisoformat(due) == d if due else False
        except (ValueError, TypeError):
            return False
    return False


def _cat_color(task: dict) -> str:
    return CAT_PINK if task.get("category", "personal") == "personal" else WORK_ACCENT


def _show_cal_week_view_UNUSED(parent: ctk.CTkFrame) -> None:
    """Unused — calendar tab is month-only."""
    from datetime import timedelta as _td  # noqa: PLC0415

    global _expanded_row
    _expanded_row.clear()

    for widget in parent.winfo_children():
        widget.destroy()

    today = _date.today()
    week_start = today - _td(days=today.weekday())
    all_tasks = [t for t in _get_store().get_all_tasks() if not t.get("paused")]

    HOUR_S   = 6
    HOUR_E   = 22
    SLOT_H   = 44      # px per hour
    TIME_W   = 32      # left time-label column
    SB_W     = 14      # scrollbar width
    COL_W    = (PANEL_WIDTH - TIME_W - SB_W - 2) // 7   # ≈ 42 px
    HEADER_H = 42
    CANVAS_W = TIME_W + 7 * COL_W
    CANVAS_H = (HOUR_E - HOUR_S) * SLOT_H

    DOW = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]

    # ── Fixed day-header canvas ──────────────────────────────────────────
    hdr = tk.Canvas(parent, height=HEADER_H, width=CANVAS_W,
                    bg=SAGE_BG, highlightthickness=0, bd=0)
    hdr.pack(fill="x")

    for i, abbr in enumerate(DOW):
        day_date = week_start + _td(days=i)
        x0, x1 = TIME_W + i * COL_W, TIME_W + (i + 1) * COL_W
        xm = (x0 + x1) // 2
        is_today = day_date == today
        bg  = CAT_PINK  if is_today else SAGE_CARD
        fg  = "#FFFFFF" if is_today else DARK_TEXT
        mfg = "#FFFFFF" if is_today else MUTED_TEXT
        hdr.create_rectangle(x0 + 1, 1, x1 - 1, HEADER_H - 1,
                             fill=bg, outline=BORDER_COLOR)
        hdr.create_text(xm, 13, text=abbr,
                        fill=fg, font=("SF Pro Text", 10, "bold"))
        hdr.create_text(xm, 29, text=day_date.strftime("%-m/%-d"),
                        fill=mfg, font=("SF Pro Text", 9))

    # ── Scrollable time grid ─────────────────────────────────────────────
    grid_outer = tk.Frame(parent, bg=SAGE_BG)
    grid_outer.pack(fill="both", expand=True)

    vbar = tk.Scrollbar(grid_outer, orient="vertical", width=SB_W)
    vbar.pack(side="right", fill="y")

    canvas = tk.Canvas(grid_outer, bg=SAGE_BG, highlightthickness=0, bd=0,
                       width=CANVAS_W, yscrollcommand=vbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    vbar.config(command=canvas.yview)
    canvas.config(scrollregion=(0, 0, CANVAS_W, CANVAS_H))

    # Hour lines + labels
    for h in range(HOUR_S, HOUR_E + 1):
        y = (h - HOUR_S) * SLOT_H
        label = f"{h % 12 or 12}{'a' if h < 12 else 'p'}"
        canvas.create_text(TIME_W - 4, y + 2, text=label, anchor="ne",
                           fill=MUTED_TEXT, font=("SF Pro Text", 10))
        canvas.create_line(TIME_W, y, CANVAS_W, y, fill=BORDER_COLOR, width=1)

    # Vertical column separators
    for i in range(8):
        x = TIME_W + i * COL_W
        canvas.create_line(x, 0, x, CANVAS_H, fill=BORDER_COLOR, width=1)

    # Current-time indicator (today's column only)
    now = datetime.now()
    if HOUR_S <= now.hour < HOUR_E:
        dow_idx = today.weekday()
        cy = (now.hour - HOUR_S) * SLOT_H + (now.minute / 60) * SLOT_H
        cx0 = TIME_W + dow_idx * COL_W
        cx1 = cx0 + COL_W
        canvas.create_oval(cx0 - 4, cy - 4, cx0 + 4, cy + 4,
                           fill=DESTRUCTIVE, outline="")
        canvas.create_line(cx0, cy, cx1, cy, fill=DESTRUCTIVE, width=2)

    # ── Event blocks ─────────────────────────────────────────────────────
    for task in all_tasks:
        ttype = task.get("type", "")
        color = _cat_color(task)
        hour  = task.get("hour", 9)
        minute = task.get("minute", 0)

        if hour < HOUR_S or hour >= HOUR_E:
            continue

        y0 = (hour - HOUR_S) * SLOT_H + round((minute / 60) * SLOT_H) + 2
        y1 = y0 + SLOT_H - 6

        if ttype == "daily":
            cols = range(7)
        elif ttype in ("scheduled", "weekly"):
            dow = task.get("day_of_week")
            if dow is None or not _fires_this_week(task, today):
                continue
            cols = [dow]
        else:
            continue

        name  = task.get("name", "")
        chars = max(1, (COL_W - 6) // 6)   # ~6px per char at size 9

        for col in cols:
            bx0 = TIME_W + col * COL_W + 2
            bx1 = TIME_W + (col + 1) * COL_W - 2
            canvas.create_rectangle(bx0, y0, bx1, y1,
                                    fill=color, outline="", width=0)
            canvas.create_text(bx0 + 3, y0 + (y1 - y0) // 2,
                               text=name[:chars], anchor="w",
                               fill=DARK_TEXT, font=("SF Pro Text", 9))

    # Legend (below the grid so it doesn't eat content space)
    leg = tk.Frame(parent, bg=SAGE_BG)
    leg.pack(fill="x", padx=12, pady=(2, 4))
    tk.Label(leg, text="● Personal", fg=CAT_PINK, bg=SAGE_BG,
             font=("SF Pro Text", 10)).pack(side="left")
    tk.Label(leg, text="    ● Work", fg=WORK_ACCENT, bg=SAGE_BG,
             font=("SF Pro Text", 10)).pack(side="left")

    # Scroll to current hour on open
    if HOUR_S <= now.hour < HOUR_E:
        frac = max(0.0, ((now.hour - HOUR_S - 1) * SLOT_H) / CANVAS_H)
        canvas.after(50, lambda: canvas.yview_moveto(frac))

    canvas.bind("<MouseWheel>",
                lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))


def _show_cal_month_view(parent: ctk.CTkFrame) -> None:
    """Month grid calendar — clickable day cells, prev/next nav."""
    import calendar as _cal  # noqa: PLC0415

    global _cal_month_offset

    for widget in parent.winfo_children():
        widget.destroy()

    today = _date.today()
    month = today.month + _cal_month_offset
    year  = today.year
    while month > 12:
        month -= 12
        year  += 1
    while month < 1:
        month += 12
        year  -= 1

    all_tasks = [t for t in _get_store().get_all_tasks() if not t.get("paused")]
    weeks = _cal.monthcalendar(year, month)

    # Compact layout that fits 6-week months without clipping
    SB_W     = 14
    MARGIN   = 4
    CELL_W   = (PANEL_WIDTH - MARGIN * 2 - SB_W) // 7   # ≈ 44 px
    HDR_H    = 18
    DAY_H    = 14
    PILL_H   = 11
    PILL_GAP = 1
    MAX_PILLS = 2
    CELL_H   = DAY_H + (PILL_H + PILL_GAP) * MAX_PILLS + 5   # = 43
    ROW_H    = CELL_H + 2
    CANVAS_W = CELL_W * 7
    CANVAS_H = HDR_H + len(weeks) * ROW_H

    # ── Navigation ───────────────────────────────────────────────────────
    nav = tk.Frame(parent, bg=SAGE_BG)
    nav.pack(fill="x", padx=10, pady=(6, 3))

    def go_prev():
        global _cal_month_offset
        _cal_month_offset -= 1
        _show_cal_month_view(parent)

    def go_next():
        global _cal_month_offset
        _cal_month_offset += 1
        _show_cal_month_view(parent)

    ctk.CTkButton(nav, text="‹", width=30, height=26, fg_color=SAGE_BUTTON,
                  hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=6,
                  command=go_prev).pack(side="left")
    tk.Label(nav, text=f"{_cal.month_name[month]} {year}",
             fg=DARK_TEXT, bg=SAGE_BG,
             font=("SF Pro Text", 13, "bold")).pack(side="left", expand=True)
    ctk.CTkButton(nav, text="›", width=30, height=26, fg_color=SAGE_BUTTON,
                  hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=6,
                  command=go_next).pack(side="right")

    # ── Legend — outlined chips so pastels are visible on sage green ──────
    leg = tk.Frame(parent, bg=SAGE_BG)
    leg.pack(fill="x", padx=12, pady=(0, 4))
    for label, color in [("Personal", CAT_PINK), ("Work", WORK_ACCENT)]:
        wrap = tk.Frame(leg, bg=SAGE_BG)
        wrap.pack(side="left", padx=(0, 14))
        # Outline frame makes the chip visible on any background
        outline = tk.Frame(wrap, bg=DARK_TEXT, width=16, height=16)
        outline.pack(side="left", pady=2)
        outline.pack_propagate(False)
        chip = tk.Frame(outline, bg=color)
        chip.place(x=1, y=1, width=14, height=14)
        tk.Label(wrap, text=f"  {label}", fg=DARK_TEXT, bg=SAGE_BG,
                 font=("SF Pro Text", 12)).pack(side="left")

    # ── Scrollable canvas wrapper ─────────────────────────────────────────
    outer = tk.Frame(parent, bg=SAGE_BG)
    outer.pack(fill="both", expand=True, padx=MARGIN)

    vbar = tk.Scrollbar(outer, orient="vertical", width=SB_W)
    vbar.pack(side="right", fill="y")

    canvas = tk.Canvas(outer, bg=SAGE_BG, highlightthickness=0, bd=0,
                       width=CANVAS_W, cursor="hand2",
                       yscrollcommand=vbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    vbar.config(command=canvas.yview)
    canvas.config(scrollregion=(0, 0, CANVAS_W, CANVAS_H))
    canvas.bind("<MouseWheel>",
                lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    # Day-of-week header
    for i, lbl in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
        canvas.create_text(i * CELL_W + CELL_W // 2, HDR_H // 2,
                           text=lbl, fill=DARK_TEXT,
                           font=("SF Pro Text", 10, "bold"))

    cell_map: dict[tuple, _date] = {}

    for wi, week in enumerate(weeks):
        for di, day_num in enumerate(week):
            cx0 = di * CELL_W
            cy0 = HDR_H + wi * ROW_H
            cx1 = cx0 + CELL_W

            if day_num == 0:
                continue

            day_date = _date(year, month, day_num)
            cell_map[(wi, di)] = day_date
            is_today = day_date == today

            canvas.create_rectangle(cx0 + 1, cy0 + 1, cx1 - 1, cy0 + CELL_H,
                                    fill=SAGE_CARD, outline=BORDER_COLOR, width=1)

            # Day number — tiny cat icon for today, plain number otherwise
            xm = cx0 + CELL_W // 2
            if is_today:
                _cy = cy0 + DAY_H // 2 + 1
                try:
                    from PIL import ImageFilter  # noqa: PLC0415
                    _cp = os.path.join(_CATS_DIR, _CAT_FILES[0])
                    # Render at 4× then downscale for clean edges
                    _scale = 4
                    _cat_sz = 14
                    _glow_sz = 28
                    _cat_hi = (_cat_sz * _scale, _cat_sz * _scale)
                    _glow_hi = (_glow_sz * _scale, _glow_sz * _scale)
                    _off_hi = ((_glow_sz - _cat_sz) * _scale) // 2
                    _cat_img = Image.open(_cp).convert("RGBA").resize(_cat_hi, Image.LANCZOS)
                    # Glow: blur the alpha at high-res then tint pink
                    _alpha_hi = Image.new("L", _glow_hi, 0)
                    _alpha_hi.paste(_cat_img.split()[3], (_off_hi, _off_hi))
                    _glow_mask = _alpha_hi.filter(ImageFilter.GaussianBlur(radius=10))
                    # Amplify the glow mask so it's bright even after downscale
                    _glow_mask = _glow_mask.point(lambda p: min(255, int(p * 2.5)))
                    _pink = Image.new("RGBA", _glow_hi, (255, 150, 180, 0))
                    _pink.putalpha(_glow_mask)
                    # Composite glow + sharp cat at high-res, then downscale
                    _result_hi = Image.new("RGBA", _glow_hi, (0, 0, 0, 0))
                    _result_hi = Image.alpha_composite(_result_hi, _pink)
                    _result_hi.paste(_cat_img, (_off_hi, _off_hi), _cat_img.split()[3])
                    _result = _result_hi.resize((_glow_sz, _glow_sz), Image.LANCZOS)
                    _ph = ImageTk.PhotoImage(_result)
                    if not hasattr(canvas, "_today_cat"):
                        canvas._today_cat = []
                    canvas._today_cat.append(_ph)
                    canvas.create_image(xm, _cy, image=_ph)
                except Exception:
                    canvas.create_oval(xm - 8, _cy - 8, xm + 8, _cy + 8,
                                       fill=CAT_PINK, outline="")
                num_col = CAT_PINK
            else:
                num_col = DARK_TEXT
            if not is_today:
                canvas.create_text(xm, cy0 + DAY_H // 2 + 1, text=str(day_num),
                                   fill=num_col, font=("SF Pro Text", 10))

            # Event pills — use more saturated colors so they read on SAGE_CARD
            day_tasks = sorted(
                [t for t in all_tasks if _task_fires_on_date(t, day_date)],
                key=lambda t: (t.get("hour", 9), t.get("minute", 0)),
            )
            pill_y = cy0 + DAY_H + 2
            chars  = max(1, (CELL_W - 6) // 6)

            has_overflow = len(day_tasks) > MAX_PILLS
            visible = day_tasks[:MAX_PILLS - 1] if has_overflow else day_tasks[:MAX_PILLS]
            for task in visible:
                pill_col = CAT_PINK if task.get("category", "personal") == "personal" else WORK_ACCENT
                canvas.create_rectangle(cx0 + 2, pill_y, cx1 - 2, pill_y + PILL_H,
                                        fill=pill_col, outline=BORDER_COLOR, width=1)
                canvas.create_text(cx0 + CELL_W // 2, pill_y + PILL_H // 2 - 1,
                                   text=task.get("name", "")[:chars],
                                   fill=DARK_TEXT, font=("SF Pro Text", 7))
                pill_y += PILL_H + PILL_GAP

            if has_overflow:
                remaining = len(day_tasks) - (MAX_PILLS - 1)
                canvas.create_rectangle(cx0 + 2, pill_y, cx1 - 2, pill_y + PILL_H,
                                        fill=SAGE_BG, outline=BORDER_COLOR, width=1)
                canvas.create_text(cx0 + CELL_W // 2, pill_y + PILL_H // 2,
                                   text=f"+ {remaining} more",
                                   fill=MUTED_TEXT, font=("SF Pro Text", 6))

    def on_click(event: tk.Event) -> None:
        cy = canvas.canvasy(event.y)
        if cy < HDR_H:
            return
        di = int(event.x // CELL_W)
        wi = int((cy - HDR_H) // ROW_H)
        day_date = cell_map.get((wi, di))
        if day_date:
            _show_cal_day_view(parent, day_date)

    canvas.bind("<Button-1>", on_click)


def _show_cal_day_view(parent: ctk.CTkFrame, day: _date) -> None:
    """Drill-down: compact task list for a single tapped date."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415

    for widget in parent.winfo_children():
        widget.destroy()

    today = _date.today()
    all_tasks = [t for t in _get_store().get_all_tasks() if not t.get("paused")]
    day_tasks = sorted(
        [t for t in all_tasks if _task_fires_on_date(t, day)],
        key=lambda t: (t.get("hour", 9), t.get("minute", 0)),
    )

    # ── Header ───────────────────────────────────────────────────────────
    hdr = ctk.CTkFrame(parent, fg_color="transparent")
    hdr.pack(fill="x", padx=12, pady=(8, 4))

    ctk.CTkButton(hdr, text="← Calendar", width=90, height=26,
                  fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
                  text_color=DARK_TEXT, corner_radius=6,
                  command=lambda: _show_cal_month_view(parent)).pack(side="left")

    day_label = day.strftime("%a, %b %-d")
    if day == today:
        day_label += "  — Today"
    ctk.CTkLabel(hdr, text=day_label, font=BODY_FONT,
                 text_color="#B86478" if day == today else DARK_TEXT,
                 fg_color="transparent").pack(side="left", padx=(10, 0))

    # ── Task list ────────────────────────────────────────────────────────
    scroll = ctk.CTkScrollableFrame(parent, fg_color=SAGE_BG)
    scroll.pack(fill="both", expand=True, padx=0, pady=(0, 4))

    if not day_tasks:
        ctk.CTkLabel(scroll, text="Nothing scheduled.", font=BODY_FONT,
                     text_color=MUTED_TEXT, fg_color="transparent").pack(pady=20)
        return

    personal = [t for t in day_tasks if t.get("category", "personal") == "personal"]
    work     = [t for t in day_tasks if t.get("category", "personal") == "work"]

    _STRIPE = {"personal": CAT_PINK, "work": WORK_ACCENT}

    for section_tasks, cat_key, section_label in [
        (personal, "personal", "Personal"),
        (work,     "work",     "Work"),
    ]:
        if not section_tasks:
            continue

        stripe_col = _STRIPE[cat_key]

        # Section heading with colored chip
        sh = tk.Frame(scroll, bg=SAGE_BG)
        sh.pack(fill="x", padx=6, pady=(8, 2))
        tk.Frame(sh, bg=stripe_col, width=12, height=12).pack(side="left", pady=2)
        tk.Label(sh, text=f"  {section_label}", fg=DARK_TEXT, bg=SAGE_BG,
                 font=("SF Pro Text", 12, "bold")).pack(side="left")

        for task in section_tasks:
            # tk.Frame avoids CTkFrame's expand behaviour inside CTkScrollableFrame
            card = tk.Frame(scroll, bg=SAGE_CARD, bd=0)
            card.pack(fill="x", padx=2, pady=2)

            tk.Frame(card, bg=stripe_col, width=5).pack(side="left", fill="y")

            hour, minute = task.get("hour", 9), task.get("minute", 0)
            time_str = datetime(2000, 1, 1, hour, minute).strftime("%-I:%M %p")

            inner = tk.Frame(card, bg=SAGE_CARD)
            inner.pack(side="left", padx=8, pady=6)

            tk.Label(inner, text=task.get("name", "Unnamed"),
                     font=BODY_FONT, fg=DARK_TEXT, bg=SAGE_CARD,
                     anchor="w").pack(anchor="w")
            tk.Label(inner, text=time_str,
                     font=SMALL_FONT, fg=MUTED_TEXT, bg=SAGE_CARD,
                     anchor="w").pack(anchor="w")


# ── Form View ─────────────────────────────────────────────────────────────────

def _render_fields(field_frame: ctk.CTkFrame,
                   prefill: dict | None = None,
                   category: str = "personal") -> dict:
    """Populate field_frame with the unified task creation/edit form.

    Returns dict with keys: name, start_date, recurring, frequency, day_of_week_var,
    end_date, end_date_enabled, time, notes, is_rock_report (work only).
    All prior children of field_frame are destroyed before rendering.
    If prefill is provided, widgets are pre-populated with existing task values.
    """
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415
    from datetime import date  # noqa: PLC0415

    for widget in field_frame.winfo_children():
        widget.destroy()

    fields: dict = {}
    p = prefill or {}
    today_str = date.today().isoformat()
    start_date_str = p.get("start_date", today_str)

    def _label(text: str) -> None:
        ctk.CTkLabel(
            field_frame, text=text, font=SMALL_FONT, text_color=DARK_TEXT,
            fg_color="transparent", anchor="w",
        ).pack(fill="x", padx=0, pady=(6, 1))

    def _add_entry(label_text: str, key: str, placeholder: str = "",
                   initial: str = "") -> ctk.CTkEntry:
        _label(label_text)
        entry = ctk.CTkEntry(
            field_frame, fg_color=SAGE_CARD, border_color=BORDER_COLOR,
            text_color=DARK_TEXT, font=BODY_FONT, placeholder_text=placeholder,
        )
        entry.pack(fill="x", padx=0, pady=(0, 2))
        if initial:
            entry.insert(0, initial)
        fields[key] = entry
        return entry

    def _add_time_combo(label_text: str, key: str, default: str) -> ctk.CTkComboBox:
        """Time picker: dropdown for common slots, but also accepts typed input (e.g. 22:33)."""
        _label(label_text)
        combo = ctk.CTkComboBox(
            field_frame, values=_TIME_SLOTS,
            fg_color=SAGE_CARD, border_color=BORDER_COLOR,
            button_color=SAGE_BUTTON, button_hover_color=BUTTON_HOVER,
            text_color=DARK_TEXT, font=BODY_FONT,
        )
        combo.set(default)
        combo.pack(fill="x", padx=0, pady=(0, 2))
        fields[key] = combo  # CTkComboBox.get() works the same as StringVar.get()
        return combo

    # ── Task name ────────────────────────────────────────────────────────
    _add_entry("Task name", "name", initial=p.get("name", ""))

    # ── Date: editable entry + calendar picker ───────────────────────────
    _label("Date")
    _date_row = ctk.CTkFrame(field_frame, fg_color="transparent")
    _date_row.pack(fill="x", pady=(0, 2))
    _date_var = ctk.StringVar(value=start_date_str)
    _date_entry = ctk.CTkEntry(
        _date_row, textvariable=_date_var, font=BODY_FONT, text_color=DARK_TEXT,
        fg_color=SAGE_CARD, border_color=BORDER_COLOR,
    )
    _date_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

    def _open_date_picker() -> None:
        import calendar as _cal  # noqa: PLC0415
        from datetime import timedelta as _td  # noqa: PLC0415

        try:
            current = _date.fromisoformat(_date_var.get().strip())
        except (ValueError, TypeError):
            current = _date.today()

        _picker_offset = [0]  # month offset from current's month

        picker = ctk.CTkToplevel(field_frame)
        picker.title("")
        picker.resizable(False, False)
        picker.attributes("-topmost", True)
        picker.configure(fg_color=SAGE_BG)

        # Size: 7 cols × 34px wide, 6 rows × 26px tall + nav + padding
        _CAL_W, _CAL_H = 7 * 34 + 12, 6 * 26 + 56
        # Position just below the date entry field
        _entry_x = _date_entry.winfo_rootx()
        _entry_y = _date_entry.winfo_rooty() + _date_entry.winfo_height() + 2
        picker.geometry(f"{_CAL_W}x{_CAL_H}+{_entry_x}+{_entry_y}")

        cal_frame = ctk.CTkFrame(picker, fg_color=SAGE_BG)
        cal_frame.pack(fill="both", expand=True, padx=6, pady=6)

        def _draw_picker() -> None:
            for w in cal_frame.winfo_children():
                w.destroy()

            base = _date(current.year, current.month, 1)
            mo = base.month + _picker_offset[0]
            yr = base.year
            while mo > 12:
                mo -= 12; yr += 1
            while mo < 1:
                mo += 12; yr -= 1

            nav = tk.Frame(cal_frame, bg=SAGE_BG)
            nav.pack(fill="x")
            ctk.CTkButton(nav, text="‹", width=26, height=22, fg_color=SAGE_BUTTON,
                          hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=4,
                          command=lambda: [_picker_offset.__setitem__(0, _picker_offset[0] - 1), _draw_picker()]
                          ).pack(side="left")
            tk.Label(nav, text=f"{_cal.month_name[mo]} {yr}", fg=DARK_TEXT, bg=SAGE_BG,
                     font=("SF Pro Text", 11, "bold")).pack(side="left", expand=True)
            ctk.CTkButton(nav, text="›", width=26, height=22, fg_color=SAGE_BUTTON,
                          hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=4,
                          command=lambda: [_picker_offset.__setitem__(0, _picker_offset[0] + 1), _draw_picker()]
                          ).pack(side="right")

            CELL = 34
            weeks = _cal.monthcalendar(yr, mo)
            canvas = tk.Canvas(cal_frame, bg=SAGE_BG, highlightthickness=0,
                               width=CELL * 7, height=20 + len(weeks) * 26)
            canvas.pack(pady=(2, 0))

            for i, h in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
                canvas.create_text(i * CELL + CELL // 2, 10, text=h, fill=MUTED_TEXT,
                                   font=("SF Pro Text", 9, "bold"))
            today_d = _date.today()
            for wi, week in enumerate(weeks):
                for di, dn in enumerate(week):
                    if dn == 0:
                        continue
                    d = _date(yr, mo, dn)
                    cx0, cy0 = di * CELL, 20 + wi * 26
                    is_sel = (d == _date.fromisoformat(_date_var.get()) if _date_var.get() else False)
                    is_today_d = d == today_d
                    bg = "#EE9AB8" if is_sel else ("#FFE0EC" if is_today_d else SAGE_CARD)
                    canvas.create_rectangle(cx0 + 1, cy0 + 1, cx0 + CELL - 1, cy0 + 23,
                                            fill=bg, outline="")
                    canvas.create_text(cx0 + CELL // 2, cy0 + 12, text=str(dn),
                                       fill=DARK_TEXT, font=("SF Pro Text", 10))

            def _on_pick(event) -> None:
                di = int(event.x // CELL)
                wi = int((event.y - 20) // 26)
                if wi < 0 or wi >= len(weeks):
                    return
                dn = weeks[wi][di] if 0 <= di < 7 else 0
                if dn == 0:
                    return
                picked = _date(yr, mo, dn)
                _date_var.set(picked.isoformat())
                picker.destroy()

            canvas.bind("<Button-1>", _on_pick)

        _draw_picker()
        picker.after(10, lambda: picker.focus_force())

    ctk.CTkButton(
        _date_row, text="📅", width=32, height=32, fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=6,
        command=_open_date_picker,
    ).pack(side="left")
    fields["start_date"] = _date_var

    # ── Recurring checkbox + conditional fields ───────────────────────────
    _prefill_type = p.get("type", "")
    _is_recurring_prefill = _prefill_type in {"daily", "scheduled", "weekly", "quarterly", "monthly"}
    recurring_var = ctk.BooleanVar(value=_is_recurring_prefill)

    # Determine prefill frequency
    if _prefill_type == "daily":
        _prefill_freq = "Daily"
    elif _prefill_type in ("scheduled", "weekly", "quarterly"):
        _prefill_freq = "Weekly"
    elif _prefill_type == "monthly":
        _prefill_freq = "Monthly"
    else:
        _prefill_freq = "Daily"

    freq_var = ctk.StringVar(value=_prefill_freq)

    _prefill_dow = _DOW_NAME.get(p.get("day_of_week", 0), "Mon")
    day_of_week_var = ctk.StringVar(value=_prefill_dow)

    _prefill_end_date = p.get("end_date", "")
    end_date_var = ctk.StringVar(value=_prefill_end_date)
    end_date_enabled_var = ctk.BooleanVar(value=bool(_prefill_end_date))

    fields["recurring"] = recurring_var
    fields["frequency"] = freq_var
    fields["day_of_week_var"] = day_of_week_var
    fields["end_date"] = end_date_var
    fields["end_date_enabled"] = end_date_enabled_var

    # Widget-list holders for show/hide
    _recurring_widgets: list = []
    _dow_widgets: list = []
    _end_date_widgets: list = []

    _label("Recurring?")
    recurring_cb = ctk.CTkCheckBox(
        field_frame, text="", variable=recurring_var,
        fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
        checkmark_color=DARK_TEXT, border_color=BORDER_COLOR,
    )
    recurring_cb.pack(anchor="w", padx=0, pady=(0, 2))

    def _show_dow_row() -> None:
        if not _dow_widgets:
            lbl = ctk.CTkLabel(
                field_frame, text="Day of week", font=SMALL_FONT,
                text_color=DARK_TEXT, fg_color="transparent", anchor="w",
            )
            lbl.pack(fill="x", padx=0, pady=(6, 1))
            m = ctk.CTkOptionMenu(
                field_frame, values=_DOW_OPTIONS, variable=day_of_week_var,
                fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                font=BODY_FONT,
            )
            m.pack(fill="x", padx=0, pady=(0, 2))
            _dow_widgets.extend([lbl, m])

    def _hide_dow_row() -> None:
        for w in _dow_widgets:
            w.destroy()
        _dow_widgets.clear()

    def _show_end_date_fields() -> None:
        if not _end_date_widgets:
            lbl = ctk.CTkLabel(
                field_frame, text="End date", font=SMALL_FONT,
                text_color=DARK_TEXT, fg_color="transparent", anchor="w",
            )
            lbl.pack(fill="x", padx=0, pady=(6, 1))
            ed_row = ctk.CTkFrame(field_frame, fg_color="transparent")
            ed_row.pack(fill="x", pady=(0, 2))
            ed_entry = ctk.CTkEntry(
                ed_row, textvariable=end_date_var, font=BODY_FONT,
                text_color=DARK_TEXT, fg_color=SAGE_CARD, border_color=BORDER_COLOR,
            )
            ed_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

            def _open_end_date_picker() -> None:
                import calendar as _cal2  # noqa: PLC0415
                from datetime import timedelta as _td2  # noqa: PLC0415

                try:
                    current2 = _date.fromisoformat(end_date_var.get().strip())
                except (ValueError, TypeError):
                    current2 = _date.today()

                _ep_offset = [0]

                ep = ctk.CTkToplevel(field_frame)
                ep.title("")
                ep.resizable(False, False)
                ep.attributes("-topmost", True)
                ep.configure(fg_color=SAGE_BG)

                _CAL_W2, _CAL_H2 = 7 * 34 + 12, 6 * 26 + 56
                _ex = ed_entry.winfo_rootx()
                _ey = ed_entry.winfo_rooty() + ed_entry.winfo_height() + 2
                ep.geometry(f"{_CAL_W2}x{_CAL_H2}+{_ex}+{_ey}")

                ep_frame = ctk.CTkFrame(ep, fg_color=SAGE_BG)
                ep_frame.pack(fill="both", expand=True, padx=6, pady=6)

                def _draw_ep() -> None:
                    for w2 in ep_frame.winfo_children():
                        w2.destroy()

                    base2 = _date(current2.year, current2.month, 1)
                    mo2 = base2.month + _ep_offset[0]
                    yr2 = base2.year
                    while mo2 > 12:
                        mo2 -= 12; yr2 += 1
                    while mo2 < 1:
                        mo2 += 12; yr2 -= 1

                    nav2 = tk.Frame(ep_frame, bg=SAGE_BG)
                    nav2.pack(fill="x")
                    ctk.CTkButton(nav2, text="‹", width=26, height=22, fg_color=SAGE_BUTTON,
                                  hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=4,
                                  command=lambda: [_ep_offset.__setitem__(0, _ep_offset[0] - 1), _draw_ep()]
                                  ).pack(side="left")
                    tk.Label(nav2, text=f"{_cal2.month_name[mo2]} {yr2}", fg=DARK_TEXT, bg=SAGE_BG,
                             font=("SF Pro Text", 11, "bold")).pack(side="left", expand=True)
                    ctk.CTkButton(nav2, text="›", width=26, height=22, fg_color=SAGE_BUTTON,
                                  hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=4,
                                  command=lambda: [_ep_offset.__setitem__(0, _ep_offset[0] + 1), _draw_ep()]
                                  ).pack(side="right")

                    CELL2 = 34
                    weeks2 = _cal2.monthcalendar(yr2, mo2)
                    canvas2 = tk.Canvas(ep_frame, bg=SAGE_BG, highlightthickness=0,
                                        width=CELL2 * 7, height=20 + len(weeks2) * 26)
                    canvas2.pack(pady=(2, 0))

                    for i2, h2 in enumerate(["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]):
                        canvas2.create_text(i2 * CELL2 + CELL2 // 2, 10, text=h2, fill=MUTED_TEXT,
                                            font=("SF Pro Text", 9, "bold"))
                    today_d2 = _date.today()
                    for wi2, week2 in enumerate(weeks2):
                        for di2, dn2 in enumerate(week2):
                            if dn2 == 0:
                                continue
                            d2 = _date(yr2, mo2, dn2)
                            cx2, cy2 = di2 * CELL2, 20 + wi2 * 26
                            is_sel2 = (d2 == _date.fromisoformat(end_date_var.get()) if end_date_var.get() else False)
                            is_today_d2 = d2 == today_d2
                            bg2 = "#EE9AB8" if is_sel2 else ("#FFE0EC" if is_today_d2 else SAGE_CARD)
                            canvas2.create_rectangle(cx2 + 1, cy2 + 1, cx2 + CELL2 - 1, cy2 + 23,
                                                     fill=bg2, outline="")
                            canvas2.create_text(cx2 + CELL2 // 2, cy2 + 12, text=str(dn2),
                                                fill=DARK_TEXT, font=("SF Pro Text", 10))

                    def _on_pick2(event2) -> None:
                        di2 = int(event2.x // CELL2)
                        wi2 = int((event2.y - 20) // 26)
                        if wi2 < 0 or wi2 >= len(weeks2):
                            return
                        dn2 = weeks2[wi2][di2] if 0 <= di2 < 7 else 0
                        if dn2 == 0:
                            return
                        picked2 = _date(yr2, mo2, dn2)
                        end_date_var.set(picked2.isoformat())
                        ep.destroy()

                    canvas2.bind("<Button-1>", _on_pick2)

                _draw_ep()
                ep.after(10, lambda: ep.focus_force())

            ctk.CTkButton(
                ed_row, text="📅", width=32, height=32, fg_color=SAGE_BUTTON,
                hover_color=BUTTON_HOVER, text_color=DARK_TEXT, corner_radius=6,
                command=_open_end_date_picker,
            ).pack(side="left")
            _end_date_widgets.extend([lbl, ed_row])

    def _hide_end_date_fields() -> None:
        for w in _end_date_widgets:
            w.destroy()
        _end_date_widgets.clear()
        end_date_var.set("")

    def _on_freq_change(freq: str) -> None:
        if freq == "Weekly":
            _show_dow_row()
        else:
            _hide_dow_row()

    def _show_recurring_section() -> None:
        if _recurring_widgets:
            return
        # Frequency label + menu
        lbl_freq = ctk.CTkLabel(
            field_frame, text="Frequency", font=SMALL_FONT,
            text_color=DARK_TEXT, fg_color="transparent", anchor="w",
        )
        lbl_freq.pack(fill="x", padx=0, pady=(6, 1))
        freq_menu = ctk.CTkOptionMenu(
            field_frame, values=["Daily", "Weekly", "Monthly"],
            variable=freq_var,
            fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
            button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
            font=BODY_FONT,
            command=_on_freq_change,
        )
        freq_menu.pack(fill="x", padx=0, pady=(0, 2))
        _recurring_widgets.extend([lbl_freq, freq_menu])

        # Show day-of-week row if currently Weekly
        if freq_var.get() == "Weekly":
            _show_dow_row()

        # End date checkbox
        lbl_end = ctk.CTkLabel(
            field_frame, text="End date?", font=SMALL_FONT,
            text_color=DARK_TEXT, fg_color="transparent", anchor="w",
        )
        lbl_end.pack(fill="x", padx=0, pady=(6, 1))
        end_cb = ctk.CTkCheckBox(
            field_frame, text="", variable=end_date_enabled_var,
            fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
            checkmark_color=DARK_TEXT, border_color=BORDER_COLOR,
            command=lambda: _show_end_date_fields() if end_date_enabled_var.get() else _hide_end_date_fields(),
        )
        end_cb.pack(anchor="w", padx=0, pady=(0, 2))
        _recurring_widgets.extend([lbl_end, end_cb])

        # Pre-show end date fields if enabled
        if end_date_enabled_var.get():
            _show_end_date_fields()

    def _hide_recurring_section() -> None:
        _hide_dow_row()
        _hide_end_date_fields()
        for w in _recurring_widgets:
            w.destroy()
        _recurring_widgets.clear()

    def _on_recurring_change() -> None:
        if recurring_var.get():
            _show_recurring_section()
        else:
            _hide_recurring_section()

    recurring_cb.configure(command=_on_recurring_change)

    # Pre-show recurring section if task is already recurring
    if _is_recurring_prefill:
        _show_recurring_section()

    # ── Reminder time (always shown) ─────────────────────────────────────
    time_default = _format_time(p.get("hour", 9), p.get("minute", 0)) if p else "9:00 AM"
    _add_time_combo("Reminder time", "time", time_default)

    # ── Notes ────────────────────────────────────────────────────────────
    _add_entry("Notes (optional)", "notes", initial=p.get("notes", ""))

    # ── Is Rock? (work tasks only) ───────────────────────────────────────
    is_rock_var = ctk.BooleanVar(value=bool(p.get("is_rock", False)) if p else False)
    is_rock_report_var = ctk.BooleanVar(value=bool(p.get("is_rock_report", False)) if p else False)
    if category == "work":
        _label("Is Rock?")
        ctk.CTkCheckBox(
            field_frame, text="Include in weekly Rock Report",
            variable=is_rock_var,
            fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
            checkmark_color=DARK_TEXT, border_color=BORDER_COLOR,
            font=SMALL_FONT,
        ).pack(anchor="w", padx=0, pady=(0, 2))
        ctk.CTkCheckBox(
            field_frame, text="Show Rock Report in popup",
            variable=is_rock_report_var,
            fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
            checkmark_color=DARK_TEXT, border_color=BORDER_COLOR,
            font=SMALL_FONT,
        ).pack(anchor="w", padx=0, pady=(0, 2))
    fields["is_rock"] = is_rock_var
    fields["is_rock_report"] = is_rock_report_var

    return fields


def _show_error(parent: ctk.CTkFrame, message: str) -> None:
    """Show a temporary error label in the parent frame."""
    from ui.styles import SMALL_FONT  # noqa: PLC0415
    from ui.styles import DESTRUCTIVE  # noqa: PLC0415
    lbl = ctk.CTkLabel(
        parent,
        text=message,
        font=SMALL_FONT,
        text_color=DESTRUCTIVE,
        fg_color="transparent",
        anchor="w",
    )
    lbl.pack(fill="x", padx=0, pady=(2, 0))


def _save_task(parent: ctk.CTkFrame, fields: dict,
               error_frame: ctk.CTkFrame, category: str = "personal") -> None:
    """Validate fields, call store.add_task(), switch back to list view on success."""
    # Clear prior error messages
    for widget in error_frame.winfo_children():
        widget.destroy()

    name = fields.get("name", None)
    name_val = name.get().strip() if name else ""
    if not name_val:
        _show_error(error_frame, "This field is required.")
        return

    start_date_raw = fields.get("start_date", None)
    if isinstance(start_date_raw, str):
        start_date_str = start_date_raw
    elif start_date_raw is not None:
        start_date_str = start_date_raw.get().strip() or datetime.now().date().isoformat()
    else:
        start_date_str = datetime.now().date().isoformat()

    notes_entry = fields.get("notes", None)
    notes_val = notes_entry.get().strip() if notes_entry else ""

    hour, minute = 9, 0
    if "time" in fields:
        time_str = fields["time"].get()
        parsed = _parse_time(time_str) if time_str else None
        if parsed is None and time_str:
            _show_error(error_frame, "Enter a valid time (e.g. 9:00 AM).")
            return
        if parsed:
            hour, minute = parsed

    is_recurring = fields["recurring"].get() if "recurring" in fields else False
    freq = fields["frequency"].get() if "frequency" in fields else "Daily"
    is_rock = bool(fields["is_rock"].get()) if "is_rock" in fields else False
    is_rock_report = bool(fields["is_rock_report"].get()) if "is_rock_report" in fields else False

    # Determine end_date_str
    end_date_str = ""
    if is_recurring and fields.get("end_date_enabled") and fields["end_date_enabled"].get():
        end_date_str = fields["end_date"].get().strip() if fields.get("end_date") else ""

    from ui.tk_host import send_to_main  # noqa: PLC0415

    store = _get_store()
    task_id: str | None = None

    if not is_recurring:
        task_id = store.add_task(
            type="one_time",
            name=name_val,
            due_date=start_date_str,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            notes=notes_val,
            category=category,
            is_rock=is_rock,
            is_rock_report=is_rock_report,
        )

    elif freq == "Daily":
        task_id = store.add_task(
            type="daily",
            name=name_val,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            end_date=end_date_str,
            notes=notes_val,
            category=category,
            is_rock=is_rock,
            is_rock_report=is_rock_report,
        )

    elif freq == "Weekly":
        dow_var = fields.get("day_of_week_var")
        dow = _parse_dow(dow_var.get() if dow_var else "Mon")
        if dow is None:
            _show_error(error_frame, "Enter a valid day (e.g. Mon, Tue, Wed).")
            return
        task_id = store.add_task(
            type="scheduled",
            name=name_val,
            day_of_week=dow,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            end_date=end_date_str,
            notes=notes_val,
            category=category,
            is_rock=is_rock,
            is_rock_report=is_rock_report,
        )

    elif freq == "Monthly":
        try:
            from datetime import date as _d  # noqa: PLC0415
            day_of_month = _d.fromisoformat(start_date_str).day
        except (ValueError, TypeError):
            day_of_month = 1
        task_id = store.add_task(
            type="monthly",
            name=name_val,
            day_of_month=day_of_month,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            end_date=end_date_str,
            notes=notes_val,
            category=category,
        )

    # Register the new task with the scheduler immediately
    if task_id:
        send_to_main("reschedule_task", task_id=task_id)

    # Success — return to list view
    _refresh_list(parent, category=category)


def _update_task(parent: ctk.CTkFrame, task_id: str, fields: dict,
                 error_frame: ctk.CTkFrame,
                 category: str = "personal") -> None:
    """Validate fields, write updates to store, reschedule job, return to list."""
    from ui.tk_host import send_to_main  # noqa: PLC0415

    for widget in error_frame.winfo_children():
        widget.destroy()

    name = fields.get("name")
    name_val = name.get().strip() if name else ""
    if not name_val:
        _show_error(error_frame, "This field is required.")
        return

    start_date_raw = fields.get("start_date")
    if isinstance(start_date_raw, str):
        start_date_str = start_date_raw
    elif start_date_raw is not None:
        start_date_str = start_date_raw.get().strip() or datetime.now().date().isoformat()
    else:
        start_date_str = datetime.now().date().isoformat()

    notes_entry = fields.get("notes")
    notes_val = notes_entry.get().strip() if notes_entry else ""

    hour, minute = 9, 0
    if "time" in fields:
        time_str = fields["time"].get()
        parsed = _parse_time(time_str) if time_str else None
        if parsed is None and time_str:
            _show_error(error_frame, "Enter a valid time (e.g. 9:00 AM).")
            return
        if parsed:
            hour, minute = parsed

    is_recurring = fields["recurring"].get() if "recurring" in fields else False
    freq = fields["frequency"].get() if "frequency" in fields else "Daily"
    is_rock = bool(fields["is_rock"].get()) if "is_rock" in fields else False
    is_rock_report = bool(fields["is_rock_report"].get()) if "is_rock_report" in fields else False

    end_date_str = ""
    if is_recurring and fields.get("end_date_enabled") and fields["end_date_enabled"].get():
        end_date_str = fields["end_date"].get().strip() if fields.get("end_date") else ""

    store = _get_store()
    updates: dict = {"name": name_val, "notes": notes_val,
                     "start_date": start_date_str, "category": category,
                     "is_rock": is_rock, "is_rock_report": is_rock_report}

    if not is_recurring:
        updates.update({
            "type": "one_time",
            "due_date": start_date_str,
            "hour": hour,
            "minute": minute,
        })

    elif freq == "Daily":
        updates.update({
            "type": "daily",
            "hour": hour,
            "minute": minute,
            "end_date": end_date_str,
        })

    elif freq == "Weekly":
        dow_var = fields.get("day_of_week_var")
        dow = _parse_dow(dow_var.get() if dow_var else "Mon")
        if dow is None:
            _show_error(error_frame, "Enter a valid day (e.g. Mon, Tue, Wed).")
            return
        updates.update({
            "type": "scheduled",
            "day_of_week": dow,
            "hour": hour,
            "minute": minute,
            "end_date": end_date_str,
        })

    elif freq == "Monthly":
        try:
            from datetime import date as _d  # noqa: PLC0415
            day_of_month = _d.fromisoformat(start_date_str).day
        except (ValueError, TypeError):
            day_of_month = 1
        updates.update({
            "type": "monthly",
            "day_of_month": day_of_month,
            "hour": hour,
            "minute": minute,
            "end_date": end_date_str,
        })

    store.update_task(task_id, **updates)
    send_to_main("reschedule_task", task_id=task_id)
    _refresh_list(parent, category=category)


def _show_edit_view(parent: ctk.CTkFrame, task: dict, category: str) -> None:
    """Replace parent content with the edit form pre-populated from task."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415

    for widget in parent.winfo_children():
        widget.destroy()

    scroll = ctk.CTkScrollableFrame(parent, fg_color=SAGE_BG, width=PANEL_WIDTH - 32)
    scroll.pack(fill="both", expand=True, padx=0, pady=(2, 0))

    field_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    field_frame.pack(fill="x", padx=16, pady=0)

    error_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    error_frame.pack(fill="x", padx=16, pady=0)

    fields = _render_fields(field_frame, prefill=task, category=category)

    btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
    btn_frame.pack(fill="x", padx=16, pady=(4, 8))

    task_id = task["id"]
    ctk.CTkButton(
        btn_frame,
        text="Save Changes",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=12,
        command=lambda: _update_task(parent, task_id, fields, error_frame, category),
    ).pack(fill="x", pady=(0, 4))

    ctk.CTkButton(
        btn_frame,
        text="Cancel",
        fg_color=SAGE_CARD,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        border_width=1,
        border_color=BORDER_COLOR,
        corner_radius=12,
        command=lambda: _refresh_list(parent, category=category),
    ).pack(fill="x")


def _show_form_view(parent: ctk.CTkFrame, category: str = "personal") -> None:
    """Replace parent content with the inline task creation form."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415

    # Clear existing children
    for widget in parent.winfo_children():
        widget.destroy()

    # Scrollable area for fields
    scroll = ctk.CTkScrollableFrame(
        parent,
        fg_color=SAGE_BG,
        width=PANEL_WIDTH - 32,
    )
    scroll.pack(fill="both", expand=True, padx=0, pady=(2, 0))

    # Dynamic field area
    field_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    field_frame.pack(fill="x", padx=16, pady=0)

    # Error display area
    error_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    error_frame.pack(fill="x", padx=16, pady=0)

    # Render fields
    fields = _render_fields(field_frame, category=category)

    # Buttons
    btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
    btn_frame.pack(fill="x", padx=16, pady=(4, 8))

    ctk.CTkButton(
        btn_frame,
        text="Save Task",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=12,
        command=lambda: _save_task(parent, fields, error_frame, category),
    ).pack(fill="x", pady=(0, 4))

    ctk.CTkButton(
        btn_frame,
        text="Discard Task",
        fg_color=SAGE_CARD,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        border_width=1,
        border_color=BORDER_COLOR,
        corner_radius=12,
        command=lambda: _refresh_list(parent, category=category),
    ).pack(fill="x")


# ── Public entry point ─────────────────────────────────────────────────────────

def open_panel() -> None:
    """
    Open (or un-hide) the main panel anchored top-right.
    Must be called from the tkinter thread (via enqueue).
    Task list is always refreshed on each open.
    """
    global _panel
    from ui.tk_host import get_root  # noqa: PLC0415

    root = get_root()

    if _panel is not None and _panel.winfo_exists():
        # Refresh task list content before showing
        for widget in _panel.winfo_children():
            widget.destroy()
        try:
            _rebuild_panel(_panel)
        finally:
            _panel.deiconify()
            _panel.lift()
            _panel.focus_force()
            _panel.after(100, _panel.lift)
        return

    # ── Position: top-right below menu bar ───────────────────────────────
    visible    = NSScreen.mainScreen().visibleFrame()
    total_h    = root.winfo_screenheight()
    menu_bar_h = total_h - int(visible.size.height) - int(visible.origin.y)
    margin     = 8
    x = int(visible.origin.x + visible.size.width) - PANEL_WIDTH - margin
    y = menu_bar_h + margin

    # ── Build window ─────────────────────────────────────────────────────
    _panel = ctk.CTkToplevel(root)
    _panel.title("")
    _panel.geometry(f"{PANEL_WIDTH}x{PANEL_HEIGHT}+{x}+{y}")
    _panel.configure(fg_color=SAGE_BG)
    _panel.resizable(False, False)
    _panel.attributes("-topmost", True)
    _panel.protocol("WM_DELETE_WINDOW", _hide_panel)
    _panel.bind("<Command-w>", lambda _e: _hide_panel())

    _rebuild_panel(_panel)

    _panel.deiconify()
    _panel.after(100, _panel.lift)


def _rebuild_panel(win: ctk.CTkToplevel) -> None:
    """Build the panel contents inside win (title + tabs + content frame)."""
    global _active_tab
    from ui.styles import TITLE_FONT, SMALL_FONT  # noqa: PLC0415

    # ── Cat logo + title ──────────────────────────────────────────────────
    cat_img = _load_cat_image(52)
    ctk.CTkLabel(
        win,
        image=cat_img,
        text="",
        fg_color="transparent",
    ).pack(pady=(12, 2))

    ctk.CTkLabel(
        win,
        text="Purrductivity",
        font=TITLE_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
    ).pack(pady=(0, 4))

    # ── Category tab bar ─────────────────────────────────────────────────
    tab_var = ctk.StringVar(value=_active_tab.capitalize())
    tab_bar = ctk.CTkSegmentedButton(
        win,
        values=["Personal", "Work", "Calendar"],
        variable=tab_var,
        fg_color=SAGE_CARD,
        selected_color=SAGE_BUTTON,
        selected_hover_color=BUTTON_HOVER,
        unselected_color=SAGE_CARD,
        unselected_hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
    )
    tab_bar.pack(fill="x", padx=16, pady=(0, 4))

    # ── Filter bar (hidden when Calendar tab is active) ───────────────────
    _STANDARD_FILTERS = {"all": "All", "today": "Today", "week": "Week"}
    filter_var = ctk.StringVar(value=_STANDARD_FILTERS.get(_active_filter, "Today"))
    filter_container = tk.Frame(win, bg=SAGE_BG)
    if _active_tab != "calendar":
        filter_container.pack(fill="x")
    filter_bar = ctk.CTkSegmentedButton(
        filter_container,
        values=["Today", "Week", "All"],
        variable=filter_var,
        fg_color=SAGE_CARD,
        selected_color=CAT_PINK,
        selected_hover_color=BUTTON_HOVER,
        unselected_color=SAGE_CARD,
        unselected_hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
    )
    filter_bar.pack(fill="x", padx=16, pady=(0, 4))

    # ── Rock Report button — work tab only ───────────────────────────────
    rock_row = ctk.CTkFrame(filter_container, fg_color="transparent")
    if _active_tab == "work":
        rock_row.pack(fill="x", padx=16, pady=(0, 4))

    def _open_rock_report() -> None:
        from ui.rock_report import open_rock_report  # noqa: PLC0415
        open_rock_report(_get_store())

    ctk.CTkButton(
        rock_row,
        text="Rock Report",
        fg_color=WORK_ACCENT,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=8,
        height=28,
        font=SMALL_FONT,
        command=_open_rock_report,
    ).pack(fill="x")

    # ── Cat strip at bottom (must be packed before fill+expand content) ──
    cat_canvas = _add_cat_strip(win)

    # ── Content frame fills remaining space ──────────────────────────────
    content = ctk.CTkFrame(win, fg_color=SAGE_BG)
    content.pack(fill="both", expand=True, padx=0, pady=0)

    def on_tab_change(value: str) -> None:
        global _active_tab, _active_filter
        _active_tab = value.lower()
        if _active_tab == "calendar":
            filter_container.pack_forget()
        else:
            _active_filter = "today"
            filter_var.set("Today")
            filter_container.pack(fill="x", after=tab_bar)
        if _active_tab == "work":
            rock_row.pack(fill="x", padx=16, pady=(0, 4))
        else:
            rock_row.pack_forget()
        _refresh_list(content, category=_active_tab)
        _draw_cats_on_canvas(cat_canvas)

    def on_filter_change(value: str) -> None:
        global _active_filter
        _active_filter = {"All": "all", "Today": "today", "Week": "week"}[value]
        _refresh_list(content, category=_active_tab)

    tab_bar.configure(command=on_tab_change)
    filter_bar.configure(command=on_filter_change)

    _refresh_list(content, category=_active_tab)
