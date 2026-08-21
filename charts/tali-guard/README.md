# TaskLattice Guard Helm Chart

This chart deploys exactly two Guard application component types:

- **Guard Controller** — TypeScript UI/API, Better Auth, desired state,
  reconciliation, audit, telemetry ingest, and capacity views.
- **Guard Runner** — Python/NeMo data plane. `GuardRails 0` is the mandatory
  baseline pool and authoritative NeMo configuration compiler; `default` remains
  only its internal protocol ID. Every Runner pool is a StatefulSet, so instance
  IDs use stable ordinal Pod names such as `tali-guard-runner-0` instead of
  rollout-dependent hashes.

PostgreSQL and optional Redis are infrastructure dependencies, not additional
Guard application components.

## Images and dependencies

| Purpose | Default image/configuration | Required |
| --- | --- | --- |
| Controller | `ghcr.io/tasklattice/tali-guard-controller:0.2.0` | Yes, exactly one replica |
| Runner | `ghcr.io/tasklattice/tali-guard-runner:0.2.0` | Yes, GuardRails 0 >= 2 replicas |
| PostgreSQL | External PostgreSQL 14+ | Yes |
| Development PostgreSQL | `postgres:17-alpine` | Only when `postgresql.enabled=true` |
| Development Redis | `redis:7.4-alpine` | Local two-replica GuardRails 0 only |
| Redis | `runner.callContextRedisUrl` | Only when any Runner pool has more than one replica |

Integration setup instructions always target the stable Runtime Service through
its canonical in-cluster DNS name:
`http://<service>.<namespace>.svc.cluster.local:<service-port>`. Helm derives
the service, namespace, and port from the release. The endpoint contains no
Runner Pod or instance identity, never points at `controller.publicUrl`, and
does not require a manually maintained hostname.

LiteLLM stores that Integration base URL and appends its Basic Guardrail API
suffix (`/beta/litellm_basic_guardrail_api`) for runtime callbacks. Runner
implements that contract directly; Controller remains outside the request path.

Production image repositories/tags and dependency contracts live in
[`values.yaml`](values.yaml). The self-contained OrbStack/local profile lives in
[`values-dev.yaml`](values-dev.yaml).

## OrbStack/local installation

The development profile contains explicitly marked local-only credentials and
an Ed25519 signing key, enables single-node PostgreSQL plus Redis infrastructure,
and asks Helm to generate and retain the control-channel mTLS CA and certificates.
Its baseline login is username `admin` and password `admin`. Controller maps
the username to the internal Better Auth email `admin@tasklattice.local`.

One command rebuilds the moving `:dev` images and installs or upgrades the
whole Guard release on the `orbstack` context:

```bash
make helm-install
```

When the repository `.env` contains `DEEPSEEK_API_KEY` and/or `NVAPI_API_KEY`,
this target also creates or updates the `tali-guard-provider-keys` Secret.
DeepSeek is connected to Controller's authoring-only policy analyst. NVIDIA
Content Safety, Topic Control, and the chat-completion Jailbreak Judge model are
connected to every Runner pool through one Provider configuration. The command
prints the exact selected models during installation.

The equivalent direct Helm flow, after `make images`, is:

```bash
helm upgrade --install tali-guard ./charts/tali-guard \
  --kube-context orbstack \
  --namespace tali \
  --create-namespace \
  --values ./charts/tali-guard/values-dev.yaml \
  --server-side=false \
  --timeout 30s
```

`make helm-install` keeps both application tags fixed at `dev` and changes a
Helm-managed rollout revision annotation on every run. Controller and all
Runner pools therefore replace their Pods and load the latest local `dev`
images even though the image names remain unchanged. The command submits the
upgrade without waiting for Pod readiness; use `make helm-status` to inspect
the rollout separately.

Check the deployment and access Controller:

```bash
make helm-status
```

