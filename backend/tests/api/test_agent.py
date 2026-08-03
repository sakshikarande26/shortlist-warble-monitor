"""Marketing agent tests. The Anthropic client is always mocked — these
never make a network call, and never touch the Warble API.
"""

import pathlib
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import agent
from app.db import dao
from app.db.base import get_session
from app.main import app


async def _seed() -> None:
    async with get_session() as session:
        await dao.upsert_creator(
            session, id="wc_a", handle="h", name="n", platform="p",
            followers=10_000, fetched_at_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id="wp_a", creator_id="wc_a", platform="p",
            first_seen_sim_hours=0.0, caption="a caption",
        )
        for sim_hours, views in [
            (0.0, 2000), (1.0, 3000), (2.0, 4500), (3.0, 6750), (4.0, 10125), (5.0, 15187)
        ]:
            await dao.insert_sample(
                session, post_id="wp_a", views=views, likes=views // 10, comments=views // 100,
                metrics_at="2026-07-01T00:00:00Z", sim_hours=sim_hours, source="live",
            )
        await session.commit()


async def _chat(message: str = "what changed?", session_id: str = "s1", post_id: str | None = None) -> dict:
    body = {"session_id": session_id, "message": message}
    if post_id:
        body["selected_post_id"] = post_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/agent/chat", json=body)
    assert response.status_code == 200
    return response.json()


def _fake_reply(text: str):
    """Mimics the shape of an Anthropic messages.create() response."""
    block = type("Block", (), {"type": "text", "text": text})()
    return type("Response", (), {"content": [block]})()


@pytest.fixture(autouse=True)
def _clear_sessions():
    agent._SESSIONS.clear()
    yield
    agent._SESSIONS.clear()


@pytest.mark.asyncio
async def test_falls_back_when_key_missing(monkeypatch):
    await _seed()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    body = await _chat()

    assert body["llm_available"] is False
    assert body["text"]  # a real deterministic answer, not an error string
    assert body["facts_used"]["program"]["posts_watched"] == 1


@pytest.mark.asyncio
async def test_falls_back_when_api_errors(monkeypatch):
    await _seed()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic") as client_cls:
        client_cls.return_value.messages.create = AsyncMock(side_effect=RuntimeError("boom"))
        body = await _chat()

    assert body["llm_available"] is False
    assert "error" not in body["text"].lower()


@pytest.mark.asyncio
async def test_invented_number_is_rejected(monkeypatch):
    await _seed()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic") as client_cls:
        client_cls.return_value.messages.create = AsyncMock(
            return_value=_fake_reply("This post pulled in 987654 views from a 42% lift.")
        )
        body = await _chat(post_id="wp_a")

    assert body["llm_available"] is False
    assert "987654" not in body["text"]


@pytest.mark.asyncio
async def test_grounded_reply_is_kept(monkeypatch):
    await _seed()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic") as client_cls:
        client_cls.return_value.messages.create = AsyncMock(
            return_value=_fake_reply("Momentum has held rather than spiked once. Worth a look.")
        )
        body = await _chat(post_id="wp_a")

    assert body["llm_available"] is True
    assert body["text"].startswith("Momentum has held")


@pytest.mark.asyncio
async def test_reply_contradicting_status_is_rejected(monkeypatch):
    await _seed()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        actual = (await client.get("/api/posts/wp_a")).json()["status_label"]
    wrong = "Steady" if actual != "Steady" else "Taking off"

    with patch("anthropic.AsyncAnthropic") as client_cls:
        client_cls.return_value.messages.create = AsyncMock(
            return_value=_fake_reply(f"This one is {wrong} and not worth your time.")
        )
        body = await _chat(post_id="wp_a")

    assert body["llm_available"] is False


@pytest.mark.asyncio
async def test_session_memory_accumulates_and_clears(monkeypatch):
    await _seed()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    await _chat("first question", session_id="s-mem")
    await _chat("second question", session_id="s-mem")
    assert len(agent._SESSIONS["s-mem"]) == 4  # 2 user + 2 assistant

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/agent/chat/s-mem")
    assert response.status_code == 200
    assert "s-mem" not in agent._SESSIONS


@pytest.mark.asyncio
async def test_history_is_capped(monkeypatch):
    await _seed()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    for i in range(agent.MAX_HISTORY_MESSAGES):
        await _chat(f"question {i}", session_id="s-cap")

    assert len(agent._SESSIONS["s-cap"]) == agent.MAX_HISTORY_MESSAGES


def test_no_api_key_in_frontend_source():
    """The key is server-side only; nothing in the frontend may reference it."""
    frontend = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "src"
    for path in frontend.rglob("*.ts*"):
        assert "ANTHROPIC_API_KEY" not in path.read_text(), f"key referenced in {path}"
        assert "sk-ant-" not in path.read_text(), f"key literal in {path}"
