"""TONE-04: Phase 2 style constants — BADGE_DOT and DESTRUCTIVE."""
import re

import pytest

HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_badge_dot_importable():
    """BADGE_DOT is importable without a tkinter root."""
    from ui.styles import BADGE_DOT  # noqa: PLC0415
    assert BADGE_DOT is not None


def test_badge_dot_value():
    """BADGE_DOT equals the expected hex value from UI spec (TONE-04)."""
    from ui.styles import BADGE_DOT  # noqa: PLC0415
    assert BADGE_DOT == "#E8748A"


def test_destructive_importable():
    """DESTRUCTIVE is importable without a tkinter root."""
    from ui.styles import DESTRUCTIVE  # noqa: PLC0415
    assert DESTRUCTIVE is not None


def test_destructive_value():
    """DESTRUCTIVE equals the expected hex value."""
    from ui.styles import DESTRUCTIVE  # noqa: PLC0415
    assert DESTRUCTIVE == "#C0392B"


def test_existing_constants_still_importable():
    """All existing Phase 1 constants remain importable and unchanged."""
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
    assert SAGE_BG == "#C8D5BC"
    assert SAGE_CARD == "#EEF3E8"
    assert DARK_TEXT == "#4A5240"
    assert SAGE_BUTTON == "#A8C49A"
    assert BUTTON_HOVER == "#8FAE80"
    assert BORDER_COLOR == "#9CB88C"
    assert CAT_CREAM == "#F5EFE0"
    assert CAT_PINK == "#F0C0C8"
    assert CAT_OUTLINE == "#C4A882"


def test_new_constants_are_valid_hex():
    """BADGE_DOT and DESTRUCTIVE match valid #RRGGBB hex pattern."""
    from ui.styles import BADGE_DOT, DESTRUCTIVE  # noqa: PLC0415
    assert HEX_PATTERN.match(BADGE_DOT), f"BADGE_DOT={BADGE_DOT!r} is not valid #RRGGBB hex"
    assert HEX_PATTERN.match(DESTRUCTIVE), f"DESTRUCTIVE={DESTRUCTIVE!r} is not valid #RRGGBB hex"
