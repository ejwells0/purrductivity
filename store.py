# store.py
# TaskStore — single access point for all task persistence (TinyDB).
# Source: Phase 2 Research — Pattern 1 (schema), Pattern 7 (progress math),
#         Pitfall 2 (threading lock), Pitfall 5 (Query() reuse), Pitfall 6 (snooze)
import threading
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from tinydb import TinyDB, Query


_DB_PATH = Path(__file__).parent / "data" / "tasks.db"


class TaskStore:
    """Thread-safe TinyDB wrapper. All reads/writes go through this class."""

    def __init__(self, db_path: str | Path = _DB_PATH):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(str(db_path))
        self._tasks = self._db.table("tasks")
        self._lock = threading.Lock()

    # ── CRUD ──────────────────────────────────────────────────────────

    def add_task(self, **fields) -> str:
        """Create a new task. Returns stable UUID task_id string."""
        task_id = str(uuid.uuid4())
        doc = {
            "id": task_id,
            "notes": "",
            "completed_count": 0,
            "progress": 0,
            "snoozed_until": None,
            "last_done": None,
            "paused": False,
            "category": "personal",
            **fields,
        }
        with self._lock:
            self._tasks.insert(doc)
        return task_id

    def get_task(self, task_id: str) -> dict | None:
        """Return task document by app-level id, or None if not found."""
        with self._lock:
            return self._tasks.get(Query().id == task_id)

    def get_all_tasks(self) -> list[dict]:
        """Return all tasks (including paused)."""
        with self._lock:
            return self._tasks.all()

    def get_active_tasks(self) -> list[dict]:
        """Return tasks where paused is False."""
        with self._lock:
            return self._tasks.search(Query().paused == False)  # noqa: E712

    def update_snooze(self, task_id: str, until: datetime) -> None:
        """Set snoozed_until to ISO string."""
        with self._lock:
            self._tasks.update(
                {"snoozed_until": until.isoformat()},
                Query().id == task_id,
            )

    def mark_done(self, task_id: str) -> None:
        """Increment completed_count, set last_done, clear snooze."""
        with self._lock:
            task = self._tasks.get(Query().id == task_id)
            if task is None:
                return
            self._tasks.update(
                {
                    "completed_count": task["completed_count"] + 1,
                    "last_done": datetime.now().isoformat(),
                    "snoozed_until": None,
                },
                Query().id == task_id,
            )

    def update_task(self, task_id: str, **fields) -> None:
        """Update specified fields on a task. Preserves all other fields."""
        with self._lock:
            self._tasks.update(fields, Query().id == task_id)

    def delete_task(self, task_id: str) -> None:
        """Permanently remove a task from the store."""
        with self._lock:
            self._tasks.remove(Query().id == task_id)

    def clear_snooze(self, task_id: str) -> None:
        """Clear snoozed_until without incrementing count (used on re-fire)."""
        with self._lock:
            self._tasks.update({"snoozed_until": None}, Query().id == task_id)

    def close(self) -> None:
        self._db.close()


# ── Progress Math ─────────────────────────────────────────────────────────────
# Source: Phase 2 Research — Pattern 7
# Pure stdlib datetime arithmetic. No external dependencies.

def weekly_expected_fraction(today: date) -> float:
    """Monday=0 through Sunday=6; returns fraction of week elapsed (1/7 to 7/7)."""
    return (today.weekday() + 1) / 7


def quarterly_expected_fraction(today: date) -> float:
    """Returns fraction of current calendar quarter elapsed.
    Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec.
    Uses (days_elapsed + 1) / total_days so day 1 is non-zero."""
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = date(today.year, quarter_start_month, 1)
    next_quarter_month = quarter_start_month + 3
    if next_quarter_month > 12:
        quarter_end = date(today.year + 1, 1, 1)
    else:
        quarter_end = date(today.year, next_quarter_month, 1)
    total_days = (quarter_end - quarter_start).days
    days_elapsed = (today - quarter_start).days
    return min((days_elapsed + 1) / total_days, 1.0)


def is_behind(task: dict, today: date) -> bool:
    """Return True if task is a goal type and actual progress < expected progress."""
    if task["type"] == "weekly":
        target = task.get("weekly_target", 1)
        if target == 1:
            # Binary task (once a week): only behind if the scheduled day has arrived
            # this week and it hasn't been done yet.
            dow = task.get("day_of_week", 6)
            if today.weekday() < dow:
                return False  # scheduled day hasn't arrived yet
            last_done = task.get("last_done")
            if last_done:
                try:
                    week_start = today - timedelta(days=today.weekday())
                    if datetime.fromisoformat(last_done).date() >= week_start:
                        return False  # done this week
                except (ValueError, TypeError):
                    pass
            return True
        expected = weekly_expected_fraction(today) * target
        return task.get("completed_count", 0) < expected
    elif task["type"] == "quarterly":
        expected = quarterly_expected_fraction(today) * 100
        return task.get("progress", 0) < expected
    else:
        return False
