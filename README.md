# TaskLattice Guard

TaskLattice Guard is an enterprise Guardrail control plane and data-plane
runtime for internal AI applications. Teams define, test, version, assign, and
enforce Guardrails without coupling the product model to an evaluator vendor.

## Product model

```text
Guardrail
├── Purpose
├── Topic policies
├── Controls
├── Actions
├── Tests
└── Versions

Guardrail Assignment
├── Traffic Scope
└── Guardrail Version
```

- **Guardrail** is the complete, editable protection configuration.
- **Control** is one capability inside a Guardrail, such as secrets, personal
  information, prompt injection, contextual grounding, or automated reasoning.
- **Guardrail Version** is an immutable plan produced only by a passing test run.
- **Guardrail Assignment** binds one tested Guardrail Version to a Traffic Scope.
- **Traffic Scope** is a nested AND/OR expression over trusted request facts.
- **Enforcement** is a non-bypassable system-managed baseline.
- **Integration** authenticates and normalizes LiteLLM, HTTP, or A2A traffic.
- **Evidence** records decisions, tests, and governance changes without storing
  model request or response bodies.

The UI navigation follows the same model:

```text
Guardrails · Assignments · Enforcements · Integrations · Evidence
```

## End-to-end flow

```text
Create Guardrail
      ↓
Review generated and custom tests
      ↓
Pass test run → create immutable Guardrail Version
      ↓
Create Assignment with Traffic Scope
      ↓
Integration normalizes an incoming request
      ↓
Resolve and pin one Guardrail Version
      ↓
Run module DAG → collect partial fragments
      ↓
Deterministic resolver → allow, transform, clarify, or reject
      ↓
Record evidence
```

Requests that match no explicit Assignment use the system-managed baseline
Assignment and default Guardrail. The baseline cannot be disabled or selected
for a user-created Assignment.

## Data-plane architecture

The runtime executes a compiled module DAG rather than a global stage pipeline.
Independent modules can run concurrently; dependencies are explicit.

```text
immutable content ─┬─→ Data Protection ───────┐
                   ├─→ Interaction Safety ────┼─→ Decision Fragments
                   └─→ Business Assurance ────┘           ↓
                                                   Deterministic Resolver
                                                            ↓
                                              allow / transform / block
```

Each module owns its internal progressive evaluation:

```text
deterministic → fast semantic → deep judge
```

Escalation occurs only when the immutable plan requires it. Vendor-specific
parallel execution, including NeMo `parallel: true`, remains an implementation
detail inside a module and does not change Assignment or Guardrail semantics.

Modules emit immutable assessments containing findings, coverage, patches,
latency, and trace data. They do not mutate shared request content. The
deterministic resolver orders fragments, applies reviewed enforcement actions,
detects conflicting patches, verifies required coverage, and produces one final
decision.

### Automated Reasoning

Automated Reasoning providers are detection-only. They return formal findings:

```text
VALID
INVALID
SATISFIABLE
IMPOSSIBLE
TRANSLATION_AMBIGUOUS
TOO_COMPLEX
NO_TRANSLATIONS
```

The deterministic resolver owns enforcement. `VALID` passes, `INVALID` uses the
reviewed Guardrail action, ambiguity asks for clarification, and impossible or
overly complex evaluation fails closed. Provider judgment and product
enforcement remain separate.

## Traffic Scope

Traffic Scopes support nested AND/OR groups and the operators `equals`,
`contains`, `starts_with`, and `glob`. Supported facts include protocol,
Integration identity, authenticated principal, verified JWT claims, HTTP
method/host/path/header, model, LiteLLM metadata, and A2A metadata.

```json
{
  "name": "Finance production traffic",
  "guardrail_id": "guardrail-finance",
  "traffic_scope": {
    "combinator": "and",
    "rules": [
      {"field": "integration.id", "key": "", "operator": "equals", "value": "integration-prod"},
      {"field": "model", "key": "", "operator": "glob", "value": "qwen-*"}
    ]
  },
  "enabled": true
}
```

User-created Assignments require at least one rule. Equally specific matches
fail closed instead of relying on creation order. Identity boundaries should use
facts verified by the Integration rather than caller-controlled headers.

