from app.detector.evaluate import evaluate_post
from app.detector.momentum import SamplePoint


def pts(views: list[int]) -> list[SamplePoint]:
    return [SamplePoint(sim_hours=float(i), views=v) for i, v in enumerate(views)]


def test_insufficient_data():
    result = evaluate_post(pts([100]), followers=10_000)
    assert result.state == "NEW"
    assert result.reason == "insufficient_data"

    result = evaluate_post([], followers=10_000)
    assert result.state == "NEW"
    assert result.reason == "insufficient_data"


def test_flat_post():
    views = [1000, 1005, 1010, 1015, 1020, 1025]
    result = evaluate_post(pts(views), followers=10_000)
    assert result.state == "NEW"


def test_slow_riser_never_breaks_out():
    views = [3000, 3600, 4400, 5000, 5050, 5060]
    result = evaluate_post(pts(views), followers=10_000)
    assert result.state == "COOLING"


def test_real_breakout():
    views = [2000, 3000, 4500, 6750, 10125, 15187]
    result = evaluate_post(pts(views), followers=10_000)
    assert result.state == "BREAKOUT"
    assert result.reason == "sustained_growth_breakout"
    assert result.score > 0


def test_small_number_false_spike_does_not_alert():
    result = evaluate_post(pts([5, 50]), followers=10_000)
    assert result.state == "NEW"
    assert result.reason == "below_volume_floor"


def test_follower_normalization_changes_outcome_for_identical_trajectory():
    views = [3000, 3600]
    small_creator = evaluate_post(pts(views), followers=2_000)
    large_creator = evaluate_post(pts(views), followers=2_000_000)
    assert small_creator.state == "WATCH"
    assert large_creator.state == "NEW"
    assert small_creator.score > large_creator.score
