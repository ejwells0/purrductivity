# ui/tk_process.py
# Tkinter child process entry point.
# Runs on the child process's main thread — no conflict with rumps.
import customtkinter as ctk
import ui.tk_host as _host


def run_tk(cmd_queue, resp_queue) -> None:
    """
    Entry point for the tkinter subprocess.
    cmd_queue is a multiprocessing.Queue; main process puts commands into it.
    resp_queue is a multiprocessing.Queue; child process puts responses into it.
    """
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    # Store root so panel.py can access it via get_root()
    _host._root = root
    # Wire both queues so enqueue() and send_to_main() work in the child process
    _host.init(cmd_queue)
    _host.init_resp(resp_queue)

    def _poll() -> None:
        try:
            while True:
                msg = cmd_queue.get_nowait()
                # Backward compat: bare string "show" from old enqueue callers
                if isinstance(msg, str):
                    cmd, kwargs = msg, {}
                else:
                    cmd = msg.get("cmd", "")
                    kwargs = {k: v for k, v in msg.items() if k != "cmd"}

                if cmd == "show":
                    from ui.panel import open_panel  # noqa: PLC0415
                    open_panel()
                elif cmd == "show_reminder":
                    from ui.reminder_popup import show_reminder  # noqa: PLC0415
                    show_reminder(kwargs["task_id"])
                elif cmd == "done":
                    from ui.reminder_popup import handle_done  # noqa: PLC0415
                    handle_done(kwargs["task_id"])
                elif cmd == "snooze":
                    from ui.reminder_popup import handle_snooze  # noqa: PLC0415
                    handle_snooze(kwargs["task_id"], kwargs["minutes"])
                elif cmd == "badge":
                    pass  # Plan 04 wires badge into app.py main process; child ignores
                elif cmd == "schedule_snooze":
                    from ui.tk_host import send_to_main  # noqa: PLC0415
                    send_to_main("schedule_snooze", task_id=kwargs["task_id"], minutes=kwargs["minutes"])
                else:
                    import logging  # noqa: PLC0415
                    logging.getLogger(__name__).warning("Unknown IPC command: %r", cmd)
        except Exception:
            pass
        root.after(100, _poll)

    root.after(100, _poll)
    root.mainloop()