## Persistence

SQLite stores the current product model directly:

- `guardrails`
- `guardrail_versions`
- `assignments`
- `integrations`
- `integration_credentials`
- `test_cases`
- `test_runs`
- `evidence_events`
- identity and session tables

The schema identifier is `tasklattice-guard-schema-v2`, and the default local
path is `data/tasklattice-guard-schema-v2.db`. There are no migrations, legacy
column aliases, or read fallbacks. A database with any other schema identifier
is rejected; initialize a new database for this architecture.

## Local development

Requirements: Python 3.11–3.13, Node.js 24, and `uv`.

```sh
cp .env.example .env
make sync
make web-build
make run
```

Open <http://127.0.0.1:8091>. For UI development, run `make run` and
`make web-dev`; Vite serves <http://127.0.0.1:8092> and proxies `/api`.

Run all checks:

```sh
make test
```

## Helm deployment

The chart in `charts/tasklattice-guard` deploys the API, UI, deterministic
runtime, and persistent SQLite state. An external evaluator or active
Integration is not required to create and test locally executable Guardrails.

```sh
make helm-lint
make helm-install
make helm-test
```

The Service defaults to `LoadBalancer`. Persistent state is retained when the
release is uninstalled.

```sh
make helm-uninstall
```

## Optional evaluators

Deterministic Controls are always available. Optional model-backed evaluators
use the existing dependencies and OpenAI-compatible HTTP contracts:

```text
MODEL_GUARDRAILS_NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL=nvidia/llama-3.1-nemotron-safety-guard-8b-v3
MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL=nvidia/llama-3.1-nemoguard-8b-topic-control
MODEL_GUARDRAILS_GROUNDING_MODEL=<openai-compatible-grounding-judge-model>
MODEL_GUARDRAILS_NVIDIA_API_KEY=replace-me

MODEL_GUARDRAILS_DEEP_JUDGE_BASE_URL=https://api.deepseek.com
MODEL_GUARDRAILS_DEEP_JUDGE_MODEL=deepseek-v4-flash
MODEL_GUARDRAILS_DEEP_JUDGE_API_KEY_ENV_VAR=DEEPSEEK_API_KEY

MODEL_GUARDRAILS_AUTOMATED_REASONING_ENDPOINT_URL=https://reasoning.example.com/v1/evaluate
MODEL_GUARDRAILS_AUTOMATED_REASONING_API_KEY=replace-me
```

The generic Deep Judge is used for prompt security, Topic Control, and
contextual grounding. A dedicated NVIDIA topic or grounding model takes
precedence for its matching Control. `*_API_KEY_ENV_VAR` settings point to an
existing environment variable, so local `.env` files do not need duplicate
secret values.

The optional control-plane intent analyzer turns natural-language purpose into
reviewable Topic Control suggestions. It never creates or changes a Guardrail:

```text
MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL=https://api.deepseek.com
MODEL_GUARDRAILS_CONTROL_PLANE_AI_MODEL=deepseek-v4-flash
MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY_ENV_VAR=DEEPSEEK_API_KEY
```

## API

The current contract exposes only the current product model:

- `GET /api/v1/guardrail-templates`
- `GET /api/v1/control-definitions`
- `GET|POST /api/v1/guardrails`
- `GET|PATCH /api/v1/guardrails/{id}`
- `GET /api/v1/guardrail-versions?guardrail_id={id}`
- `GET|POST /api/v1/test-cases?guardrail_id={id}`
- `DELETE /api/v1/test-cases/{id}`
- `GET|POST /api/v1/test-runs?guardrail_id={id}`
- `GET /api/v1/test-runs/{id}`
- `GET|POST /api/v1/assignments`
- `PATCH /api/v1/assignments/{id}`
- `GET /api/v1/traffic-scope-fields`
- `GET|POST /api/v1/integrations`
- `GET /api/v1/decisions`
- `GET /api/v1/metrics`
- `GET /api/v1/system-status`
- `GET /api/v1/intent-analysis-status`
- `POST /api/v1/intent-analyses`
- `POST /api/v1/initial-admin`
- `GET|POST|DELETE /api/v1/session`
