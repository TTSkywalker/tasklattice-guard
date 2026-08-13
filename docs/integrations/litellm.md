# Connect LiteLLM to TaskLattice Guard

The TaskLattice LiteLLM image includes **TaskLattice Guard** as a Guardrail
Provider. Connect one LiteLLM Gateway in the LiteLLM Admin UI with:

- **Endpoint** — the stable URL for one TaskLattice Integration;
- **Secret** — the matching one-time Integration credential;
- **Protection stages** — **Before model**, **After model**, or both;
- **Guard unavailable** behavior — block the request or continue without
  protection; and
- optional **Advanced** settings for timeout and default application.

LiteLLM owns these runtime settings and decides when to call TaskLattice Guard.
TaskLattice Guard does not consume them as part of the Integration protocol.
You do not need to edit `config.yaml`, select a generic provider, or restart
LiteLLM after connecting it.

## Before you begin

You need:

- a TaskLattice LiteLLM image version that contains the **TaskLattice Guard**
  Provider;
- network access from LiteLLM to the TaskLattice Guard service;
- permission to create an Integration in TaskLattice Guard; and
- a secure place to store the one-time Secret.

If **TaskLattice Guard** does not appear in LiteLLM's Provider list, verify that
the Gateway is running the packaged TaskLattice LiteLLM image. Do not choose
**Custom** or another vendor's Provider as a substitute.

## 1. Create the Integration

In TaskLattice Guard:

1. Open **Integrations**.
2. Choose **Add integration**.
3. Select **TaskLattice Guard for LiteLLM**.
4. Give this Gateway a recognizable name and create the Integration.

TaskLattice displays the connection pair:

```text
Endpoint: https://guard.example.com/runtime/v1/integrations/<integration-uuid>
Secret:   tali_integration_<one-time-secret>
```

Copy the Secret and store it securely before leaving the setup screen. The
complete value is shown only once; after you confirm that it is stored,
TaskLattice collapses it to a non-secret key hint.

The Endpoint and Secret are a pair. The Integration UUID identifies the
Gateway instance, but it is not authentication. A Secret issued for another
Integration is rejected.

## 2. Add TaskLattice Guard in LiteLLM

In the LiteLLM Admin UI:

1. Open **Guardrails > Guardrail Garden**.
2. Open **TaskLattice Guard**, choose **Create Guardrail**, and confirm
   **TaskLattice Guard** in the Provider flow.
3. Paste the TaskLattice **Endpoint**.
4. Paste the matching **Secret**.
5. Under **Protection stages**, select **Before model**, **After model**, or
   both. At least one stage is required.
6. Under **Guard unavailable**, choose:
   - **Block request** (recommended and the default); or
   - **Continue without protection** for an availability-first deployment.
7. Under **Advanced**, review:
   - **Runtime timeout** — 1–60 seconds, default 10 seconds. A timeout follows the
     selected **Guard unavailable** behavior; and
   - **Apply to every request** — on by default. Turn it off only when clients
     explicitly select this Guardrail.
8. Choose **Verify & connect**.

LiteLLM validates the Endpoint and Secret against TaskLattice's side-effect-free
verification endpoint, saves the Provider settings, and activates it in the
running instance. Verification does not count as Guardrail traffic and does not
advance the Integration's callback status. There is no `config.yaml` change and
no LiteLLM restart or redeploy after this step.

**Before model** inspects model input and **After model** inspects model output.
These are LiteLLM hooks: LiteLLM sends only the callback phases you select, while
the TaskLattice Integration URL and wire protocol remain unchanged.

Use the Endpoint exactly as TaskLattice displays it. It must end with the
Integration UUID:

```text
https://guard.example.com/runtime/v1/integrations/<integration-uuid>
```

Do not append the callback suffix. The Provider adds the protocol path
internally:

```text
/beta/litellm_basic_guardrail_api
```

**Continue without protection** is deliberately narrow. It applies only when
LiteLLM cannot reach Guard because of a network failure or timeout, or receives
HTTP 502, 503, or 504. It never bypasses a TaskLattice policy block, HTTP 4xx or
500, or an invalid Guard response.

## 3. Verify real traffic

Send one model request through the connected LiteLLM Gateway. TaskLattice marks
the Integration as verified as soon as it receives any authenticated callback
stage enabled in LiteLLM. TaskLattice reports setup progress per Integration:

1. **Awaiting callback** — no real callback has arrived;
2. **Verified** — at least one input or output callback was observed.

An Input-only or Output-only Provider configuration can therefore complete
setup without enabling the other stage. TaskLattice continues to record input
and output timestamps separately for runtime observability, but a missing
optional stage does not block verification.

The TaskLattice setup screen refreshes this status automatically. No LiteLLM
restart is required while waiting for verification.

## Multiple LiteLLM Gateways

Create one TaskLattice Integration for each LiteLLM Gateway. Each Gateway gets
an independent Endpoint and Secret:

```text
Gateway A -> /runtime/v1/integrations/11111111-1111-4111-8111-111111111111 + Secret A
Gateway B -> /runtime/v1/integrations/22222222-2222-4222-8222-222222222222 + Secret B
```

TaskLattice rejects mixed pairs such as Gateway A's Endpoint with Secret B.
The Integration ID is also available as `integration.id` in Traffic Scope, so
Deployments can select different Guardrails for different Gateways.

Reusing a LiteLLM `litellm_call_id` in two Gateways is safe. TaskLattice
namespaces call context by Integration, so input/output state does not cross
between Gateways.

## Rotate a Secret without restarting LiteLLM

1. In the TaskLattice Integration details, generate a new credential.
2. Save the new one-time Secret.
3. Edit **TaskLattice Guard** in the LiteLLM Guardrails page.
4. Keep the same Endpoint, enter the new Secret, and choose **Verify & connect**.
5. Send one model request and wait for TaskLattice to receive any enabled stage
   and report **Verified**.
6. Revoke the old credential in TaskLattice.

TaskLattice permits overlapping credentials during rotation and refuses to
revoke the last active credential. The update takes effect immediately in
LiteLLM; no Gateway restart is needed.

## Troubleshooting

### TaskLattice Guard is missing from the Provider list

Confirm that LiteLLM is running the TaskLattice-packaged image version. The
Provider is not supplied by an unmodified upstream LiteLLM image. Do not use
**Custom** as a fallback; it creates inline code rather than this remote
Guardrail connection.

### Verify & connect rejects the connection

- confirm that LiteLLM can reach the Endpoint over the network;
- copy the Endpoint without the callback suffix;
- use the complete Secret, not the masked key hint;
- confirm that the Endpoint and Secret belong to the same Integration; and
- confirm that the Integration is enabled.

### Setup remains at Awaiting callback

Check Gateway networking, the Endpoint, and the Secret. Then send a model
request through the LiteLLM instance where the Provider was added.

## Security checklist

- Keep the one-time Secret in a secret manager.
- Use HTTPS outside an isolated development environment.
- Use one Integration and Secret pair per Gateway.
- Keep the stable TaskLattice service or ingress URL as the Endpoint; never use
  a Pod or node address.
- Rotate the Secret if it appears in a screenshot, log, support bundle, or
  source repository.
- Disable the Integration to reject all callbacks immediately when a Gateway
  must stop sending enforcement traffic.

TaskLattice Guard uses LiteLLM's Generic Guardrail API as its wire protocol,
while the packaged Provider removes protocol-level settings from the human
configuration path. For payload and response details, see the
[LiteLLM Generic Guardrail API contract](https://docs.litellm.ai/docs/adding_provider/generic_guardrail_api#api-contract).
