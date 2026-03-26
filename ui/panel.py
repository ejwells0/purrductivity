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
    BORDER_COLOR, CAT_PINK, MUTED_TEXT, DESTRUCTIVE,
)

PANEL_WIDTH  = 340
PANEL_HEIGHT = 570

_CATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cats")
_CAT_FILES = sorted(
    f for f in os.listdir(_CATS_DIR) if f.lower().endswith(".png")
)

_panel: ctk.CTkToplevel | None = None
_active_tab: str = "personal"
_active_filter: str = "all"   # "all" | "today" | "week"
_expanded_row: list = []   # at most one expanded row card at a time

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
            until = datetime.fromisoformat(task["snoozed_until"])
            time_str = until.strftime("%-I:%M %p")
            return f"Snoozed until {time_str}", CAT_PINK
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
    elif t == "quarterly":
        due = task.get("due_quarter", "")
        return f"Due {due}" if due else "Quarterly", DARK_TEXT
    return "", DARK_TEXT


def _badge_colors(task_type: str) -> tuple[str, str]:
    """Return (border_color, text_color) for a type badge."""
    if task_type == "daily":
        return CAT_PINK, CAT_PINK
    return BORDER_COLOR, DARK_TEXT


def _badge_label(task_type: str) -> str:
    return task_type.capitalize()


# ── Filter helpers ────────────────────────────────────────────────────────────

def _fires_today(task: dict, today: _date) -> bool:
    t = task.get("type", "")
    dow = today.weekday()
    if t == "daily":
        return True
    if t in ("scheduled", "weekly"):
        return task.get("day_of_week") == dow
    if t == "quarterly":
        return task.get("check_in_enabled", False) and task.get("check_in_dow") == dow
    return False


def _fires_this_week(task: dict) -> bool:
    t = task.get("type", "")
    if t in ("daily", "scheduled", "weekly"):
        return True
    if t == "quarterly":
        return task.get("check_in_enabled", False)
    return False


def _done_today(task: dict, today: _date) -> bool:
    last_done = task.get("last_done")
    if not last_done:
        return False
    try:
        return datetime.fromisoformat(last_done).date() == today
    except (ValueError, TypeError):
        return False


# ── List View ─────────────────────────────────────────────────────────────────

def _delete_task(task_id: str, parent: ctk.CTkFrame, category: str) -> None:
    """Delete a task from store, cancel its scheduler job, refresh list."""
    from ui.tk_host import send_to_main  # noqa: PLC0415
    _get_store().delete_task(task_id)
    send_to_main("cancel_job", task_id=task_id)
    _show_list_view(parent, category=category)


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
    _show_list_view(parent, category=category)


def _resume_task(task_id: str, parent: ctk.CTkFrame, category: str) -> None:
    """Write paused=False to store, re-register APScheduler job, refresh list."""
    from ui.tk_host import send_to_main  # noqa: PLC0415
    _get_store().update_task(task_id, paused=False)
    send_to_main("reschedule_task", task_id=task_id)
    _show_list_view(parent, category=category)


