import math

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import dao
from app.db.base import get_session
from app.main import app


async def _seed_creator(creator_id: str = "wc_0000000001", followers: int = 10_000) -> None:
    async with get_session() as session:
        await dao.upsert_creator(
            session, id=creator_id, handle="h", name="n", platform="p",
            followers=followers, fetched_at_sim_hours=0.0,
        )
        await session.commit()


async def _seed_post(post_id: str, creator_id: str = "wc_0000000001") -> None:
    async with get_session() as session:
        await dao.upsert_post(
            session, id=post_id, creator_id=creator_id,
            platform="p", first_seen_sim_hours=0.0, caption="a caption",
        )
        await session.commit()


async def _insert_samples(post_id: str, points: list[tuple[float, int]]) -> None:
    async with get_session() as session:
        for sim_hours, views in points:
            await dao.insert_sample(
                session, post_id=post_id, views=views, likes=views // 10, comments=views // 100,
                metrics_at="t", sim_hours=sim_hours, source="live",
            )
        await session.commit()


async def _get_home() -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/home")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_home_breakout_post_lands_in_act_now():
    await _seed_creator()
    await _seed_post("wp_0000000001")
    await _insert_samples(
        "wp_0000000001",
        [(0.0, 2000), (1.0, 3000), (2.0, 4500), (3.0, 6750), (4.0, 10125), (5.0, 15187)],
    )

    body = await _get_home()

    act_now_ids = [p["post_id"] for p in body["act_now"]]
    watch_ids = [p["post_id"] for p in body["watch_closely"]]
    assert "wp_0000000001" in act_now_ids
    assert "wp_0000000001" not in watch_ids

    post = next(p for p in body["act_now"] if p["post_id"] == "wp_0000000001")
    assert post["state"] == "BREAKOUT"
    assert post["status_label"] == "Taking off"
    assert post["views"] == 15187
    assert post["latest_sim_hours"] == 5.0
    assert body["current_sim_hours"] == 5.0
    assert post["sparkline"] == [2000, 3000, 4500, 6750, 10125, 15187]
    # Sole post for this creator — no baseline to compare against, so the
    # comparative signal falls back to the post's own trajectory.
    assert post["evidence"]["creator_pace_basis"] == "self"


@pytest.mark.asyncio
async def test_home_flat_post_excluded_from_triage():
    await _seed_creator()
    await _seed_post("wp_0000000002")
    await _insert_samples(
        "wp_0000000002",
        [(0.0, 1000), (1.0, 1005), (2.0, 1010), (3.0, 1015), (4.0, 1020), (5.0, 1025)],
    )

    home_body = await _get_home()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        detail_response = await client.get("/api/posts/wp_0000000002")

    act_now_ids = [p["post_id"] for p in home_body["act_now"]]
    watch_ids = [p["post_id"] for p in home_body["watch_closely"]]
    assert "wp_0000000002" not in act_now_ids
    assert "wp_0000000002" not in watch_ids
    assert home_body["total_posts"] == 1

    detail_body = detail_response.json()
    assert detail_body["state"] == "NEW"
    assert detail_body["status_label"] == "Steady"
    assert detail_body["alert_sent"] is False
    assert detail_body["published_at"] is None  # never set by _seed_post; present but null


