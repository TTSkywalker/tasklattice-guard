# TaskLattice Guard Helm chart

This chart installs the TaskLattice Guard control plane and its NeMo Guardrails
production runtime. The default policy runs locally without an active LiteLLM
Integration or an external model.

## Install

Kubernetes requires lowercase namespace names; the TALI namespace is `tali`.

```sh
helm upgrade --install tasklattice-guard . \
  --namespace tali \
  --create-namespace \
  --wait
```

The default Service is `LoadBalancer`. OrbStack assigns a local external
address; inspect it with:

```sh
kubectl --namespace tali get service tali-guard
```

A fresh persistent volume is initialized with the local administrator
`admin` / `admin`. Sign in and use **Change password** from the account menu
before exposing the Service beyond a trusted setup network. The password is
stored in the persistent database and is not reset by pod restarts or upgrades.

## Important values

| Value | Default | Purpose |
| --- | --- | --- |
| `image.repository` | `ghcr.io/tasklattice/tasklattice-guard` | Container repository |
| `image.tag` | `dev` | Container tag |
| `workloadNameOverride` | `tali-guard` | Kubernetes Service and Deployment name; Pod names inherit this prefix |
| `service.type` | `LoadBalancer` | Kubernetes Service exposure |
| `service.port` | `38081` | Kubernetes Service port; the Guard container continues to listen on `8091` |
| `persistence.enabled` | `true` | Persist the local SQLite fallback state |
| `persistence.existingClaim` | empty | Existing PVC override; otherwise the chart creates `tali-guard` |
| `persistence.retain` | `true` | Retain the PVC after uninstall |
| `database.path` | `/var/lib/tasklattice/model-guardrails/tasklattice-guard-policy-schema-v3.db` | Persistent Policy, Guardrail, Deployment, Evidence, and identity database |
| `database.url` | empty | SQLAlchemy database URL; intended for non-secret development configuration |
| `database.existingSecret` | empty | Existing Secret containing the production database URL |
| `database.secretKey` | `database-url` | Key within `database.existingSecret` |
| `runtime.publicBaseUrl` | `http://localhost:38081` | Stable public origin used to generate per-Integration callback URLs |
| `playgroundChat.model` | empty | General-purpose model used only to generate Playground conversations |
| `playgroundChat.existingSecret` | empty | Existing Secret containing the Playground model API key |
| `evaluators.nvidia.baseUrl` | empty | Base URL for optional NVIDIA Guard Models |
| `evaluators.nvidia.contentSafetyModel` | empty | Dedicated NVIDIA model for harmful-content input/output checks |
| `evaluators.nvidia.topicControlModel` | empty | Dedicated NVIDIA model for Topic and Organization Policy checks |
| `evaluators.nvidia.groundingModel` | empty | NVIDIA-hosted Guard Model used for contextual-grounding evidence |
| `evaluators.automatedReasoning.endpointUrl` | empty | Formal-reasoning provider endpoint returning detection-only findings |
| `evaluators.automatedReasoning.existingSecret` | empty | Existing Secret containing the reasoning provider API key |
| `evaluators.jailbreakDetection.nimBaseUrl` | empty | Optional NeMo Jailbreak Detection NIM base URL |
| `evaluators.jailbreakDetection.serverEndpoint` | `classify` | Classification path appended by NeMo; use `/v1/security/nvidia/nemoguard-jailbreak-detect` for NVIDIA's hosted API |
| `evaluators.jailbreakDetection.existingSecret` | empty | Existing Secret containing the Jailbreak Detection API key |
| `observability.runtimeP95BudgetMs` | `2500` | Runtime P95 latency budget shown on the operational dashboard |
| `observability.runtimeP99BudgetMs` | `5000` | Runtime P99 latency budget shown on the operational dashboard |
| `observability.maxConcurrencyPerGuardrail` | `64` | Maximum concurrent requests admitted to one prewarmed Guardrail Version |
| `observability.openTelemetry.enabled` | `false` | Export NeMo runtime telemetry over OTLP/HTTP |
| `observability.openTelemetry.endpoint` | empty | OTLP/HTTP collector base URL or traces endpoint |
| `controlPlaneAgent.deepseek.model` | `deepseek-v4-flash` | Model used only to structure policy intent |
| `controlPlaneAgent.deepseek.existingSecret` | empty | Existing Secret containing the DeepSeek API key |

For the NVIDIA-hosted Runtime path, configure the dedicated model roles with
one NVIDIA Secret. The Jailbreak Detection endpoint reuses that credential:

```sh
helm upgrade tasklattice-guard . --namespace tali \
  --set evaluators.nvidia.baseUrl=https://integrate.api.nvidia.com/v1 \
  --set evaluators.nvidia.contentSafetyModel=nvidia/llama-3.1-nemotron-safety-guard-8b-v3 \
  --set evaluators.nvidia.topicControlModel=nvidia/llama-3.1-nemoguard-8b-topic-control \
  --set evaluators.nvidia.existingSecret=tasklattice-guard-nvidia \
  --set evaluators.jailbreakDetection.nimBaseUrl=https://ai.api.nvidia.com \
  --set evaluators.jailbreakDetection.serverEndpoint=/v1/security/nvidia/nemoguard-jailbreak-detect
```

These values never configure a `main` model inside NeMo Runtime.

Application persistence is managed through SQLAlchemy ORM. New deployments
create the current ORM schema directly; there is no legacy-schema compatibility
or application migration layer. SQLite remains the zero-configuration,
single-replica fallback. Operators can provide another SQLAlchemy URL through
`database.existingSecret` and own its availability and rollout policy.
Integration credentials are
generated only when an Integration is registered in the UI. NVIDIA evaluator
settings remain optional.

```sh
kubectl --namespace tali create secret generic tasklattice-guard-database \
  --from-literal=database-url='postgresql+psycopg://guard:replace-me@postgres:5432/guard'
helm upgrade tasklattice-guard . --namespace tali \
  --set database.existingSecret=tasklattice-guard-database \
  --set replicaCount=3
```

The Playground chat model and optional control-plane assistant may share an
existing DeepSeek Secret, but they remain outside Runtime evaluation. The
Playground model generates test conversations; the assistant only turns
business intent into an editable Policy draft. NeMo Runtime never registers
either model as an evaluator. Configure both without placing the key in Helm
history by creating a Secret and referencing it:

```sh
kubectl --namespace tali create secret generic tasklattice-guard-deepseek \
  --from-literal=api-key='replace-me'
helm upgrade tasklattice-guard . --namespace tali \
  --set playgroundChat.baseUrl=https://api.deepseek.com \
  --set playgroundChat.model=deepseek-v4-flash \
  --set playgroundChat.existingSecret=tasklattice-guard-deepseek \
  --set controlPlaneAgent.deepseek.existingSecret=tasklattice-guard-deepseek
```

When OpenTelemetry is enabled, TaskLattice forces NeMo message-content capture
off. Exported telemetry contains operational dimensions such as Guardrail ID,
version, rail/action outcome, latency, runtime engine, and configuration checksum;
it does not contain prompt or response bodies.