def _confirm_delete(task_id: str, task_name: str, parent: ctk.CTkFrame,
                    category: str) -> None:
    """Show CTkToplevel confirm dialog before deleting."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415
    from ui.tk_host import get_root  # noqa: PLC0415
    dlg = ctk.CTkToplevel(get_root())
    dlg.title("")
    dlg.geometry("280x140")
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
    dlg.after(50, dlg.lift)


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
    elif _active_filter == "week":
        tasks = [t for t in tasks if t.get("paused") or _fires_this_week(t)]

    if not tasks:
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

        for task in tasks:
            is_paused = task.get("paused", False)
            done = _done_today(task, today)
            task_type = task.get("type", "")
            is_goal = task_type in ("weekly", "quarterly")

            # Card color: dimmer background for paused tasks
            card_color = SAGE_BG if is_paused else SAGE_CARD
            name_color = MUTED_TEXT if is_paused else DARK_TEXT

            # ── Row card ─────────────────────────────────────────────
            row_card = ctk.CTkFrame(scroll, fg_color=card_color, corner_radius=8)
            row_card.pack(fill="x", padx=0, pady=3)

            # ── Main info row (click to expand) ──────────────────────
            info_row = ctk.CTkFrame(row_card, fg_color="transparent")
            info_row.pack(fill="x", padx=8, pady=(8, 4))
            info_row.grid_columnconfigure(0, weight=1)
            info_row.grid_columnconfigure(1, weight=0)

            # Left: task name + status subtitle
            left = ctk.CTkFrame(info_row, fg_color="transparent")
            left.grid(row=0, column=0, sticky="nsew")

            ctk.CTkLabel(
                left, text=task.get("name", "Unnamed"), font=BODY_FONT,
                text_color=name_color, fg_color="transparent", anchor="w",
            ).pack(fill="x")

            # Status subtitle
            if is_paused:
                status_text, status_color = "Paused", MUTED_TEXT
            elif done:
                status_text, status_color = "Done today", SAGE_BUTTON
            elif is_goal:
                behind = is_behind(task, today)
                if behind:
                    status_text, status_color = "Behind", DESTRUCTIVE
                else:
                    status_text, status_color = "On Track", SAGE_BUTTON
            else:
                status_text, status_color = _next_fire_label(task)

            if status_text:
                ctk.CTkLabel(
                    left, text=status_text, font=SMALL_FONT,
                    text_color=status_color, fg_color="transparent", anchor="w",
                ).pack(fill="x")

            # Progress bar for goal tasks (not paused, not done)
            if is_goal and not is_paused:
                if task_type == "weekly":
                    target = task.get("weekly_target", 1)
                    actual = task.get("completed_count", 0)
                    fraction = min(actual / target, 1.0) if target else 0.0
                else:  # quarterly
                    fraction = min(task.get("progress", 0) / 100, 1.0)
                fill_col = DESTRUCTIVE if is_behind(task, today) else SAGE_BUTTON
                _draw_progress_bar(left, fraction, fill_col, width=180)

            # Right: type badge
            border_c, text_c = _badge_colors(task_type)
            badge_frame = ctk.CTkFrame(
                info_row, fg_color=SAGE_CARD, border_width=1,
                border_color=border_c, corner_radius=4,
            )
            badge_frame.grid(row=0, column=1, sticky="ne", padx=(4, 0))
            ctk.CTkLabel(
                badge_frame, text=_badge_label(task_type), font=SMALL_FONT,
                text_color=text_c, fg_color="transparent",
            ).pack(padx=6, pady=2)

            # ── Action sub-frame (hidden until row clicked) ──────────
            action_frame = ctk.CTkFrame(row_card, fg_color="transparent")
            # Do NOT pack action_frame here — _toggle_expand does it on click

            _task_snap = task
            _tid = task["id"]
            _tname = task.get("name", "this task")

            # Wire up row click on info_row to toggle actions
            info_row.bind(
                "<Button-1>",
                lambda e, af=action_frame: _toggle_expand(af),
            )
            # Also bind on left sub-frame and badge so whole row is clickable
            left.bind("<Button-1>", lambda e, af=action_frame: _toggle_expand(af))
            badge_frame.bind("<Button-1>", lambda e, af=action_frame: _toggle_expand(af))

            # Action buttons inside action_frame
            btn_row = ctk.CTkFrame(action_frame, fg_color="transparent")
            btn_row.pack(fill="x", pady=(0, 2))

            ctk.CTkButton(
                btn_row, text="Edit", fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
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

    # ── Add Task button (always shown) ────────────────────────────────
    ctk.CTkButton(
        parent, text="+ Add Task", fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT, corner_radius=12,
        command=lambda: _show_form_view(parent, category=category),
    ).pack(fill="x", padx=16, pady=(4, 8))


# ── Form View ─────────────────────────────────────────────────────────────────

def _render_fields(field_frame: ctk.CTkFrame, task_type: str,
                   prefill: dict | None = None) -> dict:
    """Populate field_frame with widgets for task_type.

    Returns dict mapping field name → widget (CTkEntry, StringVar, BooleanVar, or str).
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

    def _add_option_menu(label_text: str, key: str, values: list,
                         default: str) -> ctk.CTkOptionMenu:
        _label(label_text)
        var = ctk.StringVar(value=default)
        menu = ctk.CTkOptionMenu(
            field_frame, values=values, variable=var,
            fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
            button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
            font=BODY_FONT,
        )
        menu.pack(fill="x", padx=0, pady=(0, 2))
        fields[key] = var   # store StringVar so _save_task calls .get()
        return menu

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

    # ── Task name (always present, CTkEntry) ─────────────────────────────
    _add_entry("Task name", "name", initial=p.get("name", ""))

    # ── Start date: non-editable label ───────────────────────────────────
    _label("Start date")
    ctk.CTkLabel(
        field_frame, text=start_date_str, font=BODY_FONT, text_color=DARK_TEXT,
        fg_color=SAGE_CARD, anchor="w", corner_radius=6,
    ).pack(fill="x", padx=0, pady=(0, 2), ipady=6)
    fields["start_date"] = start_date_str

    # ── Type-specific fields ─────────────────────────────────────────────
    if task_type == "Scheduled":
        dow_default = _DOW_NAME.get(p.get("day_of_week", 0), "Mon")
        time_default = _format_time(p.get("hour", 9), p.get("minute", 0)) if p else "9:00 AM"
        _add_option_menu("Day of week", "day_of_week", _DOW_OPTIONS, dow_default)
        _add_time_combo("Reminder time", "time", time_default)

    elif task_type == "Daily":
        time_default = _format_time(p.get("hour", 9), p.get("minute", 0)) if p else "9:00 AM"
        _add_time_combo("Reminder time", "time", time_default)

    elif task_type == "Weekly":
        dow_default = _DOW_NAME.get(p.get("day_of_week", 0), "Mon")
        time_default = _format_time(p.get("hour", 9), p.get("minute", 0)) if p else "9:00 AM"
        _add_option_menu("Day of week", "day_of_week", _DOW_OPTIONS, dow_default)
        _add_time_combo("Reminder time", "time", time_default)
        # Optional weekly target toggle
        prefill_target = p.get("weekly_target", 1)
        prefill_toggle = prefill_target > 1
        _label("Set weekly target?")
        toggle_var = ctk.BooleanVar(value=prefill_toggle)
        target_var = ctk.StringVar(value=str(prefill_target))
        target_menu_holder: list = []

        def _on_toggle_change() -> None:
            if toggle_var.get():
                if not target_menu_holder:
                    m = ctk.CTkOptionMenu(
                        field_frame,
                        values=[str(i) for i in range(1, 11)],
                        variable=target_var,
                        fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                        button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                        font=BODY_FONT,
                    )
                    m.pack(fill="x", padx=0, pady=(0, 2))
                    target_menu_holder.append(m)
            else:
                for m in target_menu_holder:
                    m.destroy()
                target_menu_holder.clear()
                target_var.set("1")

        ctk.CTkCheckBox(
            field_frame, text="", variable=toggle_var,
            fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
            checkmark_color=DARK_TEXT, border_color=BORDER_COLOR,
            command=_on_toggle_change,
        ).pack(anchor="w", padx=0, pady=(0, 2))
        # Pre-show the target menu if toggle was on
        if prefill_toggle:
            m = ctk.CTkOptionMenu(
                field_frame,
                values=[str(i) for i in range(1, 11)],
                variable=target_var,
                fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                font=BODY_FONT,
            )
            m.pack(fill="x", padx=0, pady=(0, 2))
            target_menu_holder.append(m)
        fields["weekly_target"] = target_var

    elif task_type == "Quarterly":
        q_opts = _quarter_options()
        due_default = p.get("due_quarter", q_opts[0])
        if due_default not in q_opts:
            q_opts = [due_default] + q_opts
        _add_option_menu("Due date", "due_quarter", q_opts, due_default)
        # Opt-in weekly check-in
        prefill_checkin = p.get("check_in_enabled", False)
        prefill_checkin_day = _DOW_NAME.get(p.get("check_in_dow", 0), "Mon")
        prefill_checkin_time = _format_time(p.get("hour", 9), p.get("minute", 0)) if p else "9:00 AM"
        _label("Weekly check-in?")
        checkin_var = ctk.BooleanVar(value=prefill_checkin)
        checkin_day_var = ctk.StringVar(value=prefill_checkin_day)
        checkin_time_var = ctk.StringVar(value=prefill_checkin_time)
        checkin_menu_holder: list = []

        def _on_checkin_change() -> None:
            if checkin_var.get():
                if not checkin_menu_holder:
                    lbl_day = ctk.CTkLabel(
                        field_frame, text="Check-in day", font=SMALL_FONT,
                        text_color=DARK_TEXT, fg_color="transparent", anchor="w",
                    )
                    lbl_day.pack(fill="x", padx=0, pady=(6, 1))
                    m_day = ctk.CTkOptionMenu(
                        field_frame, values=_DOW_OPTIONS, variable=checkin_day_var,
                        fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                        button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                        font=BODY_FONT,
                    )
                    m_day.pack(fill="x", padx=0, pady=(0, 2))
                    lbl_time = ctk.CTkLabel(
                        field_frame, text="Check-in time", font=SMALL_FONT,
                        text_color=DARK_TEXT, fg_color="transparent", anchor="w",
                    )
                    lbl_time.pack(fill="x", padx=0, pady=(6, 1))
                    m_time = ctk.CTkOptionMenu(
                        field_frame, values=_TIME_SLOTS, variable=checkin_time_var,
                        fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                        button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                        font=BODY_FONT,
                    )
                    m_time.pack(fill="x", padx=0, pady=(0, 2))
                    checkin_menu_holder.extend([lbl_day, m_day, lbl_time, m_time])
            else:
                for w in checkin_menu_holder:
                    w.destroy()
                checkin_menu_holder.clear()

        ctk.CTkCheckBox(
            field_frame, text="", variable=checkin_var,
            fg_color=SAGE_BUTTON, hover_color=BUTTON_HOVER,
            checkmark_color=DARK_TEXT, border_color=BORDER_COLOR,
            command=_on_checkin_change,
        ).pack(anchor="w", padx=0, pady=(0, 2))
        # Pre-show check-in fields if enabled
        if prefill_checkin:
            lbl_day = ctk.CTkLabel(
                field_frame, text="Check-in day", font=SMALL_FONT,
                text_color=DARK_TEXT, fg_color="transparent", anchor="w",
            )
            lbl_day.pack(fill="x", padx=0, pady=(6, 1))
            m_day = ctk.CTkOptionMenu(
                field_frame, values=_DOW_OPTIONS, variable=checkin_day_var,
                fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                font=BODY_FONT,
            )
            m_day.pack(fill="x", padx=0, pady=(0, 2))
            lbl_time = ctk.CTkLabel(
                field_frame, text="Check-in time", font=SMALL_FONT,
                text_color=DARK_TEXT, fg_color="transparent", anchor="w",
            )
            lbl_time.pack(fill="x", padx=0, pady=(6, 1))
            m_time = ctk.CTkOptionMenu(
                field_frame, values=_TIME_SLOTS, variable=checkin_time_var,
                fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                font=BODY_FONT,
            )
            m_time.pack(fill="x", padx=0, pady=(0, 2))
            checkin_menu_holder.extend([lbl_day, m_day, lbl_time, m_time])
        fields["check_in_enabled"] = checkin_var
        fields["check_in_day"] = checkin_day_var
        fields["check_in_time"] = checkin_time_var

    # ── Notes (always present) ────────────────────────────────────────────
    _add_entry("Notes (optional)", "notes", initial=p.get("notes", ""))

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


