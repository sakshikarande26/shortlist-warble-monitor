from fastapi import FastAPI

from app.api.routes import router as api_router

app = FastAPI(title="Warble Breakout Monitor")
app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
