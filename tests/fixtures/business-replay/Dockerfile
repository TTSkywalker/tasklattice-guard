# Use the same pinned Relay image, replacing only its TaskLattice Guard Provider.
# Build with the Relay repository as context, never the Guard repository.
ARG RELAY_BASE=ghcr.io/tasklattice/tali-litellm:dev
FROM ${RELAY_BASE}
USER root
COPY infra/litellm/v1.87.0/overlay/litellm/proxy/guardrails/guardrail_hooks/tasklattice_guard /app/litellm/proxy/guardrails/guardrail_hooks/tasklattice_guard
COPY infra/litellm/v1.87.0/tests /tmp/tasklattice-guard-tests
RUN LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONPATH=/app python -m unittest discover -s /tmp/tasklattice-guard-tests
USER 65532:65532
