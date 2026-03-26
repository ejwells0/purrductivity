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
from datetime import datetime

import customtkinter as ctk
from PIL import Image
from AppKit import NSScreen

from ui.styles import (
    SAGE_BG, SAGE_CARD, DARK_TEXT, SAGE_BUTTON, BUTTON_HOVER,
    BORDER_COLOR, CAT_PINK,
)

PANEL_WIDTH  = 340
PANEL_HEIGHT = 460

_CATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cats")
_CAT_FILES = sorted(
    f for f in os.listdir(_CATS_DIR) if f.lower().endswith(".png")
)

_panel: ctk.CTkToplevel | None = None

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


# ── List View ─────────────────────────────────────────────────────────────────

def _show_list_view(parent: ctk.CTkFrame) -> None:
    """Populate parent with scrollable task list + Add Task button, or empty state."""
    from ui.styles import BODY_FONT, SMALL_FONT, TITLE_FONT  # noqa: PLC0415

    # Clear existing children
    for widget in parent.winfo_children():
        widget.destroy()

    tasks = _get_store().get_active_tasks()

    if not tasks:
        # ── Empty state ───────────────────────────────────────────────
        cat_img = _load_cat_image(80)
        ctk.CTkLabel(
            parent,
            image=cat_img,
            text="",
            fg_color="transparent",
        ).pack(pady=(24, 4))

        ctk.CTkLabel(
            parent,
            text="No tasks yet",
            font=TITLE_FONT,
            text_color=DARK_TEXT,
            fg_color="transparent",
        ).pack(pady=(4, 2))

        ctk.CTkLabel(
            parent,
            text="You haven't added anything to chase yet.\nHit '+ Add Task' to start.",
            font=BODY_FONT,
            text_color=DARK_TEXT,
            fg_color="transparent",
            justify="center",
        ).pack(pady=(2, 16))

    else:
        # ── Scrollable task list ──────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(
            parent,
            fg_color=SAGE_BG,
            width=PANEL_WIDTH - 32,
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=(8, 4))

        for task in tasks:
            row = ctk.CTkFrame(scroll, fg_color=SAGE_CARD, corner_radius=8)
            row.pack(fill="x", padx=0, pady=3)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=0)

            # Left column: task name + fire time
            left = ctk.CTkFrame(row, fg_color="transparent")
            left.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=6)

            ctk.CTkLabel(
                left,
                text=task.get("name", "Unnamed"),
                font=BODY_FONT,
                text_color=DARK_TEXT,
                fg_color="transparent",
                anchor="w",
            ).pack(fill="x")

            fire_text, fire_color = _next_fire_label(task)
            if fire_text:
                ctk.CTkLabel(
                    left,
                    text=fire_text,
                    font=SMALL_FONT,
                    text_color=fire_color,
                    fg_color="transparent",
                    anchor="w",
                ).pack(fill="x")

            # Right column: type badge (CTkFrame wrapper for border support)
            border_c, text_c = _badge_colors(task.get("type", ""))
            badge_frame = ctk.CTkFrame(
                row,
                fg_color=SAGE_CARD,
                border_width=1,
                border_color=border_c,
                corner_radius=4,
            )
            badge_frame.grid(row=0, column=1, sticky="e", padx=(4, 10), pady=6)
            ctk.CTkLabel(
                badge_frame,
                text=_badge_label(task.get("type", "")),
                font=SMALL_FONT,
                text_color=text_c,
                fg_color="transparent",
            ).pack(padx=6, pady=2)

    # ── Add Task button (always shown) ────────────────────────────────
    ctk.CTkButton(
        parent,
        text="+ Add Task",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=12,
        command=lambda: _show_form_view(parent),
    ).pack(fill="x", padx=16, pady=(4, 8))


# ── Form View ─────────────────────────────────────────────────────────────────

