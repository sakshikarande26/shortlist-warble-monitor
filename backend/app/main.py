import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.agent import router as agent_router
from app.api.routes import router as api_router

app = FastAPI(title="Warble Breakout Monitor")
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
    return {"status": "ok"}


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
        candidate = (_FRONTEND_DIST / full_path).resolve()
        # Only serve real files that are actually inside the dist directory;
        # anything else is a client-side route and gets the app shell.
        if full_path and candidate.is_file() and candidate.is_relative_to(_FRONTEND_DIST):
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
