"""Tests for store.py — TaskStore CRUD, progress math, concurrency."""
import threading
from datetime import date, datetime

import pytest


def test_taskstore_creates_fresh_db(tmp_path):
    """TaskStore creates a fresh in-memory db via tmp_path."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    assert store.get_all_tasks() == []
    store.close()


def test_add_task_scheduled_returns_uuid(tmp_path):
    """add_task for scheduled type returns a UUID string."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="scheduled",
        name="Stand-up",
        day_of_week=0,
        hour=9,
        minute=0,
        start_date="2026-03-25",
    )
    assert isinstance(task_id, str)
    assert len(task_id) == 36  # UUID format
    store.close()


def test_get_task_returns_expected_keys(tmp_path):
    """get_task returns dict with all expected keys."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="scheduled",
        name="Stand-up",
        day_of_week=0,
        hour=9,
        minute=0,
        start_date="2026-03-25",
    )
    task = store.get_task(task_id)
    expected_keys = {
        "id", "type", "name", "day_of_week", "hour", "minute", "start_date",
        "notes", "completed_count", "snoozed_until", "last_done", "paused",
    }
    assert expected_keys.issubset(set(task.keys()))
    store.close()


def test_add_task_daily(tmp_path):
    """add_task for daily type succeeds and get_task returns correct type."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="daily",
        name="Meditation",
        hour=8,
        minute=0,
        start_date="2026-03-25",
    )
    task = store.get_task(task_id)
    assert task["type"] == "daily"
    assert task["name"] == "Meditation"
    store.close()


def test_add_task_weekly(tmp_path):
    """add_task for weekly type succeeds."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="weekly",
        name="Report",
        weekly_target=3,
        hour=10,
        minute=0,
        start_date="2026-03-25",
    )
    task = store.get_task(task_id)
    assert task["type"] == "weekly"
    assert task["weekly_target"] == 3
    store.close()


def test_add_task_quarterly(tmp_path):
    """add_task for quarterly type succeeds."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="quarterly",
        name="OKRs",
        total_target=52,
        hour=9,
        minute=0,
        start_date="2026-03-25",
    )
    task = store.get_task(task_id)
    assert task["type"] == "quarterly"
    assert task["total_target"] == 52
    store.close()


def test_get_all_tasks_returns_list(tmp_path):
    """get_all_tasks returns list of all tasks."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    store.add_task(type="daily", name="Habit 1", hour=8, minute=0, start_date="2026-03-25")
    store.add_task(type="daily", name="Habit 2", hour=9, minute=0, start_date="2026-03-25")
    tasks = store.get_all_tasks()
    assert len(tasks) == 2
    store.close()


def test_update_snooze(tmp_path):
    """update_snooze sets snoozed_until to ISO string."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="scheduled", name="Stand-up", day_of_week=0, hour=9, minute=0, start_date="2026-03-25"
    )
    until = datetime(2026, 3, 25, 15, 45)
    store.update_snooze(task_id, until)
    task = store.get_task(task_id)
    assert task["snoozed_until"] == "2026-03-25T15:45:00"
    store.close()


