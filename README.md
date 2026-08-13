# TaskLattice Guard

**Turn business-readable AI safety policies into protection that teams can trust and operate.**

TaskLattice Guard is a guardrail management and enforcement platform for enterprise AI applications. It gives security, business, and AI teams a shared way to define acceptable behavior, validate protection policies, and apply reviewed guardrails to real traffic.

Rather than embedding disconnected safety rules in every application, TaskLattice Guard creates one governed lifecycle for AI protection—from business intent to runtime decisions and audit-ready evidence. It works across AI applications, agents, gateways, and models, so teams can evolve their AI stack without rebuilding their governance model.

## Core Advantages

- **NeMo-native protection** — Every released Guardrail is enforced through NVIDIA NeMo Guardrails, with TaskLattice adding the product lifecycle needed to operate it safely.
- **Business-first policies** — Describe purpose, allowed behavior, and boundaries in language that product, risk, and security teams can review together.
- **Reusable protection** — Manage guardrails independently from individual applications and models, then apply them wherever they are needed.
- **Validate before release** — Run reviewed Test Cases before creating a deployable version, reducing the risk of unreviewed policies reaching production.
- **Context-aware deployment** — Apply the right guardrail to the right application, user group, model, or business scenario.
- **Protection by default** — A managed baseline covers traffic that does not match a specific deployment.
- **Clear, privacy-conscious evidence** — Understand why decisions were made and how policies changed without retaining model request or response bodies.

## Product Architecture

TaskLattice Guard separates the governance path from the protected-traffic path.
The control plane determines what has been reviewed and deployed; NVIDIA NeMo
Guardrails is the single production engine that executes those decisions.

```text
 GOVERNANCE PATH                                  PROTECTED-TRAFFIC PATH

 Security · Business · AI Teams                   AI Apps · Agents · Gateways
                │                                               │
                ▼                                               │ input / output
 ┌──────────────────────────────────────┐                        ▼
 │       TaskLattice Control Plane      │        ┌────────────────────────────┐
 │                                      │        │ Trusted Integration Layer  │
 │ Define → Validate → Version → Deploy │        │ Authenticate · Normalize   │
 │ Traffic Scopes · Evidence · Overview │        └──────────────┬─────────────┘
 └──────────────┬───────────────────────┘                       │
                │                                               ▼
      reviewed, immutable                             Resolve Deployment
       Guardrail Version                              + pin exact Version
                │                                               │
                ▼                                               ▼
 ┌───────────────────────────────────────────────────────────────────────────┐
 │                  Versioned NeMo Runtime Registry                         │
 │        Prewarmed · Isolated per Version · Safe to Roll Back              │
 └─────────────────────────────────┬─────────────────────────────────────────┘
                                   ▼
 ┌────────────────────── NVIDIA NeMo Guardrails ─────────────────────────────┐
 │                                                                          │
 │  Input Rails / Output Rails                                              │
 │                                                                          │
 │                NeMo-native Protections + TaskLattice Actions             │
 │                  Local checks · Safety models · Policy services          │
 │                                      │                                   │
 │                                      ▼                                   │
 │       Policy Modules: Data Protection · Interaction Safety ·            │
 │                       Business Assurance                                │
 │          Independent modules in the same wave run in parallel           │
 │                                      │                                   │
 │                                      ▼                                   │
 │                    Deterministic policy resolution                       │
 │                 Deadlines · Isolation · Fail-closed                      │
 └─────────────────────────────────┬─────────────────────────────────────────┘
                                   ▼
                         Allow · Transform · Block
                                   │
                   Privacy-conscious Metrics & Evidence
                                   │
                                   └──────▶ Control Plane Overview / OpenTelemetry
```

The architecture is built around six principles:

- **Govern separately, enforce consistently** — Teams manage intent, review,
  release, and deployment in the control plane while NeMo handles runtime
  enforcement.
- **Run exactly what was reviewed** — Every request is pinned to an immutable
  Guardrail Version, so an input and its matching output cannot drift between
  policies.
- **Use one production policy engine** — Native NeMo rails and TaskLattice
  extensions execute inside the same NeMo lifecycle rather than competing
  policy pipelines.
- **Parallelize independent modules, escalate checks deliberately** — Data
  Protection, Interaction Safety, and Business Assurance run concurrently when
  they have no dependency. Within one Rule, local matching, Guard Models, and
  Policy Judges form an ordered, conditional escalation path rather than three
  permanently parallel evaluators. Transformations and enforcement are still
  resolved in a stable order.
- **Fail safely under pressure** — Prewarmed, version-isolated runtimes combine
  admission limits and deadlines with fail-closed behavior for required checks.
- **Observe without retaining model content** — Operational metrics and evidence
  support improvement and audit without storing request or response bodies.

## Core Product Concepts

| Concept | Meaning |
| --- | --- |
| **Policy Library** | The catalog of reusable, searchable Policies available to a Guardrail. |
| **Policy** | A reusable protection capability containing one or more executable Rules and their reviewed Test Cases. |
| **Rule** | The smallest product-level behavior that can be configured, executed, and verified by Test Cases. A Rule may be implemented by a regex, keyword matcher, category matcher, Colang Flow, Python Action, or model-backed check. |
| **Test Case** | A versioned input or output example, its expected decision, and the Rules whose behavior it verifies. |
| **Guardrail** | A deployable composition of version-pinned Policies, business intent, parameter values, and enforcement actions. |
| **Validation Run** | An immutable execution of a Guardrail's reviewed Test Cases through the same runtime used for production traffic. |
| **Guardrail Version** | An immutable, validated release of a Guardrail that can be safely deployed. |
| **Deployment** | A binding between a Guardrail Version and the traffic it should protect. |
| **Traffic Scope** | The complete AND/OR expression that determines whether a Deployment applies. |
| **Traffic Condition** | One leaf predicate inside a Traffic Scope, such as an Integration ID, model, protocol, or trusted request attribute. |
| **Integration** | The connection between TaskLattice Guard and an AI application, agent, or gateway. |
| **NeMo Runtime** | The RailsConfig, Rails, Flows, Python Actions, and models that execute each selected Guardrail Version. |
| **Evidence** | An immutable record of Validation Runs, Policy changes, Deployments, and runtime decisions for review and audit. |

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

A deployed version remains stable while teams work on the next revision. New Policy changes take effect only after a Validation Run passes, a new Guardrail Version is created, and a Deployment deliberately selects that version.

## Local Administrator

A fresh deployment creates its first local administrator automatically. Sign in with username `admin` and password `admin`, then use **Change password** in the account menu to replace the deployment default. Restarting or upgrading the service never resets a changed password.

## Designed For

- Enterprise assistants and internal knowledge experiences
- Customer-facing AI conversations and content generation
- Agents, workflows, and automated tasks
- Multi-model platforms and centralized AI gateways
- Organizations that require policy review, traceable change, and privacy-aware oversight
