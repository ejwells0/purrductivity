# ui/tk_host.py
# Persistent hidden CTk root + queue polling for thread-safe UI.
# Source: Phase 1 Research — Pattern 1; Pitfall 1 (wrong thread), Pitfall 2 (multiple roots)
#
# CRITICAL RULES (enforced by tests):
#   - ctk.CTk() is created ONCE and never destroyed
#   - All UI commands come in via enqueue() — never called directly from app.py/scheduler.py
#   - The thread is daemon=True so it won't prevent interpreter exit
import queue
import threading
import customtkinter as ctk

_queue: queue.Queue = queue.Queue()
_root: ctk.CTk | None = None


def _poll() -> None:
    try:
        while True:
            fn, kwargs = _queue.get_nowait()
            fn(**kwargs)
    except queue.Empty:
        pass
    if _root is not None:
        _root.after(100, _poll)


def start_tk_thread() -> None:
    """Start the tkinter daemon thread. MUST be called before rumps.App.run()."""
    def _run() -> None:
        global _root
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")  # overridden by per-widget fg_color
        _root = ctk.CTk()
        _root.withdraw()          # Hidden root — never shown to user
        _root.after(100, _poll)
        _root.mainloop()
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def enqueue(fn, **kwargs) -> None:
    """Thread-safe: schedule UI work from any thread (rumps callbacks, timers, etc)."""
    _queue.put((fn, kwargs))
