# Multi-tenancy design and progress

Updated: 2026-09-29. This is the implementation record for the `feat/multi_tanent` branch. It records the intended boundary, the resources checked, and the work verified in the branch. The stakeholder-facing proposal is [multi-tenancy-github-proposal.md](multi-tenancy-github-proposal.md). Update the progress table and limitations when implementation changes.

## Proposal alignment to implement

The demo proposal now defines Model Providers as resources supplied and managed by the internal platform. Tenants may select available providers, but may not own, share, manage, or view their credentials. It also requires the side panel to show the active tenant and scope links, counts, recent items, and shortcuts to that tenant's owned and explicitly shared resources. The implementation record below describes the branch's earlier tenant-owned Provider design; its schema, APIs, sharing rules, UI, and tests need to be revised to match this decision. The current side panel also needs an active-tenant indicator and a review of its navigation and cached data on identity switch. Keep this design gap open until the changes and their verification are recorded here.

## Goal and demo

Each signed-in user acts in one tenant. The canonical tenant IDs are `tenantA`, `tenantB`, and `tenantC`. The demo mock SSO chooser offers **tenantA (admin)**, **tenantB (group_b)**, and **tenantC (group_c)**. All three demo users are tenant-local administrators so they can create and share resources within their own tenant; `group_b` and `group_c` are their display labels, not cross-tenant roles. Switching identities must switch server-side authority and invalidate resource caches in the browser. The chooser is a local demonstration of an identity provider redirect, not a production SSO protocol. It is opt-in through `CONTROLLER_MOCK_SSO_ENABLED`. A caller-supplied tenant header or request body must never override the tenant established by authentication.

Tenant ownership applies to resource records, not merely to the console's navigation. A list returns only owned or explicitly shared resources. A direct ID read, mutation, nested route, validation, publication, credential operation, and resource reference must enforce the same boundary. The CLI calls the same Controller API and inherits the same authorization behavior.

### Local walkthrough

1. Apply the Controller database migrations and set `CONTROLLER_HTTP_HOST=127.0.0.1` and `CONTROLLER_MOCK_SSO_ENABLED=true` in the local Controller configuration. The flag is accepted only on a loopback, non-production Controller. Start the Controller and console, then use **Mock SSO** on the login page (or visit `/mock-sso`).
2. Select `tenantA (admin)` and inspect existing migrated resources. Existing single-tenant records belong to tenantA. Mock SSO also seeds one disabled Endpoint, `mock-sso-endpoint-tenantA`, in tenantA. Open **Sharing** (`/sharing`) to select one owned resource and tenantB as recipient.
3. Sign out, select `tenantB (group_b)`, and confirm its own disabled `mock-sso-endpoint-tenantB` and the shared resource are visible while tenantA's other resources are absent. Switch to `tenantC (group_c)` to confirm only its own disabled `mock-sso-endpoint-tenantC` appears. All three Endpoint IDs are deterministic; startup seeding is idempotent and occurs only with mock SSO enabled.
4. Sign back in to tenantA, revoke the grant from **Sharing**, and confirm tenantB no longer sees it. For a Router composition demonstration, share a published Guardrail and then select it as a Router target in tenantB. Endpoint binding remains same-tenant.

The seeded Endpoints are disabled examples for viewing tenant inventories. Create a Guardrail or Router while signed in as each tenant to compare those inventories on a fresh database.

Demo account passwords are derived server-side from `BETTER_AUTH_SECRET`. Rotating that secret after the accounts are seeded invalidates mock selector sign-in for those existing accounts; reset the local demo accounts/database before repeating the walkthrough with a new secret.

Public email signup is disabled. The initial tenantA administrator is created by the trusted bootstrap command; the three demo accounts are created by local startup provisioning only while mock SSO is enabled. Tenant-local user invitation and a real identity provider remain future work.

## Resource inventory and ownership

This inventory follows [the operations CLI resource list](ops-cli-proposal.md) and the Controller schema. `tenant_id` on a root record is the authority for its children. Existing `created_by`, `deleted_by`, and Policy `owner` fields are attribution or display metadata; they are not a tenant authorization key.

