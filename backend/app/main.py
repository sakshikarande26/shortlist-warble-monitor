from fastapi import FastAPI

app = FastAPI(title="Warble Breakout Monitor")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
