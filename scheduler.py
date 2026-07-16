# scheduler.py
# APScheduler BackgroundScheduler — replaces Phase 1 rumps.Timer stub.
# Source: Phase 2 Research — Pattern 2 (APScheduler setup), Pattern 3 (overdue check),
#         Pitfall 1 (spawn guard), Pitfall 2 (threading lock in TaskStore), Pitfall 6 (snooze)
#
# CRITICAL: All job callbacks must complete in under 5ms.
# Only enqueue() calls are allowed in callbacks — no blocking I/O.
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from store import TaskStore
from ui.tk_host import enqueue

log = logging.getLogger(__name__)

# APScheduler day_of_week string mapping (0=Mon..6=Sun -> "mon".."sun")
_DOW_MAP = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}


class ReminderScheduler:
    def __init__(self, store: TaskStore) -> None:
        self._store = store
        self._scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "misfire_grace_time": 300,
                "max_instances": 1,
            },
            logger=log,
        )

    def start(self) -> None:
        """Start the BackgroundScheduler and load all jobs from TaskStore."""
        self._scheduler.start()
        self._load_jobs()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ── Job loading ───────────────────────────────────────────────────

    def _load_jobs(self) -> None:
        """Read all active tasks from TaskStore and register APScheduler jobs."""
        now = datetime.now()
        for task in self._store.get_active_tasks():
            task_id = task["id"]

            # If snoozed: schedule one-shot re-fire at snoozed_until
            if task.get("snoozed_until"):
                fire_at = datetime.fromisoformat(task["snoozed_until"])
                if fire_at <= now:
                    # Overdue snooze: clear the stale DB field immediately so the
                    # badge reflects _pending_badge_state rather than a stale snooze,
                    # then fire the popup and light the badge.
                    self._store.clear_snooze(task_id)
                    enqueue("show_reminder", task_id=task_id)
                    from app import request_badge_update  # noqa: PLC0415
                    request_badge_update(True)
                else:
                    self._add_snooze_job(task_id, fire_at)
                continue  # skip regular cron job while snoozed

            # Compute next_fire to detect overdue regular reminders
            next_fire = _compute_next_cron_fire(task)
            if next_fire and next_fire <= now:
                enqueue("show_reminder", task_id=task_id)
                from app import request_badge_update  # noqa: PLC0415
                request_badge_update(True)
                # Still register cron job so future fires continue
            self._add_cron_job(task)

    def _add_cron_job(self, task: dict) -> None:
        """Register a recurring CronTrigger job for a task."""
        task_id = task["id"]
        t = task["type"]
        hour = task.get("hour", 9)
        minute = task.get("minute", 0)

        if t == "scheduled":
            dow = _DOW_MAP[task["day_of_week"]]
            end_date_str = task.get("end_date", "")
            end_dt = datetime.fromisoformat(end_date_str + "T23:59:59") if end_date_str else None
            trigger = CronTrigger(day_of_week=dow, hour=hour, minute=minute, end_date=end_dt)
        elif t == "daily":
            end_date_str = task.get("end_date", "")
            end_dt = datetime.fromisoformat(end_date_str + "T23:59:59") if end_date_str else None
            trigger = CronTrigger(hour=hour, minute=minute, end_date=end_dt)
        elif t == "monthly":
            day_of_month = task.get("day_of_month", 1)
            end_date_str = task.get("end_date", "")
            end_dt = datetime.fromisoformat(end_date_str + "T23:59:59") if end_date_str else None
            trigger = CronTrigger(day=day_of_month, hour=hour, minute=minute, end_date=end_dt)
        elif t == "weekly":
            dow = _DOW_MAP.get(task.get("day_of_week", 0), "mon")
            end_date_str = task.get("end_date", "")
            end_dt = datetime.fromisoformat(end_date_str + "T23:59:59") if end_date_str else None
            trigger = CronTrigger(day_of_week=dow, hour=hour, minute=minute, end_date=end_dt)
        elif t == "quarterly":
            if not task.get("check_in_enabled", False):
                return  # no recurring popup when check-in is disabled
            check_in_dow = _DOW_MAP.get(task.get("check_in_dow", 0), "mon")
            trigger = CronTrigger(day_of_week=check_in_dow, hour=hour, minute=minute)
        elif t == "one_time":
            due_str = task.get("due_date")
            if not due_str:
                return
            try:
                due_d = date.fromisoformat(due_str)
                fire_dt = datetime(due_d.year, due_d.month, due_d.day, hour, minute)
            except (ValueError, TypeError):
                return
            if fire_dt <= datetime.now():
                return  # already past
            trigger = DateTrigger(run_date=fire_dt)
        else:
            log.warning("Unknown task type %r — skipping job registration", t)
            return

        self._scheduler.add_job(
            func=_fire_reminder,
            trigger=trigger,
            args=[task_id],
            id=f"task_{task_id}",
            replace_existing=True,
        )

    def _add_snooze_job(self, task_id: str, fire_at: datetime) -> None:
        """Register a one-shot DateTrigger job for a snoozed re-fire."""
        self._scheduler.add_job(
            func=_fire_reminder,
            trigger=DateTrigger(run_date=fire_at),
            args=[task_id],
            id=f"snooze_{task_id}",
            replace_existing=True,
        )

    # ── Public scheduling API ─────────────────────────────────────────

    def schedule_snooze(self, task_id: str, minutes: int) -> None:
        """Schedule a one-shot re-fire job 'minutes' from now."""
        fire_at = datetime.now() + timedelta(minutes=minutes)
        self._add_snooze_job(task_id, fire_at)

    def reschedule_task(self, task_id: str) -> None:
        """Re-register the cron job for a task after its fields have been edited."""
        task = self._store.get_task(task_id)
        if task is None or task.get("paused"):
            return
        self._add_cron_job(task)

    def cancel_job(self, task_id: str) -> None:
        """Remove regular and snooze jobs for a task (used on done/delete)."""
        for job_id in (f"task_{task_id}", f"snooze_{task_id}"):
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass


