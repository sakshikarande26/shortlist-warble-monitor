"""Direct tests of WarbleClient against a mocked httpx transport — no real
network. These specifically cover the real-API-shape fixes (data envelope
unwrap, status-code-derived duplicate signal, note length cap) that the
sampler/alerter tests can't exercise, since those use a hand-rolled fake
that bypasses WarbleClient.post_alert/_request entirely.
"""

import httpx
import pytest

from app.client.client import WarbleClient
from app.client.exceptions import WarbleValidationError


def _client_with_transport(handler) -> WarbleClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://warble.test/v1")
    return WarbleClient(api_key="test-key", client=http_client)


@pytest.mark.asyncio
async def test_get_creators_unwraps_data_envelope():
    async def handler(request):
        return httpx.Response(200, json={"data": [{
            "id": "wc_0000000001", "handle": "h", "name": "n",
            "category": "c", "bio": "b", "platform": "clip", "followers": 100,
        }]})

    client = _client_with_transport(handler)
    creators = await client.get_creators()
    assert len(creators) == 1
    assert creators[0].followers == 100


@pytest.mark.asyncio
async def test_get_creator_posts_uses_data_and_next_cursor():
    async def handler(request):
        return httpx.Response(200, json={
            "data": [{
                "id": "wp_0000000001", "creator_id": "wc_0000000001",
                "creator_handle": "h", "creator_name": "n", "platform": "clip",
                "published_at": "2026-07-05T00:00:00.000Z", "caption": "c",
                "metrics": {"views": 1, "likes": 2, "comments": 3},
                "metrics_cached_at": "2026-07-06T00:00:00.000Z",
            }],
            "next_cursor": "abc",
        })

    client = _client_with_transport(handler)
    page = await client.get_creator_posts("wc_0000000001")
    assert len(page.data) == 1
    assert page.data[0].metrics.views == 1
    assert page.data[0].metrics_cached_at == "2026-07-06T00:00:00.000Z"
    assert page.next_cursor == "abc"


@pytest.mark.asyncio
async def test_get_posts_batch_unwraps_data_envelope():
    async def handler(request):
        return httpx.Response(200, json={"data": [{
            "id": "wp_0000000001", "creator_id": "wc_0000000001",
            "creator_handle": "h", "creator_name": "n", "platform": "clip",
            "published_at": "2026-07-05T00:00:00.000Z", "caption": "c",
            "metrics": {"views": 1, "likes": 2, "comments": 3},
            "metrics_at": "2026-07-06T00:00:00.000Z",
        }]})

    client = _client_with_transport(handler)
    result = await client.get_posts_batch(["wp_0000000001"])
    assert len(result.posts) == 1
    assert result.posts[0].metrics.views == 1
    assert result.missing_ids == []


@pytest.mark.asyncio
async def test_get_alerts_unwraps_data_envelope():
    async def handler(request):
        return httpx.Response(200, json={"data": [{
            "post_id": "wp_0000000001", "note": None,
            "received_sim_hours": 1.5, "received_at": "2026-07-06T00:00:00.000Z",
        }]})

    client = _client_with_transport(handler)
    alerts = await client.get_alerts()
    assert len(alerts) == 1
    assert alerts[0].received_sim_hours == 1.5
    assert alerts[0].note is None


@pytest.mark.asyncio
async def test_post_alert_201_is_not_duplicate():
    async def handler(request):
        return httpx.Response(201, json={
            "ok": True, "post_id": "wp_0000000001",
            "received_sim_hours": 1.0, "received_at": "2026-07-06T00:00:00.000Z",
            "duplicate": False,
        })

    client = _client_with_transport(handler)
    result = await client.post_alert("wp_0000000001")
    assert result.duplicate is False


@pytest.mark.asyncio
async def test_post_alert_status_code_wins_over_disagreeing_body_field():
    async def handler(request):
        # Body claims not-duplicate, but the documented status code (200)
        # says duplicate — status code is authoritative per the docs.
        return httpx.Response(200, json={
            "ok": True, "post_id": "wp_0000000001",
            "received_sim_hours": 1.0, "received_at": "2026-07-06T00:00:00.000Z",
            "duplicate": False,
        })

    client = _client_with_transport(handler)
    result = await client.post_alert("wp_0000000001")
    assert result.duplicate is True


@pytest.mark.asyncio
async def test_post_alert_rejects_note_over_500_chars_without_a_request():
    called = False

    async def handler(request):
        nonlocal called
        called = True
        return httpx.Response(201, json={})

    client = _client_with_transport(handler)
    with pytest.raises(WarbleValidationError):
        await client.post_alert("wp_0000000001", note="x" * 501)
    assert called is False
