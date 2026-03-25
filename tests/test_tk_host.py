"""SHELL-04: tk_host starts a daemon thread; _queue is a queue.Queue instance."""
import pytest
import queue

# tk_host.py does not exist yet — test will xfail until Plan 02 creates it
pytestmark = pytest.mark.xfail(reason="ui/tk_host.py not yet created (Plan 02)", strict=False)


def test_tk_thread_is_daemon():
    """start_tk_thread() starts a daemon thread (won't prevent interpreter exit)."""
    import threading
    from ui.tk_host import start_tk_thread, _queue  # noqa: PLC0415

    assert isinstance(_queue, queue.Queue), "_queue must be a queue.Queue instance"

    before = set(t.ident for t in threading.enumerate())
    start_tk_thread()

    import time
    time.sleep(0.3)  # Allow thread to start

    new_threads = [t for t in threading.enumerate() if t.ident not in before]
    daemon_threads = [t for t in new_threads if t.daemon]
    assert len(daemon_threads) >= 1, "start_tk_thread() must start at least one daemon thread"
