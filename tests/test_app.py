"""SHELL-01: rumps.App initializes with name and emoji title without raising."""
import pytest

rumps = pytest.importorskip("rumps", reason="rumps not installed")

# app.py does not exist yet — test will xfail until Plan 02 creates it
pytestmark = pytest.mark.xfail(reason="app.py not yet created (Plan 02)", strict=False)


def test_app_init():
    """PurrductivityApp can be instantiated; title is set; no exception raised."""
    from app import PurrductivityApp  # noqa: PLC0415
    instance = PurrductivityApp()
    assert instance.title == "🐱"
