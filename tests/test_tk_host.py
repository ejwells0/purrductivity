"""SHELL-04: tk_host exposes setup/get_root/enqueue API; enqueue uses root.after()."""
import pytest


def test_enqueue_schedules_via_after(monkeypatch):
    """enqueue() calls root.after(0, ...) — thread-safe scheduling."""
    import ui.tk_host as host

    calls = []

    class FakeRoot:
        def after(self, delay, fn):
            calls.append((delay, fn))

    monkeypatch.setattr(host, "_root", FakeRoot())

    def my_fn(value=None):
        pass

    host.enqueue(my_fn, value=42)
    assert len(calls) == 1, "enqueue() must call root.after once"
    delay, fn = calls[0]
    assert delay == 0, "enqueue() must use after(0, ...) for immediate scheduling"


@pytest.mark.skip(reason="setup() requires macOS main thread with a display — verified via python main.py")
def test_setup_creates_root():
    """setup() creates a hidden CTk root on the calling thread."""
    from ui.tk_host import setup, get_root  # noqa: PLC0415
    setup()
    assert get_root() is not None
