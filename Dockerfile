FROM python:3.13-slim

# install uv (official standalone binary)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/backend

# copy dependency files first (better layer caching)
COPY backend/pyproject.toml backend/uv.lock ./

# install deps into the image
RUN uv sync --frozen --no-dev

# copy the rest of the backend
COPY backend/ ./

# run the collector
CMD ["uv", "run", "python", "-m", "app.collector.loop"]
