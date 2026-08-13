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
| `persistence.enabled` | `true` | Persist SQLite control-plane state |
| `persistence.existingClaim` | empty | Existing PVC override; otherwise the chart creates `tali-guard` |
| `persistence.retain` | `true` | Retain the PVC after uninstall |
| `database.path` | `/var/lib/tasklattice/model-guardrails/tasklattice-guard-policy-schema-v3.db` | Persistent Policy, Guardrail, Deployment, Evidence, and identity database |
| `runtime.publicBaseUrl` | `http://localhost:38081` | Stable public origin used to generate per-Integration callback URLs |
| `evaluators.nvidia.baseUrl` | empty | Base URL for optional NVIDIA Guard Models |
| `evaluators.nvidia.groundingModel` | empty | NVIDIA-hosted Guard Model used for contextual-grounding evidence |
| `evaluators.deepJudge.model` | empty | Provider-neutral runtime Policy Judge model for prompt security, Topic Safety, and contextual grounding |
| `evaluators.deepJudge.existingSecret` | empty | Existing Secret containing the runtime Policy Judge API key |
| `evaluators.automatedReasoning.endpointUrl` | empty | Formal-reasoning provider endpoint returning detection-only findings |
| `evaluators.automatedReasoning.existingSecret` | empty | Existing Secret containing the reasoning provider API key |
| `evaluators.jailbreakDetection.nimBaseUrl` | empty | Optional NeMo Jailbreak Detection NIM base URL |
| `evaluators.jailbreakDetection.existingSecret` | empty | Existing Secret containing the Jailbreak Detection API key |
| `observability.runtimeP95BudgetMs` | `2500` | Runtime P95 latency budget shown on the operational dashboard |
| `observability.runtimeP99BudgetMs` | `5000` | Runtime P99 latency budget shown on the operational dashboard |
| `observability.maxConcurrencyPerGuardrail` | `64` | Maximum concurrent requests admitted to one prewarmed Guardrail Version |
| `observability.openTelemetry.enabled` | `false` | Export NeMo runtime telemetry over OTLP/HTTP |
| `observability.openTelemetry.endpoint` | empty | OTLP/HTTP collector base URL or traces endpoint |
| `controlPlaneAgent.deepseek.model` | `deepseek-v4-flash` | Model used only to structure policy intent |
| `controlPlaneAgent.deepseek.existingSecret` | empty | Existing Secret containing the DeepSeek API key |

The current early-development database contract is Policy schema v3. The
project has not launched and does not provide historical schema compatibility;
use a fresh database when the schema identifier changes.

TaskLattice Guard currently uses SQLite, so `replicaCount` is restricted to
`1`. Integration credentials are generated only when an Integration is
registered in the UI. NVIDIA evaluator settings remain optional.

A runtime Policy Judge and the optional control-plane assistant may safely
share an existing DeepSeek Secret, but they remain separate capabilities. The
Judge backs NeMo runtime Actions for selected Policies. The assistant only turns
business intent into an editable Policy draft and never inspects runtime
traffic. Configure both without placing the key in Helm history by creating a
Secret and referencing it:

```sh
kubectl --namespace tali create secret generic tasklattice-guard-deepseek \
  --from-literal=api-key='replace-me'
helm upgrade tasklattice-guard . --namespace tali \
  --set evaluators.deepJudge.baseUrl=https://api.deepseek.com \
  --set evaluators.deepJudge.model=deepseek-v4-flash \
  --set evaluators.deepJudge.existingSecret=tasklattice-guard-deepseek \
  --set controlPlaneAgent.deepseek.existingSecret=tasklattice-guard-deepseek
```

When OpenTelemetry is enabled, TaskLattice forces NeMo message-content capture
off. Exported telemetry contains operational dimensions such as Guardrail ID,
version, rail/action outcome, latency, runtime engine, and configuration checksum;
it does not contain prompt or response bodies.