| Resource or view | Ownership boundary | Current phase |
| --- | --- | --- |
| Custom Policy, immutable versions, validation runs | Policy tenant; child records inherit through `policy_id` | Core scope |
| Guardrail, versions, artifacts, test cases, validation runs | Guardrail tenant; child records inherit through `guardrail_id` | Core scope |
| Traffic Router, draft Routes and Targets, published revisions | Router tenant; embedded Routes and Targets inherit from Router | Core scope |
| Endpoint and its credential verifier | Endpoint tenant; binding requires the Endpoint and Router to belong to the same tenant | Core scope |
| Legacy Guardrail Router (`guardrail_router`) | Explicit owner; references must be authorized | Core schema scope; verify API paths |
| Model Provider, Model, model assignment validations and configuration revisions | Provider/Model and revision management are tenant-owned; Runner delivery also needs a tenant boundary | Management scoping implemented; Runner activation remains tenantA only |
| Runtime events, route assignments, endpoint activity, metrics and distributions | Attribute to the invoking Endpoint or Router tenant at ingestion; query by that tenant before pagination and aggregation | Tenant keys and query filters implemented; verify ingress and aggregation paths |
| Audit events | Tenant of the affected resource at write time, including delete and share changes; filter before pagination | Tenant key, trigger, list filter, and share audit implemented; verify with PostgreSQL |
| Personal access tokens | User account and its tenant; token role/module permissions constrain access further | Session and token identity paths implemented; verify persisted-token behavior with PostgreSQL |
| Runner pools and Runner instances | Platform infrastructure rather than tenant-owned workloads | Globally readable; mutations restricted to tenantA administrators in this phase |
| System status | Deployment-wide readiness and configured model summary | Public and global, matching the pre-existing API |
| Built-in Policy catalog, Protection presets, Actions, selector fields | System-managed read-only catalog | Global read-only |

The core scope matches the first group of resource editors in the console. The broader inventory matters because a tenant-filtered Guardrail list does not isolate telemetry, model credentials, or audit history. Those gaps are tracked explicitly below and must not be described as production-complete multi-tenancy.

## Authorization rules

1. Derive the acting tenant from the authenticated session or personal access token's current user. A platform administrator role, if introduced later, needs an explicit separate path; an ordinary tenant administrator cannot inspect another tenant by ID.
2. Ownership grants read and permitted write operations. Sharing grants **read access** to one recipient tenant and composition use where that resource type supports cross-tenant references. It never transfers ownership, edit, publish, delete, credential access, or the power to share onward. An Endpoint or Router share is a read-only management view; it does not permit cross-tenant Endpoint binding. Removing a grant prevents new reads and references immediately. Revocation returns a conflict while the recipient's published Router uses a shared Guardrail, while a published or compiling Guardrail version uses a shared Policy, or while a validated or active model configuration uses a shared Model or Provider. The recipient must remove those references first.
3. Share grants identify a concrete root resource kind and ID, owner tenant, and recipient tenant. The allowed kinds in this phase are Policy, Guardrail, Traffic Router, Endpoint, Model Provider, and Model; each grant is read-only. A grant to a Guardrail does not expose that Guardrail's runtime logs or the owner's other resources. A grant to a Policy does not expose unrelated Guardrails. A shared Endpoint exposes configuration metadata but never its credential verifier. A shared Model does not imply a share of its Provider; a tenant must be able to read/use both before assigning that Model. Child versions can be read only through an authorized parent.
4. The server validates every cross-resource edge. A Guardrail may bind a Policy that is owned or shared to its tenant. A Router may target a Guardrail that is owned or shared to its tenant. A new Model must belong to the same tenant as its Provider; an assignment may use a separately shared Model and Provider. Endpoint binding is same-tenant only because Endpoint credentials define the caller boundary. Revalidate at draft save, preview, publish, rollback, and binding as applicable, including references in JSON snapshots.
5. Resource responses expose `tenantId`/ownership and share state where useful, but the client never decides authorization. Direct reads of hidden resources and writes to shared resources return a consistent not-found response to avoid existence disclosure. A dependency conflict may count references across tenants, but its message must not name another tenant's private resources.
6. Shared resources display source tenant and read-only status. The recipient must be able to tell whether a resource is owned or shared when choosing it in a Guardrail or Router editor.

