"""SHELL-04: tk_host starts a daemon thread; _queue is a queue.Queue instance."""
import pytest
import queue


# tk_host.py exists but start_tk_thread() starts a macOS tkinter mainloop;
# running it in a pytest session causes the process to hang.
# Test is skipped here and verified manually / in Plan 02 integration testing.
@pytest.mark.skip(reason="start_tk_thread() hangs in pytest (needs macOS display event loop)")
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
