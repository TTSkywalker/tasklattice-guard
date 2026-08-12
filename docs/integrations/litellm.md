# Connect LiteLLM to TaskLattice Guard

The TaskLattice LiteLLM image includes **TaskLattice Guard** as a Guardrail
Provider. Connect one LiteLLM Gateway by entering only two values in the
LiteLLM Admin UI:

- **Endpoint** — the stable URL for one TaskLattice Integration;
- **Secret** — the matching one-time Integration credential.

The Provider owns the callback path, input/output modes, always-on behavior,
and fail-closed defaults. You do not need to edit `config.yaml`, select a
generic provider, or restart LiteLLM after connecting it.

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

1. Open **Guardrails** and choose **Add Guardrail**.
2. Under **Provider**, select **TaskLattice Guard**.
3. Paste the TaskLattice **Endpoint**.
4. Paste the matching **Secret**.
5. Choose **Verify & connect**.

That is the complete Provider configuration. LiteLLM validates the Endpoint and
Secret against TaskLattice's side-effect-free verification endpoint, saves the
Provider, and activates it in the running instance. Verification does not count
as Guardrail traffic and does not advance the Integration's callback status.
There is no `config.yaml` change and no LiteLLM restart or redeploy after this
step.

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

The Provider also fixes these security behaviors internally, so they are not
configuration fields:

- inspect both model input and model output;
- apply TaskLattice Guard by default;
- block when the Guard service is unreachable; and
- block on invalid or failed Guard responses.

## 3. Verify real traffic

Send one normal model request through the connected LiteLLM Gateway. Use a
request that reaches the model so LiteLLM emits both callback phases.
TaskLattice reports setup progress per Integration:

1. **Awaiting input** — no input callback has arrived;
2. **Awaiting output** — input was received, but output has not arrived;
3. **Verified** — both input and output callbacks were observed.

A request blocked by the Input Rail proves that input inspection is connected,
but it cannot produce an output callback. Send an allowed request to complete
both directions.

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
Assignments can select different Guardrails for different Gateways.

Reusing a LiteLLM `litellm_call_id` in two Gateways is safe. TaskLattice
namespaces call context by Integration, so input/output state does not cross
between Gateways.

## Rotate a Secret without restarting LiteLLM

1. In the TaskLattice Integration details, generate a new credential.
2. Save the new one-time Secret.
3. Edit **TaskLattice Guard** in the LiteLLM Guardrails page.
4. Keep the same Endpoint, enter the new Secret, and choose **Verify & connect**.
5. Send one normal model request and wait for TaskLattice to report **Verified**.
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

### Setup remains at Awaiting input

Check Gateway networking, the Endpoint, and the Secret. Then send a model
request through the LiteLLM instance where the Provider was added.

### Setup remains at Awaiting output

Send an allowed request that reaches the model. A request stopped by the Input
Rail has no model output to inspect.

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
