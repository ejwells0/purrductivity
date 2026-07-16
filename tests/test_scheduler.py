"""Tests for scheduler.py — APScheduler job registration, snooze, overdue check."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tasks):
    """Return a mock TaskStore whose get_active_tasks() returns the given list."""
    store = MagicMock()
    store.get_active_tasks.return_value = tasks
    return store


def _scheduled_task(task_id="task-1"):
    return {
        "id": task_id,
        "type": "scheduled",
        "name": "Stand-up",
        "day_of_week": 0,
        "hour": 9,
        "minute": 0,
        "snoozed_until": None,
        "paused": False,
    }


def _daily_task(task_id="task-2"):
    return {
        "id": task_id,
        "type": "daily",
        "name": "Meditation",
        "hour": 8,
        "minute": 0,
        "snoozed_until": None,
        "paused": False,
    }


def _weekly_task(task_id="task-3"):
    return {
        "id": task_id,
        "type": "weekly",
        "name": "Report",
        "weekly_target": 3,
        "hour": 10,
        "minute": 0,
        "snoozed_until": None,
        "paused": False,
    }


def _quarterly_task(task_id="task-4"):
    return {
        "id": task_id,
        "type": "quarterly",
        "name": "OKRs",
        "total_target": 52,
        "check_in_enabled": True,
        "check_in_dow": 0,
        "hour": 9,
        "minute": 0,
        "snoozed_until": None,
        "paused": False,
    }


# ---------------------------------------------------------------------------
# Test: empty store — no jobs registered
# ---------------------------------------------------------------------------

def test_empty_store_no_jobs():
    """With no tasks in store, _load_jobs registers no jobs."""
    from scheduler import ReminderScheduler

    store = _make_store([])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    with patch("scheduler.enqueue") as mock_enqueue:
        sched._load_jobs()

    mock_bg.add_job.assert_not_called()
    mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# Test: scheduled task registers job with correct id
# ---------------------------------------------------------------------------

def test_scheduled_task_registers_cron_job():
    """A scheduled task registers a job with id f'task_{task_id}'."""
    from scheduler import ReminderScheduler
    from apscheduler.triggers.cron import CronTrigger

    task = _scheduled_task("abc-123")
    store = _make_store([task])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    # Patch enqueue and _compute_next_cron_fire to return a future time (not overdue)
    future = datetime.now() + timedelta(hours=1)
    with patch("scheduler.enqueue"), patch("scheduler._compute_next_cron_fire", return_value=future):
        sched._load_jobs()

    job_ids = [call_args[1]["id"] for call_args in mock_bg.add_job.call_args_list]
    assert "task_abc-123" in job_ids


# ---------------------------------------------------------------------------
# Test: daily task registers CronTrigger job
# ---------------------------------------------------------------------------

def test_daily_task_registers_cron_job():
    """A daily task registers a CronTrigger job."""
    from scheduler import ReminderScheduler
    from apscheduler.triggers.cron import CronTrigger

    task = _daily_task("daily-1")
    store = _make_store([task])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    future = datetime.now() + timedelta(hours=1)
    with patch("scheduler.enqueue"), patch("scheduler._compute_next_cron_fire", return_value=future):
        sched._load_jobs()

    mock_bg.add_job.assert_called_once()
    call_kwargs = mock_bg.add_job.call_args[1]
    assert call_kwargs["id"] == "task_daily-1"
    # trigger should be a CronTrigger instance
    assert isinstance(call_kwargs["trigger"], CronTrigger)


# ---------------------------------------------------------------------------
# Test: weekly task registers CronTrigger job
# ---------------------------------------------------------------------------

def test_weekly_task_registers_cron_job():
    """A weekly task registers a CronTrigger job."""
    from scheduler import ReminderScheduler
    from apscheduler.triggers.cron import CronTrigger

    task = _weekly_task("weekly-1")
    store = _make_store([task])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    future = datetime.now() + timedelta(hours=1)
    with patch("scheduler.enqueue"), patch("scheduler._compute_next_cron_fire", return_value=future):
        sched._load_jobs()

    mock_bg.add_job.assert_called_once()
    call_kwargs = mock_bg.add_job.call_args[1]
    assert isinstance(call_kwargs["trigger"], CronTrigger)


# ---------------------------------------------------------------------------
# Test: quarterly task registers CronTrigger job
# ---------------------------------------------------------------------------

def test_quarterly_task_registers_cron_job():
    """A quarterly task registers a CronTrigger job."""
    from scheduler import ReminderScheduler
    from apscheduler.triggers.cron import CronTrigger

    task = _quarterly_task("qtr-1")
    store = _make_store([task])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    future = datetime.now() + timedelta(hours=1)
    with patch("scheduler.enqueue"), patch("scheduler._compute_next_cron_fire", return_value=future):
        sched._load_jobs()

    mock_bg.add_job.assert_called_once()
    call_kwargs = mock_bg.add_job.call_args[1]
    assert isinstance(call_kwargs["trigger"], CronTrigger)


# ---------------------------------------------------------------------------
# Test: future snooze registers DateTrigger job
# ---------------------------------------------------------------------------

def test_future_snooze_registers_date_trigger():
    """A task with future snoozed_until registers a DateTrigger snooze job."""
    from scheduler import ReminderScheduler
    from apscheduler.triggers.date import DateTrigger

    future_dt = datetime.now() + timedelta(minutes=15)
    task = _daily_task("snoozed-1")
    task["snoozed_until"] = future_dt.isoformat()

    store = _make_store([task])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    with patch("scheduler.enqueue") as mock_enqueue:
        sched._load_jobs()

    # Should register a snooze job, not call enqueue immediately
    mock_enqueue.assert_not_called()
    mock_bg.add_job.assert_called_once()
    call_kwargs = mock_bg.add_job.call_args[1]
    assert call_kwargs["id"] == "snooze_snoozed-1"
    assert isinstance(call_kwargs["trigger"], DateTrigger)


# ---------------------------------------------------------------------------
# Test: past snooze fires immediately via enqueue
# ---------------------------------------------------------------------------

def test_past_snooze_fires_immediately():
    """A task with past snoozed_until calls enqueue immediately (overdue snooze)."""
    from scheduler import ReminderScheduler

    past_dt = datetime.now() - timedelta(minutes=30)
    task = _daily_task("overdue-snoozed")
    task["snoozed_until"] = past_dt.isoformat()

    store = _make_store([task])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    with patch("scheduler.enqueue") as mock_enqueue:
        sched._load_jobs()

    # Should call enqueue immediately, NOT add a DateTrigger job
    mock_enqueue.assert_called_once_with("show_reminder", task_id="overdue-snoozed")
    mock_bg.add_job.assert_not_called()


# ---------------------------------------------------------------------------
# Test: schedule_snooze adds DateTrigger job ~N minutes from now
# ---------------------------------------------------------------------------

def test_schedule_snooze_adds_date_trigger_job():
    """schedule_snooze(task_id, 15) adds a DateTrigger job 15min from now."""
    from scheduler import ReminderScheduler
    from apscheduler.triggers.date import DateTrigger

    store = _make_store([])
    sched = ReminderScheduler(store)

    mock_bg = MagicMock()
    sched._scheduler = mock_bg

    before = datetime.now()
    sched.schedule_snooze("mytask", 15)
    after = datetime.now()

    mock_bg.add_job.assert_called_once()
    call_kwargs = mock_bg.add_job.call_args[1]
    assert call_kwargs["id"] == "snooze_mytask"
    assert isinstance(call_kwargs["trigger"], DateTrigger)
    # Verify the run_date is approximately 15 minutes from now
    run_date = call_kwargs["trigger"].run_date
    # APScheduler may return timezone-aware datetime; normalise to naive for comparison
    if run_date.tzinfo is not None:
        run_date = run_date.replace(tzinfo=None)
    expected_min = before + timedelta(minutes=14, seconds=59)
    expected_max = after + timedelta(minutes=15, seconds=1)
    assert expected_min <= run_date <= expected_max


# ---------------------------------------------------------------------------
# Test: _fire_reminder calls enqueue("show_reminder", task_id=...)
# ---------------------------------------------------------------------------

def test_fire_reminder_calls_enqueue():
    """_fire_reminder calls enqueue('show_reminder', task_id=task_id)."""
    with patch("scheduler.enqueue") as mock_enqueue:
        from scheduler import _fire_reminder
        _fire_reminder("test-task-99")
    mock_enqueue.assert_called_once_with("show_reminder", task_id="test-task-99")


# ---------------------------------------------------------------------------
# Test: ReminderScheduler does NOT auto-start BackgroundScheduler on init
# ---------------------------------------------------------------------------

def test_scheduler_not_started_on_init():
    """Creating ReminderScheduler does not start the BackgroundScheduler."""
    from scheduler import ReminderScheduler

    store = _make_store([])
    with patch("scheduler.BackgroundScheduler") as MockBS:
        mock_instance = MagicMock()
        MockBS.return_value = mock_instance
        sched = ReminderScheduler(store)

    # start() should NOT have been called during __init__
    mock_instance.start.assert_not_called()
