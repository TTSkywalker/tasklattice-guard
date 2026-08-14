# NeMo Runtime Operations

TaskLattice is the enterprise control plane and product layer. NVIDIA NeMo
Guardrails is the only production policy engine. Existing TaskLattice detectors
and external providers are registered as immutable, version-pinned NeMo Python
Actions; they are not invoked by a second production policy DAG.

The runtime compatibility baseline is `nemoguardrails[tracing]==0.23.0`.
Capabilities and telemetry behavior in this document must be revalidated before
upgrading that pin.

## Request path

```text
HTTP / LiteLLM
      │
      ▼
Authenticate and normalize trusted request facts
      │
      ▼
Resolve Deployment → Guardrail ID + immutable Version
      │
      ▼
Acquire prewarmed NeMo instance by ID + Version + Checksum
      │
      ▼
Dispatch by the artifact's explicit runtime_profile
  ├─ iorails_native
  ├─ llmrails_colang1_standard
  └─ llmrails_colang2_programmable
      │
      ▼
Use NeMo's final Allow / Transform / Block result
      │
      ▼
Product response + enterprise audit + bounded SLO metrics
```

An input request with a call ID pins its Deployment and immutable Guardrail
Version for the matching output request. LiteLLM uses `litellm_call_id`; the HTTP
API returns a generated `call_id` when the caller does not provide one. The
LiteLLM adapter remains responsible only for authentication, trusted-fact
normalization, protocol conversion, and mapping the final result to `NONE`,
`BLOCKED`, or `GUARDRAIL_INTERVENED`.

## Three independent runtime dimensions

Do not treat the word "three" as one shared execution model. TaskLattice has
three separate dimensions with different concurrency semantics:

| Dimension | Members | Runtime relationship |
| --- | --- | --- |
| NeMo runtime profile | `iorails_native`, `llmrails_colang1_standard`, `llmrails_colang2_programmable` | One immutable Guardrail Version selects exactly one profile. Profiles never run in parallel or fall back into one another. |
| Policy Module | Data Protection, Interaction Safety, Business Assurance | Independent modules in the same dependency wave may run concurrently. Grounding and Automated Reasoning wait for required upstream results such as masking. |
| Detection depth | Local Rule matcher, dedicated Guard Model, specialized evaluator | Checks for the same Rule run in an ordered route. The compiler only admits evaluators explicitly registered for that capability. |

Parallelism therefore exists between independent Policy Modules, Policies, and
Rules. It does not mean that local matching, a Guard Model, and a specialized evaluator
always run as three parallel evaluators.

General-purpose chat models are not Runtime dependencies. NVIDIA Guard Models
and formal reasoning providers are admitted only for their declared
capabilities. DeepSeek can generate Playground conversations or translate
human intent into a reviewable control-plane draft, but it is never registered
as a NeMo Runtime Action and never receives production traffic for evaluation.

The NVIDIA runtime mapping is explicit rather than provider-wide:

| Runtime capability | Dedicated evaluator |
| --- | --- |
| Harmful input/output | `content_safety` model |
| Allowed/restricted topics and organization policy | `topic_control` model |
| Prompt injection and jailbreak | Jailbreak Detection NIM `/classify` endpoint |
| Contextual grounding | Explicit grounding evaluator only |
| Automated reasoning | Explicit immutable-policy provider only |

An NVIDIA credential grants access; it does not make an arbitrary NVIDIA chat
model a Runtime evaluator. `NeMoConfigCompiler` rejects `main` and every model
type other than the dedicated Guard Model roles admitted above.

## Runtime profiles

| Profile | Engine and language | Operational use |
| --- | --- | --- |
| `iorails_native` | IORails, native Colang 1 | Pure NeMo library rails in a NeMo-owned generation lifecycle. With NeMo 0.23 it is not the general standalone HTTP/LiteLLM fast path. |
| `llmrails_colang1_standard` | LLMRails, Colang 1, Python Actions | Main enterprise standalone-check lane for simple, single-pass policies. It uses the official rail lifecycle, `check_async` where only a check status is needed, and `generate_async` with `output_vars`/logs where the product result needs evidence. |
| `llmrails_colang2_programmable` | LLMRails, Colang 2, Python Actions | Complex policy orchestration: escalation, dependency waves, events/state, aggregation, and conflict resolution. |

