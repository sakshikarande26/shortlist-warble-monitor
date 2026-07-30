"""Probe GET /me only. Does NOT touch any other endpoint, since the sim
clock starts on the first non-/me request — this script must never
activate it.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.client import WarbleClient
from app.config import settings


async def main() -> None:
    async with WarbleClient(
        api_key=settings.warble_api_key, base_url=settings.warble_base_url
    ) as client:
        me = await client.get_me()
        print(json.dumps(me.model_dump(), indent=2))
        print("rate limit:", client.last_rate_limit.model_dump() if client.last_rate_limit else None)


if __name__ == "__main__":
    asyncio.run(main())
