# app.py
# rumps.App subclass — menu bar icon and menu items.
# Source: Phase 1 Research — Pattern 2, Phase 2 Research — Pattern 6 (badge compositing)
#
# RULE: No ctk.* or tk.* calls here. All UI goes through enqueue().
import os
import tempfile

import rumps
from AppKit import NSApplication, NSImage
from PIL import Image, ImageDraw

from ui.tk_host import enqueue
from ui.styles import BADGE_DOT

_BASE_ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "cat_icon.png")
_badge_tmp: str | None = None
_pending_badge_state: bool = False   # Set from APScheduler thread; read by main thread timer


def _build_badged_icon() -> str:
    """Composite a BADGE_DOT circle onto the cat icon; return temp file path."""
    global _badge_tmp
    img = Image.open(_BASE_ICON).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    r = max(3, w // 6)
    cx, cy = w - r - 2, h - r - 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BADGE_DOT)
    if _badge_tmp is None:
        fd, _badge_tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
    img.save(_badge_tmp)
    return _badge_tmp


def request_badge_update(pending: bool) -> None:
    """Called from APScheduler thread — sets flag; main-thread timer applies it."""
    global _pending_badge_state
    _pending_badge_state = pending


class PurrductivityApp(rumps.App):
    def __init__(self, scheduler, store, resp_queue):
        super().__init__(
            name="Purrductivity",
            title="",
            icon=_BASE_ICON,
            quit_button="Quit Purrductivity",
            template=False,
        )
        self._scheduler = scheduler
        self._store = store
        self._resp_queue = resp_queue
        self._badge_pending = False
        self.menu = ["Open", None]
        # Set Dock icon to match the menu bar cat
        _dock_icon = NSImage.alloc().initWithContentsOfFile_(_BASE_ICON)
        if _dock_icon:
            NSApplication.sharedApplication().setApplicationIconImage_(_dock_icon)
        # Poll badge state every 500ms on main thread
        self._badge_timer = rumps.Timer(self._apply_badge, 0.5)
        self._badge_timer.start()

    @rumps.clicked("Open")
    def open_panel_clicked(self, _sender):
        enqueue("show")

    def _drain_resp_queue(self) -> None:
        """Drain commands from the child process. Called every 500ms from _apply_badge."""
        try:
            while True:
                msg = self._resp_queue.get_nowait()
                cmd = msg.get("cmd", "")
                if cmd == "schedule_snooze":
                    self._scheduler.schedule_snooze(msg["task_id"], msg["minutes"])
                elif cmd == "mark_done":
                    self._store.mark_done(msg["task_id"])
                elif cmd == "reschedule_task":
                    self._scheduler.reschedule_task(msg["task_id"])
                elif cmd == "cancel_job":
                    self._scheduler.cancel_job(msg["task_id"])
                elif cmd == "badge_clear":
                    request_badge_update(False)
        except Exception:
            pass  # Empty queue raises queue.Empty — swallow it

    def _apply_badge(self, _sender) -> None:
        """Main-thread timer: apply any pending badge state change.

        Badge is on when a reminder recently fired OR any task has an overdue snooze.
        Only past-due snoozes count — future snoozes have no popup yet so the badge
        would show with nothing for the user to act on.
        Polling the store covers the case where the child process cleared snooze via
        Done — once snoozed_until is None in the DB, the badge turns off without a
        round-trip IPC message.
        """
        import datetime as _dt  # noqa: PLC0415
        self._drain_resp_queue()
        now_iso = _dt.datetime.now().isoformat()
        any_snoozed = any(
            t.get("snoozed_until") and t["snoozed_until"] <= now_iso
            for t in self._store.get_active_tasks()
        )
        new_state = _pending_badge_state or any_snoozed
        if new_state != self._badge_pending:
            self._badge_pending = new_state
            if self._badge_pending:
                self.icon = _build_badged_icon()
            else:
                self.icon = _BASE_ICON