Open <http://localhost:38081> directly and sign in with `admin` / `admin`. The
bootstrap operation only creates a missing Better Auth user; Controller restarts
and Helm upgrades do not reset a password that has subsequently been changed.
No port-forward process is required. A development-only data-plane Service is
exposed separately at <http://localhost:38082>;
its root returns component metadata, while protected traffic uses `/runtime/v1`.
The host-facing development endpoint remains `http://localhost:38082`, while
Integration setup instructions use
`http://tali-guard-runtime.tali.svc.cluster.local:8091` for callers
inside the cluster.

## Production installation

Keep `postgresql.enabled=false`. Provide a PostgreSQL URL through an existing
Secret, preferably created by the platform secret manager:

```bash
kubectl -n guard-system create secret generic guard-database \
  --from-literal=database-url='postgresql://guard:REDACTED@postgres.example:5432/guard'
```

Create a Better Auth bootstrap administrator Secret with a strong, unique
password. Production has no application default credentials, and the chart's
default minimum password length is 12:

```bash
kubectl -n guard-system create secret generic guard-bootstrap-admin \
  --from-literal=email='admin@example.com' \
  --from-literal=password='replace-with-a-long-random-password' \
  --from-literal=name='Administrator'
```

Create an asymmetric Ed25519 artifact-signing Secret:

```bash
openssl genpkey -algorithm ED25519 -out private-key.pem
openssl pkey -in private-key.pem -pubout -out public-key.pem
kubectl -n guard-system create secret generic guard-artifact-signing \
  --from-file=private-key.pem \
  --from-file=public-key.pem
```

Create `guard-control-tls` with these keys:

- `ca.crt`
- `tls.crt` and `tls.key` for the Controller server certificate
- `runner.crt` and `runner.key` for the Runner client certificate

The Controller certificate must be valid for the Controller Service DNS name.
Both certificates must chain to `ca.crt`. Production intentionally requires an
externally managed Secret instead of auto-generating a private CA.

To enable business-boundary generation, create a separate model credential
Secret:

```bash
kubectl -n guard-system create secret generic guard-control-plane-ai \
  --from-literal=api-key='replace-with-provider-key'
```

Then set `controlPlaneAgent.deepseek.existingSecret=guard-control-plane-ai` in
the production values file. `baseUrl`, `model`, `provider`, and `secretKey` can
be overridden under the same values object.

NVIDIA runtime evaluators use `evaluators.nvidia`. Content Safety, Topic
Control, and Jailbreak share its OpenAI-compatible `baseUrl` and credential;
their independently configurable model names are `contentSafetyModel`,
`topicControlModel`, and `jailbreakModel`.

Install with a private production values file containing the actual public URL,
image tags, resource sizing, and ingress configuration:

```bash
helm upgrade --install tali-guard ./charts/tali-guard \
  --namespace guard-system \
  --create-namespace \
  --values ./values-production.yaml \
  --set database.existingSecret=guard-database \
  --set security.bootstrapAdmin.existingSecret=guard-bootstrap-admin \
  --set security.artifactSigning.existingSecret=guard-artifact-signing \
  --set security.controlTls.existingSecret=guard-control-tls \
  --set-string runner.callContextRedisUrl='redis://managed-redis.guard-system.svc:6379/0' \
  --rollback-on-failure \
  --wait \
  --timeout 15m
```

## Scaling contract

Controller remains one replica in this chart version. GuardRails 0 defaults to
two StatefulSet replicas with `minAvailable: 1`; the generated Pods are
`<release>-tali-guard-runner-0` and `-1`. Scale the data plane with
`runner.default.replicaCount` and `runner.pools`. Production must set
`runner.callContextRedisUrl` when any pool has more than one replica so
input/output checks for one request remain pinned to the same Guardrail
generation across Pods. The development profile provides its own Redis.

Every Runner pool gets a stable logical Runtime Service; individual Pod names
are never part of the upstream contract. Kubernetes performs ordinary balancing
with no session affinity. Input/output consistency comes from `call_id` and the
required shared Redis context when a pool has multiple replicas. Controller
Ingress exposes only the management UI/API, and protected runtime traffic never
traverses Controller.

Each pool also gets a private headless governing Service for StatefulSet network
identity. Upstream integrations continue to use only the load-balanced Runtime
Service; the headless Service and ordinal Pod names are not public endpoints.
