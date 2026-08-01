"""Tunable thresholds for momentum scoring and the breakout state machine.

All numeric defaults here are best-effort starting points, not calibrated
against real Warble traffic (we don't have any yet — same caveat as the
client's inferred response schemas). They're collected in one place
specifically so they can be tuned later without touching scoring logic.
"""

# --- Volume floor: an interval qualifies as a momentum signal if it clears
# EITHER gate below (not both) — a big post adding a huge absolute number of
# views (e.g. +40k) can be well under the relative-growth threshold once its
# base is large, and that's still a real breakout, not noise. The relative
# path stays paired with SMALL_ABSOLUTE_FLOOR so it can't be satisfied by a
# tiny-number spike (5 -> 50 views = 900% but only +45, still rejected).
MIN_VIEWS_FLOOR = 500  # absolute view gain that alone is enough to qualify
RELATIVE_GROWTH_THRESHOLD_PCT = 15.0  # % growth that qualifies IF paired with SMALL_ABSOLUTE_FLOOR
SMALL_ABSOLUTE_FLOOR = 100  # minimum absolute gain for the relative-growth path to count

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
