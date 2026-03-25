# main.py
# Entry point: setup CTk root FIRST (main thread), then wire rumps + scheduler.
# Source: Phase 1 Research — Pattern 6 (revised); build order is MANDATORY
#
# ORDER IS CRITICAL:
#   1. setup()           — create hidden CTk root on main thread (before NSRunLoop starts)
#   2. scheduler.start() — register the reminder timer
#   3. tick_timer.start()— rumps.Timer pumps tkinter every 50ms from within NSRunLoop
#   4. app.run()         — blocks main thread in NSRunLoop forever
import rumps
from ui.tk_host import setup, tick
from scheduler import ReminderScheduler
from app import PurrductivityApp

if __name__ == "__main__":
    setup()

    scheduler = ReminderScheduler()
    scheduler.start()

    tick_timer = rumps.Timer(lambda _: tick(), 0.05)
    tick_timer.start()

    PurrductivityApp().run()
