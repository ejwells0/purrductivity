# ui/panel.py
# Main panel — CTkToplevel positioned top-right below menu bar.
# Source: Phase 1 Research — Pattern 3; Pitfall 3 (behind menu bar), Pitfall 5 (behind windows)
#
# MUST be called from the tkinter thread (via enqueue). Never call directly from
# app.py or scheduler.py.
import customtkinter as ctk
from AppKit import NSScreen

from ui.styles import LAVENDER_BG, CREAM_TEXT, BORDER_COLOR
# BODY_FONT and TITLE_FONT are imported inside open_panel() to defer font
# creation until the tkinter root exists (they use module __getattr__ which
# calls CTkFont() — requires a live tk root).

PANEL_WIDTH  = 360
PANEL_HEIGHT = 500

_panel: ctk.CTkToplevel | None = None


def open_panel() -> None:
    """
    Open (or un-hide) the main panel anchored to the top-right corner.
    Must be called from the tkinter thread (via enqueue).
    """
    global _panel
    from ui.tk_host import _root  # imported here to avoid circular import at module load

    if _panel is not None and _panel.winfo_exists():
        _panel.deiconify()
        _panel.lift()
        _panel.after(100, _panel.lift)  # CTkToplevel issue #1219 workaround
        return

    # ── Screen geometry (NSScreen accounts for notch and menu bar) ────────────
    # NSScreen origin: bottom-left. tkinter geometry: top-left. Conversion needed.
    visible      = NSScreen.mainScreen().visibleFrame()
    total_h      = _root.winfo_screenheight()
    # Pixels from top of screen consumed by menu bar (and notch on MacBook Pro):
    menu_bar_h   = total_h - int(visible.size.height) - int(visible.origin.y)
    margin       = 8
    x = int(visible.origin.x + visible.size.width) - PANEL_WIDTH - margin
    y = menu_bar_h + margin

    # ── Build window ──────────────────────────────────────────────────────────
    _panel = ctk.CTkToplevel(_root)
    _panel.title("")
    _panel.geometry(f"{PANEL_WIDTH}x{PANEL_HEIGHT}+{x}+{y}")
    _panel.configure(fg_color=LAVENDER_BG)
    _panel.resizable(False, False)

    # Stay on top; survive Cmd+W and macOS window gestures (SHELL-03)
    _panel.attributes("-topmost", True)
    # WM_DELETE_WINDOW: hide instead of destroy — one root, never recreated (Pitfall 2)
    _panel.protocol("WM_DELETE_WINDOW", _panel.withdraw)

    # ── Placeholder content ───────────────────────────────────────────────────
    # Fonts are imported here (after tk root exists) to avoid RuntimeError at module import
    from ui.styles import TITLE_FONT, BODY_FONT  # noqa: PLC0415

    header = ctk.CTkLabel(
        _panel,
        text="Purrductivity 🐱",
        font=TITLE_FONT,
        text_color=CREAM_TEXT,
        fg_color="transparent",
    )
    header.pack(pady=(20, 4))

    sub = ctk.CTkLabel(
        _panel,
        text="Your tasks will appear here.",
        font=BODY_FONT,
        text_color=CREAM_TEXT,
        fg_color="transparent",
    )
    sub.pack(pady=4)

    close_btn = ctk.CTkButton(
        _panel,
        text="Close",
        fg_color=BORDER_COLOR,
        hover_color="#B89DD0",
        text_color=CREAM_TEXT,
        corner_radius=8,
        command=_panel.withdraw,
    )
    close_btn.pack(pady=20)

    _panel.deiconify()
    _panel.after(100, _panel.lift)  # CTkToplevel issue #1219 workaround
