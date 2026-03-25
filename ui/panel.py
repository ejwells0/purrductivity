# ui/panel.py
# Main panel — frameless CTkToplevel with kawaii cat face, positioned top-right.
# MUST be called from the tkinter thread (via enqueue). Never call directly from
# app.py or scheduler.py.
import tkinter as tk
import customtkinter as ctk
from AppKit import NSScreen

from ui.styles import (
    SAGE_BG, DARK_TEXT, SAGE_BUTTON, BUTTON_HOVER,
    CAT_CREAM, CAT_PINK, CAT_OUTLINE,
)

PANEL_WIDTH  = 340
PANEL_HEIGHT = 480

_panel: ctk.CTkToplevel | None = None


def _hide_panel() -> None:
    """Hide the panel without destroying it."""
    if _panel is not None and _panel.winfo_exists():
        _panel.withdraw()


def _draw_cat_face(parent: ctk.CTkFrame) -> tk.Canvas:
    """Draw a kawaii cat face on a Canvas and return it."""
    w, h = 160, 148
    canvas = tk.Canvas(parent, width=w, height=h, bg=SAGE_BG, highlightthickness=0)

    cx, cy = w // 2, h // 2 + 8   # head center — shifted down so ears fit above
    rx, ry = 44, 40                # head radii

    # ── Ears (drawn first so head overlaps the bases) ─────────────────────
    ear_top_y = cy - ry - 20
    # Left ear — outer
    canvas.create_polygon(
        cx - rx + 4,      cy - ry + 8,
        cx - rx // 2 - 2, ear_top_y,
        cx - 4,           cy - ry + 4,
        fill=CAT_CREAM, outline=CAT_OUTLINE, width=2,
    )
    # Left ear — inner pink
    canvas.create_polygon(
        cx - rx + 12,     cy - ry + 7,
        cx - rx // 2 - 2, ear_top_y + 10,
        cx - 10,          cy - ry + 5,
        fill=CAT_PINK, outline="",
    )
    # Right ear — outer
    canvas.create_polygon(
        cx + 4,           cy - ry + 4,
        cx + rx // 2 + 2, ear_top_y,
        cx + rx - 4,      cy - ry + 8,
        fill=CAT_CREAM, outline=CAT_OUTLINE, width=2,
    )
    # Right ear — inner pink
    canvas.create_polygon(
        cx + 10,          cy - ry + 5,
        cx + rx // 2 + 2, ear_top_y + 10,
        cx + rx - 12,     cy - ry + 7,
        fill=CAT_PINK, outline="",
    )

    # ── Head ──────────────────────────────────────────────────────────────
    canvas.create_oval(
        cx - rx, cy - ry, cx + rx, cy + ry,
        fill=CAT_CREAM, outline=CAT_OUTLINE, width=2,
    )

    # ── Eyes ──────────────────────────────────────────────────────────────
    eye_y   = cy - 8
    eye_off = 14
    eye_r   = 8
    for ex in (cx - eye_off, cx + eye_off):
        canvas.create_oval(
            ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r,
            fill="#3D3530", outline="",
        )
        # Sparkle highlight
        canvas.create_oval(ex + 2, eye_y - 5, ex + 6, eye_y - 1, fill="white", outline="")

    # ── Nose ──────────────────────────────────────────────────────────────
    nose_y = cy + 10
    canvas.create_polygon(
        cx, nose_y - 4,
        cx - 5, nose_y + 3,
        cx + 5, nose_y + 3,
        fill=CAT_PINK, outline="",
    )

    # ── Mouth (W-shape) ──────────────────────────────────────────────────
    canvas.create_line(
        cx - 8, nose_y + 6,
        cx - 3, nose_y + 11,
        cx,     nose_y + 7,
        cx + 3, nose_y + 11,
        cx + 8, nose_y + 6,
        fill=CAT_OUTLINE, width=2, smooth=True,
    )

    # ── Whiskers (3 per side) ─────────────────────────────────────────────
    for dy in (-6, 0, 6):
        canvas.create_line(
            cx - 44, nose_y + dy, cx - 14, nose_y + dy // 2,
            fill=CAT_OUTLINE, width=1,
        )
        canvas.create_line(
            cx + 44, nose_y + dy, cx + 14, nose_y + dy // 2,
            fill=CAT_OUTLINE, width=1,
        )

    # ── Blush ─────────────────────────────────────────────────────────────
    for bx in (cx - 24, cx + 24):
        canvas.create_oval(bx - 10, eye_y + 6, bx + 10, eye_y + 14, fill=CAT_PINK, outline="")

    return canvas


def open_panel() -> None:
    """
    Open (or un-hide) the main panel anchored top-right.
    Must be called from the tkinter thread (via enqueue).
    """
    global _panel
    from ui.tk_host import get_root

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
    # Hide on close (both native X button and Cmd+W)
    _panel.protocol("WM_DELETE_WINDOW", _hide_panel)
    _panel.bind("<Command-w>", lambda _e: _hide_panel())

    # ── Cat face ─────────────────────────────────────────────────────────
    cat_canvas = _draw_cat_face(_panel)
    cat_canvas.pack(pady=(20, 4))

    # ── Title ─────────────────────────────────────────────────────────────
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
