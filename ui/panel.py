# ui/panel.py
# Main panel — CTkToplevel with kawaii cat image, positioned top-right.
# MUST be called from the tkinter thread (via enqueue). Never call directly from
# app.py or scheduler.py.
import os
import random
import customtkinter as ctk
from PIL import Image
from AppKit import NSScreen

from ui.styles import SAGE_BG, DARK_TEXT, SAGE_BUTTON, BUTTON_HOVER

PANEL_WIDTH  = 340
PANEL_HEIGHT = 460

_CATS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cats")
_CAT_COUNT = 15

_panel: ctk.CTkToplevel | None = None


def _hide_panel() -> None:
    """Hide the panel without destroying it."""
    if _panel is not None and _panel.winfo_exists():
        _panel.withdraw()


def _load_cat_image(size: int = 160) -> ctk.CTkImage:
    """Pick a random cat and return a CTkImage scaled to size×size."""
    idx = random.randint(1, _CAT_COUNT)
    path = os.path.join(_CATS_DIR, f"cat_{idx:02d}.png")
    img = Image.open(path).convert("RGBA")
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def open_panel() -> None:
    """
    Open (or un-hide) the main panel anchored top-right.
    Must be called from the tkinter thread (via enqueue).
    """
    global _panel
    from ui.tk_host import get_root  # noqa: PLC0415

    root = get_root()

    if _panel is not None and _panel.winfo_exists():
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

    # ── Cat image ────────────────────────────────────────────────────────
    cat_img = _load_cat_image(160)
    ctk.CTkLabel(_panel, image=cat_img, text="", fg_color="transparent").pack(pady=(20, 4))

    # ── Title + subtitle ─────────────────────────────────────────────────
    from ui.styles import TITLE_FONT, BODY_FONT  # noqa: PLC0415
    ctk.CTkLabel(
        _panel,
        text="Purrductivity",
        font=TITLE_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
    ).pack(pady=(4, 2))

    ctk.CTkLabel(
        _panel,
        text="Your tasks will appear here.",
        font=BODY_FONT,
        text_color=DARK_TEXT,
        fg_color="transparent",
    ).pack(pady=4)

    ctk.CTkButton(
        _panel,
        text="Close",
        fg_color=SAGE_BUTTON,
        hover_color=BUTTON_HOVER,
        text_color=DARK_TEXT,
        corner_radius=12,
        command=_hide_panel,
    ).pack(pady=16)

    _panel.deiconify()
    _panel.after(100, _panel.lift)
