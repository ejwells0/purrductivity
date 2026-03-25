# ui/styles.py
# Cat-themed pastel palette for Purrductivity (TONE-03)
# Source: Phase 1 Research — Pattern 4: Pastel Style Constants
import customtkinter as ctk

# ── Palette ──────────────────────────────────────────────────────────────────
LAVENDER_BG   = "#E8D5F5"   # Soft lavender — main background
PEACH_ACCENT  = "#FFD4B8"   # Warm peach — accent / highlight
CREAM_TEXT    = "#5C4A6B"   # Deep muted purple — readable on lavender
BORDER_COLOR  = "#C9A8E0"   # Slightly deeper lavender — borders
WHITE_CARD    = "#FFF8F2"   # Near-cream white — card backgrounds

# ── Fonts ─────────────────────────────────────────────────────────────────────
# SF Pro is the macOS system font; falls back to Helvetica if unavailable.
# CustomTkinter accepts family names directly — safe to specify even if font
# resolution happens at render time.
#
# NOTE: CTkFont requires a tkinter root to exist at instantiation time.
# Fonts are created lazily on first access so that importing styles.py
# (e.g. in tests) does not crash before the tkinter daemon thread is running.
_TITLE_FONT = None
_BODY_FONT = None
_SMALL_FONT = None


def _get_title_font():
    global _TITLE_FONT
    if _TITLE_FONT is None:
        _TITLE_FONT = ctk.CTkFont(family="SF Pro Rounded", size=18, weight="bold")
    return _TITLE_FONT


def _get_body_font():
    global _BODY_FONT
    if _BODY_FONT is None:
        _BODY_FONT = ctk.CTkFont(family="SF Pro Text", size=14)
    return _BODY_FONT


def _get_small_font():
    global _SMALL_FONT
    if _SMALL_FONT is None:
        _SMALL_FONT = ctk.CTkFont(family="SF Pro Text", size=12)
    return _SMALL_FONT


class _LazyFont:
    """Descriptor that creates a CTkFont on first attribute access."""
    def __init__(self, getter):
        self._getter = getter

    def __get__(self, obj, objtype=None):
        return self._getter()


# Module-level names that behave like CTkFont instances but are lazy.
# panel.py and other UI code can use TITLE_FONT, BODY_FONT, SMALL_FONT
# directly as CTkFont values — they will be created on first use.
class _FontProxy:
    TITLE_FONT = _LazyFont(_get_title_font)
    BODY_FONT  = _LazyFont(_get_body_font)
    SMALL_FONT = _LazyFont(_get_small_font)


# Expose as module-level names via a simpler approach: plain callables.
# panel.py imports TITLE_FONT and passes it to CTkLabel(font=TITLE_FONT).
# Since CTkFont is lazy, access must happen after tk_host starts.
# Use module __getattr__ for lazy resolution.
import sys as _sys
_this = _sys.modules[__name__]


def __getattr__(name):
    if name == "TITLE_FONT":
        return _get_title_font()
    if name == "BODY_FONT":
        return _get_body_font()
    if name == "SMALL_FONT":
        return _get_small_font()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
