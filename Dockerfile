# ---------- build stage ----------
FROM python:3.13-slim AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies (no dev group)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY mock_calendar_api/ mock_calendar_api/
COPY main.py .

# ---------- runtime stage ----------
FROM python:3.13-slim

WORKDIR /app

# Copy the virtual-env and app from the builder
COPY --from=builder /app /app

# Ensure the data directory exists for the SQLite volume mount
RUN mkdir -p /app/data

EXPOSE 8000

# Run via the uv-managed venv
CMD ["/app/.venv/bin/uvicorn", "mock_calendar_api:app", "--host", "0.0.0.0", "--port", "8000"]
