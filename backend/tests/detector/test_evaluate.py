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


def test_real_large_post_trajectory_reaches_breakout_during_the_climb():
    # Exact real data for post wp_1047778c8d: long, effectively flat run
    # around ~85k-105k views, then an explosive climb toward 1.13M.
    # Includes real duplicate-timestamp rows (e.g. two rows at sim_hours
    # 25.321: 845590 and 1021326) to re-validate dedup end-to-end on this
    # trajectory. Before the OR-gate fix, the climb's later intervals (huge
    # absolute gains but single-digit-percent relative growth once the base
    # is large) failed the AND-gated volume floor and got demoted straight
    # back to COOLING instead of confirming into BREAKOUT.
    raw = [
        (0.032, 85503), (0.032, 85419), (0.032, 85419), (0.048, 86009),
        (0.548, 86703), (0.548, 86964), (1.049, 86964), (1.335, 85419),
        (1.335, 87340), (1.335, 85419), (1.434, 85419), (1.434, 85419),
        (1.434, 87488), (2.466, 88206), (2.466, 88206), (2.966, 88970),
        (2.966, 88719), (3.466, 90239), (3.466, 90400), (3.966, 90400),
        (4.467, 92067), (4.467, 92102), (4.967, 92102), (4.967, 92706),
        (5.467, 92911), (5.467, 93304), (5.967, 93432), (5.967, 93432),
        (6.467, 93432), (6.967, 94333), (6.967, 94714), (7.468, 93432),
        (7.468, 95423), (7.468, 95590), (7.968, 95590), (7.968, 95590),
        (8.468, 95590), (8.968, 95590), (8.968, 97024), (9.468, 97215),
        (9.468, 97215), (9.968, 97215), (9.968, 97215), (10.469, 97215),
        (10.969, 98255), (10.969, 98429), (11.469, 98429), (11.469, 98429),
        (11.969, 98429), (11.969, 99246), (12.469, 99323), (12.469, 99323),
        (12.969, 99323), (13.47, 98429), (13.47, 99483), (13.47, 99483),
        (13.97, 99483), (13.97, 99483), (14.47, 99900), (14.784, 98429),
        (14.784, 98429), (14.784, 100394), (14.817, 100496), (15.317, 100904),
        (15.317, 100968), (15.818, 101076), (15.818, 101104), (16.318, 101538),
        (16.318, 101538), (16.818, 101538), (17.318, 101538), (17.318, 102236),
        (17.818, 102289), (17.818, 102289), (18.318, 102763), (18.318, 102289),
        (18.819, 103022), (19.319, 103108), (19.319, 103108), (19.819, 103108),
        (19.819, 103108), (20.319, 103618), (20.319, 103601), (20.819, 103776),
        (20.819, 102289), (20.819, 103692), (21.319, 103846), (21.82, 103846),
        (21.82, 103846), (22.32, 103846), (22.32, 104037), (22.82, 104322),
        (22.82, 104048), (23.32, 104390), (23.82, 104390), (23.82, 105572),
        (24.32, 170002), (24.32, 305159), (24.821, 481118), (24.821, 674966),
        (25.321, 845590), (25.321, 1021326), (25.821, 1091002),
        (26.321, 1131730), (26.321, 1131757),
    ]
    samples = [SamplePoint(sim_hours=h, views=v) for h, v in raw]

    result = evaluate_post(samples, followers=1_022_599)

    assert result.state == "BREAKOUT"
    assert result.reason == "sustained_growth_breakout"


def test_follower_normalization_changes_outcome_for_identical_trajectory():
    views = [3000, 3600]
    small_creator = evaluate_post(pts(views), followers=2_000)
    large_creator = evaluate_post(pts(views), followers=2_000_000)
    assert small_creator.state == "WATCH"
    assert large_creator.state == "NEW"
    assert small_creator.score > large_creator.score
