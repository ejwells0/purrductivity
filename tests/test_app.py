"""SHELL-01: rumps.App initializes with icon and no title text."""
import pytest

rumps = pytest.importorskip("rumps", reason="rumps not installed")


def test_app_init():
    """PurrductivityApp can be instantiated; icon is set; no exception raised."""
    from app import PurrductivityApp  # noqa: PLC0415
    instance = PurrductivityApp()
    assert instance.icon == "assets/cat_icon.png"
