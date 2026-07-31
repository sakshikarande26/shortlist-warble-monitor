from app.detector.momentum import SamplePoint, compute_interval_signals


def pts(views: list[int]) -> list[SamplePoint]:
    return [SamplePoint(sim_hours=float(i), views=v) for i, v in enumerate(views)]


def test_no_intervals_with_fewer_than_two_samples():
    assert compute_interval_signals(pts([100]), followers=1000) == []
    assert compute_interval_signals([], followers=1000) == []


def test_velocity_and_absolute_gain_are_per_sim_hour():
    signals = compute_interval_signals(pts([1000, 1600]), followers=10_000)
    assert len(signals) == 1
    assert signals[0].absolute_gain == 600
    assert signals[0].velocity == 600.0  # 1 sim-hour apart
    assert signals[0].relative_growth_pct == 60.0


def test_below_volume_floor_blocks_tiny_absolute_gain_despite_huge_percentage():
    signals = compute_interval_signals(pts([5, 50]), followers=10_000)
    assert signals[0].relative_growth_pct == 900.0  # huge % ...
    assert signals[0].absolute_gain == 45  # ... but tiny absolute gain
    assert signals[0].qualifies is False
    assert signals[0].gate_reason == "below_volume_floor"


def test_follower_normalization_favors_small_creator():
    """Same raw trajectory, different follower counts: the small-follower
    creator's reach-velocity is far higher, so it should score higher."""
    samples = pts([3000, 3600])
    small = compute_interval_signals(samples, followers=2_000)[0]
    large = compute_interval_signals(samples, followers=2_000_000)[0]
    assert small.follower_velocity > large.follower_velocity
    assert small.score > large.score
    assert small.qualifies is True
    assert large.qualifies is False
    assert large.gate_reason == "weak_normalized_momentum"


def test_acceleration_is_none_for_first_interval_then_populated():
    signals = compute_interval_signals(pts([1000, 1600, 2400]), followers=10_000)
    assert signals[0].acceleration is None
    assert signals[1].acceleration == signals[1].velocity - signals[0].velocity