def _save_task(parent: ctk.CTkFrame, fields: dict, type_var: ctk.StringVar,
               error_frame: ctk.CTkFrame, category: str = "personal") -> None:
    """Validate fields, call store.add_task(), switch back to list view on success."""
    # Clear prior error messages
    for widget in error_frame.winfo_children():
        widget.destroy()

    task_type = type_var.get()
    name = fields.get("name", None)
    name_val = name.get().strip() if name else ""
    if not name_val:
        _show_error(error_frame, "This field is required.")
        return

    # start_date is now stored as a string constant (not a widget)
    start_date_raw = fields.get("start_date", None)
    if isinstance(start_date_raw, str):
        start_date_str = start_date_raw
    elif start_date_raw is not None:
        start_date_str = start_date_raw.get().strip() or datetime.now().date().isoformat()
    else:
        start_date_str = datetime.now().date().isoformat()

    notes_entry = fields.get("notes", None)
    notes_val = notes_entry.get().strip() if notes_entry else ""

    # Parse time (shared by Scheduled, Daily, Weekly — quarterly has no time field)
    hour, minute = 9, 0
    if "time" in fields:
        time_str = fields["time"].get()  # StringVar from CTkOptionMenu
        parsed = _parse_time(time_str) if time_str else None
        if parsed is None and time_str:
            _show_error(error_frame, "Enter a valid time (e.g. 9:00 AM).")
            return
        if parsed:
            hour, minute = parsed

    from ui.tk_host import send_to_main  # noqa: PLC0415

    store = _get_store()
    task_id: str | None = None

    if task_type == "Scheduled":
        dow_val = fields.get("day_of_week", None)
        dow_str = dow_val.get() if dow_val else ""  # StringVar from CTkOptionMenu
        dow = _parse_dow(dow_str)
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
            notes=notes_val,
            category=category,
        )

    elif task_type == "Daily":
        task_id = store.add_task(
            type="daily",
            name=name_val,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            notes=notes_val,
            category=category,
        )

    elif task_type == "Weekly":
        dow_var = fields.get("day_of_week")
        day_of_week = _parse_dow(dow_var.get() if dow_var else "Mon")
        weekly_var = fields.get("weekly_target", None)
        weekly_str = weekly_var.get() if weekly_var else "1"  # StringVar, default "1"
        try:
            weekly_target = int(weekly_str)
        except (ValueError, TypeError):
            _show_error(error_frame, "Enter a whole number for weekly target.")
            return
        task_id = store.add_task(
            type="weekly",
            name=name_val,
            day_of_week=day_of_week,
            weekly_target=weekly_target,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            notes=notes_val,
            category=category,
        )

    elif task_type == "Quarterly":
        due_quarter_var = fields.get("due_quarter")
        due_quarter = due_quarter_var.get() if due_quarter_var else "Q1 2026"
        check_in_var = fields.get("check_in_enabled")
        check_in_enabled = check_in_var.get() if check_in_var else False
        check_in_day_var = fields.get("check_in_day")
        check_in_day_str = check_in_day_var.get() if check_in_day_var else "Mon"
        check_in_dow = _parse_dow(check_in_day_str) if check_in_enabled else None
        check_in_time_var = fields.get("check_in_time")
        check_in_time_str = check_in_time_var.get() if check_in_time_var else "9:00 AM"
        parsed_time = _parse_time(check_in_time_str) if check_in_enabled else None
        ci_hour, ci_minute = parsed_time if parsed_time else (9, 0)
        task_id = store.add_task(
            type="quarterly",
            name=name_val,
            due_quarter=due_quarter,
            progress=0,
            check_in_enabled=check_in_enabled,
            check_in_dow=check_in_dow,
            hour=ci_hour,
            minute=ci_minute,
            start_date=start_date_str,
            notes=notes_val,
            category=category,
        )

    # Register the new task with the scheduler immediately
    if task_id:
        send_to_main("reschedule_task", task_id=task_id)

    # Success — return to list view
    _show_list_view(parent, category=category)


