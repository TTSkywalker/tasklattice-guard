# Connect LiteLLM to TaskLattice Guard

TaskLattice Guard implements LiteLLM's [Generic Guardrail API](https://docs.litellm.ai/docs/adding_provider/generic_guardrail_api). Each Integration represents one concrete LiteLLM Gateway and receives its own stable API base URL and credential.

## Before you begin

You need:

- a reachable public or private TaskLattice Guard URL;
- a LiteLLM Gateway that can reach that URL;
- permission to create an Integration in TaskLattice Guard; and
- a secret manager or another safe place to store the one-time credential.

TaskLattice shows a new credential only once. Treat it as a secret. The Integration UUID in the URL identifies the Gateway instance, but it is not authentication; TaskLattice also requires the matching credential.

## 1. Create a LiteLLM Integration

In **Integrations**, choose **Add integration**, select the LiteLLM Generic Guardrail adapter, and give the Gateway a recognizable name.

The result contains two values:

```text
API base URL: https://guard.example.com/runtime/v1/integrations/<integration-uuid>
API key:      tali_integration_<one-time-secret>
```

Copy both values before leaving the setup screen. Do not copy the callback suffix into `api_base`. LiteLLM automatically appends:

```text
/beta/litellm_basic_guardrail_api
```

The resulting callback is therefore:

```text
POST https://guard.example.com/runtime/v1/integrations/<integration-uuid>/beta/litellm_basic_guardrail_api
X-API-Key: tali_integration_<one-time-secret>
```

This behavior is part of LiteLLM's Generic Guardrail implementation: it appends the callback path when `api_base` does not already end with it. TaskLattice deliberately generates the shorter instance API base.

## 2. Store the credential

Put the values in the LiteLLM Gateway's secret configuration. The names below are examples; keep separate values for every Gateway.

```bash
TASKLATTICE_GUARD_API_BASE='https://guard.example.com/runtime/v1/integrations/<integration-uuid>'
TASKLATTICE_GUARD_API_KEY='tali_integration_<one-time-secret>'
```

Do not commit the key to `config.yaml`, a container image, or source control.

## 3. Configure LiteLLM

The generated `config.yaml` snippet is the canonical setup path. TaskLattice is
not a vendor name in LiteLLM's provider list:

- If the LiteLLM Admin UI offers **Provider → Generic Guardrail API**, that is
  the matching provider type.
- Do not select **Custom**. That creates a custom-code guardrail inside LiteLLM;
  it does not configure this remote API integration.
- Do not substitute another vendor provider. If **Generic Guardrail API** is not
  available in the installed LiteLLM version, use `config.yaml` as shown below.

Add this guardrail to the Gateway's `config.yaml`:

```yaml
litellm_settings:
  guardrails:
    - guardrail_name: tasklattice-guard
      litellm_params:
        guardrail: generic_guardrail_api
        mode: [pre_call, post_call]
        api_base: os.environ/TASKLATTICE_GUARD_API_BASE
        api_key: os.environ/TASKLATTICE_GUARD_API_KEY
        default_on: true
        unreachable_fallback: fail_closed
        fail_on_error: true
```

The important settings are:

- `pre_call` sends model input through the TaskLattice Input Rail.
- `post_call` sends model output through the TaskLattice Output Rail.
- `default_on: true` applies the guardrail even when a caller does not name it explicitly.
- `unreachable_fallback: fail_closed` blocks when the endpoint is unreachable, times out, or an upstream proxy returns 502, 503, or 504.
- `fail_on_error: true` blocks on every guardrail error, including non-2xx or malformed responses.

LiteLLM documents `fail_on_error: false` as a complete guardrail bypass on errors. Do not use fail-open behavior when TaskLattice is a security boundary unless that availability tradeoff has been explicitly accepted.

Restart or reload LiteLLM after changing its configuration.

## 4. Verify both callback phases

Send a real model request through that LiteLLM Gateway. TaskLattice reports setup progress per Integration:

1. `Awaiting input` — no pre-call callback has arrived yet.
2. `Awaiting output` — an input callback arrived, but no post-call callback has arrived.
3. `Verified` — both input and output callbacks have been observed.

Use a request that reaches the model so LiteLLM can emit both phases. A blocked input correctly proves the Input Rail is connected, but there will be no model response and therefore no Output Rail callback.

If setup remains at `Awaiting input`, check Gateway networking, the API base, and the key. If it remains at `Awaiting output`, confirm that `post_call` is present and that the test request was not stopped before model execution.

## Multiple LiteLLM Gateways

Create one Integration for each Gateway. Every Gateway uses the same TaskLattice public service, but has a different Integration UUID and credential:

```text
Gateway A -> /runtime/v1/integrations/11111111-1111-4111-8111-111111111111 + Key A
Gateway B -> /runtime/v1/integrations/22222222-2222-4222-8222-222222222222 + Key B
```

TaskLattice rejects mixed pairs such as Gateway A's URL with Key B. This prevents a copied or misrouted credential from silently attributing traffic to the wrong Gateway. The Integration ID is also available as `integration.id` in Traffic Scope, so Assignments can select different Guardrails for different Gateways.

Reusing a LiteLLM `litellm_call_id` in two Gateways is safe: TaskLattice namespaces the call context by Integration, so input/output state does not cross between Gateways.

## Rotate or revoke a credential

Rotate without downtime:

1. Create a new credential from the Integration details.
2. Store the new value in the Gateway's secret manager.
3. restart or reload the Gateway and verify a real request;
4. revoke the old credential.

TaskLattice allows more than one active credential during rotation, but refuses to revoke the last active credential. Revoked credentials cannot call the runtime URL. The Integration API and UI expose only credential IDs and non-secret key hints; the original value cannot be retrieved later.

## Disable an Integration

Disabling an Integration immediately rejects its runtime calls, even when the caller supplies a previously valid key. Re-enable it only after confirming that the Gateway should resume enforcement traffic.

## Stable URL and future high availability

Configure a stable service or ingress URL, never a TaskLattice node, Pod, or host address. TaskLattice Guard can later add replicas and load balancing behind that same public domain. LiteLLM holds only the stable Integration API base and key, so it does not need to know or change when the TaskLattice high-availability topology changes.

## Security checklist

- Keep the Integration credential in a secret manager.
- Use HTTPS outside an isolated development environment.
- Leave both pre-call and post-call modes enabled.
- Keep `default_on: true` for an always-on security boundary.
- Keep fail-closed behavior unless a documented risk decision says otherwise.
- Use a separate Integration and key for every Gateway.
- Rotate a key if it appears in a screenshot, log, support bundle, or source control.

For the underlying payload and response shapes, see the [LiteLLM Generic Guardrail API contract](https://docs.litellm.ai/docs/adding_provider/generic_guardrail_api#api-contract).
