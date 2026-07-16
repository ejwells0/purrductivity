"""REM-05/REM-06: Progress math boundary and typical-case tests."""
from datetime import date

import pytest


# ---------------------------------------------------------------------------
# REM-05: weekly_expected_fraction boundary values
# ---------------------------------------------------------------------------

def test_weekly_fraction_monday():
    """Monday (weekday=0): weekly_expected_fraction returns 1/7."""
    from store import weekly_expected_fraction
    monday = date(2026, 3, 23)  # weekday() == 0
    result = weekly_expected_fraction(monday)
    assert abs(result - 1 / 7) < 1e-9


def test_weekly_fraction_wednesday():
    """Wednesday (weekday=2): weekly_expected_fraction returns 3/7."""
    from store import weekly_expected_fraction
    wednesday = date(2026, 3, 25)  # weekday() == 2
    result = weekly_expected_fraction(wednesday)
    assert abs(result - 3 / 7) < 1e-9


def test_weekly_fraction_sunday():
    """Sunday (weekday=6): weekly_expected_fraction returns 7/7 = 1.0."""
    from store import weekly_expected_fraction
    sunday = date(2026, 3, 29)  # weekday() == 6
    result = weekly_expected_fraction(sunday)
    assert result == 1.0


def test_weekly_fraction_tuesday():
    """Tuesday (weekday=1): weekly_expected_fraction returns 2/7."""
    from store import weekly_expected_fraction
    tuesday = date(2026, 3, 24)  # weekday() == 1
    result = weekly_expected_fraction(tuesday)
    assert abs(result - 2 / 7) < 1e-9


def test_weekly_fraction_saturday():
    """Saturday (weekday=5): weekly_expected_fraction returns 6/7."""
    from store import weekly_expected_fraction
    saturday = date(2026, 3, 28)  # weekday() == 5
    result = weekly_expected_fraction(saturday)
    assert abs(result - 6 / 7) < 1e-9


# ---------------------------------------------------------------------------
# REM-06: quarterly_expected_fraction boundary values
# ---------------------------------------------------------------------------

def test_quarterly_fraction_first_day_q1():
    """First day of Q1 (Jan 1): (days_elapsed + 1) / total_days = 1/90."""
    from store import quarterly_expected_fraction
    # Q1 2026 = Jan 1 .. Mar 31 = 90 days (2026 is not a leap year)
    jan1 = date(2026, 1, 1)
    result = quarterly_expected_fraction(jan1)
    assert abs(result - 1 / 90) < 1e-9


def test_quarterly_fraction_near_end_of_q1():
    """Near end of Q1 (Mar 22, day 80): returns (80 + 1) / 90 = 81/90."""
    from store import quarterly_expected_fraction
    # Mar 22 2026: days elapsed since Jan 1 = 80; fraction = (80 + 1) / 90
    mar22 = date(2026, 3, 22)
    days_elapsed = (mar22 - date(2026, 1, 1)).days  # should be 80
    assert days_elapsed == 80
    result = quarterly_expected_fraction(mar22)
    assert abs(result - 81 / 90) < 1e-9


def test_quarterly_fraction_capped_at_one():
    """Last day of the quarter: returns exactly 1.0 (capped by min())."""
    from store import quarterly_expected_fraction
    # Q1 2026 last day = Mar 31: days_elapsed = 89, (89 + 1) / 90 = 1.0
    mar31 = date(2026, 3, 31)
    days_elapsed = (mar31 - date(2026, 1, 1)).days
    assert days_elapsed == 89
    result = quarterly_expected_fraction(mar31)
    assert result == 1.0


def test_quarterly_fraction_first_day_q2():
    """First day of Q2 (Apr 1): returns 1/91 (Q2 2026 = Apr 1 .. Jun 30 = 91 days)."""
    from store import quarterly_expected_fraction
    apr1 = date(2026, 4, 1)
    result = quarterly_expected_fraction(apr1)
    assert abs(result - 1 / 91) < 1e-9


def test_quarterly_fraction_never_exceeds_one():
    """quarterly_expected_fraction never returns > 1.0."""
    from store import quarterly_expected_fraction
    # Test a full set of dates spanning a quarter
    for day_offset in range(0, 95):
        d = date(2026, 1, 1)
        from datetime import timedelta
        d = d + timedelta(days=day_offset)
        result = quarterly_expected_fraction(d)
        assert result <= 1.0, f"Got {result} > 1.0 for {d}"


# ---------------------------------------------------------------------------
# REM-05: is_behind for weekly tasks at exact threshold
# ---------------------------------------------------------------------------

def test_is_behind_weekly_at_threshold_not_behind():
    """weekly_target=7, completed=3, Wednesday → expected=3.0 → NOT behind (3 < 3.0 is False)."""
    from store import is_behind
    task = {"type": "weekly", "weekly_target": 7, "completed_count": 3}
    wednesday = date(2026, 3, 25)  # expected = 3/7 * 7 = 3.0
    assert is_behind(task, wednesday) is False


def test_is_behind_weekly_one_below_threshold_behind():
    """weekly_target=7, completed=2, Wednesday → expected=3.0 → behind."""
    from store import is_behind
    task = {"type": "weekly", "weekly_target": 7, "completed_count": 2}
    wednesday = date(2026, 3, 25)
    assert is_behind(task, wednesday) is True


# ---------------------------------------------------------------------------
# REM-06: is_behind for quarterly tasks
# ---------------------------------------------------------------------------

def test_is_behind_quarterly_at_threshold_not_behind():
    """progress=2 (%), first day Q1 → expected=1/90*100≈1.11 → NOT behind (2 >= 1.11)."""
    from store import is_behind
    # days_elapsed=0, fraction=1/90; expected_pct = 1/90*100 ≈ 1.11
    jan1 = date(2026, 1, 1)
    task = {"type": "quarterly", "progress": 2}
    assert is_behind(task, jan1) is False


def test_is_behind_quarterly_one_below_threshold_behind():
    """progress=1 (%), first day Q1 → expected≈1.11 → behind (1 < 1.11)."""
    from store import is_behind
    jan1 = date(2026, 1, 1)
    task = {"type": "quarterly", "progress": 1}
    assert is_behind(task, jan1) is True


# ---------------------------------------------------------------------------
# Non-goal types always return False
# ---------------------------------------------------------------------------

def test_is_behind_scheduled_returns_false():
    """is_behind returns False for type='scheduled' regardless of completed_count."""
    from store import is_behind
    task = {"type": "scheduled", "name": "Stand-up", "completed_count": 0}
    assert is_behind(task, date(2026, 3, 25)) is False


def test_is_behind_scheduled_high_count_still_false():
    """is_behind returns False for type='scheduled' even with high completed_count."""
    from store import is_behind
    task = {"type": "scheduled", "name": "Stand-up", "completed_count": 999}
    assert is_behind(task, date(2026, 3, 25)) is False


def test_is_behind_daily_returns_false():
    """is_behind returns False for type='daily' regardless of completed_count."""
    from store import is_behind
    task = {"type": "daily", "name": "Meditation", "completed_count": 0}
    assert is_behind(task, date(2026, 3, 25)) is False


def test_is_behind_daily_high_count_still_false():
    """is_behind returns False for type='daily' even with high completed_count."""
    from store import is_behind
    task = {"type": "daily", "name": "Meditation", "completed_count": 999}
    assert is_behind(task, date(2026, 3, 25)) is False