def _update_task(parent: ctk.CTkFrame, task_id: str, fields: dict,
                 type_var: ctk.StringVar, error_frame: ctk.CTkFrame,
                 category: str = "personal") -> None:
    """Validate fields, write updates to store, reschedule job, return to list."""
    from ui.tk_host import send_to_main  # noqa: PLC0415

    for widget in error_frame.winfo_children():
        widget.destroy()

    task_type = type_var.get()
    name = fields.get("name")
    name_val = name.get().strip() if name else ""
    if not name_val:
        _show_error(error_frame, "This field is required.")
        return

    start_date_raw = fields.get("start_date")
    start_date_str = start_date_raw if isinstance(start_date_raw, str) else datetime.now().date().isoformat()

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

    store = _get_store()
    updates: dict = {"name": name_val, "notes": notes_val,
                     "start_date": start_date_str, "category": category,
                     "type": task_type.lower()}

    if task_type == "Scheduled":
        dow_val = fields.get("day_of_week")
        dow = _parse_dow(dow_val.get() if dow_val else "")
        if dow is None:
            _show_error(error_frame, "Enter a valid day (e.g. Mon, Tue, Wed).")
            return
        updates.update({"day_of_week": dow, "hour": hour, "minute": minute})

    elif task_type == "Daily":
        updates.update({"hour": hour, "minute": minute})

    elif task_type == "Weekly":
        dow_var = fields.get("day_of_week")
        day_of_week = _parse_dow(dow_var.get() if dow_var else "Mon")
        weekly_var = fields.get("weekly_target")
        weekly_str = weekly_var.get() if weekly_var else "1"
        try:
            weekly_target = int(weekly_str)
        except (ValueError, TypeError):
            _show_error(error_frame, "Enter a whole number for weekly target.")
            return
        updates.update({"day_of_week": day_of_week, "hour": hour,
                         "minute": minute, "weekly_target": weekly_target})

    elif task_type == "Quarterly":
        due_quarter_var = fields.get("due_quarter")
        due_quarter = due_quarter_var.get() if due_quarter_var else ""
        check_in_var = fields.get("check_in_enabled")
        check_in_enabled = check_in_var.get() if check_in_var else False
        check_in_day_var = fields.get("check_in_day")
        check_in_day_str = check_in_day_var.get() if check_in_day_var else "Mon"
        check_in_dow = _parse_dow(check_in_day_str) if check_in_enabled else None
        check_in_time_var = fields.get("check_in_time")
        check_in_time_str = check_in_time_var.get() if check_in_time_var else "9:00 AM"
        parsed_time = _parse_time(check_in_time_str) if check_in_enabled else None
        ci_hour, ci_minute = parsed_time if parsed_time else (9, 0)
        updates.update({"due_quarter": due_quarter, "check_in_enabled": check_in_enabled,
                         "check_in_dow": check_in_dow, "hour": ci_hour, "minute": ci_minute})

    store.update_task(task_id, **updates)
    send_to_main("reschedule_task", task_id=task_id)
    _show_list_view(parent, category=category)


