from app.detector.momentum import SamplePoint, _dedupe_samples, compute_interval_signals


def pts(views: list[int]) -> list[SamplePoint]:
    return [SamplePoint(sim_hours=float(i), views=v) for i, v in enumerate(views)]


def test_dedupe_collapses_identical_duplicate_timestamps():
    samples = [
        SamplePoint(sim_hours=0.548, views=16818),
        SamplePoint(sim_hours=0.548, views=16818),
    ]
    assert _dedupe_samples(samples) == [SamplePoint(sim_hours=0.548, views=16818)]


def test_dedupe_keeps_max_views_when_duplicates_disagree_and_are_out_of_order():
    # Same sim_hours, two different view counts, arriving out of order (as
    # they can when cache and live samples land in the same tick) — dedup
    # must keep the max (freshest reading) regardless of input order.
    samples = [
        SamplePoint(sim_hours=2.966, views=16971),
        SamplePoint(sim_hours=2.966, views=17136),
    ]
    assert _dedupe_samples(samples) == [SamplePoint(sim_hours=2.966, views=17136)]


def test_dedupe_sorts_ascending_for_unsorted_unique_timestamps():
    samples = [SamplePoint(sim_hours=1.0, views=200), SamplePoint(sim_hours=0.5, views=100)]
    assert [s.sim_hours for s in _dedupe_samples(samples)] == [0.5, 1.0]


def test_compute_interval_signals_never_emits_a_zero_delta_interval():
    samples = [
        SamplePoint(sim_hours=1.0, views=1000),
        SamplePoint(sim_hours=1.0, views=1000),  # exact duplicate
        SamplePoint(sim_hours=2.0, views=2000),
    ]
    signals = compute_interval_signals(samples, followers=10_000)
    assert len(signals) == 1  # the duplicate collapsed, not a phantom 0-gain interval
    assert signals[0].sim_hours == 2.0


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


def test_large_absolute_gain_qualifies_despite_low_relative_growth():
    # Bug 1: a big post gaining +40,728 views is only 3.7% growth once its
    # base is ~1.09M -- below the 15% relative threshold -- but that's still
    # a real, large breakout. Must qualify on the absolute path alone.
    signals = compute_interval_signals(pts([1091002, 1131730]), followers=1_000_000)
    assert signals[0].absolute_gain == 40728
    assert signals[0].relative_growth_pct < 15.0
    assert signals[0].qualifies is True
    assert signals[0].gate_reason is None


def test_relative_growth_path_qualifies_smaller_fast_growing_post():
    # Below MIN_VIEWS_FLOOR on its own, but clears both the relative
    # threshold and SMALL_ABSOLUTE_FLOOR -- the "smaller posts growing
    # fast" path should qualify.
    signals = compute_interval_signals(pts([1000, 1200]), followers=10_000)
    assert signals[0].absolute_gain == 200  # < MIN_VIEWS_FLOOR (500)
    assert signals[0].relative_growth_pct == 20.0  # >= RELATIVE_GROWTH_THRESHOLD_PCT
    assert signals[0].qualifies is True


def test_relative_growth_path_still_blocked_below_small_absolute_floor():
    # Clears the 15% relative threshold but the absolute gain (80) is under
    # SMALL_ABSOLUTE_FLOOR (100) -- must NOT qualify via the relative path.
    signals = compute_interval_signals(pts([500, 580]), followers=10_000)
    assert signals[0].relative_growth_pct == 16.0
    assert signals[0].absolute_gain == 80
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