The compiled artifact stores `runtime_profile`, `runtime_engine`, and
`colang_version`. Runtime dispatch uses the profile directly. There is no
automatic fallback between engines, languages, or profiles.

### Admission rules

The compiler selects `iorails_native` only when every configured flow is
supported by IORails and no custom Action is required. It selects the standard
profile when it can prove all of the following:

- every check is a one-step Action with no fast-to-deep escalation;
- modules have no dependency waves;
- independent parallel checks are block-only;
- at most one Action can modify content;
- no cross-content-block final aggregation is required; and
- no custom Colang 2 events, state, or resolver behavior is required.

Secrets, deterministic PII, built-in content policies, deterministic
topic checks, one-step prompt-security checks, and simple single judges are
eligible when their concrete configuration satisfies these constraints.

Any fast-to-deep escalation, `depends_on` relationship, multi-wave graph,
multiple possible transforms, Grounding, Automated Reasoning, cross-content
aggregation, custom Colang 2 Flow, or resolver-dependent result selects the
programmable profile. Admission is based on the compiled orchestration shape,
not only on the risk name.

## Python Actions and standard-lane lifecycle

All policy implementations are registered as Python Actions for both LLMRails
profiles. The programmable profile additionally registers only those Actions
needed for Colang 2 event recording and final resolution.

Built-in regex, keyword, and category Rules are not translated rule-by-rule
into Colang. Their versioned Policy asset remains the source,
`BuiltinContentFilter` remains the Python matching implementation, and
`GuardContentFilterAction` is the NeMo entry point. The same
boundary applies to deterministic and external-provider checks: Python detects;
Colang owns the rail lifecycle.

A standard-lane Action returns an explicit value with this logical contract:

```text
verdict: safe | unsafe | uncertain | error
content: original or proposed transformed content
proposed_action: pass | redact | rewrite | ... | reject
reason: bounded operator-facing explanation
findings: structured, versioned evidence
provider_latency_ms: provider time, if any
failure_mode: fail_open | fail_closed
```

The Colang 1 flow consumes that value:

- safe or fail-open: continue;
- enforceable block or fail-closed: stop through NeMo's rail lifecycle;
- the single allowed modifier: update `$user_message` or `$bot_message`; and
- expose the explicit decision and activated rails through `output_vars` and the
  structured generation log.

The product layer maps that NeMo result to its response DTO. It does not recover
standard-lane results from process-local result/decision side channels and does
not independently re-resolve the policy.

## Policy implementation mapping

| Policy capability | NeMo execution |
| --- | --- |
| Content Safety | Native input/output content-safety flow when admitted to IORails; otherwise the configured LLMRails Action/flow. |
| Personal information | Version-pinned Python detection/masking Action in the standard lane unless a complex composition requires Colang 2. |
| Topic Safety | Native topic-safety flow for an IORails-compatible NeMo-owned generation; deterministic or dedicated Topic Control Action otherwise. |
| Jailbreak | Dedicated Jailbreak Detection model when configured; local fast detection otherwise. |
| Prompt Injection | Dedicated Jailbreak Detection model when configured; local fast detection otherwise. |
| Secrets | Deterministic Python Action, normally standard. |
| Built-in content policies | Versioned Python Actions over TaskLattice Policy Rules, normally standard. |
| Organization Policy | Dedicated NVIDIA Topic Control Action evaluated against compiled business boundaries; no generic LLM fallback exists. |
| Contextual Grounding | Programmable full-output Action backed only by a configured grounding-specific evaluator. |
| Automated Reasoning | Programmable full-output Action bound to an immutable external policy ID/version. |

Built-in prompt assets live with their owning Policy implementation under
`app/nemo/builtin_policies/<policy>/v<version>`. They are copied into the
immutable NeMo snapshot at compile time. Runtime initialization does not read a
process-wide mutable profile directory.