def _show_edit_view(parent: ctk.CTkFrame, task: dict, category: str) -> None:
    """Replace parent content with the edit form pre-populated from task."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415

    for widget in parent.winfo_children():
        widget.destroy()

    # Type selector (pre-set to task's current type)
    type_map = {"scheduled": "Scheduled", "daily": "Daily",
                "weekly": "Weekly", "quarterly": "Quarterly"}
    initial_type = type_map.get(task.get("type", "scheduled"), "Scheduled")
    type_var = ctk.StringVar(value=initial_type)
    type_selector = ctk.CTkSegmentedButton(
        parent,
        values=["Scheduled", "Daily", "Weekly", "Quarterly"],
        variable=type_var,
        fg_color=SAGE_CARD,
        selected_color=SAGE_BUTTON,
        selected_hover_color=BUTTON_HOVER,
        unselected_color=SAGE_CARD,
        unselected_hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
    )
    type_selector.pack(fill="x", padx=16, pady=(0, 4))

    scroll = ctk.CTkScrollableFrame(parent, fg_color=SAGE_BG, width=PANEL_WIDTH - 32)
    scroll.pack(fill="both", expand=True, padx=0, pady=(2, 0))

    field_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    field_frame.pack(fill="x", padx=16, pady=0)

    error_frame = ctk.CTkFrame(scroll, fg_color="transparent")
    error_frame.pack(fill="x", padx=16, pady=0)

    fields = _render_fields(field_frame, type_var.get(), prefill=task)

    def on_type_change(value: str) -> None:
        nonlocal fields
        # Keep prefill for name/notes/start_date even when switching type
        fields = _render_fields(field_frame, value, prefill=task)

    type_selector.configure(command=on_type_change)

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
        command=lambda: _update_task(parent, task_id, fields, type_var, error_frame, category),
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
        command=lambda: _show_list_view(parent, category=category),
    ).pack(fill="x")


def _show_form_view(parent: ctk.CTkFrame, category: str = "personal") -> None:
    """Replace parent content with the inline task creation form."""
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415

    # Clear existing children
    for widget in parent.winfo_children():
        widget.destroy()

    # Type selector
    type_var = ctk.StringVar(value="Scheduled")
    type_selector = ctk.CTkSegmentedButton(
        parent,
        values=["Scheduled", "Daily", "Weekly", "Quarterly"],
        variable=type_var,
        fg_color=SAGE_CARD,
        selected_color=SAGE_BUTTON,
        selected_hover_color=BUTTON_HOVER,
        unselected_color=SAGE_CARD,
        unselected_hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
    )
    type_selector.pack(fill="x", padx=16, pady=(12, 4))

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

    # Render initial fields
    fields = _render_fields(field_frame, type_var.get())

    def on_type_change(value: str) -> None:
        nonlocal fields
        fields = _render_fields(field_frame, value)

    type_selector.configure(command=on_type_change)

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
        command=lambda: _save_task(parent, fields, type_var, error_frame, category),
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
        command=lambda: _show_list_view(parent, category=category),
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
    from ui.styles import TITLE_FONT  # noqa: PLC0415

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
        values=["Personal", "Work"],
        variable=tab_var,
        fg_color=SAGE_CARD,
        selected_color=SAGE_BUTTON,
        selected_hover_color=BUTTON_HOVER,
        unselected_color=SAGE_CARD,
        unselected_hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
    )
    tab_bar.pack(fill="x", padx=16, pady=(0, 4))

    # ── Filter bar ───────────────────────────────────────────────────────
    _filter_label_map = {"all": "All", "today": "Today", "week": "This Week"}
    filter_var = ctk.StringVar(value=_filter_label_map.get(_active_filter, "All"))
    filter_bar = ctk.CTkSegmentedButton(
        win,
        values=["All", "Today", "This Week"],
        variable=filter_var,
        fg_color=SAGE_CARD,
        selected_color=CAT_PINK,
        selected_hover_color=BUTTON_HOVER,
        unselected_color=SAGE_CARD,
        unselected_hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
    )
    filter_bar.pack(fill="x", padx=16, pady=(0, 6))

    # ── Cat strip at bottom (must be packed before fill+expand content) ──
    cat_canvas = _add_cat_strip(win)

    # ── Content frame fills remaining space ──────────────────────────────
    content = ctk.CTkFrame(win, fg_color=SAGE_BG)
    content.pack(fill="both", expand=True, padx=0, pady=0)

    def on_tab_change(value: str) -> None:
        global _active_tab
        _active_tab = value.lower()
        _show_list_view(content, category=_active_tab)
        _draw_cats_on_canvas(cat_canvas)

    def on_filter_change(value: str) -> None:
        global _active_filter
        _active_filter = {"All": "all", "Today": "today", "This Week": "week"}[value]
        _show_list_view(content, category=_active_tab)

    tab_bar.configure(command=on_tab_change)
    filter_bar.configure(command=on_filter_change)

    _show_list_view(content, category=_active_tab)
