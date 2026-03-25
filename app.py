# app.py
# rumps.App subclass — menu bar icon and menu items.
# Source: Phase 1 Research — Pattern 2, Phase 2 Research — Pattern 6 (badge compositing)
#
# RULE: No ctk.* or tk.* calls here. All UI goes through enqueue().
import os
import tempfile

import rumps
from PIL import Image, ImageDraw

from ui.tk_host import enqueue
from ui.styles import BADGE_DOT

_BASE_ICON = "assets/cat_icon.png"
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
    def __init__(self, scheduler, store):
        super().__init__(
            name="Purrductivity",
            title="",
            icon=_BASE_ICON,
            quit_button="Quit Purrductivity",
            template=True,
        )
        self._scheduler = scheduler
        self._store = store
        self._badge_pending = False
        self.menu = ["Open", None]
        # Poll badge state every 500ms on main thread
        self._badge_timer = rumps.Timer(self._apply_badge, 0.5)
        self._badge_timer.start()

    @rumps.clicked("Open")
    def open_panel_clicked(self, _sender):
        enqueue("show")

    def _apply_badge(self, _sender) -> None:
        """Main-thread timer: apply any pending badge state change.

        Badge is on when a reminder recently fired OR any task is currently snoozed.
        Polling the store for snoozed tasks covers the case where the child process
        has cleared snooze via Done — once snoozed_until is None in the DB, the badge
        turns off without needing a round-trip IPC message.
        """
        any_snoozed = any(
            t.get("snoozed_until") for t in self._store.get_active_tasks()
        )
        new_state = _pending_badge_state or any_snoozed
        if new_state != self._badge_pending:
            self._badge_pending = new_state
            if self._badge_pending:
                self.icon = _build_badged_icon()
            else:
                self.icon = _BASE_ICON