# ── Module-level callback (must be picklable for APScheduler) ─────────

def _fire_reminder(task_id: str) -> None:
    """APScheduler job callback. MUST complete in < 5ms. enqueue() only."""
    enqueue("show_reminder", task_id=task_id)
    from app import request_badge_update  # noqa: PLC0415
    request_badge_update(True)


def _compute_next_cron_fire(task: dict) -> datetime | None:
    """Compute the previous scheduled fire time for overdue detection.
    Returns a datetime in the past if the task was due before now, else None.
    Used only for startup overdue check — APScheduler handles future fires.
    """
    now = datetime.now()
    t = task["type"]
    hour = task.get("hour", 9)
    minute = task.get("minute", 0)

    # End-date check: if the task has expired, never fire overdue
    end_date_str = task.get("end_date", "")
    if end_date_str:
        try:
            if date.fromisoformat(end_date_str) < date.today():
                return None
        except (ValueError, TypeError):
            pass

    if t == "scheduled":
        dow = task["day_of_week"]  # 0=Mon
        today_dow = now.weekday()
        days_since = (today_dow - dow) % 7
        last_fire = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if days_since > 0:
            last_fire = last_fire - timedelta(days=days_since)
        # Rough check: if today is the right day but time hasn't passed yet, go back 7 days
        if last_fire > now:
            last_fire -= timedelta(days=7)
        # Only fire overdue if the missed fire was today — skip past-day misses
        if last_fire.date() != date.today():
            return None
        # Don't fire overdue for tasks that haven't had their first occurrence yet.
        # If start_date is missing (old task), treat as created today — don't fire.
        start_date = task.get("start_date") or date.today().isoformat()
        if last_fire.date() < date.fromisoformat(start_date):
            return None
        # Don't re-fire if already marked done on the same day as the last fire
        last_done = task.get("last_done")
        if last_done:
            try:
                if datetime.fromisoformat(last_done).date() >= last_fire.date():
                    return None
            except (ValueError, TypeError):
                pass
        return last_fire
    elif t == "daily":
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            candidate -= timedelta(days=1)
        start_date = task.get("start_date") or date.today().isoformat()
        if candidate.date() < date.fromisoformat(start_date):
            return None
        last_done = task.get("last_done")
        if last_done:
            try:
                if datetime.fromisoformat(last_done).date() >= candidate.date():
                    return None
            except (ValueError, TypeError):
                pass
        return candidate

    elif t == "weekly":
        # Only fire overdue on the exact scheduled day of week
        if now.weekday() != task.get("day_of_week", 0):
            return None
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return None  # scheduled time hasn't come yet today
        start_date = task.get("start_date") or date.today().isoformat()
        if candidate.date() < date.fromisoformat(start_date):
            return None
        last_done = task.get("last_done")
        if last_done:
            try:
                if datetime.fromisoformat(last_done).date() >= candidate.date():
                    return None
            except (ValueError, TypeError):
                pass
        return candidate

    elif t == "monthly":
        # Only fire overdue on the exact scheduled day of month
        day_of_month = task.get("day_of_month", 1)
        if now.day != day_of_month:
            return None
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return None  # scheduled time hasn't come yet today
        start_date = task.get("start_date") or date.today().isoformat()
        if candidate.date() < date.fromisoformat(start_date):
            return None
        last_done = task.get("last_done")
        if last_done:
            try:
                if datetime.fromisoformat(last_done).date() >= candidate.date():
                    return None
            except (ValueError, TypeError):
                pass
        return candidate

    elif t == "quarterly":
        # Only fire overdue if check-in is enabled and today is the check-in day
        if not task.get("check_in_enabled", False):
            return None
        if now.weekday() != task.get("check_in_dow", 0):
            return None
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return None
        start_date = task.get("start_date") or date.today().isoformat()
        if candidate.date() < date.fromisoformat(start_date):
            return None
        last_done = task.get("last_done")
        if last_done:
            try:
                if datetime.fromisoformat(last_done).date() >= candidate.date():
                    return None
            except (ValueError, TypeError):
                pass
        return candidate

    elif t == "one_time":
        due_str = task.get("due_date")
        if not due_str:
            return None
        try:
            due_d = date.fromisoformat(due_str)
            candidate = datetime(due_d.year, due_d.month, due_d.day, hour, minute)
        except (ValueError, TypeError):
            return None
        if candidate > now:
            return None
        if candidate.date() != date.today():
            return None
        last_done = task.get("last_done")
        if last_done:
            try:
                if datetime.fromisoformat(last_done).date() >= candidate.date():
                    return None
            except (ValueError, TypeError):
                pass
        return candidate

    return None
