"""TONE-03: Style constants are valid hex colors."""
import pytest
import re

HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_color_constants():
    """All color constants in styles.py are valid 6-digit hex strings."""
    from ui.styles import (  # noqa: PLC0415
        SAGE_BG,
        SAGE_CARD,
        DARK_TEXT,
        SAGE_BUTTON,
        BUTTON_HOVER,
        BORDER_COLOR,
        CAT_CREAM,
        CAT_PINK,
        CAT_OUTLINE,
    )
    constants = {
        "SAGE_BG":      SAGE_BG,
        "SAGE_CARD":    SAGE_CARD,
        "DARK_TEXT":    DARK_TEXT,
        "SAGE_BUTTON":  SAGE_BUTTON,
        "BUTTON_HOVER": BUTTON_HOVER,
        "BORDER_COLOR": BORDER_COLOR,
        "CAT_CREAM":    CAT_CREAM,
        "CAT_PINK":     CAT_PINK,
        "CAT_OUTLINE":  CAT_OUTLINE,
    }
    for name, value in constants.items():
        assert HEX_PATTERN.match(value), f"{name}={value!r} is not a valid #RRGGBB hex"

    assert SAGE_BG == "#C8D5BC"
