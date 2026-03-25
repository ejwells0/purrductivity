"""SHELL-04: tk_host bridge — enqueue() sends to IPC queue; get_root() returns stored root."""
import pytest


def test_enqueue_puts_show_dict_on_queue(monkeypatch):
    """enqueue('show') puts {'cmd': 'show'} dict on the IPC queue."""
    import ui.tk_host as host
    from unittest.mock import MagicMock

    fake_q = MagicMock()
    monkeypatch.setattr(host, "_cmd_queue", fake_q)

    host.enqueue("show")

    fake_q.put.assert_called_once_with({"cmd": "show"})


def test_enqueue_puts_kwargs_in_dict(monkeypatch):
    """enqueue('show_reminder', task_id='abc') puts {'cmd': 'show_reminder', 'task_id': 'abc'}."""
    import ui.tk_host as host
    from unittest.mock import MagicMock

    fake_q = MagicMock()
    monkeypatch.setattr(host, "_cmd_queue", fake_q)

    host.enqueue("show_reminder", task_id="abc-123")

    fake_q.put.assert_called_once_with({"cmd": "show_reminder", "task_id": "abc-123"})


def test_enqueue_noop_without_queue(monkeypatch):
    """enqueue() does nothing if queue not initialised (safe before child spawns)."""
    import ui.tk_host as host
    monkeypatch.setattr(host, "_cmd_queue", None)
    host.enqueue("show")  # should not raise


@pytest.mark.skip(reason="get_root() requires the tkinter child process — verified via python main.py")
def test_get_root_returns_root():
    from ui.tk_host import get_root  # noqa: PLC0415
    assert get_root() is not None
