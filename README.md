# TaskLattice Model Guardrails

A standalone model input/output guardrail service built with FastAPI and
[NVIDIA NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails). It exposes
LiteLLM's Generic Guardrail API while keeping policies and model-provider
configuration independent from LiteLLM, TaskLattice, and application
dashboards.

## Scope

This service owns provider-model guardrails only:

- input checks before a provider call;
- output checks for complete responses;
- cumulative output checks during streaming responses;
- bounded request context shared between input and output checks.

Dialog, retrieval, tool execution, and other agent-lifecycle guardrails belong
inside the agent runtime where their business context is available.

```text
Client
  |
  v
LiteLLM or another AI Gateway
  |  pre_call / during_call / post_call
  v
TaskLattice Model Guardrails
  |-- FastPass: deterministic Colang/Python checks
  |-- Content Safety: optional NVIDIA guard model
  `-- Topic Control: optional NVIDIA topic model
```

The gateway decides whether a guardrail is attached to a request. This service
does not manage projects, routes, teams, virtual keys, or dashboard state.

## Default policy

The bundled `profiles/model-io-default-v1` profile evaluates requests in three
stages:

1. Static Python actions block high-confidence secrets and identifiers without
   a model call.
2. NVIDIA Nemotron Safety Guard optionally evaluates input and output against
   its content-safety taxonomy.
3. NVIDIA NemoGuard Topic Control optionally evaluates input against the
   business-topic guidelines in `prompts.yml`.

The service works without the NVIDIA models; in that mode only the bundled
deterministic policy is active. Topic Control is input-only by design.

## Requirements

- Python 3.11, 3.12, or 3.13
- [`uv`](https://docs.astral.sh/uv/) for the documented development workflow
- Docker or another OCI builder for container builds
- An NVIDIA NIM-compatible endpoint only when model-backed rails are enabled

## Quick start

```sh
cp .env.example .env
uv sync --all-extras --frozen
set -a
. ./.env
set +a
uv run uvicorn app.main:app --host 0.0.0.0 --port 8091
```

Verify readiness:

```sh
curl --fail http://127.0.0.1:8091/health/ready
```

Expected response:

```json
{"status":"ready"}
```

## Configuration

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `MODEL_GUARDRAILS_API_KEY` | Production | `local-model-guardrails-key` | Shared key accepted through the `x-api-key` header. Always override the development default in production. |
| `MODEL_GUARDRAILS_PROFILE_PATH` | No | `profiles/model-io-default-v1` | NeMo profile containing `config.yml`, Colang flows, prompts, and optional actions. |
| `MODEL_GUARDRAILS_NVIDIA_BASE_URL` | With either NVIDIA model | Empty | Base URL of an NVIDIA NIM-compatible API, including `/v1`. It may point to a local isolated-network deployment. |
| `MODEL_GUARDRAILS_NVIDIA_API_KEY` | Provider-dependent | Empty | Credential sent to the configured model endpoint. |
| `MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL` | No | Empty | Content-safety model identifier used for input and output. |
| `MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL` | No | Empty | Topic-control model identifier used for input. |

The included `.env.example` enables static checks only. To enable NVIDIA model
rails, configure for example:

```text
MODEL_GUARDRAILS_NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL=nvidia/llama-3.1-nemotron-safety-guard-8b-v3
MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL=nvidia/llama-3.1-nemoguard-8b-topic-control
MODEL_GUARDRAILS_NVIDIA_API_KEY=replace-me
```

Do not commit real provider or service credentials.

## API

### Health checks

- `GET /health/live`
- `GET /health/ready`

### Generic Guardrail API

- `POST /beta/litellm_basic_guardrail_api`
- Authentication: `x-api-key: <MODEL_GUARDRAILS_API_KEY>`

Minimal input check:

```sh
curl --fail-with-body \
  --request POST \
  --url http://127.0.0.1:8091/beta/litellm_basic_guardrail_api \
  --header 'content-type: application/json' \
  --header 'x-api-key: local-model-guardrails-key' \
  --data '{
    "input_type": "request",
    "litellm_call_id": "example-1",
    "texts": ["Summarize this document."],
    "structured_messages": [
      {"role": "user", "content": "Summarize this document."}
    ]
  }'
```

Allowed content returns:

```json
{"action":"NONE"}
```

A blocked request returns HTTP 200 with a structured intervention so the
gateway can apply its own client-facing error contract:

```json
{
  "action": "BLOCKED",
  "blocked_reason": "Model input blocked by tasklattice model input."
}
```

Modified content uses `GUARDRAIL_INTERVENED` and includes replacement `texts`.

## LiteLLM integration

Register the same service endpoint for the required lifecycle phases. Guardrails
remain opt-in because `default_on` is false.

```yaml
guardrails:
  - guardrail_name: tasklattice-model-input
    litellm_params:
      guardrail: generic_guardrail_api
      mode: pre_call
      default_on: false
      api_base: http://model-guardrails:8091
      api_key: os.environ/MODEL_GUARDRAILS_API_KEY
      unreachable_fallback: fail_closed

  - guardrail_name: tasklattice-model-during-call
    litellm_params:
      guardrail: generic_guardrail_api
      mode: during_call
      default_on: false
      api_base: http://model-guardrails:8091
      api_key: os.environ/MODEL_GUARDRAILS_API_KEY
      unreachable_fallback: fail_closed

  - guardrail_name: tasklattice-model-output
    litellm_params:
      guardrail: generic_guardrail_api
      mode: post_call
      default_on: false
      api_base: http://model-guardrails:8091
      api_key: os.environ/MODEL_GUARDRAILS_API_KEY
      unreachable_fallback: fail_closed
```

During streaming, LiteLLM sends cumulative output to the post-call streaming
hook. A blocked result terminates the stream, but chunks already delivered to
the client cannot be retracted.

## Container

Build and run the service:

```sh
docker build --tag tasklattice-model-guardrails:dev .
docker run --rm \
  --publish 8091:8091 \
  --env MODEL_GUARDRAILS_API_KEY=replace-me \
  tasklattice-model-guardrails:dev
```

Pass model credentials with a runtime secret mechanism rather than baking them
into the image.

## Policy customization

`MODEL_GUARDRAILS_PROFILE_PATH` is the policy extension boundary. A profile may
contain:

```text
profiles/<profile-name>/
  actions.py
  config.yml
  prompts.yml
  rails.co
```

Changing the profile does not change the HTTP contract. Add policy-specific
tests before deploying a modified profile.

## Development

```sh
make sync
make test
make run
make image
```

The test suite covers the HTTP contract, authentication, request-context reuse,
static policy behavior, response modification, blocking, and simulated NVIDIA
Content Safety and Topic Control calls.

## Repository layout

```text
app/                         FastAPI service and NeMo runtime adapter
profiles/model-io-default-v1 Bundled Colang policy and actions
tests/                       Unit and local integration tests
Dockerfile                   Production container image
pyproject.toml               Python package and test configuration
uv.lock                      Reproducible dependency lock
```

## Current operational constraints

- Request context is an in-memory, bounded, best-effort cache. Multiple service
  replicas do not share it.
- Health readiness currently verifies process initialization, not reachability
  of optional external guard models.
- The bundled model prompt and output parsers target NVIDIA Nemotron models;
  other guard-model families require a model-specific adapter.
