# ui/tk_host.py
# Persistent hidden CTk root + queue-based UI dispatch.
# Source: Phase 1 Research — Pattern 1 (revised); Pitfall 1 (wrong thread)
#
# ARCHITECTURE: rumps owns the main thread (NSRunLoop).
# CTk root is created on the main thread BEFORE rumps starts.
# A rumps.Timer calls tick() every 50ms to pump tkinter events.
# No background threads — all UI runs on the main thread.
#
# API:
#   setup()        — create hidden CTk root; MUST be called on the main thread before rumps
#   tick()         — drain queue + pump tkinter; called by rumps.Timer in main.py
#   enqueue(fn)    — thread-safe: schedule UI work from any thread
import queue
import customtkinter as ctk

_queue: queue.Queue = queue.Queue()
_root: ctk.CTk | None = None


def setup() -> None:
    """Create the hidden CTk root on the main thread. Call before rumps.App.run()."""
    global _root
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")  # overridden by per-widget fg_color
    _root = ctk.CTk()
    _root.withdraw()  # Hidden root — never shown to user


def tick() -> None:
    """Drain the work queue and pump the tkinter event loop.
    Must be called periodically from the main thread (via rumps.Timer).
    """
    if _root is None:
        return
    try:
        while True:
            fn, kwargs = _queue.get_nowait()
            fn(**kwargs)
    except queue.Empty:
        pass
    _root.update_idletasks()
    _root.update()


def enqueue(fn, **kwargs) -> None:
    """Thread-safe: schedule UI work from any thread (rumps callbacks, timers, etc)."""
    _queue.put((fn, kwargs))
