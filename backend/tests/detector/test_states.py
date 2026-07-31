from app.detector.momentum import SamplePoint, compute_interval_signals
from app.detector.states import run_state_machine


def pts(views: list[int]) -> list[SamplePoint]:
    return [SamplePoint(sim_hours=float(i), views=v) for i, v in enumerate(views)]


def test_flat_post_stays_new():
    views = [1000, 1005, 1010, 1015, 1020, 1025]
    signals = compute_interval_signals(pts(views), followers=10_000)
    history = run_state_machine(signals)
    assert all(s.state == "NEW" for s in history)


def test_single_jump_goes_to_watch_not_further():
    # One qualifying interval, then flat — should reach WATCH and fall back
    # to NEW, never RISING: a single jump alone must not be enough.
    views = [3000, 3600, 3610, 3620]
    signals = compute_interval_signals(pts(views), followers=10_000)
    history = run_state_machine(signals)
    assert history[0].state == "WATCH"
    assert "RISING" not in {s.state for s in history}
    assert "BREAKOUT" not in {s.state for s in history}


def test_slow_riser_reaches_rising_then_cools_never_breaks_out():
    # Two strong intervals (qualify) then plateaus (relative growth drops
    # below threshold) -> RISING, then demoted to COOLING.
    views = [3000, 3600, 4400, 5000, 5050, 5060]
    signals = compute_interval_signals(pts(views), followers=10_000)
    history = run_state_machine(signals)
    states = [s.state for s in history]
    assert "RISING" in states
    assert "BREAKOUT" not in states
    assert history[-1].state == "COOLING"


def test_real_breakout_progresses_through_all_states():
    views = [2000, 3000, 4500, 6750, 10125, 15187]
    signals = compute_interval_signals(pts(views), followers=10_000)
    history = run_state_machine(signals)
    states = [s.state for s in history]
    assert states[0] == "WATCH"
    assert "RISING" in states
    assert "BREAKOUT" in states
    assert history[-1].state == "BREAKOUT"
    assert history[-1].reason == "sustained_growth_breakout"


def test_breakout_demotes_to_cooling_when_momentum_stops():
    views = [2000, 3000, 4500, 6750, 10125, 10130]  # last interval flat
    signals = compute_interval_signals(pts(views), followers=10_000)
    history = run_state_machine(signals)
    assert history[-2].state == "BREAKOUT"
    assert history[-1].state == "COOLING"
    assert history[-1].reason == "momentum_fading_cooling"


def test_cooling_reearns_watch_not_straight_back_to_breakout():
    # Breakout, cool off, then one more qualifying interval — must land on
    # WATCH, not jump straight back to RISING/BREAKOUT.
    views = [2000, 3000, 4500, 6750, 10125, 10130, 14000]
    signals = compute_interval_signals(pts(views), followers=10_000)
    history = run_state_machine(signals)
    assert history[-2].state == "COOLING"
    assert history[-1].state == "WATCH"
