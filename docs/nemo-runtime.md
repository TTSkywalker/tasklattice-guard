# NeMo Runtime Operations

TaskLattice is the control plane and product layer. NVIDIA NeMo Guardrails is the
only production policy engine. Existing TaskLattice detectors and external
providers are registered as version-pinned NeMo Actions; they are not invoked by
a second production policy DAG.

## Request path

```text
HTTP / LiteLLM
      │
      ▼
Authenticate and normalize trusted request facts
      │
      ▼
Resolve Assignment → Guardrail ID + Version
      │
      ▼
Acquire prewarmed NeMo instance by ID + Version + Checksum
      │
      ▼
NeMo runtime selected by compiled capability
  ├─ IORails: pure native NeMo flows
  └─ LLMRails: Colang 2.x policy graph
       ├─ native NeMo Actions
       └─ TaskLattice extension Actions
      │
      ▼
Allow / Transform / Block + Evidence + Metrics
```

An input request with a call ID pins its Assignment and immutable Guardrail
Version for the matching output request. LiteLLM uses `litellm_call_id`; the HTTP
API returns a generated `call_id` when the caller does not provide one.

## Control mapping

| Control | NeMo execution |
| --- | --- |
| Content Safety | Native input/output content-safety flow |
| Personal information | Native sensitive-data flow with the TaskLattice detector registered as NeMo's detection/masking Action |
| Topic Control | Native input topic-safety flow when a topic model is configured; version-specific output Action otherwise |
| Jailbreak | Native model-based flow when a Jailbreak Detection NIM is configured; fast/judge Actions otherwise |
| Prompt Injection | Fast and optional judge Actions, because NeMo 0.23's injection library flow does not represent the product's input prompt-injection contract |
| Secrets | Deterministic Action |
| Built-in Content Filter | Versioned deterministic Action |
| Organization Policy | Policy Judge Action |
| Contextual Grounding | Full-output Grounding Action with query and source Content Blocks |
| Automated Reasoning | Full-output Action bound to an immutable external policy ID/version |

Native-only compatible configurations are constructed with `IORails` and
`require_iorails=True`. Configurations containing custom Colang or Actions are
constructed explicitly with `LLMRails`; they cannot silently fall back between
engines.

Built-in Prompt assets live with their owning Control under
`app/nemo/builtin_controls/<control>/v<version>`. They are loaded as package
resources and copied into the immutable NeMo snapshot at compile time. The
runtime does not read a process-wide `profiles/` directory, so changing a source
asset cannot change an already released Guardrail Version.

## Version lifecycle and rollback

Activation compiles and validates an immutable `NeMoConfigSnapshot`, computes its
SHA-256 checksum, constructs the exact NeMo runtime, and only then commits the
version and Assignment switch. Active versions stay resident in the registry;
inactive versions are kept in a bounded LRU. Initialization is serialized and
deduplicated, so production traffic does not construct an active runtime on the
hot path.

Rollback validates and prewarms the selected historical snapshot, then updates
the Guardrail and every bound Assignment in one SQLite transaction. Calls already
pinned at input continue on their original version; new calls use the rolled-back
version.

## Concurrency and latency

The compiler translates module dependencies into Colang waves. Independent
modules and risk flows run with Colang 2.x `start`/`match`; stages within one risk
remain ordered so an uncertain fast result can escalate to a deeper judge.
Python providers implement Actions only and do not schedule a second policy DAG.
All mutations are deferred until detection completes and are resolved by the
final NeMo Action in this priority order:

```text
reject → clarify → fallback → regenerate → rewrite → redirect → redact → pass
```

Each prewarmed Guardrail Version has an admission limit controlled by
`MODEL_GUARDRAILS_RUNTIME_MAX_CONCURRENCY_PER_GUARDRAIL`. Different Guardrails
have independent limits and continue in parallel. Waiting for a slot is measured
as queue latency and remains inside the whole-request deadline. Each Action has
a share of its module timeout; the request deadline is the critical dependency
path across Colang waves plus a small orchestration allowance. A required timeout,
queue deadline, or provider error fails closed in enforce mode.

Latency cannot be guaranteed by configuration alone. Operate it as an SLO:

1. Set `MODEL_GUARDRAILS_RUNTIME_P95_BUDGET_MS` and
   `MODEL_GUARDRAILS_RUNTIME_P99_BUDGET_MS`.
2. Watch overall, queue, rail, and Action P50/P95/P99 on the Overview page.
3. Alert on budget breach, timeout, fail-closed count, or cache misses.
4. Keep provider connection pools warm and scale external model endpoints to the
   measured concurrency envelope.
5. Promote only after the representative load test satisfies the target SLO.

## Observability and privacy

The local metrics store records request outcome and latency plus Guardrail and
Control Version, Rail/Flow/Action identity, Queue/Rail/Action/Provider latency,
parallel group, active concurrency, SLO breach, timeout, cache result, and
configuration checksum. It never uses prompt, response, user ID, credential, or
raw URL as a metric label.

Set `MODEL_GUARDRAILS_OTEL_ENABLED=true` and an OTLP/HTTP endpoint to export NeMo
telemetry. TaskLattice always sets NeMo's message-content capture switch to
`false` before initializing tracing.

## NeMo-only invariant

Every released version uses `nemo_only`, and the control plane exposes no runtime
mode switch. No retired engine is built or available in the production request
path. The persisted `execution_mode` column makes that invariant explicit. A
database from another schema version is rejected instead of migrated.
