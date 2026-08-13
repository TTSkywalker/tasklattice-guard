# syntax=docker/dockerfile:1

FROM node:24-alpine AS ui-build

WORKDIR /build/web

COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY web ./
RUN npm run build


FROM python:3.12-slim AS python-dependencies

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PROJECT_ENVIRONMENT=/opt/tasklattice/venv \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /build

# This layer changes only when the dependency contract changes. Application
# source is intentionally copied later so normal code edits reuse the venv.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project


FROM python:3.12-slim AS runtime

ENV PATH="/opt/tasklattice/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_GUARDRAILS_DATABASE_PATH=/var/lib/tasklattice/model-guardrails/tasklattice-guard-schema-v6.db \
    MODEL_GUARDRAILS_UI_DIST_PATH=/opt/tasklattice/model-guardrails/web/dist

WORKDIR /opt/tasklattice/model-guardrails

RUN useradd --system --uid 65532 --no-create-home tasklattice \
    && mkdir -p /var/lib/tasklattice/model-guardrails \
    && chown -R 65532:65532 /var/lib/tasklattice/model-guardrails

COPY --from=python-dependencies /opt/tasklattice/venv /opt/tasklattice/venv
COPY README.md THIRD_PARTY_NOTICES.md ./
COPY app ./app
COPY --from=ui-build /build/web/dist ./web/dist

USER 65532:65532
EXPOSE 8091
VOLUME ["/var/lib/tasklattice/model-guardrails"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
