# TaskLattice Guard Helm chart

This chart installs TaskLattice Guard as a standalone safety control plane. The
default deterministic evaluator can compile and test Safes without
an active LiteLLM Integration or an external model.

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
kubectl --namespace tali get service tasklattice-guard
```

## Important values

| Value | Default | Purpose |
| --- | --- | --- |
| `image.repository` | `ghcr.io/tasklattice/tasklattice-guard` | Container repository |
| `image.tag` | `dev` | Container tag |
| `service.type` | `LoadBalancer` | Kubernetes Service exposure |
| `persistence.enabled` | `true` | Persist SQLite control-plane state |
| `persistence.retain` | `true` | Retain the PVC after uninstall |
| `database.path` | `/var/lib/tasklattice/model-guardrails/tasklattice-guard-v8.db` | V8 policy and identity state |
| `evaluators.nvidia.baseUrl` | empty | Enable model-backed evaluators |
| `controlPlaneAgent.deepseek.model` | `deepseek-v4-flash` | Model used only to structure policy intent |
| `controlPlaneAgent.deepseek.existingSecret` | empty | Existing Secret containing the DeepSeek API key |

TaskLattice Guard currently uses SQLite, so `replicaCount` is restricted to
`1`. Gateway Adapter credentials are generated only when an Adapter is
registered in the UI. NVIDIA evaluator settings remain optional.

The optional DeepSeek control-plane assistant does not inspect runtime model
traffic. It only turns a business user's natural-language protection intent
into an editable rule draft. Configure it without placing the key in Helm
history by creating a Secret and referencing it:

```sh
kubectl --namespace tali create secret generic tasklattice-guard-deepseek \
  --from-literal=api-key='replace-me'
helm upgrade tasklattice-guard . --namespace tali \
  --set controlPlaneAgent.deepseek.existingSecret=tasklattice-guard-deepseek
```
