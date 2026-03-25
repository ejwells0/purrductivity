"""SHELL-01: rumps.App initializes with name and emoji title without raising."""
import pytest

rumps = pytest.importorskip("rumps", reason="rumps not installed")


def test_app_init():
    """PurrductivityApp can be instantiated; title is set; no exception raised."""
    from app import PurrductivityApp  # noqa: PLC0415
    instance = PurrductivityApp()
    assert instance.title == "P"
