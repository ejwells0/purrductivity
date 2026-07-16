# ui/tk_process.py
# Tkinter child process entry point.
# Runs on the child process's main thread — no conflict with rumps.
import os
import customtkinter as ctk
import ui.tk_host as _host

_ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "cat_icon.png")


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

    # Set dock icon: cat on pastel pink rounded square, standard 1024px canvas
    try:
        import tempfile  # noqa: PLC0415
        from PIL import Image, ImageDraw  # noqa: PLC0415
        from AppKit import NSApplication, NSImage  # noqa: PLC0415
        from Foundation import NSBundle  # noqa: PLC0415

        # Set process display name
        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = "Purrductivity"
            info["CFBundleDisplayName"] = "Purrductivity"

        # 1024x1024 canvas — standard macOS icon size, matches dock sizing of other apps
        size = 1024
        outer_pad = 80         # transparent outer margin — matches macOS icon grid sizing
        sq = size - outer_pad * 2
        radius = int(sq * 0.225)  # standard macOS squircle-ish radius

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        sq_img = Image.new("RGBA", (sq, sq), (0, 0, 0, 0))
        ImageDraw.Draw(sq_img).rounded_rectangle([0, 0, sq - 1, sq - 1], radius=radius, fill="#F0C0C8")
        canvas.paste(sq_img, (outer_pad, outer_pad), sq_img.split()[3])

        cat = Image.open(_ICON_PATH).convert("RGBA")
        inner_pad = int(sq * 0.12)
        cat_size = sq - inner_pad * 2
        cat = cat.resize((cat_size, cat_size), Image.LANCZOS)
        canvas.paste(cat, (outer_pad + inner_pad, outer_pad + inner_pad), cat.split()[3])

        _fd, _tmp = tempfile.mkstemp(suffix=".png")
        os.close(_fd)
        canvas.save(_tmp)

        _img = NSImage.alloc().initWithContentsOfFile_(_tmp)
        if _img:
            NSApplication.sharedApplication().setApplicationIconImage_(_img)
    except Exception:
        pass

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
        except Exception as _e:
            import queue as _q, logging, traceback  # noqa: PLC0415
            if isinstance(_e, _q.Empty):
                pass  # Normal — queue is empty, nothing to do
            else:
                logging.getLogger(__name__).error("IPC poll error:\n%s", traceback.format_exc())
        root.after(100, _poll)

    root.after(100, _poll)
    root.mainloop()
