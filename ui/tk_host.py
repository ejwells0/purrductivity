# ui/tk_host.py
# Persistent hidden CTk root with thread-safe UI scheduling.
#
# ARCHITECTURE:
#   - setup()          called on the main thread before spawning rumps thread
#   - get_root()       returns the CTk root (main.py calls .mainloop() on it)
#   - enqueue(fn)      thread-safe via root.after(0, ...) — safe from any thread
#
# WHY after(0) INSTEAD OF root.update():
#   root.update() called from a rumps Timer causes GIL re-entrancy —
#   Tcl fires Python callbacks (PythonCmd) while Python already holds the GIL,
#   causing SIGABRT. after(0, ...) schedules work on the tkinter event loop
#   without holding the GIL, which is safe from any thread.
import customtkinter as ctk

_root: ctk.CTk | None = None


def setup() -> None:
    """Create the hidden CTk root on the main thread. MUST be called first."""
    global _root
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")  # overridden by per-widget fg_color
    _root = ctk.CTk()
    _root.withdraw()  # Hidden root — never shown to user


def get_root() -> ctk.CTk:
    """Return the CTk root. main.py calls get_root().mainloop() to run the event loop."""
    assert _root is not None, "setup() must be called before get_root()"
    return _root


def enqueue(fn, **kwargs) -> None:
    """Thread-safe: schedule UI work on the tkinter main thread from any thread."""
    if _root is not None:
        _root.after(0, lambda: fn(**kwargs))
