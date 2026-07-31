"""Pure momentum scoring: samples in, per-interval signals out.

No DB or network imports here on purpose — `SamplePoint` is a plain
dataclass decoupled from the SQLAlchemy `Sample` ORM model, so this module
is testable with synthetic data alone (see backend/tests/detector/).
"""

from dataclasses import dataclass

from app.detector import config


@dataclass(frozen=True)
class SamplePoint:
    sim_hours: float
    views: int


@dataclass(frozen=True)
class IntervalSignal:
    sim_hours: float  # sim_hours of the later sample in the pair
    absolute_gain: int
    relative_growth_pct: float
    velocity: float  # views / sim-hour
    acceleration: float | None  # change in velocity vs the prior interval; None until a 3rd sample exists
    follower_velocity: float  # velocity normalized by creator follower count ("reach velocity")
    trajectory_ratio: float  # velocity relative to the post's own early (baseline) pace
    score: float  # composite, bounded [0, 1]
    qualifies: bool
    gate_reason: str | None  # why it didn't qualify (None if it did)


def _velocity(a: SamplePoint, b: SamplePoint) -> float:
    delta_hours = b.sim_hours - a.sim_hours
    if delta_hours <= 0:
        return 0.0
    return (b.views - a.views) / delta_hours


def _dedupe_samples(samples: list[SamplePoint]) -> list[SamplePoint]:
    """Collapse multiple rows at the same sim_hours (cache + live sampling,
    or loop-timing collisions writing two rows in the same tick) down to one
    point per timestamp, keeping the max views seen at that timestamp — the
    freshest/highest reading. Without this, duplicate timestamps produce
    phantom zero-hours intervals between them: zero (or even negative, if
    the duplicate rows arrived out of order) gain, which scores 0 and breaks
    the state machine's consecutive-confirmation streak even when the
    underlying growth is a real, sustained breakout.

    Input doesn't need to be pre-sorted or duplicate-free; output is sorted
    ascending by sim_hours with strictly increasing timestamps.
    """
    best_by_hour: dict[float, int] = {}
    for sample in samples:
        current_best = best_by_hour.get(sample.sim_hours)
        if current_best is None or sample.views > current_best:
            best_by_hour[sample.sim_hours] = sample.views
    return [SamplePoint(sim_hours=hour, views=views) for hour, views in sorted(best_by_hour.items())]


def compute_interval_signals(samples: list[SamplePoint], followers: int) -> list[IntervalSignal]:
    """Compute one IntervalSignal per consecutive (deduplicated) sample pair.

    Samples don't need to be pre-sorted or duplicate-free — see
    _dedupe_samples. Fewer than 2 distinct timestamps yields no intervals.
    """
    samples = _dedupe_samples(samples)
    if len(samples) < 2:
        return []

    followers = max(followers, 1)

    # Baseline: the post's own early velocity, averaged over its first
    # BASELINE_WINDOW_SAMPLES intervals — a first-order proxy for "the
    # trajectory this post was already on," so later intervals can be judged
    # against their own post rather than an arbitrary global constant.
    baseline_count = min(config.BASELINE_WINDOW_SAMPLES, len(samples) - 1)
    baseline_velocities = [
        _velocity(samples[i], samples[i + 1]) for i in range(baseline_count)
    ]
    baseline_velocity = sum(baseline_velocities) / len(baseline_velocities)
    baseline_velocity = max(baseline_velocity, config.BASELINE_EPSILON)

    signals: list[IntervalSignal] = []
    prev_velocity: float | None = None

    for i in range(1, len(samples)):
        a, b = samples[i - 1], samples[i]
        # Should be unreachable after _dedupe_samples (which guarantees
        # strictly increasing timestamps), but never divide by zero — skip
        # rather than emit a phantom interval either way.
        if b.sim_hours - a.sim_hours <= 0:
            continue
        absolute_gain = b.views - a.views
        relative_growth_pct = absolute_gain / max(a.views, 1) * 100
        velocity = _velocity(a, b)
        acceleration = None if prev_velocity is None else velocity - prev_velocity
        prev_velocity = velocity

        follower_velocity = velocity / followers
        trajectory_ratio = velocity / baseline_velocity

        score = 0.5 * min(trajectory_ratio / config.BASELINE_RATIO_REFERENCE, 1.0) + 0.5 * min(
            follower_velocity / config.FOLLOWER_VELOCITY_REFERENCE, 1.0
        )
        score = max(score, 0.0)

        if absolute_gain < config.MIN_VIEWS_FLOOR:
            gate_reason = "below_volume_floor"
        elif relative_growth_pct < config.RELATIVE_GROWTH_THRESHOLD_PCT:
            gate_reason = "insufficient_relative_growth"
        elif score < config.WATCH_SCORE_THRESHOLD:
            gate_reason = "weak_normalized_momentum"
        else:
            gate_reason = None

        signals.append(
            IntervalSignal(
                sim_hours=b.sim_hours,
                absolute_gain=absolute_gain,
                relative_growth_pct=relative_growth_pct,
                velocity=velocity,
                acceleration=acceleration,
                follower_velocity=follower_velocity,
                trajectory_ratio=trajectory_ratio,
                score=score,
                qualifies=gate_reason is None,
                gate_reason=gate_reason,
            )
        )

    return signals
