"""Tests for ui/reminder_popup._get_tone_message — tone message generation.

All tests import _get_tone_message inside the function body to avoid CTk init issues.
These tests are RED (failing) in Wave 0 — _get_tone_message does not exist yet.
Wave 1 will implement the function to make them green.
"""
from datetime import date


def test_get_tone_message_weekly_behind():
    """Weekly task behind schedule → result contains '😾' (harsh message)."""
    from ui.reminder_popup import _get_tone_message
    # Wednesday 2026-03-25: weekday()=2, weekly_expected_fraction=3/7
    # weekly_target=7 → expected=3; completed_count=1 → behind (1 < 3)
    task = {
        "type": "weekly",
        "name": "Exercise",
        "weekly_target": 7,
        "completed_count": 1,
    }
    result = _get_tone_message(task, today=date(2026, 3, 25))
    assert "😾" in result, f"Expected '😾' in harsh message, got: {result!r}"


def test_get_tone_message_weekly_on_track():
    """Weekly task on track → result contains '🐾' (friendly message)."""
    from ui.reminder_popup import _get_tone_message
    # Wednesday 2026-03-25: weekly_expected_fraction=3/7
    # weekly_target=7 → expected=3; completed_count=3 → on track (3 >= 3)
    task = {
        "type": "weekly",
        "name": "Exercise",
        "weekly_target": 7,
        "completed_count": 3,
    }
    result = _get_tone_message(task, today=date(2026, 3, 25))
    assert "🐾" in result, f"Expected '🐾' in friendly message, got: {result!r}"


def test_get_tone_message_quarterly_behind():
    """Quarterly task behind schedule → result contains '😾' (harsh message)."""
    from ui.reminder_popup import _get_tone_message
    # Q2 2026 start: date(2026,4,1), quarterly_expected_fraction ≈ 0.077 → expected% ≈ 7.7
    # progress=5 → behind (5 < 7.7)
    task = {
        "type": "quarterly",
        "name": "Learn Piano",
        "progress": 5,
    }
    result = _get_tone_message(task, today=date(2026, 4, 1))
    assert "😾" in result, f"Expected '😾' in harsh message, got: {result!r}"


def test_get_tone_message_quarterly_on_track():
    """Quarterly task on track → result contains '🐾' (friendly message)."""
    from ui.reminder_popup import _get_tone_message
    # Q2 2026 start: date(2026,4,1), quarterly_expected_fraction ≈ 0.077 → expected% ≈ 7.7
    # progress=95 → on track (95 >= 7.7)
    task = {
        "type": "quarterly",
        "name": "Learn Piano",
        "progress": 95,
    }
    result = _get_tone_message(task, today=date(2026, 4, 1))
    assert "🐾" in result, f"Expected '🐾' in friendly message, got: {result!r}"


def test_get_tone_message_non_goal_passthrough():
    """Non-goal task (scheduled/daily) → returns a non-empty string from _CAT_MESSAGES pool."""
    from ui.reminder_popup import _get_tone_message
    task = {"type": "scheduled", "name": "Stand-up"}
    result = _get_tone_message(task)
    assert isinstance(result, str), f"Expected str, got {type(result)}"
    assert len(result) > 0, "Expected non-empty string for non-goal task"
