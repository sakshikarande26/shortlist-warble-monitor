"""Pure breakout state machine: a sequence of per-interval momentum signals
in, a sequence of states out. Carries a small amount of memory (a
consecutive-qualifying-interval counter) across the walk, which is exactly
why this needs to be a state machine rather than a stateless per-sample
classifier — a single outlier interval must not be enough to alert.
"""

from dataclasses import dataclass
from typing import Literal

from app.detector import config
from app.detector.momentum import IntervalSignal

PostState = Literal["NEW", "WATCH", "RISING", "BREAKOUT", "COOLING"]


@dataclass(frozen=True)
class StateAtTime:
    sim_hours: float
    state: PostState
    score: float
    reason: str


# Total consecutive qualifying intervals needed to go all the way from a
# cold start to BREAKOUT: the RISING confirmation streak, then further
# confirmations on top of it for BREAKOUT.
_HITS_FOR_BREAKOUT = (
    config.CONSECUTIVE_CONFIRMATIONS_FOR_RISING + config.CONSECUTIVE_CONFIRMATIONS_FOR_BREAKOUT
)


def run_state_machine(signals: list[IntervalSignal]) -> list[StateAtTime]:
    history: list[StateAtTime] = []
    state: PostState = "NEW"
    consecutive_hits = 0

    for signal in signals:
        if signal.qualifies:
            consecutive_hits += 1

            if state == "NEW":
                state = "WATCH"
                reason = "single_spike_watch"
            elif state == "WATCH":
                if consecutive_hits >= config.CONSECUTIVE_CONFIRMATIONS_FOR_RISING:
                    state = "RISING"
                    reason = "sustained_growth_rising"
                else:
                    reason = "single_spike_watch"
            elif state == "RISING":
                if consecutive_hits >= _HITS_FOR_BREAKOUT:
                    state = "BREAKOUT"
                    reason = "sustained_growth_breakout"
                else:
                    reason = "sustained_growth_rising"
            elif state == "BREAKOUT":
                reason = "sustained_growth_breakout"
            else:  # COOLING re-qualifying: has to re-earn RISING/BREAKOUT, not jump straight back
                state = "WATCH"
                consecutive_hits = 1
                reason = "single_spike_watch"
        else:
            consecutive_hits = 0
            if state == "WATCH":
                state = "NEW"
                reason = signal.gate_reason or "no_momentum"
            elif state in ("RISING", "BREAKOUT"):
                state = "COOLING"
                reason = "momentum_fading_cooling"
            else:  # NEW or COOLING: stays put
                reason = signal.gate_reason or "no_momentum"

        history.append(
            StateAtTime(sim_hours=signal.sim_hours, state=state, score=signal.score, reason=reason)
        )

    return history