@pytest.mark.asyncio
async def test_home_comparative_mover_lands_in_watch_closely_without_absolute_state():
    """The core of the comparative-ranking fix: a post that never
    independently qualifies for the detector's own state machine (stays
    NEW) should still surface on Home — in watch_closely, since it isn't
    BREAKOUT — if it's growing much faster than this specific creator's
    OTHER posts at the same age. Ranking is relative to the creator's own
    norm, not the absolute detector state.
    """
    await _seed_creator()
    # Two unremarkable baseline posts — flat growth, never independently
    # qualify, but define "typical" pace for this creator at each age.
    for post_id in ("wp_baseline_1", "wp_baseline_2"):
        await _seed_post(post_id)
        await _insert_samples(
            post_id,
            [(0.0, 1000), (1.0, 1010), (2.0, 1020), (3.0, 1030), (4.0, 1040), (5.0, 1050)],
        )
    # Grows ~8x faster than this creator's other posts at the same age, but
    # each individual interval still stays under the detector's own
    # absolute qualification floor (80 views/hour, 8% relative growth —
    # both below MIN_VIEWS_FLOOR/RELATIVE_GROWTH_THRESHOLD_PCT), so its own
    # state never leaves NEW.
    await _seed_post("wp_mover")
    await _insert_samples(
        "wp_mover",
        [(0.0, 1000), (1.0, 1080), (2.0, 1160), (3.0, 1240), (4.0, 1320), (5.0, 1400)],
    )

    body = await _get_home()

    act_now_ids = [p["post_id"] for p in body["act_now"]]
    watch_ids = [p["post_id"] for p in body["watch_closely"]]
    assert "wp_mover" in watch_ids
    assert "wp_mover" not in act_now_ids
    assert "wp_baseline_1" not in act_now_ids and "wp_baseline_1" not in watch_ids
    assert "wp_baseline_2" not in act_now_ids and "wp_baseline_2" not in watch_ids

    mover = next(p for p in body["watch_closely"] if p["post_id"] == "wp_mover")
    assert mover["state"] == "NEW"  # never independently qualifies
    assert mover["status_label"] == "Worth watching"
    assert mover["evidence"]["creator_pace_basis"] == "creator"
    assert mover["evidence"]["creator_pace_ratio"] > 2.0
    # Never a raw score/percentile anywhere else on the post
    assert "percentile" not in mover and "rank" not in mover


@pytest.mark.asyncio
async def test_home_caps_watch_closely_and_drops_the_weakest_overflow():
    """Cap each section at 5 — more qualifying movers than that, and the
    weakest simply don't make today's list (they're still individually
    "Worth watching" if you look them up directly; see the creator-detail
    tests). There's no overflow between sections — act_now and
    watch_closely are strictly membership-partitioned by status_label.
    """
    await _seed_creator()
    # More flat baseline posts than the nearest-neighbor window, so every
    # mover's own baseline is drawn only from genuinely flat posts, not
    # contaminated by nearest-by-age ties with the OTHER movers below.
    for i in range(8):
        post_id = f"wp_baseline_{i}"
        await _seed_post(post_id)
        await _insert_samples(
            post_id,
            [(0.0, 1000), (1.0, 1010), (2.0, 1020), (3.0, 1030), (4.0, 1040), (5.0, 1050)],
        )
    # Six movers, each faster than the last, so ranking is unambiguous.
    # Every one stays under the absolute qualification floor.
    mover_ids = []
    for i in range(6):
        post_id = f"wp_mover_{i}"
        mover_ids.append(post_id)
        step = 60 + i * 10  # 60, 70, ..., 110 views/hour
        views = [1000]
        for _ in range(5):
            views.append(views[-1] + step)
        await _seed_post(post_id)
        await _insert_samples(post_id, list(zip([0.0, 1.0, 2.0, 3.0, 4.0, 5.0], views)))

    body = await _get_home()
    act_now_ids = [p["post_id"] for p in body["act_now"]]
    watch_ids = [p["post_id"] for p in body["watch_closely"]]

    assert act_now_ids == []  # no BREAKOUT posts in this scenario
    assert len(watch_ids) == 5  # capped, not all 6
    for i in range(8):
        assert f"wp_baseline_{i}" not in watch_ids

    # The 5 fastest movers make the cut; the single slowest (wp_mover_0)
    # doesn't — comparative rank, not insertion order.
    assert set(watch_ids) == {f"wp_mover_{i}" for i in range(1, 6)}
    assert "wp_mover_0" not in watch_ids


@pytest.mark.asyncio
async def test_home_section_membership_always_agrees_with_badge_text():
    """The explicit invariant this feature is built around: whatever a
    post's section is, its own status_label must say the same thing. This
    is the test that would fail on the original bug (an "Act now" section
    containing a card badged "Steady")."""
    await _seed_creator("wc_a")
    await _seed_post("wp_breakout", creator_id="wc_a")
    await _insert_samples(
        "wp_breakout",
        [(0.0, 2000), (1.0, 3000), (2.0, 4500), (3.0, 6750), (4.0, 10125), (5.0, 15187)],
    )

    await _seed_creator("wc_b")
    await _seed_post("wp_baseline", creator_id="wc_b")
    await _insert_samples(
        "wp_baseline",
        [(0.0, 1000), (1.0, 1010), (2.0, 1020), (3.0, 1030), (4.0, 1040), (5.0, 1050)],
    )
    await _seed_post("wp_mover", creator_id="wc_b")
    await _insert_samples(
        "wp_mover",
        [(0.0, 1000), (1.0, 1080), (2.0, 1160), (3.0, 1240), (4.0, 1320), (5.0, 1400)],
    )

    body = await _get_home()
    assert body["act_now"], "expected at least one act_now post for this invariant to be meaningful"
    assert body["watch_closely"], "expected at least one watch_closely post for this invariant to be meaningful"

    for post in body["act_now"]:
        assert post["status_label"] == "Taking off", (
            f"act_now contains {post['post_id']!r} badged {post['status_label']!r}"
        )
    for post in body["watch_closely"]:
        assert post["status_label"] == "Worth watching", (
            f"watch_closely contains {post['post_id']!r} badged {post['status_label']!r}"
        )


