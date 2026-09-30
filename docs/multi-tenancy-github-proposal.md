# Proposal: Multi-tenant resource isolation demo

## Summary

Introduce tenants so each organization has its own Controller resources, including Guardrails, Routers, Endpoints, Policies, and Models. Model Providers come from the internal platform and remain platform-managed. A tenant sees and manages its own resources and may explicitly share a resource with another tenant for read-only access and supported composition.

The first milestone is a demo with three fixed identities. A temporary mock SSO chooser will let testers switch between them. It is only a Stage 1 test fixture, not a proposed product authentication component.

## Why

The single-organization workflow does not show how separate teams can manage their own protection and routing configurations without seeing or changing another team's private resources. We need a small, testable tenant boundary and a way to demonstrate intentional sharing.

## Demo scope

### Tenant ownership

- Give each signed-in identity one tenant. The server determines the tenant from the identity; request parameters and headers cannot override it.
- Apply ownership to resource lists, direct-ID reads, writes, child versions, and references between resources. The operations CLI follows the same API rules as the console.
- Start with the tenant-owned resource families that make the demo meaningful: Policy, Guardrail, Traffic Router, Endpoint, and Model. Keep built-in catalogs shared and read-only.
- The internal platform supplies Model Providers and controls their credentials and availability. Tenants may view and select providers made available to them, but cannot create, edit, delete, or share providers.
- Show a resource's owner tenant in the console. A recipient can distinguish a shared resource from one it owns.

### Tenant-scoped side panel

- Show the active tenant in the side panel. Resource links, counts, recent items, and shortcuts reflect only that tenant's owned resources and explicit shares.
- Hide links and actions the active tenant cannot use, including platform-only Model Provider management. A provider made available by the platform may appear as a read-only selection where relevant.
- Refresh the side panel on identity switch so names and counts from the previous tenant never remain visible.

### Sharing

- Let a tenant owner select one Policy, Guardrail, Router, Endpoint, or Model and one recipient tenant, grant read-only access, and revoke the grant.
- A recipient can inspect a shared resource but cannot edit, publish, delete, or share it onward.
- Permit supported composition: a tenant can use a shared Policy in its Guardrail or a shared Guardrail in its Router. An Endpoint remains bound only to a Router in its own tenant.
- Sharing is not transitive. Sharing a Router does not automatically expose its target Guardrails; sharing a Model does not grant access to platform-managed Provider credentials or management.
- Record grant and revoke actions. If a recipient still has an active configuration that uses a shared resource, explain the dependency and require its removal before revocation.

### Temporary sign-in fixture

For Stage 1 testing, redirect to a local mock SSO chooser with three fixed options:

| Choice | Demo identity |
| --- | --- |
| `tenantA` | `admin` |
| `tenantB` | `group_b` |
| `tenantC` | `group_c` |

Selecting an option signs in as that fixed tenant and shows its available resources. Switching options must clear cached data from the previous identity. The chooser is enabled only for the demo and is not part of the long-term authentication design.

## Demo walkthrough

1. Sign in as `tenantA` and create a Guardrail and Router. Confirm they appear in tenantA's inventory and side panel.
2. Switch to `tenantB`. Confirm tenantA's unshared resources disappear from both the page and side panel, and create a tenantB resource.
3. Switch back to `tenantA` and share the Guardrail with `tenantB`.
4. Sign in as `tenantB`. Confirm the shared Guardrail is visible as read-only and can be selected as a Router target. Confirm tenantB cannot edit or reshare it.
5. Sign in as `tenantC`. Confirm neither tenantA's private resources nor the A-to-B share are visible.
6. Remove tenantB's active reference, revoke the share as tenantA, and confirm tenantB loses access.

## Acceptance criteria

- [ ] Each demo identity sees its own resources and explicit shares, with no unshared cross-tenant resources in lists or direct-ID reads.
- [ ] The side panel identifies the active tenant and shows only that tenant's available links, resource names, and counts; switching identities refreshes it.
- [ ] Model Providers are supplied by the internal platform. Tenants can select available providers but cannot manage them or view their credentials.
- [ ] Writes to another tenant's resources, including shared resources, are rejected by the API.
- [ ] Cross-resource references follow the ownership and sharing rules above.
- [ ] Grant and revoke are visible in the console and recorded for audit.
- [ ] The three mock SSO choices switch identity and available resources without stale browser data.
- [ ] The walkthrough works through both the console and the operations CLI where those resource commands exist.
