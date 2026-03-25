"""SHELL-01: rumps.App initializes with name and emoji title without raising."""
import pytest

rumps = pytest.importorskip("rumps", reason="rumps not installed")

# app.py exists but requires a running tkinter root for CTkFont at import time;
# test is xfail until the full integration environment is available (Plan 02 wire-up)
pytestmark = pytest.mark.xfail(reason="app.py requires running tkinter root (Plan 02)", strict=False)


def test_app_init():
    """PurrductivityApp can be instantiated; title is set; no exception raised."""
    from app import PurrductivityApp  # noqa: PLC0415
    instance = PurrductivityApp()
    assert instance.title == "🐱"
