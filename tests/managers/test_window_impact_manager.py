"""Tests for the window-open impact baseline."""

from custom_components.roommind.managers.window_impact_manager import WindowImpactManager


def test_window_impact_baseline_persists_only_while_open(monkeypatch):
    manager = WindowImpactManager()
    monkeypatch.setattr("custom_components.roommind.managers.window_impact_manager.time.time", lambda: 100.0)
    baseline = manager.update("sala", True, 25.0)
    assert baseline is not None and baseline.temp == 25.0
    assert manager.update("sala", True, 25.5) is baseline
    assert manager.update("sala", False, 25.5) is None
