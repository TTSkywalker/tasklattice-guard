# TaskLattice Guard

TaskLattice Guard is an enterprise safety control plane for internal AI
applications. Security and platform teams define human-readable safety intent,
assign it to explicit request filters, and review evidence without managing the
underlying evaluator topology.

## Product model

```text
Enterprise baseline or human intent
        -> Safe
        -> reviewed test cases + Test Run
        -> tested Safe revision becomes available automatically
        -> Workload (request filters + tested Safe binding)
        -> optional Integration/Adapter
        -> decision Evidence
```

The primary user-facing objects are:

- **Safe** — the approved purpose, topic boundaries, protections, business
  actions, enforcement mode, and output-delivery posture for internal AI.
- **Workload** — an AND filter over normalized HTTP, authentication, model,
  LiteLLM, A2A, or Adapter fields, bound to one tested Safe revision.
- **Integration** — an optional LiteLLM, generic HTTP, or A2A enforcement connection.
- **Evidence** — privacy-preserving records for tests, configuration changes,
  and runtime decisions across the organization.

**Conversation Playground** is an ephemeral validation surface, not another
persistent product object. It applies a selected Safe's current draft rules
to user input or assistant output one turn at a time, carrying the preceding
conversation as evaluation context. It does not call the business model or
write chat content to Evidence or formal Safe tests.

Enterprise templates and individual protection capabilities are used inside
Safe creation and editing rather than appearing as separate navigation
areas. Draft numbers, publishing, generated plans, evaluator selection, and
filter ranking remain implementation details. Passing Safe tests
automatically produces the immutable version used by new workloads;
existing workloads remain pinned to their last tested version until they are
changed.

## Progressive safety evaluation

The runtime separates evaluator verdicts from policy enforcement:

```text
Evaluator verdict     safe | unsafe | uncertain | error
Routing               complete | enforce | escalate | fail closed
Policy decision       allow | transform | block
Enforcement action    pass | redact | rewrite | regenerate | redirect | reject
```

Evaluation depth is progressive:

```text
L1  Deterministic
      | decisive
      +--------------------------> decision
      | continue
      v
L2  Fast Semantic
      | safe / unsafe -----------> decision
      | uncertain
      v
L3  Deep Judge ------------------> contextual policy decision
```

Balanced semantic protections may invoke Deep Judge only for uncertain
classifications. Purpose-aware Topic Control and organization policy use Deep
Judge directly because the full Safe intent is required. The runtime never
exposes model size as a product concept.

## Architecture

```text
Control Plane UI -> flat /api/v1 resources -> FastAPI -> SQLite V9
                              |
                              +-> immutable tested versions + workload index

HTTP / LiteLLM / A2A / SDK -> Protocol Adapter -> normalized RequestContext
                                                      |
                                                      v
                                               Workload Filter Resolver
                                                      |
                                                      +-> Deterministic
                                                      +-> Fast Semantic
                                                      +-> Deep Judge
```

The Control Plane is not queried from the inference hot path. Input and output
for the same call pin one tested version. The most specific enabled Workload
filter wins; equally specific matches fail closed instead of selecting an
arbitrary Safe.

## Workload traffic filters

A Workload is not an employee directory or an organizational unit. It is a
named request-filter expression bound to one tested Safe. Filter groups use
`and` or `or` and can be nested to three levels, with at most 16 leaf rules.
An empty root expression is the single all-traffic fallback. Supported
operators are `equals`, `contains`, `starts_with`, and `glob`.

The field catalog is returned by `GET /api/v1/workload-filter-fields` and
currently includes:

| Group | Examples |
| --- | --- |
| Authentication | authenticated principal, Integration ID, verified JWT claim |
| HTTP | method, host, path, any configured Header |
| Model | model name or deployment pattern |
| LiteLLM | virtual-key alias, team ID, user ID |
| A2A | version, extensions, operation, context ID, task ID |
| Adapter | custom normalized field supplied by an authenticated Adapter |

