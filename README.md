# TaskLattice Guard

**Turn business-readable AI safety policies into protection that teams can trust and operate.**

TaskLattice Guard is a guardrail management and enforcement platform for enterprise AI applications. It gives security, business, and AI teams a shared way to define acceptable behavior, validate protection policies, and apply reviewed guardrails to real traffic.

Rather than embedding disconnected safety rules in every application, TaskLattice Guard creates one governed lifecycle for AI protection—from business intent to runtime decisions and audit-ready evidence. It works across AI applications, agents, gateways, and models, so teams can evolve their AI stack without rebuilding their governance model.

## Core Advantages

- **NeMo-native runtime** — Every released Guardrail compiles to an immutable NeMo configuration, and every configured policy check is evaluated through NVIDIA NeMo Guardrails.
- **Business-first policies** — Describe purpose, allowed behavior, and boundaries in language that product, risk, and security teams can review together.
- **Reusable protection** — Manage guardrails independently from individual applications and models, then apply them wherever they are needed.
- **Validate before release** — Run reviewed Test Cases before creating a deployable version, reducing the risk of unreviewed policies reaching production.
- **Context-aware deployment** — Apply the right guardrail to the right application, user group, model, or business scenario.
- **Protection by default** — A managed baseline covers traffic that does not match a specific deployment.
- **Clear, privacy-conscious evidence** — Understand why decisions were made and how policies changed without retaining protected runtime request or response bodies.

## Product Architecture

TaskLattice Guard separates the governance path from the protected-traffic path.
The control plane determines what has been reviewed and deployed; NVIDIA NeMo
Guardrails is the single production policy engine that evaluates the selected
Version.

```text
 AUTHORING AND RELEASE                         PROTECTED TRAFFIC (CHECK API)

 Security · Business · AI Teams                AI App · Agent · Gateway
                │                              (owns the model invocation)
                │                                           │
                ▼                                           │ input / output check
 ┌────────────────────────────────┐                          ▼
 │ TaskLattice Control Plane      │            ┌────────────────────────────┐
 │ Define Policies & Guardrails   │            │ Integration Adapter        │
 │ Validate with Test Cases       │            │ Authenticate · Normalize   │
 │ Review · Release · Roll back   │            └──────────────┬─────────────┘
 └───────────────┬────────────────┘                           ▼
                 │                             ┌────────────────────────────┐
                 ▼                             │ GuardrailRuntimeService    │
 ┌────────────────────────────────┐            │ Resolve route · Pin Version│
 │ Immutable Guardrail Version    │───────────▶└──────────────┬─────────────┘
 │ Reviewed policy snapshot       │ release / rollback        ▼
 │ Compiled NeMo configuration    │            ┌────────────────────────────┐
 │ Bindings · dependencies · hash │            │ NeMoRuntimeRegistry       │
 └────────────────────────────────┘            │ Prewarm versioned runtime  │
                                               └──────────────┬─────────────┘
                                                              ▼
                                               ┌────────────────────────────┐
                                               │ NeMo Guardrails            │
                                               │ Guardrails.generate_async  │
                                               │ Colang Input / Output Rail │
                                               └──────────────┬─────────────┘
                                                              ▼
                                               ┌────────────────────────────┐
                                               │ NeMoActionBridge           │
                                               │ Versioned ActionProviders  │
                                               │ ActionResult               │
                                               └──────────────┬─────────────┘
                                                              ▼
                                                  ProtectionDecision
                                               Allow · Transform · Block
                                                              │
                                       ┌──────────────────────┴─────────────┐
                                       ▼                                    ▼
                           Decision returned to caller       Metrics · Evidence · Traces
```

TaskLattice is an explicit guardrail decision service, not a transparent model
proxy. The application or gateway owns the model invocation, calls TaskLattice
at the input and/or output boundary, and applies the returned decision.

The architecture is built around six principles:

- **Govern separately, evaluate consistently** — Teams manage intent, review,
  release, and deployment in the control plane while NeMo evaluates configured
  policy checks at runtime.
- **Run exactly what was reviewed** — A released Version binds the reviewed
  source snapshot, compiled plan, NeMo configuration, dependencies, bindings,
  and integrity hash.
- **Use one production policy engine** — Native NeMo rails and TaskLattice
  Actions execute through the selected NeMo flow rather than a second policy
  engine running beside it.
- **Resolve once, execute exactly** — Trusted request context selects a
  Deployment and pins its exact Guardrail Version. When a call ID links input
  and output checks, both stages stay on that Version.
- **Parallelize only safe work** — A compiled flow can run independent checks
  concurrently; dependencies, transformations, and conflicts preserve required
  ordering.
- **Fail and observe safely** — Prewarmed, version-isolated runtimes combine
  admission limits and deadlines with fail-closed behavior for required checks.
  Privacy-conscious telemetry and bounded runtime evidence exclude protected
  request and response bodies.

