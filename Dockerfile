FROM node:24-alpine AS ui-build

WORKDIR /build/web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web ./
RUN npm run build


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_GUARDRAILS_DATABASE_PATH=/var/lib/tasklattice/model-guardrails/tasklattice-guard-schema-v2.db \
    MODEL_GUARDRAILS_UI_DIST_PATH=/opt/tasklattice/model-guardrails/web/dist

WORKDIR /opt/tasklattice/model-guardrails

COPY pyproject.toml README.md THIRD_PARTY_NOTICES.md ./
COPY app ./app

RUN pip install . \
    && useradd --system --uid 65532 --no-create-home tasklattice \
    && mkdir -p /var/lib/tasklattice/model-guardrails \
    && chown -R 65532:65532 /var/lib/tasklattice/model-guardrails

COPY --from=ui-build /build/web/dist ./web/dist

USER 65532:65532
EXPOSE 8091
VOLUME ["/var/lib/tasklattice/model-guardrails"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
