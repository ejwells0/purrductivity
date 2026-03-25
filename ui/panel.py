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
    elif t in ("weekly", "quarterly"):
        return f"Checks in daily at {time_str}", DARK_TEXT
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

            # Right column: type badge
            border_c, text_c = _badge_colors(task.get("type", ""))
            badge = ctk.CTkLabel(
                row,
                text=_badge_label(task.get("type", "")),
                font=SMALL_FONT,
                text_color=text_c,
                fg_color=SAGE_CARD,
                corner_radius=4,
                padx=6,
                pady=2,
            )
            badge.grid(row=0, column=1, sticky="e", padx=(4, 10), pady=6)
            badge.configure(border_width=1, border_color=border_c)

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
    """Populate field_frame with entry widgets for task_type.

    Returns dict mapping field name → CTkEntry widget.
    All prior children of field_frame are destroyed before rendering.
    """
    from ui.styles import BODY_FONT, SMALL_FONT  # noqa: PLC0415

    for widget in field_frame.winfo_children():
        widget.destroy()

    fields: dict[str, ctk.CTkEntry] = {}

    def _add_entry(label_text: str, key: str, placeholder: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(
            field_frame,
            text=label_text,
            font=SMALL_FONT,
            text_color=DARK_TEXT,
            fg_color="transparent",
            anchor="w",
        ).pack(fill="x", padx=0, pady=(6, 1))
        entry = ctk.CTkEntry(
            field_frame,
            fg_color=SAGE_CARD,
            border_color=BORDER_COLOR,
            text_color=DARK_TEXT,
            font=BODY_FONT,
            placeholder_text=placeholder,
        )
        entry.pack(fill="x", padx=0, pady=(0, 2))
        fields[key] = entry
        return entry

    # Fields shared by all types
    _add_entry("Task name", "name")
    _add_entry("Start date", "start_date", "YYYY-MM-DD")

    # Type-specific fields
    if task_type == "Scheduled":
        _add_entry("Day of week", "day_of_week", "Mon/Tue/Wed/Thu/Fri/Sat/Sun")
        _add_entry("Reminder time", "time", "9:00 AM")
    elif task_type == "Daily":
        _add_entry("Reminder time", "time", "9:00 AM")
    elif task_type == "Weekly":
        _add_entry("Weekly target", "weekly_target", "e.g. 5")
        _add_entry("Reminder time", "time", "9:00 AM")
    elif task_type == "Quarterly":
        _add_entry("Total target", "total_target", "e.g. 52")
        _add_entry("Reminder time", "time", "9:00 AM")

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

    start_date_val = fields.get("start_date", None)
    start_date_str = start_date_val.get().strip() if start_date_val else ""
    if not start_date_str:
        start_date_str = datetime.now().date().isoformat()

    notes_entry = fields.get("notes", None)
    notes_val = notes_entry.get().strip() if notes_entry else ""

    # Parse time (shared by all types that have it)
    hour, minute = 9, 0
    if "time" in fields:
        time_str = fields["time"].get().strip()
        parsed = _parse_time(time_str) if time_str else None
        if parsed is None and time_str:
            _show_error(error_frame, "Enter a valid time (e.g. 9:00 AM).")
            return
        if parsed:
            hour, minute = parsed

    store = _get_store()

    if task_type == "Scheduled":
        dow_val = fields.get("day_of_week", None)
        dow_str = dow_val.get().strip() if dow_val else ""
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
        weekly_entry = fields.get("weekly_target", None)
        weekly_str = weekly_entry.get().strip() if weekly_entry else ""
        try:
            weekly_target = int(weekly_str)
        except (ValueError, TypeError):
            _show_error(error_frame, "Enter a whole number for weekly target.")
            return
        store.add_task(
            type="weekly",
            name=name_val,
            weekly_target=weekly_target,
            hour=hour,
            minute=minute,
            start_date=start_date_str,
            notes=notes_val,
        )

    elif task_type == "Quarterly":
        total_entry = fields.get("total_target", None)
        total_str = total_entry.get().strip() if total_entry else ""
        try:
            total_target = int(total_str)
        except (ValueError, TypeError):
            _show_error(error_frame, "Enter a whole number for total target.")
            return
        store.add_task(
            type="quarterly",
            name=name_val,
            total_target=total_target,
            hour=hour,
            minute=minute,
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
