from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent import router as agent_router
from app.api.routes import router as api_router

app = FastAPI(title="Warble Breakout Monitor")
app.include_router(api_router, prefix="/api")
app.include_router(agent_router, prefix="/api")

# Local dev only: the Vite dev server/preview run on a different origin than
# the API, so the browser blocks requests without this. Regex (rather than a
# fixed port list) because Vite auto-increments the port when 5173/4173 are
# already taken.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
