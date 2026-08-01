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
async def test_home_breakout_post_lands_in_attention_queue():
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

    attention_ids = [p["post_id"] for p in body["attention_queue"]]
    other_ids = [p["post_id"] for p in body["other_posts"]]
    assert "wp_0000000001" in attention_ids
    assert "wp_0000000001" not in other_ids

    post = next(p for p in body["attention_queue"] if p["post_id"] == "wp_0000000001")
    assert post["state"] == "BREAKOUT"
    assert post["status_label"] == "Act now"
    assert post["needs_attention"] is True
    assert post["views"] == 15187


@pytest.mark.asyncio
async def test_home_flat_post_lands_in_other_posts():
    await _seed_creator()
    await _seed_post("wp_0000000002")
    await _insert_samples(
        "wp_0000000002",
        [(0.0, 1000), (1.0, 1005), (2.0, 1010), (3.0, 1015), (4.0, 1020), (5.0, 1025)],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/home")

    body = response.json()
    other_ids = [p["post_id"] for p in body["other_posts"]]
    assert "wp_0000000002" in other_ids

    post = next(p for p in body["other_posts"] if p["post_id"] == "wp_0000000002")
    assert post["state"] == "NEW"
    assert post["status_label"] == "Quiet"
    assert post["needs_attention"] is False


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


@pytest.mark.asyncio
async def test_post_detail_404_for_unknown_post():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/posts/wp_does_not_exist")

    assert response.status_code == 404
