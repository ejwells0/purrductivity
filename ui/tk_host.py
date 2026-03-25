# ui/tk_host.py
# Bridge between the main (rumps) process and the tkinter child process.
#
# WHY MULTIPROCESSING:
#   Both rumps (NSStatusBar) and tkinter (NSWindow) require the macOS main thread.
#   They cannot coexist in one process. Each process has its own main thread, so
#   the child process can own the main thread for tkinter with no conflict.
#
# IN THE MAIN PROCESS:
#   - init(queue)        stores the mp.Queue for sending commands to the child
#   - enqueue(cmd, ...)  sends a structured command dict to the child process
#
# IN THE CHILD PROCESS (ui/tk_process.py):
#   - _root is set by tk_process.run_tk() before any panel calls
#   - get_root() returns it for panel.py to use

import customtkinter as ctk

_root: "ctk.CTk | None" = None
_cmd_queue = None  # multiprocessing.Queue — set by main.py


def init(cmd_queue) -> None:
    """Store the IPC queue. Called in the main process before spawning child."""
    global _cmd_queue
    _cmd_queue = cmd_queue


def get_root() -> "ctk.CTk":
    """Return the CTk root. Only valid inside the tkinter child process."""
    assert _root is not None, "get_root() called before root was set by tk_process"
    return _root


def enqueue(cmd: str, **kwargs) -> None:
    """Send a command dict to the tkinter child process. Thread-safe.

    Usage:
        enqueue("show")
        enqueue("show_reminder", task_id="abc-123")
        enqueue("done", task_id="abc-123")
        enqueue("snooze", task_id="abc-123", minutes=15)
        enqueue("badge", state="pending")
        enqueue("badge", state="idle")
    """
    if _cmd_queue is not None:
        _cmd_queue.put({"cmd": cmd, **kwargs})
