# ui/styles.py
# Sage & cream kawaii palette (TONE-03)
import customtkinter as ctk

# ── Palette ──────────────────────────────────────────────────────────────────
SAGE_BG       = "#C8D5BC"   # Muted sage green — panel background
SAGE_CARD     = "#EEF3E8"   # Light sage — card / secondary surfaces
DARK_TEXT     = "#4A5240"   # Dark sage — readable on sage bg
SAGE_BUTTON   = "#A8C49A"   # Medium sage — button fill
BUTTON_HOVER  = "#8FAE80"   # Deeper sage — button hover
BORDER_COLOR  = "#9CB88C"   # Sage border

# Cat drawing palette
CAT_CREAM     = "#F5EFE0"   # Cat face fill
CAT_PINK      = "#F0C0C8"   # Inner ears, blush, nose
CAT_OUTLINE   = "#C4A882"   # Cat linework / whiskers

# Menu bar and action palette
BADGE_DOT     = "#E8748A"   # Pending-reminder dot on menu bar icon (TONE-04)
DESTRUCTIVE   = "#C0392B"   # Phase 3 delete/remove actions — defined now, unused in Phase 2

# ── Fonts ─────────────────────────────────────────────────────────────────────
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
    def __init__(self, getter):
        self._getter = getter

    def __get__(self, obj, objtype=None):
        return self._getter()


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
