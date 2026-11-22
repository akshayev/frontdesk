# Frontdesk — one container: FastAPI API + the built React app (ARCHITECTURE §12).
# The container never runs migrations or the seed (D-043): it only gets the frontdesk_app URL.

# ---- stage 1: build the frontend --------------------------------------------------------
FROM node:24.22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: python runtime ------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    APP_ENV=production \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
# Dependencies first (cached layer), exactly as locked, without dev tools. uv (pinned) is
# mounted for this step only, so it is not part of the final image.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.9,source=/uv,target=/usr/local/bin/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY --from=frontend /build/dist ./app/static

# Non-root runtime user; the code is owned by root and read-only to the app user.
RUN groupadd --system --gid 10001 frontdesk \
    && useradd --system --uid 10001 --gid frontdesk --no-create-home --shell /usr/sbin/nologin frontdesk
USER frontdesk

# Render sets $PORT; 8000 locally. No --proxy-headers / --forwarded-allow-ips (D-045): uvicorn
# must not rewrite the client address from X-Forwarded-For. app/security/client_ip.py reads the
# header itself (3rd entry from the right, TRUSTED_PROXY_HOPS=3 on Render, D-046).
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
