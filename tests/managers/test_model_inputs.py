"""Model inputs averaged per history interval; only replayable intervals are kept."""

from custom_components.roommind.managers.model_inputs import ModelInputs


def _cycle(mi, mode="heating", power=1.0, solar=0.0, residual=0.0, occupancy=0.0, window_closed=True, area="a"):
    mi.begin_cycle(area)
    mi.note(
        area,
        mode=mode,
        power=power,
        solar=solar,
        residual=residual,
        occupancy=occupancy,
        window_closed=window_closed,
    )


def test_a_single_mode_interval_writes_the_means():
    mi = ModelInputs()
    for power, solar in [(0.2, 1.0), (0.4, 2.0), (0.6, 3.0), (0.8, 4.0), (1.0, 5.0), (0.6, 3.0)]:
        _cycle(mi, power=power, solar=solar)
    assert mi.take("a") == {"model_power": 0.6, "model_solar": 3.0, "model_residual": 0.0, "model_occupancy": 0.0}


def test_cooling_is_negative_and_idle_zero():
    mi = ModelInputs()
    _cycle(mi, mode="cooling", power=0.5)
    assert mi.take("a")["model_power"] == -0.5
    _cycle(mi, mode="idle", power=0.7, residual=0.3)
    assert mi.take("a") == {"model_power": 0.0, "model_solar": 0.0, "model_residual": 0.3, "model_occupancy": 0.0}


def test_a_mode_change_inside_the_interval_writes_nothing():
    mi = ModelInputs()
    for _ in range(5):
        _cycle(mi, mode="heating")
    _cycle(mi, mode="idle", power=0.0, residual=0.4)
    assert mi.take("a") == {}
    _cycle(mi, mode="heating")
    _cycle(mi, mode="cooling")
    assert mi.take("a") == {}


def test_a_window_not_certainly_closed_writes_nothing():
    """Open window, open delay (raw open) and a pending sensor all report window_closed False."""
    mi = ModelInputs()
    _cycle(mi, mode="idle", power=0.0)
    _cycle(mi, mode="idle", power=0.0, window_closed=False)
    assert mi.take("a") == {}


def test_a_cycle_without_training_writes_nothing():
    mi = ModelInputs()
    _cycle(mi)
    mi.begin_cycle("a")  # processed, but returned before training
    assert mi.take("a") == {}
    _cycle(mi)
    mi.begin_cycle("a")
    mi.unusable("a")  # learning off / no outdoor temperature
    assert mi.take("a") == {}


def test_unknown_mode_writes_nothing():
    mi = ModelInputs()
    mi.begin_cycle("a")
    mi.note("a", mode=None, power=0.0, solar=0.0, residual=0.0, occupancy=0.0, window_closed=True)
    assert mi.take("a") == {}


def test_reset_starts_a_new_interval_and_rooms_are_separate():
    mi = ModelInputs()
    _cycle(mi, mode="heating", area="a")
    _cycle(mi, mode="idle", power=0.0, area="b")
    mi.reset()
    _cycle(mi, mode="cooling", power=1.0, area="a")
    assert mi.take("a")["model_power"] == -1.0
    assert mi.take("b") == {}
    mi.begin_cycle("c")
    mi.remove_room("c")
    assert mi.take("c") == {}