For example, HTTP traffic can be assigned to a finance Safe without a
TaskLattice SDK:

```json
{
  "name": "Finance HTTP Agent",
  "safe_id": "safe-finance",
  "filter": {
    "combinator": "and",
    "rules": [
      {"field":"protocol","operator":"equals","value":"http"},
      {
        "combinator": "or",
        "rules": [
          {"field":"http.header","key":"x-app-id","operator":"equals","value":"finance-agent"},
          {"field":"auth.jwt_claim","key":"department","operator":"equals","value":"finance"}
        ]
      },
      {"field":"model","operator":"glob","value":"qwen3-*"}
    ]
  },
  "enabled": true
}
```

Call the generic HTTP/A2A Guard API with the Integration credential and ordinary
headers; no language SDK is required:

```sh
curl -X POST http://127.0.0.1:8091/v1/guardrails/evaluate \
  -H 'x-api-key: <integration credential>' \
  -H 'x-app-id: finance-agent' \
  -H 'content-type: application/json' \
  -d '{"protocol":"http","texts":["Analyze the quarterly report"],"model":"qwen3-32b"}'
```

For A2A traffic, register an A2A Integration and include the standard
`A2A-Version` and `A2A-Extensions` Headers. The Adapter normalizes them to
`a2a.version` and `a2a.extensions`. Headers used as security identities must be
set by a trusted proxy or covered by authenticated transport; unchecked client
metadata must not select a weaker Safe.

## Built-in content-filter policies

TaskLattice vendors the LiteLLM 1.95.0 `litellm_content_filter` policy assets
inside the application package. The local library contains 17 templates and 81
controls, including Australia PII, Singapore PDPA, Singapore MAS AI Risk
Management, EU data protection, topic filtering, and prompt-injection
protection. MCP Security is not included because it requires execution context
outside model input and output.

LiteLLM only needs one Generic Guardrail API integration. It forwards model
content and trusted request metadata to TaskLattice; it does not select or run
these templates. TaskLattice resolves the Workload, compiles the
selected local controls into the tested Safe revision, and executes patterns,
blocked words, and categories in FastPass. The service has no runtime or build
dependency on the LiteLLM Python package.

The LiteLLM enforcement adapter deliberately stops at one model call's input
and output. The Conversation Playground accepts explicit preceding messages so
teams can validate contextual topic boundaries before integration, but it does
not become the system of record for business chat. Retrieval, tools, and agent
workflow policy still require an agent runtime that owns that context.

## Output delivery

Safes make the safety/latency tradeoff explicit:

- `interruptible` preserves streaming but may stop unsafe output after release
  has started.
- `window_buffered` holds a small release window before returning content.
- `full_buffered` requires complete response validation before release.

The service communicates this posture in its decision metadata. Actual stream
buffering is enforced by the connected Integration.

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

The standalone policy and identity model uses the V9 Filter schema. Existing
V8 policy and identity state is upgraded in place while obsolete Workload rows
are intentionally removed because their selector semantics no longer exist.

## Standalone Helm deployment

The repository includes a self-contained Helm chart at
`charts/tasklattice-guard`. It deploys the API, Control Plane UI, deterministic
evaluator, optional LiteLLM Integration credential, and persistent SQLite state. An
active LiteLLM Integration is not required to create and test Safes.
The locally built-in content-filter templates also run without an external
evaluator; custom purpose-aware Topic Control requires the configured topic
judge and fails closed when it is unavailable.

Kubernetes namespace names must be lowercase, so the TALI namespace is `tali`.
For a local OrbStack or compatible cluster:

```sh
make helm-lint
make helm-install
make helm-test
```

The equivalent direct Helm command is:

```sh
docker build --tag ghcr.io/tasklattice/tasklattice-guard:dev .
helm upgrade --install tasklattice-guard ./charts/tasklattice-guard \
  --namespace tali \
  --create-namespace \
  --wait \
  --timeout 180s
```

