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


@pytest.mark.asyncio
async def test_home_breakout_post_lands_in_act_now():
    await _seed_creator()
    await _seed_post("wp_0000000001")
    await _insert_samples(
        "wp_0000000001",
        [(0.0, 2000), (1.0, 3000), (2.0, 4500), (3.0, 6750), (4.0, 10125), (5.0, 15187)],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/home")

    assert response.status_code == 200
    body = response.json()

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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        home_response = await client.get("/api/home")
        detail_response = await client.get("/api/posts/wp_0000000002")

    home_body = home_response.json()
    act_now_ids = [p["post_id"] for p in home_body["act_now"]]
    watch_ids = [p["post_id"] for p in home_body["watch_closely"]]
    assert "wp_0000000002" not in act_now_ids
    assert "wp_0000000002" not in watch_ids
    assert home_body["total_posts"] == 1

    detail_body = detail_response.json()
    assert detail_body["state"] == "NEW"
    assert detail_body["status_label"] == "Quiet"
    assert detail_body["published_at"] is None  # never set by _seed_post; present but null


@pytest.mark.asyncio
async def test_home_comparative_mover_surfaces_without_absolute_state():
    """The core of the comparative-ranking fix: a post that never
    independently qualifies for the detector's own state machine (stays
    NEW) should still surface on Home if it's growing much faster than
    this specific creator's OTHER posts at the same age — ranking is
    relative to the creator's own norm, not the absolute detector state.
    With no BREAKOUT posts for this creator, it's the sole top mover and so
    lands in act_now itself (confirmed BREAKOUT + top movers) rather than
    watch_closely (the next tier) — see the ranking test below for tiering.
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/home")

    assert response.status_code == 200
    body = response.json()

    act_now_ids = [p["post_id"] for p in body["act_now"]]
    watch_ids = [p["post_id"] for p in body["watch_closely"]]
    assert "wp_mover" in act_now_ids
    assert "wp_baseline_1" not in act_now_ids and "wp_baseline_1" not in watch_ids
    assert "wp_baseline_2" not in act_now_ids and "wp_baseline_2" not in watch_ids

    mover = next(p for p in body["act_now"] if p["post_id"] == "wp_mover")
    assert mover["state"] == "NEW"  # never independently qualifies
    assert mover["evidence"]["creator_pace_basis"] == "creator"
    assert mover["evidence"]["creator_pace_ratio"] > 2.0
    # Never a raw score/percentile anywhere else on the post
    assert "percentile" not in mover and "rank" not in mover


@pytest.mark.asyncio
async def test_home_caps_act_now_and_overflows_extra_movers_to_watch_closely():
    """When there are more qualifying comparative movers than fit in
    act_now's cap, the extras spill into watch_closely as "the next tier" —
    ranking, not an arbitrary state split.

    Eight flat baseline posts (more than the nearest-neighbor window the
    ranking uses) so every mover's own baseline is drawn only from genuinely
    flat posts, not contaminated by nearest-by-age ties with the OTHER
    movers seeded alongside it.
    """
    await _seed_creator()
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/home")

    body = response.json()
    act_now_ids = [p["post_id"] for p in body["act_now"]]
    watch_ids = [p["post_id"] for p in body["watch_closely"]]

    assert len(act_now_ids) <= 5
    assert len(watch_ids) <= 5
    assert set(act_now_ids) | set(watch_ids) == set(mover_ids)  # all 6 movers surface somewhere
    assert set(act_now_ids) & set(watch_ids) == set()  # never in both
    for i in range(8):
        assert f"wp_baseline_{i}" not in act_now_ids
        assert f"wp_baseline_{i}" not in watch_ids

    # The fastest mover (wp_mover_5, step=110) must outrank the slowest
    # (wp_mover_0, step=60) — comparative rank, not insertion order.
    assert "wp_mover_5" in act_now_ids
    assert "wp_mover_0" in watch_ids


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
    assert body["creator"]["handle"] == "h"
    assert body["is_gone"] is False
    assert body["current_sim_hours"] == 2.466


@pytest.mark.asyncio
async def test_post_detail_404_for_unknown_post():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/posts/wp_does_not_exist")

    assert response.status_code == 404
