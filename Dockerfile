# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — CSS assets.
# Node exists only in this stage: the runtime image stays Python-only, and the
# deploy host never needs Node installed (Tailwind is a build-time concern).
# ---------------------------------------------------------------------------
FROM node:22-alpine AS assets

WORKDIR /build
COPY package.json package-lock.json* ./
# `npm ci` needs a lockfile; fall back so a fresh clone can bootstrap one.
RUN npm ci || npm install

COPY assets ./assets
COPY templates ./templates
COPY apps ./apps
COPY config ./config
RUN npm run build:css

# ---------------------------------------------------------------------------
# Stage 2 — runtime.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

# libpq5 keeps psycopg happy regardless of the wheel variant in use. curl is
# deliberately absent: the healthcheck is Python.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.12.1

# Fixed, high uid/gid: it cannot collide with a host user, and named volumes
# inherit this ownership when Docker first populates them from the image.
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid "${APP_GID}" rhp \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /bin/bash rhp

WORKDIR /app

# Dependencies first, so source changes do not invalidate the dependency layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
COPY --from=assets /build/static/css/rhp.css ./static/css/rhp.css

RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R rhp:rhp /app

USER rhp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["web"]
