# ADR 0001: NeMo-native runtime profiles

Status: Accepted

## Decision

TaskLattice uses NVIDIA NeMo Guardrails as the only production policy
orchestrator. Every immutable Guardrail Version records exactly one explicit
`runtime_profile`:

```text
Guardrail Version
├── iorails_native
│   └── IORails + native Colang 1 flows
├── llmrails_colang1_standard
│   └── LLMRails + Colang 1 flows + version-pinned Python Actions
└── llmrails_colang2_programmable
    └── LLMRails + Colang 2 flows + version-pinned Python Actions
```

The artifact also records the derived `runtime_engine` (`iorails` or
`llmrails`) and `colang_version` (`1.0` or `2.x`). Runtime code dispatches on
`runtime_profile`; it does not infer the profile from Colang syntax and it does
not fall back between engines.

This split is based on orchestration capability, not the name of a risk or
Control.

## Profile admission

| Profile | Admit | Reject from this profile |
| --- | --- | --- |
| `iorails_native` | Only IORails-supported NeMo library flows, with no dynamically registered custom Action. On the pinned NeMo 0.23 baseline this profile is restricted to a NeMo-owned generation lifecycle. | Standalone HTTP/LiteLLM checks, Python Actions, unsupported flows, or any custom orchestration. |
| `llmrails_colang1_standard` | Standalone input/output checks; secrets and PII detection; the vendored LiteLLM Content Filter; deterministic topic checks; one-step prompt-security or judge Actions; independent block-only Actions; at most one content modifier. | Escalation, dependency waves, more than one possible modifier, cross-content aggregation, or custom Colang 2 behavior. |
| `llmrails_colang2_programmable` | Fast-to-deep escalation, module dependencies and waves, multiple transforms with conflict resolution, Grounding, Automated Reasoning, cross-content aggregation, custom Controls/events/state, and resolver-dependent policies. | A configuration is not promoted out of this profile until a semantic and load-test gate proves that its simpler shape is equivalent in Colang 1. |

Admission is conservative. If the compiler cannot prove that a configuration
fits IORails or the standard Colang 1 contract, it selects
`llmrails_colang2_programmable`. An unsupported construct is never silently
dropped to make a configuration fit a faster profile.

## Python Action boundary

Python Custom Actions are the extension boundary for every LLMRails profile.
Colang owns lifecycle, ordering, parallel rail activation, blocking, message
mutation, and the final runtime result. Python owns deterministic rule matching
and external provider calls.

In particular, the imported LiteLLM Content Filter remains:

```text
vendored LiteLLM YAML/JSON
        ↓
versioned Control / Control Pack
        ↓
BuiltinContentFilter Python implementation
        ↓
TaskLatticeBuiltinContentFilterAction
```

Regex, keyword, and category rules are not expanded into generated `.co` files.
This preserves the imported rule semantics, keeps the compiled Colang artifact
small, and uses NeMo's documented Python Action integration point.

All version-pinned policy Actions are registered for both LLMRails profiles.
Only the programmable profile registers Colang 2-specific record, resolve, and
event Actions.

## Lifecycle and result ownership

The standard profile uses NeMo's Colang 1 input/output rail lifecycle. An Action
returns an explicit result containing its verdict, transformed content,
proposed action, reason, findings, provider latency, and failure mode. Colang
consumes that result to stop or mutate the message, while `output_vars` and the
structured generation log expose the product result and activated rails.

Standard-profile results must not depend on process-local result or decision
side channels. TaskLattice maps NeMo's final result into its enterprise API but
does not run a second policy resolver after NeMo has decided. The programmable
profile retains its explicit resolver only for policies that require complex
aggregation.

## Colang compatibility and ordering

- IORails artifacts remain Colang 1 because that is the engine's native
  configuration surface.
- Standard LLMRails artifacts use Colang 1 because NeMo 0.23 supports
  `check_async`, `output_vars`, structured generation logs, and tracing on this
  path.
- Programmable artifacts use Colang 2 so `start`, `await`, `match`, events, and
  state express complex orchestration inside NeMo.
- Colang 2 does not accept dots in executable flow identifiers. TaskLattice
  preserves the canonical audit identifier `tl.<control>.<version>.<flow>` and
  compiles it to an equivalent collision-free executable identifier.
- Independent block-only checks may run in parallel. A standard profile may
  have at most one mutating Action, avoiding nondeterministic message writes.
- Multiple mutations, priority resolution, and dependency waves require the
  programmable profile.

Action deadlines and failure modes remain versioned with each Rail binding.

## Observability compatibility baseline

The compatibility matrix is pinned to `nemoguardrails[tracing]==0.23.0`:

| Profile | NeMo tracing | NeMo metrics | Notes |
| --- | --- | --- | --- |
| `iorails_native` | Enabled, content capture disabled | Enabled | Inline tracing and native metrics are available, but IORails metrics are preview and do not replace product SLO metrics. |
| `llmrails_colang1_standard` | Enabled through the OpenTelemetry adapter, content capture disabled | Disabled | Activated rails, Action spans, `output_vars`, and the generation log are the runtime evidence source. |
| `llmrails_colang2_programmable` | Disabled | Disabled | NeMo 0.23's Colang 2 tracing path is incompatible with the required log behavior. Re-enable only after an upgrade-specific acceptance test. |

TaskLattice enterprise audit events, assignment/version evidence, and bounded
SLO metrics are retained for all profiles. They serve a different purpose from
NeMo runtime traces. Synthetic NeMo runtime traces are not created for IORails
or the standard profile; missing native telemetry is reported as unavailable,
not fabricated.

These settings are a version compatibility decision, not a permanent statement
about future NeMo releases. A NeMo upgrade must rerun the vertical, telemetry,
privacy, and load-test gates before this matrix changes.

## Release and migration rule

Changing profile, Colang source, Action contract, tracing configuration, or
compiler version creates a new Guardrail Version and checksum. Historical
snapshots are never recompiled or mutated in place. Promotion requires:

1. compilation and real NeMo construction for the selected profile;
2. semantic equivalence for decision, action, transformed text, and findings;
3. input/output lifecycle and fail-open/fail-closed tests;
4. representative 1/10/100 KB load tests at concurrency 1/32/128; and
5. evaluation, approval, deployment, and a reversible Assignment switch.

Migration proceeds from the least complex policies: LiteLLM Content Filter,
secrets, and PII first; then simple prompt-security/topic/judge Actions. Grounding,
Automated Reasoning, escalation, dependencies, multiple modifiers, and
cross-content aggregation remain programmable until their policy shape changes.

The benchmark protocol and executable harness are documented in
[`docs/nemo-runtime.md`](../nemo-runtime.md#profile-benchmark-gate).
