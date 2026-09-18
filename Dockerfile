# Delta Desk: one container runs the pipeline and the HTTP / WebSocket server.
# Build:  docker build -t deltadesk .
# Run:    docker run --rm -p 8000:8000 --env-file .env deltadesk
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "deltadesk", "serve", "--host", "0.0.0.0", "--port", "8000", "--speed", "60"]
