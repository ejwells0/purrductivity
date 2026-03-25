# ui/tk_process.py
# Tkinter child process entry point.
# Runs on the child process's main thread — no conflict with rumps.
import customtkinter as ctk
import ui.tk_host as _host


def run_tk(cmd_queue) -> None:
    """
    Entry point for the tkinter subprocess.
    cmd_queue is a multiprocessing.Queue; main process puts "show" into it.
    """
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    # Store root so panel.py can access it via get_root()
    _host._root = root

    def _poll() -> None:
        try:
            while True:
                cmd = cmd_queue.get_nowait()
                if cmd == "show":
                    from ui.panel import open_panel  # noqa: PLC0415
                    open_panel()
        except Exception:
            pass
        root.after(100, _poll)

    root.after(100, _poll)
    root.mainloop()