### Runtime and model boundaries

- The production Check API uses NeMo `llmrails`: straightforward plans compile
  to standard Colang 1 rails, while plans that require dependencies or
  programmable orchestration compile to Colang 2 flows. `iorails_native` is
  reserved for a future host that owns model generation and is rejected by the
  standalone Check API.
- Deterministic checks and specialized model-backed checks are registered as
  versioned Python Actions and are invoked by the active NeMo rail. There is no
  second runtime evaluator pipeline beside NeMo.
- NVIDIA safety, topic-control, grounding, and jailbreak models are dedicated
  runtime guard models. A general-purpose chat model is never registered as a
  runtime judge.
- DeepSeek or another OpenAI-compatible general-purpose model may be configured
  for Playground response generation and for control-plane intent or compliance
  document translation. Those calls do not evaluate production traffic; the
  Playground model's input and output are still checked by the selected
  Guardrail.
- Automated Reasoning is optional. When configured, NeMo invokes the provider
  as a version-pinned output Action using an immutable policy reference and
  returns proof findings for normal Guardrail enforcement.

## Core Product Concepts

| Concept | Meaning |
| --- | --- |
| **Policy Library** | The catalog of reusable, searchable Policies available to a Guardrail. |
| **Policy** | A reusable protection capability containing one or more executable Rules and their reviewed Test Cases. |
| **Rule** | The smallest product-level behavior that can be configured, executed, and verified by Test Cases. |
| **Test Case** | A versioned input or output example, its expected decision, and the Rules whose behavior it verifies. |
| **Guardrail** | A deployable composition of version-pinned Policies, business intent, parameter values, and enforcement actions. |
| **Validation Run** | An immutable execution of a Guardrail's reviewed Test Cases through the same runtime used for production traffic. |
| **Guardrail Version** | The immutable audit and rollback unit containing the reviewed policy snapshot and the executable NeMo artifact derived from it. |
| **Deployment** | One ordered route for an Integration, or a direct/default route, binding a Traffic Scope to an exact released Guardrail Version. Selecting multiple Integrations backed by the same Adapter creates one independently ordered route per Integration. Release and rollback move their version pointers atomically. |
| **Traffic Scope** | The complete AND/OR expression evaluated after the Integration route table is selected. An empty expression means any traffic from that Integration. |
| **Traffic Condition** | One leaf predicate over authenticated request facts, such as principal, protocol, HTTP path/header, model, LiteLLM identity, JWT claim, or A2A metadata. |
| **Integration** | An authenticated traffic source representing one AI application, agent, or gateway instance. Its matching Deployments form an ordered, first-match-wins route table; an empty Traffic Scope provides an any-traffic fallback. |
| **NeMo Runtime** | The version-pinned execution environment for a Guardrail's rails, flows, Actions, and model references. |
| **Evidence** | An immutable, bounded record of validation, configuration changes, deployments, and sanitized runtime decisions for review and audit. |

## How It Works

```text
Describe the business purpose and boundaries
                       ↓
Choose versioned Policies and review their Rules
                       ↓
Run the reviewed Test Cases
                       ↓
Release an immutable Guardrail Version
                       ↓
Deploy it to the intended Traffic Scope
                       ↓
Review Evidence and improve the next version
```

A deployed version remains stable while teams work on the next revision. New
Policy changes take effect only after a Validation Run passes and a new
Guardrail Version is released. Existing Deployments bound to that Guardrail
advance atomically to the released Version. Rollback validates and prewarms a
historical artifact before atomically pointing those Deployments back; checks
already in flight continue on the Version with which they started.

## Local Development

Requirements: Python 3.11–3.13, [uv](https://docs.astral.sh/uv/), Node.js, and
npm. Provider credentials are optional for the deterministic local baseline.

```bash
cp .env.example .env
make sync
make web-build
make run
```

Open `http://localhost:8091`. Run the Python tests, web type checking, and the
production web build with:

```bash
make test
```

Runtime and provider settings are documented inline in
[`.env.example`](.env.example). More implementation detail is available in
[`docs/nemo-runtime.md`](docs/nemo-runtime.md),
[`docs/policy-library.md`](docs/policy-library.md), and
[`docs/integrations/litellm.md`](docs/integrations/litellm.md).

## Local Administrator

A fresh deployment creates its first local administrator automatically. Sign in with username `admin` and password `admin`, then use **Change password** in the account menu to replace the deployment default. Restarting or upgrading the service never resets a changed password.

## Designed For

- Enterprise assistants and internal knowledge experiences
- Customer-facing AI conversations and content generation
- Agents, workflows, and automated tasks
- Multi-model platforms and centralized AI gateways
- Organizations that require policy review, traceable change, and privacy-aware oversight