@pytest.mark.asyncio
async def test_creator_pace_ratio_never_fabricated_on_degenerate_baseline():
    """Reproduces the real bug found against live data: when a creator's
    other posts are essentially flat (near-zero velocity), naively dividing
    produced ratios in the hundreds of thousands. The fix must never
    surface Infinity, NaN, or an absurd multiple — a degenerate baseline
    means "not enough history" (null), not a fabricated number.
    """
    await _seed_creator()
    # Two "baseline" posts with essentially zero growth (some samples flat,
    # one tiny blip) — a genuinely near-zero baseline velocity.
    for post_id in ("wp_dead_1", "wp_dead_2"):
        await _seed_post(post_id)
        await _insert_samples(
            post_id,
            [(0.0, 5000), (1.0, 5000), (2.0, 5000), (3.0, 5001), (4.0, 5001), (5.0, 5001)],
        )
    await _seed_post("wp_growing")
    await _insert_samples(
        "wp_growing",
        [(0.0, 1000), (1.0, 1500), (2.0, 2200), (3.0, 3300), (4.0, 4900), (5.0, 7300)],
    )

    body = await _get_home()
    all_posts = body["act_now"] + body["watch_closely"]
    growing = next((p for p in all_posts if p["post_id"] == "wp_growing"), None)

    # Whether or not it made a section, its evidence (fetched via post
    # detail, which computes the same way) must never contain a fabricated
    # value.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        detail = (await client.get("/api/posts/wp_growing")).json()

    ratio = detail["evidence"]["creator_pace_ratio"]
    if ratio is not None:
        assert math.isfinite(ratio)
        assert ratio > 0
        assert ratio <= 20.0  # the sanity ceiling — never a fake-precise huge multiple
    if growing is not None:
        assert growing["status_label"] in ("Taking off", "Worth watching", "Steady")


@pytest.mark.asyncio
async def test_post_detail_dedupes_trajectory_and_has_evidence():
    await _seed_creator(followers=10_000)
    await _seed_post("wp_0000000003")
    await _insert_samples(
        "wp_0000000003",
        [
            (0.032, 16767), (0.548, 16818), (0.548, 16818),  # real duplicate timestamp
            (1.335, 16889), (2.466, 16971),
        ],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/posts/wp_0000000003")

    assert response.status_code == 200
    body = response.json()

    trajectory_hours = [p["sim_hours"] for p in body["trajectory"]]
    assert len(trajectory_hours) == len(set(trajectory_hours))  # no duplicate timestamps
    assert len(trajectory_hours) == 4  # 5 raw samples, 1 exact duplicate collapsed

    assert body["evidence"] is not None
    assert body["evidence"]["window_hours"] is not None
    assert body["evidence"]["consecutive_qualifying_checks"] >= 0
    assert body["alert_sent"] is False
    assert body["creator"]["handle"] == "h"
    assert body["is_gone"] is False
    assert body["current_sim_hours"] == 2.466


@pytest.mark.asyncio
async def test_post_detail_404_for_unknown_post():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/posts/wp_does_not_exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_status_endpoint_reports_real_system_context():
    await _seed_creator()
    await _seed_post("wp_status_1")
    await _insert_samples(
        "wp_status_1",
        [(0.0, 2000), (1.0, 3000), (2.0, 4500), (3.0, 6750), (4.0, 10125), (5.0, 15187)],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["posts_tracked"] == 1
    assert body["last_checked_sim_hours"] == 5.0
    assert body["most_notable_post"]["post_id"] == "wp_status_1"
    assert body["most_notable_post"]["status_label"] == "Taking off"
    assert body["most_recent_alert"] is None  # no alerts submitted in this test
