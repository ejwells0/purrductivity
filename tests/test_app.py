"""SHELL-01: rumps.App initializes with icon and no title text."""
import pytest

rumps = pytest.importorskip("rumps", reason="rumps not installed")


def test_app_init():
    """PurrductivityApp can be instantiated; icon is set; no exception raised."""
    from app import PurrductivityApp  # noqa: PLC0415
    # scheduler and store are used only at runtime (badge timer + get_active_tasks);
    # passing None is safe for construction-only test.
    instance = PurrductivityApp(scheduler=None, store=None)
    assert instance.icon == "assets/cat_icon.png"
