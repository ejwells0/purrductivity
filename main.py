# main.py
# Entry point: start tk thread FIRST, then timer, then rumps (which blocks forever).
# Source: Phase 1 Research — Pattern 6; build order is MANDATORY
#
# ORDER IS CRITICAL:
#   1. start_tk_thread() — tkinter daemon thread must exist before any UI work is queued
#   2. scheduler.start() — registers the timer; timer fires 10s later via enqueue
#   3. PurrductivityApp().run() — blocks main thread in NSRunLoop forever
from ui.tk_host import start_tk_thread
from scheduler import ReminderScheduler
from app import PurrductivityApp

if __name__ == "__main__":
    start_tk_thread()

    scheduler = ReminderScheduler()
    scheduler.start()

    PurrductivityApp().run()
