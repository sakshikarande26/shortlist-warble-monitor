"""FastAPI app entrypoint: wires up the read-only dashboard API and the
agent chat router, and — when a built frontend is present — serves it
from this same process so the whole product is one deployable service.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text

from app.api.agent import router as agent_router
from app.api.routes import _DATASET_CACHE_TTL_SECONDS, _get_dataset, router as api_router
from app.db.base import get_session

logger = logging.getLogger(__name__)

# Refresh a few seconds ahead of the cache's own TTL so a real page load
# never has to pay for the fetch-and-recompute itself — it just reads
# whatever this loop last put there. That's the actual fix for "every
# reload takes 5-10s": the dashboard endpoints were computing the whole
# watchlist on demand, on whichever request happened to land after the
# cache went stale. Moving that work off the request path to a background
# loop is enough on its own; it doesn't need a distributed system.
_CACHE_WARM_INTERVAL_SECONDS = max(_DATASET_CACHE_TTL_SECONDS - 5, 5)


async def _warm_dataset_cache_forever() -> None:
    while True:
        try:
            async with get_session() as session:
                await _get_dataset(session)
        except Exception:
            logger.exception("cache warmer: failed to refresh dataset cache")
        await asyncio.sleep(_CACHE_WARM_INTERVAL_SECONDS)


@asynccontextmanager
async def _lifespan(_: FastAPI):
    warmer = asyncio.create_task(_warm_dataset_cache_forever())
    try:
        yield
    finally:
        warmer.cancel()


app = FastAPI(title="Warble Breakout Monitor", lifespan=_lifespan)
app.include_router(api_router, prefix="/api")
app.include_router(agent_router, prefix="/api")

# Local dev only: the Vite dev server/preview run on a different origin than
# the API, so the browser blocks requests without this. Regex (rather than a
# fixed port list) because Vite auto-increments the port when 5173/4173 are
# already taken. In production the frontend is served from this same origin
# (see below), so no cross-origin request happens at all.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    # Liveness contract is unchanged (always 200 — an external monitor
    # should still consider the process up), but now carries a real DB
    # reachability signal instead of a static placeholder.
    try:
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001 - health check must never itself crash
        db_status = "unreachable"
    return {"status": "ok", "db": db_status}


# --- Static frontend (production only) ---------------------------------
# When a built frontend is present, serve it from this same process so the
# deploy is a single service on a single origin. Registered AFTER the API
# routers so /api/* and /health always win; the catch-all below returns
# index.html for client-side routes like /creators or /breakouts, which
# would otherwise 404 on a hard refresh.
_DEFAULT_DIST = Path(__file__).resolve().parents[2] / "frontend_dist"
_FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST_DIR", _DEFAULT_DIST))

if (_FRONTEND_DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        # An unknown /api/* path is a client calling an endpoint that
        # doesn't exist — it must say so. Without this it fell through to
        # the SPA catch-all and got 200 OK with a page of HTML, which a
        # fetch() then failed to parse as JSON. A 404 is the honest answer
        # and much easier to debug than "why is my JSON an HTML document".
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"no such endpoint: /{full_path}")
        candidate = (_FRONTEND_DIST / full_path).resolve()
        # Only serve real files that are actually inside the dist directory;
        # anything else is a client-side route and gets the app shell.
        if full_path and candidate.is_file() and candidate.is_relative_to(_FRONTEND_DIST):
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
