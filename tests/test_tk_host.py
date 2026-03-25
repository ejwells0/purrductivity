"""SHELL-04: tk_host exposes setup/tick/enqueue API; _queue is a queue.Queue instance."""
import pytest
import queue


def test_queue_is_queue_instance():
    """_queue is a queue.Queue — required for thread-safe enqueue."""
    from ui.tk_host import _queue  # noqa: PLC0415
    assert isinstance(_queue, queue.Queue)


def test_enqueue_adds_to_queue():
    """enqueue() puts a callable + kwargs onto _queue."""
    from ui.tk_host import enqueue, _queue  # noqa: PLC0415

    sentinel = object()
    called_with = {}

    def fn(**kwargs):
        called_with.update(kwargs)

    # Drain any prior items so we can count precisely
    while not _queue.empty():
        _queue.get_nowait()

    enqueue(fn, value=sentinel)

    assert not _queue.empty(), "enqueue() must put an item on _queue"
    item = _queue.get_nowait()
    assert item == (fn, {"value": sentinel})


@pytest.mark.skip(reason="setup() requires macOS main thread with a display — verified via python main.py")
def test_setup_creates_root():
    """setup() creates a hidden CTk root on the calling thread."""
    from ui.tk_host import setup, _root  # noqa: PLC0415
    setup()
    from ui.tk_host import _root as root_after  # noqa: PLC0415
    assert root_after is not None