def _render_fields(field_frame: ctk.CTkFrame, task_type: str) -> dict:
    """Populate field_frame with widgets for task_type.

    Returns dict mapping field name → widget (CTkEntry, StringVar, BooleanVar, or str).
    All prior children of field_frame are destroyed before rendering.
    """
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415
    from datetime import date  # noqa: PLC0415

    for widget in field_frame.winfo_children():
        widget.destroy()

    fields: dict = {}
    today_str = date.today().isoformat()

    def _label(text: str) -> None:
        ctk.CTkLabel(
            field_frame, text=text, font=SMALL_FONT, text_color=DARK_TEXT,
            fg_color="transparent", anchor="w",
        ).pack(fill="x", padx=0, pady=(6, 1))

    def _add_entry(label_text: str, key: str, placeholder: str = "") -> ctk.CTkEntry:
        _label(label_text)
        entry = ctk.CTkEntry(
            field_frame, fg_color=SAGE_CARD, border_color=BORDER_COLOR,
            text_color=DARK_TEXT, font=BODY_FONT, placeholder_text=placeholder,
        )
        entry.pack(fill="x", padx=0, pady=(0, 2))
        fields[key] = entry
        return entry

    def _add_option_menu(label_text: str, key: str, values: list, default: str) -> ctk.CTkOptionMenu:
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

    # ── Task name (always present, CTkEntry) ─────────────────────────────
    _add_entry("Task name", "name")

    # ── Start date: non-editable label pre-filled with today ─────────────
    _label("Start date")
    ctk.CTkLabel(
        field_frame, text=today_str, font=BODY_FONT, text_color=DARK_TEXT,
        fg_color=SAGE_CARD, anchor="w", corner_radius=6,
    ).pack(fill="x", padx=0, pady=(0, 2), ipady=6)
    fields["start_date"] = today_str   # store as string constant, not widget

    # ── Type-specific fields ─────────────────────────────────────────────
    if task_type == "Scheduled":
        _add_option_menu("Day of week", "day_of_week", _DOW_OPTIONS, "Mon")
        _add_option_menu("Reminder time", "time", _TIME_SLOTS, "9:00 AM")

    elif task_type == "Daily":
        _add_option_menu("Reminder time", "time", _TIME_SLOTS, "9:00 AM")

    elif task_type == "Weekly":
        _add_option_menu("Day of week", "day_of_week", _DOW_OPTIONS, "Mon")
        _add_option_menu("Reminder time", "time", _TIME_SLOTS, "9:00 AM")
        # Optional weekly target toggle
        _label("Set weekly target?")
        toggle_var = ctk.BooleanVar(value=False)
        target_var = ctk.StringVar(value="1")
        target_menu_holder: list = []   # mutable container for the CTkOptionMenu ref

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
        fields["weekly_target"] = target_var   # always valid: "1" if toggle OFF

    elif task_type == "Quarterly":
        _add_option_menu("Due date", "due_quarter", _quarter_options(), _quarter_options()[0])
        # Opt-in weekly check-in
        _label("Weekly check-in?")
        checkin_var = ctk.BooleanVar(value=False)
        checkin_day_var = ctk.StringVar(value="Mon")
        checkin_menu_holder: list = []

        def _on_checkin_change() -> None:
            if checkin_var.get():
                if not checkin_menu_holder:
                    lbl2 = ctk.CTkLabel(
                        field_frame, text="Check-in day", font=SMALL_FONT,
                        text_color=DARK_TEXT, fg_color="transparent", anchor="w",
                    )
                    lbl2.pack(fill="x", padx=0, pady=(6, 1))
                    m = ctk.CTkOptionMenu(
                        field_frame,
                        values=_DOW_OPTIONS,
                        variable=checkin_day_var,
                        fg_color=SAGE_CARD, button_color=SAGE_BUTTON,
                        button_hover_color=BUTTON_HOVER, text_color=DARK_TEXT,
                        font=BODY_FONT,
                    )
                    m.pack(fill="x", padx=0, pady=(0, 2))
                    checkin_menu_holder.extend([lbl2, m])
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
        fields["check_in_enabled"] = checkin_var   # BooleanVar
        fields["check_in_day"] = checkin_day_var    # StringVar

    # ── Notes (always present) ────────────────────────────────────────────
    _add_entry("Notes (optional)", "notes", "")

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
               error_frame: ctk.CTkFrame) -> None:
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

    store = _get_store()

    if task_type == "Scheduled":
        dow_val = fields.get("day_of_week", None)
        dow_str = dow_val.get() if dow_val else ""  # StringVar from CTkOptionMenu
        dow = _parse_dow(dow_str)
        if dow is None:
            _show_error(error_frame, "Enter a valid day (e.g. Mon, Tue, Wed).")
            return
        store.add_task(
            type="scheduled",
            name=name_val,
            day_of_week=dow,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            notes=notes_val,
        )

    elif task_type == "Daily":
        store.add_task(
            type="daily",
            name=name_val,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            notes=notes_val,
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
        store.add_task(
            type="weekly",
            name=name_val,
            day_of_week=day_of_week,
            weekly_target=weekly_target,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            notes=notes_val,
        )

    elif task_type == "Quarterly":
        due_quarter_var = fields.get("due_quarter")
        due_quarter = due_quarter_var.get() if due_quarter_var else "Q1 2026"
        check_in_var = fields.get("check_in_enabled")
        check_in_enabled = check_in_var.get() if check_in_var else False
        check_in_day_var = fields.get("check_in_day")
        check_in_day_str = check_in_day_var.get() if check_in_day_var else "Mon"
        check_in_dow = _parse_dow(check_in_day_str) if check_in_enabled else None
        store.add_task(
            type="quarterly",
            name=name_val,
            due_quarter=due_quarter,
            progress=0,
            check_in_enabled=check_in_enabled,
            check_in_dow=check_in_dow,
            hour=9,     # check-in fires at 9 AM by default
            minute=0,
            start_date=start_date_str,
            notes=notes_val,
        )

    # Success — return to list view
    _show_list_view(parent)


def _show_form_view(parent: ctk.CTkFrame) -> None:
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
        command=lambda: _save_task(parent, fields, type_var, error_frame),
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
        command=lambda: _show_list_view(parent),
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
        _rebuild_panel(_panel)
        _panel.deiconify()
        _panel.lift()
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
    """Build the panel contents inside win (title + content frame)."""
    from ui.styles import TITLE_FONT  # noqa: PLC0415

    # ── Title ─────────────────────────────────────────────────────────────
    ctk.CTkLabel(
        win,
        text="Purrductivity",
        font=TITLE_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
    ).pack(pady=(16, 4))

    # ── Content frame fills remaining space ──────────────────────────────
    content = ctk.CTkFrame(win, fg_color=SAGE_BG)
    content.pack(fill="both", expand=True, padx=0, pady=0)

    _show_list_view(content)
