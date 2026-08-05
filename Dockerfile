FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /opt/tasklattice/model-guardrails

COPY pyproject.toml README.md ./
COPY app ./app
COPY profiles ./profiles

RUN pip install . \
    && useradd --system --uid 65532 --no-create-home tasklattice

USER 65532:65532
EXPOSE 8091

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8091"]