### Sharing lifecycle

An owner chooses a recipient tenant from an allowlisted server response and grants access to one resource. Grants are idempotent. The recipient sees the resource in normal lists and can use it as a reference, subject to the rules above. The owner can revoke a grant after active recipient references are removed; a still-used grant returns `share_in_use`. Grant and revoke operations are audited. A deletion must either fail while actively referenced by another tenant or make the dependency unavailable in a defined way; it must not silently leave a newly publishable reference. Share access is non-transitive: a Router shared from tenantA to tenantB does not automatically share its target Guardrails with tenantB.

## Data and migration

- Add stable tenant rows and a non-null tenant key to tenant-owned root tables. Add an indexed grant table with unique `(owner_tenant_id, recipient_tenant_id, resource_type, resource_id)` grants and ownership validation in the service. The allowed share kinds are `policy`, `guardrail`, `router`, `endpoint`, `model_provider`, and `model`.
- Backfill existing single-tenant records and users to canonical `tenantA`. Preserve current IDs, versions, and relations. Treat system-managed built-in records separately. New writes must persist the server-derived tenant in the same transaction as the resource.
- Children's tenant is resolved through their parent for management authorization. For telemetry and audit, store the tenant at event time so later deletion or revocation cannot reassign historical evidence.
- The mock identity chooser must be explicitly enabled with `CONTROLLER_MOCK_SSO_ENABLED` for a local/demo profile and must not let arbitrary input impersonate a tenant. Normal Better Auth and PAT identities should map to a tenant even when mock SSO is disabled.
- Better Auth's public email signup and built-in administrator user-management routes (`/api/auth/admin/*`) are disabled for this phase. Those routes do not establish or enforce tenant membership and must stay closed until tenant-local user management is implemented.

## Verification scenarios

- Sign in as each demo identity and confirm each sees its owned resources, with no other tenant's unshared records in list or direct-ID reads.
- Share one Guardrail from tenantA to tenantB. tenantB sees and can target it but cannot edit, publish, delete, or reshare it; tenantC sees nothing. An active recipient Router blocks revocation. Remove that reference, revoke the grant, and repeat the direct-ID and target checks.
- Try to bind tenantB's Endpoint to tenantA's Router and reference tenantC's private Guardrail from tenantB's Router. Both operations fail before they persist or publish.
- Check Policies and Guardrail nested versions, tests, artifacts, and validation routes by direct ID; check CLI/PAT requests and non-admin roles.
- Check runtime event, telemetry metrics/distribution, audit, and model configuration routes separately before claiming complete isolation.

## Progress ledger

