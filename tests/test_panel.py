"""SHELL-03: Closing the panel hides it (withdraw) rather than destroying it."""
import pytest

# panel.py does not exist yet — test will xfail until Plan 02 creates it
pytestmark = pytest.mark.xfail(reason="ui/panel.py not yet created (Plan 02)", strict=False)


def test_panel_survives_close():
    """After WM_DELETE_WINDOW fires, panel widget still exists (winfo_exists() is True)."""
    from ui.tk_host import start_tk_thread, enqueue, _root  # noqa: PLC0415
    from ui.panel import open_panel  # noqa: PLC0415
    import time

    start_tk_thread()
    time.sleep(0.3)

    enqueue(open_panel)
    time.sleep(0.5)

    from ui import panel as panel_mod  # noqa: PLC0415
    p = panel_mod._panel
    assert p is not None, "_panel must be set after open_panel() enqueued"

    # Simulate WM_DELETE_WINDOW (close button)
    enqueue(lambda: p.event_generate("<<CloseWindow>>"))
    time.sleep(0.2)

    # Panel must still exist — withdraw() not destroy()
    result = []
    enqueue(lambda: result.append(p.winfo_exists()))
    time.sleep(0.2)
    assert result and result[0] == 1, "Panel must still exist after close (withdraw, not destroy)"
