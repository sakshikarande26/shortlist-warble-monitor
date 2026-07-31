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


def test_real_trajectory_with_duplicate_timestamps_reaches_breakout():
    # Exact real data pulled from a live collector run. Duplicate sim_hours
    # (cache + live samples landing at the same instant) and out-of-order
    # views at the same timestamp — before the dedup fix, the phantom
    # zero/negative-gain intervals these duplicates produced broke the
    # consecutive-confirmation streak (score 1.0, 0.0, 1.0, 0.0, ...) and
    # this post never left NEW despite a genuine, sustained breakout.
    raw = [
        (0.032, 16767), (0.548, 16818), (0.548, 16818), (1.335, 16889),
        (2.466, 16971), (2.966, 17136), (2.966, 16971), (4.467, 19961),
        (4.967, 105594), (4.967, 49192), (5.467, 265473), (5.967, 454570),
    ]
    samples = [SamplePoint(sim_hours=h, views=v) for h, v in raw]

    result = evaluate_post(samples, followers=10_000)

    assert result.state == "BREAKOUT"
    assert result.reason == "sustained_growth_breakout"


def test_follower_normalization_changes_outcome_for_identical_trajectory():
    views = [3000, 3600]
    small_creator = evaluate_post(pts(views), followers=2_000)
    large_creator = evaluate_post(pts(views), followers=2_000_000)
    assert small_creator.state == "WATCH"
    assert large_creator.state == "NEW"
    assert small_creator.score > large_creator.score
