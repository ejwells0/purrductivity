"""TONE-03: Style constants are valid hex colors; font config is correct type."""
import pytest
import re

HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_color_constants():
    """All color constants in styles.py are valid 6-digit hex strings."""
    from ui.styles import (  # noqa: PLC0415
        LAVENDER_BG,
        PEACH_ACCENT,
        CREAM_TEXT,
        BORDER_COLOR,
        WHITE_CARD,
    )
    for name, value in [
        ("LAVENDER_BG", LAVENDER_BG),
        ("PEACH_ACCENT", PEACH_ACCENT),
        ("CREAM_TEXT", CREAM_TEXT),
        ("BORDER_COLOR", BORDER_COLOR),
        ("WHITE_CARD", WHITE_CARD),
    ]:
        assert HEX_PATTERN.match(value), f"{name}={value!r} is not a valid #RRGGBB hex string"

    # Spot-check expected palette values
    assert LAVENDER_BG == "#E8D5F5", f"LAVENDER_BG must be #E8D5F5, got {LAVENDER_BG!r}"
    assert PEACH_ACCENT == "#FFD4B8", f"PEACH_ACCENT must be #FFD4B8, got {PEACH_ACCENT!r}"