def test_mark_done(tmp_path):
    """mark_done increments completed_count, sets last_done, clears snoozed_until."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="daily", name="Meditation", hour=8, minute=0, start_date="2026-03-25"
    )
    # First snooze it
    store.update_snooze(task_id, datetime(2026, 3, 25, 9, 0))
    # Now mark done
    store.mark_done(task_id)
    task = store.get_task(task_id)
    assert task["completed_count"] == 1
    assert task["last_done"] is not None
    assert task["snoozed_until"] is None
    store.close()


def test_weekly_expected_fraction_wednesday(tmp_path):
    """Wednesday (weekday=2) returns 3/7."""
    from store import weekly_expected_fraction
    wednesday = date(2026, 3, 25)  # weekday() == 2
    assert weekly_expected_fraction(wednesday) == 3 / 7


def test_weekly_expected_fraction_monday(tmp_path):
    """Monday (weekday=0) returns 1/7."""
    from store import weekly_expected_fraction
    monday = date(2026, 3, 23)  # weekday() == 0
    assert weekly_expected_fraction(monday) == 1 / 7


def test_weekly_expected_fraction_sunday(tmp_path):
    """Sunday (weekday=6) returns 7/7 == 1.0."""
    from store import weekly_expected_fraction
    sunday = date(2026, 3, 29)  # weekday() == 6
    assert weekly_expected_fraction(sunday) == 1.0


def test_quarterly_expected_fraction_first_day_q2(tmp_path):
    """First day of Q2 2026 (2026-04-01) returns value > 0 and <= 1/13."""
    from store import quarterly_expected_fraction
    first_day_q2 = date(2026, 4, 1)
    result = quarterly_expected_fraction(first_day_q2)
    assert result > 0
    assert result <= 1 / 13


def test_is_behind_weekly_behind(tmp_path):
    """Weekly task is behind when completed_count < expected."""
    from store import is_behind
    task = {"type": "weekly", "weekly_target": 7, "completed_count": 2}
    wednesday = date(2026, 3, 25)  # expected = 3/7 * 7 = 3; actual = 2 → behind
    assert is_behind(task, wednesday) is True


def test_is_behind_weekly_not_behind(tmp_path):
    """Weekly task not behind when completed_count >= expected."""
    from store import is_behind
    task = {"type": "weekly", "weekly_target": 7, "completed_count": 3}
    wednesday = date(2026, 3, 25)  # expected = 3/7 * 7 = 3; actual = 3 → not behind
    assert is_behind(task, wednesday) is False


def test_is_behind_scheduled_never_behind(tmp_path):
    """Non-goal task types (scheduled) are never behind."""
    from store import is_behind
    task = {"type": "scheduled", "name": "Stand-up", "completed_count": 0}
    assert is_behind(task, date(2026, 3, 25)) is False


def test_concurrent_writes_no_corruption(tmp_path):
    """Concurrent calls to update_snooze do not corrupt data."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(
        type="daily", name="Concurrent Test", hour=8, minute=0, start_date="2026-03-25"
    )
    errors = []

    def worker(n):
        try:
            for _ in range(50):
                store.update_snooze(task_id, datetime(2026, 3, 25, 15, n % 60))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Concurrent write errors: {errors}"
    store.close()


def test_update_task_sets_paused_true(tmp_path):
    """update_task(paused=True) persists to store."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(type="daily", name="Habit", hour=8, minute=0, start_date="2026-03-25")
    store.update_task(task_id, paused=True)
    task = store.get_task(task_id)
    assert task["paused"] is True
    store.close()


def test_update_task_sets_paused_false(tmp_path):
    """update_task(paused=False) after True restores paused=False."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    task_id = store.add_task(type="daily", name="Habit", hour=8, minute=0, start_date="2026-03-25")
    store.update_task(task_id, paused=True)
    store.update_task(task_id, paused=False)
    task = store.get_task(task_id)
    assert task["paused"] is False
    store.close()


def test_get_active_tasks_excludes_paused(tmp_path):
    """get_active_tasks does not include tasks with paused=True."""
    from store import TaskStore
    store = TaskStore(db_path=tmp_path / "tasks.db")
    id1 = store.add_task(type="daily", name="Active", hour=8, minute=0, start_date="2026-03-25")
    id2 = store.add_task(type="daily", name="Paused", hour=9, minute=0, start_date="2026-03-25")
    store.update_task(id2, paused=True)
    active = store.get_active_tasks()
    active_ids = [t["id"] for t in active]
    assert id1 in active_ids
    assert id2 not in active_ids
    store.close()


def test_is_behind_quarterly_uses_progress_field(tmp_path):
    """is_behind for quarterly uses task['progress'] (0-100) not completed_count/total_target."""
    from datetime import date
    from store import is_behind
    # Q2 2026 start: quarterly_expected_fraction ≈ 0.077 → expected% ≈ 7.7
    q2_start = date(2026, 4, 1)
    behind_task = {"type": "quarterly", "progress": 5}   # 5 < 7.7 → behind
    on_track_task = {"type": "quarterly", "progress": 95}  # 95 >= 7.7 → not behind
    assert is_behind(behind_task, q2_start) is True
    assert is_behind(on_track_task, q2_start) is False
