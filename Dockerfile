# syntax=docker/dockerfile:1

# ---------- builder: install runtime dependencies into a relocatable prefix ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .

# Install only what the running server needs: drop test-only deps so they are not
# shipped in the final image. CI still installs the full requirements.txt to run tests.
RUN grep -viE '^(pytest|requests-mock)' requirements.txt > runtime-requirements.txt \
    && pip install --no-cache-dir --prefix=/install -r runtime-requirements.txt

# ---------- runtime: slim image with only the installed packages + app ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy the pre-installed packages/console scripts from the builder — the final
# image carries no pip download cache, build tooling or test-only dependencies.
COPY --from=builder /install /usr/local

# Application code (web/ included; tests and dev files excluded via .dockerignore).
COPY . .

# Entrypoint applies DB migrations (or create_all fallback) before the API starts.
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
# Default command the entrypoint exec's after migrations. docker-compose may override.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
