"""SHELL-04: tk_host bridge — enqueue() sends to IPC queue; get_root() returns stored root."""
import pytest


def test_enqueue_puts_show_on_queue(monkeypatch):
    """enqueue() puts 'show' on the IPC queue for the tkinter child process."""
    import ui.tk_host as host
    from unittest.mock import MagicMock

    fake_q = MagicMock()
    monkeypatch.setattr(host, "_cmd_queue", fake_q)

    host.enqueue(lambda: None)

    fake_q.put.assert_called_once_with("show")


def test_enqueue_noop_without_queue(monkeypatch):
    """enqueue() does nothing if queue not initialised (safe before child spawns)."""
    import ui.tk_host as host
    monkeypatch.setattr(host, "_cmd_queue", None)
    host.enqueue(lambda: None)  # should not raise


@pytest.mark.skip(reason="get_root() requires the tkinter child process — verified via python main.py")
def test_get_root_returns_root():
    from ui.tk_host import get_root  # noqa: PLC0415
    assert get_root() is not None
