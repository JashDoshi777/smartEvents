# LiveIQ — single-container build for Hugging Face Spaces (Docker SDK, port 7860).
#   nginx :7860  →  /api/*  →  FastAPI :8000      (prefix stripped)
#                →  /*      →  Next.js :3000
# One public port, same origin for UI and API (no CORS), SSE streaming kept unbuffered.

# ── Stage 1: build the Next.js app as a self-contained "standalone" server ──
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT=standalone \
    NEXT_PUBLIC_API_URL=/api
RUN npm run build

# ── Stage 2: runtime (Python API + node + nginx) ──
FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw \
    APP_ENV=production \
    DEBUG=false

RUN apt-get update && apt-get install -y --no-install-recommends \
      nginx build-essential libpq-dev libgomp1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# node binary only (the Next standalone bundle ships its own node_modules subset)
COPY --from=web /usr/local/bin/node /usr/local/bin/node

WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Chromium is only used by the District events scraper job. Best-effort: if the
# browser/system deps can't be installed the job logs an error, the app still runs.
RUN (playwright install --with-deps chromium && chmod -R a+rX /opt/pw) \
    || echo "WARN: chromium unavailable — district_events job will be skipped"

COPY backend/ /app/backend/
COPY --from=web /web/.next/standalone /app/web
COPY --from=web /web/.next/static /app/web/.next/static
COPY --from=web /web/public /app/web/public
COPY deploy/nginx.conf /app/nginx.conf
COPY deploy/start.sh /app/start.sh

# Hugging Face runs containers as uid 1000
RUN useradd -m -u 1000 user && chmod +x /app/start.sh && chown -R user:user /app
USER user
ENV HOME=/home/user

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:7860/api/health || exit 1
CMD ["/app/start.sh"]
