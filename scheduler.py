# scheduler.py
# rumps.Timer — fires a test popup 10 seconds after startup, then every 60s.
# Source: Phase 1 Research — Pattern 5; Pitfall 4 (timer blocks main thread)
#
# CRITICAL: Timer callbacks run on the main thread (rumps issue #22).
# Keep total callback time under 5ms. Queue only — no blocking work.
import rumps

from ui.tk_host import enqueue
from ui.panel import open_panel


class ReminderScheduler:
    def __init__(self):
        # Phase 1 only: fire test popup after 10s, then every 60s.
        # Phase 2 will replace this with APScheduler + wall-clock comparison.
        self.timer = rumps.Timer(self._check, 10)

    def start(self) -> None:
        self.timer.start()

    def _check(self, _sender) -> None:
        # CRITICAL: enqueue only — under 5ms (Pitfall 4)
        enqueue(open_panel)
