# main.py
# Entry point — tkinter mainloop owns the main thread; rumps runs in a thread.
#
# ORDER IS CRITICAL:
#   1. setup()          — create hidden CTk root on the main thread (must be first)
#   2. rumps thread     — starts rumps NSRunLoop + scheduler on a daemon thread
#   3. mainloop()       — blocks main thread; tkinter handles all UI events cleanly
#
# WHY THIS LAYOUT:
#   macOS requires NSWindow (tkinter) on the main thread, and tkinter's mainloop
#   must own that thread for callbacks to fire without GIL re-entrancy issues.
#   rumps works fine on a daemon thread (it only manages a status bar item/menu).
import threading
from ui.tk_host import setup, get_root
from scheduler import ReminderScheduler
from app import PurrductivityApp


def _run_rumps() -> None:
    scheduler = ReminderScheduler()
    scheduler.start()
    PurrductivityApp().run()


if __name__ == "__main__":
    setup()  # CTk root on main thread — must precede everything

    threading.Thread(target=_run_rumps, daemon=True).start()

    get_root().mainloop()  # blocks; all tkinter events handled here