| Work | Status | Evidence / next check |
| --- | --- | --- |
| Map existing resource and authentication paths | Done | [`ops-cli-proposal.md`](ops-cli-proposal.md), [`schema.ts`](../controller/server/db/schema.ts), [`token-permissions.ts`](../controller/server/http/token-permissions.ts) |
| Define ownership and sharing rules | Implemented for the management-plane slice | This document and HTTP/service tests; live PostgreSQL scenarios remain |
| Tenant schema and legacy backfill | Verified in PostgreSQL | [`0013_multi_tenant_resources.sql`](../controller/server/db/migrations/0013_multi_tenant_resources.sql); fresh migration and populated-table backfill passed in disposable schemas |
| Server-derived tenant principal for sessions and PATs | Verified in focused PostgreSQL cases | Real mock SSO sessions and persisted PAT identity pass; repeat with production IdP when available |
| Policy, Guardrail, Endpoint, Router isolation | Implemented; focused PostgreSQL checks pass | Service tests cover cross-tenant IDs, references, publication, and mutation; expand nested route and deployed Runner checks before production |
| Mock SSO chooser, three identities, and disabled demo Endpoints | HTTP end-to-end verified; browser walkthrough remains | Real Better Auth sessions in PostgreSQL show separate tenant inventories; seeded Endpoint IDs are `mock-sso-endpoint-tenantA/B/C` |
| Share UI and grant/revoke API | HTTP end-to-end verified for Endpoint; further composition checks pass | Grant/revoke audit rows and recipient visibility pass in PostgreSQL; active references block revocation |
| Shared-resource badges and owner-only controls | Implemented | Policy, Guardrail, Endpoint, Router, Model, and Provider views mark foreign ownership and hide owner-only controls; server authority remains decisive |
| Model Provider, Model, and model configuration management tenancy | Focused PostgreSQL checks pass | Cross-tenant inventory/share and optimistic locking pass; Runner activation remains tenantA only |
| Runtime telemetry and audit tenancy | Focused PostgreSQL checks pass | Event isolation and share audit rows pass; expand aggregation and deployed ingress checks before production |
| Runner and control-plane tenant delivery | Partial | HTTP tests cover the tenantA-only Runner mutation gate. Verify deployed Router and Guardrail snapshots retain authorized tenant links; tenant-specific model activation needs a Runner protocol change |

### Validation recorded on this branch

- `cd controller && npm run build`: passed on 2026-09-28. This includes UI TypeScript checking, the production UI build, server compilation, and `npm run openapi:check` (105 operations and 280 schemas).
- `cd controller && npm run test`: 1,142 passed and 74 skipped across 151 files after the public-signup and share-revocation fixes. The full suite was run with local loopback socket access for the gRPC and TLS tests. The 74 skipped tests are in optional database suites; `GUARD_TEST_POSTGRES_URL` is not set. This includes the cross-tenant Model/Provider and Router/Guardrail sharing scenarios.
- `cd controller && npm run test:server`: 733 passed and 74 skipped across 70 files after the public-signup and share-revocation fixes, also with local loopback socket access.
- `cd controller && npm run db:migrate` on a disposable PostgreSQL 16 database: passed. A separate migration test applied `0013` to populated legacy tables and confirmed tenantA backfill.
- `cd controller && GUARD_TEST_POSTGRES_URL=<disposable local database> npm run test:server`: 801 passed and 8 skipped across 72 files. This includes real Better Auth mock SSO sessions, cross-tenant sharing and revocation, Model/Provider isolation, and the populated migration test.
- `cd controller && GUARD_TEST_POSTGRES_URL=<disposable local database> npm run test`: 1,210 passed and 8 skipped across 153 files, including UI and PostgreSQL suites.
- Focused tenant, mock SSO, sharing, access-token, model, login, and i18n tests passed. `git diff --check` passed.

A browser walkthrough against a migrated PostgreSQL database has not yet been run. The disposable database tests exercise migrations, mock SSO and sharing through HTTP, cross-tenant composition, and basic telemetry/audit paths. Runner delivery and broader aggregation cases still need deployment-level verification before a production claim.

## Known limitations

The current implementation phase is a demonstrable management-plane slice. The Controller currently distributes one active model configuration to Runners. TenantB and tenantC can own model management records, but activating their model revisions is disabled until the control protocol and Runner support tenant-specific configurations; otherwise one tenant could replace another's active models. Runner infrastructure stays deployment-global and only tenantA administrators can mutate it. The public `/api/v1/system/status` endpoint still exposes deployment-wide readiness and configured model/provider summary, so deployments needing those names private should redact or protect that response. Basic telemetry and audit tenant tests pass in PostgreSQL; full deployment ingress and aggregation still need verification. Public signup and built-in user administration are disabled, so there is no general tenant user onboarding yet. A mock SSO chooser is suitable for local demonstration only. Production multi-tenancy requires the follow-up rows above, deployment checks, and a real identity provider trust configuration.