## Version lifecycle and rollback

Activation compiles and validates a new immutable `NeMoConfigSnapshot`, computes
its SHA-256 checksum, constructs the exact profile runtime, and only then commits
the version and Deployment switch. Active versions stay resident in the
registry; inactive versions are kept in a bounded LRU. Initialization is
serialized and deduplicated, so production traffic does not construct a runtime
on the hot path.

Changing profile admission, generated Colang, Action contract, compiler version,
or telemetry configuration always creates a new Guardrail Version and checksum.
Never recompile or patch the persisted snapshot of a historical version.

Rollback validates and prewarms the selected historical snapshot, then updates
the Guardrail and every bound Deployment in one database transaction. Calls
already pinned at input continue on their original version; new calls use the
rolled-back version.

The migration sequence is deliberately narrow:

1. create the standard profile without changing policy semantics;
2. migrate built-in content, secrets, and PII Actions;
3. prove input and output allow/mask/block equivalence against the existing
   programmable version;
4. load-test, evaluate, approve, and deploy a new version;
5. migrate simple prompt-security/topic/judge Actions only after that gate; and
6. retain Grounding, Automated Reasoning, escalation, dependency graphs,
   multiple modifiers, and cross-block aggregation in Colang 2.

## Concurrency and admission control

The programmable compiler translates module dependencies into Colang waves.
Independent modules and risk flows use Colang 2 `start`/`match`; stages within
one risk remain ordered so an uncertain fast result can escalate. Multiple
mutations are resolved in this priority order:

```text
reject → clarify → fallback → regenerate → rewrite → redirect → redact → pass
```

The standard profile may parallelize independent block-only flows and permits at
most one modifier. This lets NeMo apply the final message mutation without a
second TaskLattice resolver.

Each prewarmed Guardrail Version has an admission limit controlled by
`MODEL_GUARDRAILS_RUNTIME_MAX_CONCURRENCY_PER_GUARDRAIL`. Different Guardrails
have independent limits. Queue latency remains inside the whole-request
deadline. A required timeout, queue deadline, or provider error fails closed in
enforce mode according to the versioned binding.

Latency is an observed SLO, not a property guaranteed by the selected profile:

1. Set `MODEL_GUARDRAILS_RUNTIME_P95_BUDGET_MS` and
   `MODEL_GUARDRAILS_RUNTIME_P99_BUDGET_MS`.
2. Watch request, queue, rail, Action, and provider P50/P95/P99.
3. Alert on budget breach, timeout, fail-closed count, or cache misses.
4. Keep provider pools warm and scale endpoints to the measured concurrency
   envelope.
5. Promote only after the representative load test meets the target SLO.

## Observability and privacy

NeMo telemetry is profile-specific on the pinned 0.23 baseline:

| Profile | Tracing | Metrics |
| --- | --- | --- |
| `iorails_native` | Enabled; content capture disabled | Enabled; still preview |
| `llmrails_colang1_standard` | OpenTelemetry adapter enabled; content capture disabled | Disabled |
| `llmrails_colang2_programmable` | Disabled because the 0.23 tracing/log path is incompatible | Disabled |

Do not enable unsupported telemetry by copying one profile's YAML into another.
For Colang 2, retain product audit and SLO data while reporting NeMo-native spans
as unavailable. Reconsider the limitation only with an upgrade-specific real
runtime test.

The product metrics store records outcomes and latencies plus Guardrail and
Policy Version, Rail/Flow/Action identity, queue/rail/Action/provider latency,
parallel group, active concurrency, SLO breach, timeout, cache result, engine,
and checksum. Runtime usage/trace and the released Guardrail Version expose
the explicit profile; persisted metric rows join to it by immutable Guardrail
Version and checksum. Prompt, response, user ID, credential, and raw URL are not
metric labels.

`MODEL_GUARDRAILS_OTEL_ENABLED=true` and the OTLP/HTTP endpoint enable supported
NeMo telemetry for the compiled profile. Message-content capture remains false.
NeMo runtime traces are consumed directly for IORails and the standard profile;
synthetic Action/resolver spans are not added. Enterprise audit records remain
separate and are always retained.

