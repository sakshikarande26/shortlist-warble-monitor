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


@pytest.fixture
def _no_llm_key(monkeypatch):
    """Both places a key can come from: the process env, and settings
    (which is where a key in .env actually lands — pydantic-settings never
    exports into os.environ). Clearing only one leaves the agent quietly
    live against the real API during tests."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(agent.settings, "anthropic_api_key", None)


@pytest.mark.asyncio
async def test_falls_back_when_key_missing(_no_llm_key):
    await _seed()

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


def test_split_reply_separates_answer_and_reasoning():
    answer, reasoning = agent._split_reply(
        "ANSWER: Momentum held across checks.\nREASONING: The pace is the tell, not the raw reach."
    )
    assert answer == "Momentum held across checks."
    assert reasoning == "The pace is the tell, not the raw reach."


def test_split_reply_tolerates_missing_labels():
    """A reply that ignores the format is still a usable answer — it must
    never be dropped just because the labels weren't emitted."""
    answer, reasoning = agent._split_reply("Just a plain answer with no labels.")
    assert answer == "Just a plain answer with no labels."
    assert reasoning is None


@pytest.mark.asyncio
async def test_reasoning_is_returned_alongside_answer(monkeypatch):
    await _seed()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with patch("anthropic.AsyncAnthropic") as client_cls:
        client_cls.return_value.messages.create = AsyncMock(
            return_value=_fake_reply(
                "ANSWER: Momentum has held rather than spiked.\n"
                "REASONING: Sustained pace beats a one-off spike when deciding where spend goes."
            )
        )
        body = await _chat(post_id="wp_a")

    assert body["llm_available"] is True
    assert body["text"] == "Momentum has held rather than spiked."
    assert body["reasoning"].startswith("Sustained pace beats")


@pytest.mark.asyncio
async def test_offline_fallback_still_supplies_reasoning(_no_llm_key):
    """The side panel shouldn't go blank just because the model is down."""
    await _seed()

    body = await _chat(post_id="wp_a")

    assert body["llm_available"] is False
    assert body["reasoning"]


def test_grounded_numbers_accepts_scaled_suffix():
    """"40K" is a rounded restatement of a real 40000, not an invented
    number — the guardrail must normalize the suffix before comparing."""
    facts = {"selected_post": {"recent_gain_views": 40000}}
    assert agent._numbers_are_grounded("It picked up about 40K views.", facts)


def test_grounded_numbers_still_rejects_invented_scaled_number():
    facts = {"selected_post": {"recent_gain_views": 40000}}
    assert not agent._numbers_are_grounded("It picked up about 900K views.", facts)


@pytest.mark.asyncio
async def test_proactive_opening_line_is_not_a_user_turn(_no_llm_key):
    await _seed()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/agent/chat",
            json={"session_id": "s-proactive", "message": "", "proactive": True},
        )
    assert response.status_code == 200
    assert response.json()["text"]  # a real opening line, not empty
    assert len(agent._SESSIONS["s-proactive"]) == 1  # assistant turn only, no fake user turn


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
async def test_session_memory_accumulates_and_clears(_no_llm_key):
    await _seed()

    await _chat("first question", session_id="s-mem")
    await _chat("second question", session_id="s-mem")
    assert len(agent._SESSIONS["s-mem"]) == 4  # 2 user + 2 assistant

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.delete("/api/agent/chat/s-mem")
    assert response.status_code == 200
    assert "s-mem" not in agent._SESSIONS


@pytest.mark.asyncio
async def test_history_is_capped(_no_llm_key):
    await _seed()

    for i in range(agent.MAX_HISTORY_MESSAGES):
        await _chat(f"question {i}", session_id="s-cap")

    assert len(agent._SESSIONS["s-cap"]) == agent.MAX_HISTORY_MESSAGES


def test_no_api_key_in_frontend_source():
    """The key is server-side only; nothing in the frontend may reference it."""
    frontend = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "src"
    for path in frontend.rglob("*.ts*"):
        assert "ANTHROPIC_API_KEY" not in path.read_text(), f"key referenced in {path}"
        assert "sk-ant-" not in path.read_text(), f"key literal in {path}"


def test_creator_breakout_tally_counts_only_relevant_handles_and_caps():
    breakouts = [
        {"creator_handle": "a"},
        {"creator_handle": "a"},
        {"creator_handle": "b"},
        {"creator_handle": "c"},  # not relevant, excluded
        {"creator_handle": "d"},
        {"creator_handle": "e"},
        {"creator_handle": "f"},
        {"creator_handle": "g"},
    ]
    relevant = {"a", "b", "d", "e", "f", "g"}  # 6 relevant handles, cap is 5

    tally = agent._creator_breakout_tally(breakouts, relevant)

    assert tally["a"] == 2
    assert tally["b"] == 1
    assert "c" not in tally  # never in relevant_handles
    assert len(tally) == 5


def test_program_level_quick_prompts_return_distinct_text():
    """The offline fallback router's whole job is not collapsing different
    questions onto the same summary — this pins that down for every
    program-level quick prompt in AiPanel.tsx."""
    facts = {
        "program": {
            "posts_watched": 10,
            "creators_watched": 4,
            "status_counts": {"Taking off": 1, "Worth watching": 2, "Steady": 6, "Unavailable": 1},
            "current_sim_hour": 40.0,
            "window_progress": "Day 2 of 7",
        },
        "alerts": [{"post_id": "wp_a", "creator_handle": "a", "submitted": True}],
        "breakouts": [
            {"post_id": "wp_a", "creator_handle": "a", "climbed_multiple": 3.2, "officially_alerted": True},
        ],
        "selected_post": None,
        "top_movers": [{"creator_handle": "b", "status": "Worth watching", "baseline_multiple": 2.1}],
    }
    prompts = [
        "What changed since I checked?",
        "What deserves attention first?",
        "Give me a stakeholder update",
        "What have we alerted on so far?",
    ]
    answers = [agent.deterministic_answer(facts, p) for p in prompts]
    assert len(set(answers)) == len(answers), answers


def test_post_selected_quick_prompts_return_distinct_text():
    selected = {
        "creator_handle": "a",
        "status": "Taking off",
        "baseline_multiple": 2.4,
        "baseline_compared_to": "creator",
        "consecutive_elevated_checks": 3,
        "alert_sent": False,
        "is_creators_best_so_far": True,
        "most_recent_other_breakout": {"creator_handle": "b", "climbed_multiple": 1.8},
    }
    facts = {"selected_post": selected, "program": {}, "alerts": [], "breakouts": [], "top_movers": []}
    prompts = [
        "Why does this matter?",
        "Sustained or a spike?",
        "Explain this for leadership",
        "What would change your read?",
    ]
    answers = [agent.deterministic_answer(facts, p) for p in prompts]
    assert len(set(answers)) == len(answers), answers
