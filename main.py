# main.py
# Multiprocess entry point.
#
# ARCHITECTURE (required by macOS):
#   - rumps (NSStatusBar) needs the main thread in the parent process
#   - tkinter (NSWindow) needs the main thread in the child process
#   - IPC via multiprocessing.Queue: main sends "show", child opens panel
#
# ORDER IS CRITICAL:
#   1. mp.Queue created first
#   2. tk_host.init(q) stores queue so app.py / scheduler.py can enqueue
#   3. Child process spawned (gets its own main thread for tkinter)
#   4. rumps runs on this process's main thread
import multiprocessing as mp
import time

import ui.tk_host as tk_host
from ui.tk_process import run_tk
from store import TaskStore
from scheduler import ReminderScheduler
from app import PurrductivityApp


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    cmd_queue = mp.Queue()
    resp_queue = mp.Queue()
    tk_host.init(cmd_queue)
    tk_host.init_resp(resp_queue)

    store = TaskStore()

    tk_proc = mp.Process(target=run_tk, args=(cmd_queue, resp_queue), daemon=True)
    tk_proc.start()

    time.sleep(1.5)  # Give child process time to initialize before overdue reminders fire

    scheduler = ReminderScheduler(store)
    scheduler.start()

    PurrductivityApp(scheduler, store, resp_queue).run()