## Profile benchmark gate

[`benchmarks/nemo_runtime_profiles.py`](../benchmarks/nemo_runtime_profiles.py)
runs the repeatable HTTP benchmark matrix without participating in `pytest` or
setting timing assertions. It measures:

- `iorails_native`, `llmrails_colang1_standard`, and
  `llmrails_colang2_programmable`;
- 1 KB, 10 KB, and 100 KB request text;
- allow, mask/transform, single-block, and multiple-independent-block outcomes;
- concurrency 1, 32, and 128; and
- equivalent deployments with OpenTelemetry off and on.

The harness reports request P50/P95/P99 and throughput, plus Action/provider
latency when the response trace exposes it. It never declares one profile faster
from a hard-coded threshold. Server CPU, RSS, allocator pressure, exporter
backpressure, and collector drops must be captured from the deployment platform
over the same run interval; client-process resource use is not a substitute.

Prepare six isolated, prewarmed targets (three profiles by OTel off/on) from
newly released artifacts. The policies, provider endpoints, model versions,
timeouts, failure modes, and admission limits must otherwise match. For the
Colang 2 `otel_enabled=true` target, product/exporter telemetry may be on but
NeMo-native Colang 2 tracing stays disabled on 0.23. Do not fabricate a native
trace merely to complete the matrix.

Each target URL must accept the manifest payload and return the TaskLattice
decision DTO. The standard and programmable targets can use the public
`/v1/guardrails/evaluate` endpoint. The IORails target must be a controlled
benchmark facade around its NeMo-owned generation call; do not attach an
`iorails_native` artifact to a standalone production Deployment merely to make
the comparison. A partial C1/C2 manifest remains directly runnable against the
current public API without `--require-full-matrix`.

Copy and edit the example manifest, putting API keys in environment variables:

```bash
cp benchmarks/nemo_profiles.example.json /tmp/nemo-profiles.json
export TL_BENCH_API_KEY='replace-me'
.venv/bin/python benchmarks/nemo_runtime_profiles.py \
  --config /tmp/nemo-profiles.json \
  --output /tmp/nemo-profile-results.json \
  --rounds 3 \
  --require-full-matrix
```

The configured trigger texts must yield the same intended outcome in all three
semantically equivalent artifacts. IORails should be compared only for a policy
that it can natively express; an unsupported native case is a profile-admission
failure, not a reason to add a custom IORails side path. Run a separate C1/C2
suite when validating a standard-only modifier such as the Python LiteLLM
Content Filter. Include both a request that activates one blocking rail and a
request that activates multiple independent blocking rails; both must converge
on the same block contract without result-order drift.

For every request the harness computes a privacy-safe semantic digest over:

- `decision` and `action`;
- the exact ordered transformed text; and
- complete findings, normalized as an order-insensitive collection.

Reasons and runtime traces are intentionally excluded because they describe the
engine path, not the policy outcome. The release gate fails on HTTP errors,
unexpected outcomes, within-cell nondeterminism, or digest differences across
profiles, OTel settings, or concurrency levels for the same case and text.
Timing has no built-in pass/fail threshold; compare its JSON result to the
agreed SLO and a statistically meaningful baseline.

Use at least three interleaved rounds after warmup. Record alongside the result:

- image, NeMo, compiler, Policy, provider/model, and artifact versions;
- Guardrail ID/version/checksum for every target;
- node type, CPU quota, memory limit, replica count, and admission limit;
- collector/exporter configuration and observed span/drop counts; and
- server CPU/RSS time series covering the complete run.

Archive that evidence with Validation Run, approval, and Deployment records. Do not claim
a performance improvement from a single developer-machine sample.

## NeMo-only invariant

Every released version uses `nemo_only`, and the control plane exposes no
runtime-mode switch. No retired policy engine is built or available in the
production request path. The persisted execution mode makes that invariant
explicit; `runtime_profile` selects only among NeMo-native execution profiles.