The Service defaults to `LoadBalancer`; OrbStack assigns a locally reachable
external address. Inspect it with:

```sh
kubectl --namespace tali get service tasklattice-guard
```

Then open port `8091` on the reported external address. A new database intentionally
starts with no fake Safe or Workload. Create one from the local Topic
Filtering template, review its visible test cases, then run them directly
without an Integration:

```sh
safe_id="$(curl -sS -X POST \
  -H 'content-type: application/json' \
  -d '{"name":"Topic Filtering","template_id":"topic-filtering"}' \
  http://127.0.0.1:8092/api/v1/safes | \
  sed -n 's/.*"id":"\([^"]*\)".*/\1/p')"
curl -X POST \
  -H 'content-type: application/json' \
  -d "{\"safe_id\":\"${safe_id}\"}" \
  http://127.0.0.1:8092/api/v1/test-runs
```

The standalone runtime starts without an Integration or credential. Adding
a LiteLLM Integration in the UI creates its one-time credential. NVIDIA evaluator
values under `evaluators.nvidia` are empty by default. Persistent state is retained
when the release is uninstalled.

```sh
make helm-uninstall
```

## Model evaluators

Deterministic protection is always available. Optional NVIDIA-compatible
evaluators are configured with:

```text
MODEL_GUARDRAILS_NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL=nvidia/llama-3.1-nemotron-safety-guard-8b-v3
MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL=nvidia/llama-3.1-nemoguard-8b-topic-control
MODEL_GUARDRAILS_NVIDIA_API_KEY=replace-me
```

Safes that require an unavailable evaluator fail closed during Safe tests
and runtime enforcement.

### Control-plane intent assistant

The optional control-plane assistant is separate from runtime evaluation. It
uses DeepSeek to convert a business user's natural-language protection intent
into editable allowed and restricted Topic Control rules. The analysis endpoint
does not create or update a Safe; a user must review the draft, create the
Safe, and pass its tests.

```text
MODEL_GUARDRAILS_CONTROL_PLANE_AI_BASE_URL=https://api.deepseek.com
MODEL_GUARDRAILS_CONTROL_PLANE_AI_MODEL=deepseek-v4-flash
MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY=replace-me
```

## APIs

The control-plane contract is intentionally flat. Relationships are expressed
through identifiers and filters, not nested URL ownership:

- `GET /api/v1/safe-templates`
- `GET /api/v1/protection-definitions`
- `GET /api/v1/protections?safe_id={id}`
- `GET|POST /api/v1/safes`
- `GET|PATCH /api/v1/safes/{id}`
- `GET /api/v1/safe-revisions?safe_id={id}`
- `GET|POST /api/v1/test-cases?safe_id={id}`
- `DELETE /api/v1/test-cases/{id}`
- `GET|POST /api/v1/test-runs?safe_id={id}`
- `GET /api/v1/test-runs/{id}`
- `POST /api/v1/evaluations`
- `GET|POST /api/v1/workloads`
- `GET /api/v1/workload-filter-fields`
- `PATCH /api/v1/workloads/{id}`
- `GET /api/v1/workload-bindings?safe_id={id}&workload_id={id}`
- `GET|POST /api/v1/integrations`
- `GET /api/v1/decisions`
- `GET /api/v1/metrics`
- `GET /api/v1/system-status`
- `GET /api/v1/intent-analysis-status`
- `POST /api/v1/intent-analyses`
- `GET|POST|DELETE /api/v1/session`
- `POST /api/v1/initial-admin`
- `PATCH /api/v1/me`
- `GET|POST /api/v1/users`
- `PATCH /api/v1/users/{id}`
- `POST /v1/guardrails/evaluate`

The LiteLLM runtime adapter remains a protocol endpoint rather than a
control-plane resource:

- `POST /beta/litellm_basic_guardrail_api`

Health:

- `GET /health/live`
- `GET /health/ready`
