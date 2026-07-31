"""Tunable thresholds for momentum scoring and the breakout state machine.

All numeric defaults here are best-effort starting points, not calibrated
against real Warble traffic (we don't have any yet — same caveat as the
client's inferred response schemas). They're collected in one place
specifically so they can be tuned later without touching scoring logic.
"""

# --- Volume floor: an interval only "qualifies" as a momentum signal if it
# clears BOTH the relative and absolute gates below. The absolute gate is
# what stops tiny-number spikes (e.g. 5 -> 50 views = 900% but noise) from
# registering as breakouts.
MIN_VIEWS_FLOOR = 500  # minimum absolute view gain between samples
RELATIVE_GROWTH_THRESHOLD_PCT = 15.0  # minimum % growth between samples

# --- Baseline (post's own early trajectory) normalization.
BASELINE_WINDOW_SAMPLES = 2  # how many early intervals define a post's baseline pace
BASELINE_RATIO_REFERENCE = 3.0  # trajectory_ratio at/above this saturates that half of the score
BASELINE_EPSILON = 1e-6  # floor for baseline_velocity to avoid divide-by-near-zero blowups

# --- Follower-count normalization ("reach velocity": views/sim-hour per follower).
FOLLOWER_VELOCITY_REFERENCE = 0.01  # follower_velocity at/above this saturates that half of the score

# --- Interval qualification and state machine.
WATCH_SCORE_THRESHOLD = 0.3  # minimum composite score for an interval to "qualify"
CONSECUTIVE_CONFIRMATIONS_FOR_RISING = 2  # consecutive qualifying intervals: WATCH -> RISING
CONSECUTIVE_CONFIRMATIONS_FOR_BREAKOUT = 2  # further consecutive qualifying intervals: RISING -> BREAKOUT
