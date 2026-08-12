# TaskLattice Guard

**Turn business-readable AI safety policies into protection that teams can trust and operate.**

TaskLattice Guard is a guardrail management and enforcement platform for enterprise AI applications. It gives security, business, and AI teams a shared way to define acceptable behavior, validate protection policies, and apply reviewed guardrails to real traffic.

Rather than embedding disconnected safety rules in every application, TaskLattice Guard creates one governed lifecycle for AI protection—from business intent to runtime decisions and audit-ready evidence. It works across AI applications, agents, gateways, and models, so teams can evolve their AI stack without rebuilding their governance model.

## Core Advantages

- **NeMo-native protection** — Every released policy is enforced through NVIDIA NeMo Guardrails, with TaskLattice adding the product lifecycle needed to operate it safely.
- **Business-first policies** — Describe purpose, allowed behavior, and boundaries in language that product, risk, and security teams can review together.
- **Reusable protection** — Manage guardrails independently from individual applications and models, then apply them wherever they are needed.
- **Validate before release** — Evaluate changes before creating a deployable version, reducing the risk of unreviewed policies reaching production.
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
 │ Define → Evaluate → Version → Deploy │        │ Authenticate · Normalize   │
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
 │                         Parallel risk evaluation                         │
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
- **Detect in parallel, decide deterministically** — Independent protections can
  run concurrently, while transformations and enforcement are resolved in a
  stable order.
- **Fail safely under pressure** — Prewarmed, version-isolated runtimes combine
  admission limits and deadlines with fail-closed behavior for required checks.
- **Observe without retaining model content** — Operational metrics and evidence
  support improvement and audit without storing request or response bodies.

## Core Product Concepts

| Concept | Meaning |
| --- | --- |
| **Control** | A reusable protection capability, such as sensitive-data protection, content safety, prompt-attack defense, or business-boundary enforcement. |
| **Guardrail** | A policy that brings together business intent, selected Controls, and the actions to take when a boundary is reached. |
| **Evaluation** | The review and validation step used to confirm that a Guardrail behaves as intended before release. |
| **Guardrail Version** | An immutable, validated release of a Guardrail that can be safely deployed. |
| **Deployment** | A binding between a Guardrail Version and the traffic it should protect. |
| **Traffic Scope** | The trusted business and request context that determines which Deployment applies. |
| **Integration** | The connection between TaskLattice Guard and an AI application, agent, or gateway. |
| **Runtime** | The NeMo Guardrails engine that executes each selected, immutable Guardrail Version. |
| **Evidence** | A record of evaluations, policy changes, deployments, and protection decisions for review and audit. |

## How It Works

```text
Describe the business purpose and boundaries
                       ↓
Choose and review protection Controls
                       ↓
Evaluate expected behavior
                       ↓
Release an immutable Guardrail Version
                       ↓
Deploy it to the intended Traffic Scope
                       ↓
Review Evidence and improve the next version
```

A deployed version remains stable while teams work on the next revision. New policy changes take effect only after they have been evaluated, released, and deliberately deployed.

## Local Administrator

A fresh deployment creates its first local administrator automatically. Sign in with username `admin` and password `admin`, then use **Change password** in the account menu to replace the deployment default. Restarting or upgrading the service never resets a changed password.

## Designed For

- Enterprise assistants and internal knowledge experiences
- Customer-facing AI conversations and content generation
- Agents, workflows, and automated tasks
- Multi-model platforms and centralized AI gateways
- Organizations that require policy review, traceable change, and privacy-aware oversight
