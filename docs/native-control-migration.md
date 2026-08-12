# Native Control migration

Status: Complete

Built-in policy choices are represented by immutable, system-managed Control
Version 1 packages. Existing installations are upgraded before runtime
prewarming, preserving the Guardrail Version number while replacing its compiled
artifact with the current auditable NeMo snapshot.

```text
Existing Guardrail policy intent
├── controls[] risk
│   └── bind the matching source=built-in Control Version 1
└── control_configurations[] custom/template Rules
    └── compile into version-pinned native Actions
```

Custom Colang Controls continue through the explicit validate, evaluate, and
publish lifecycle. For released versions, startup performs an idempotent
transaction that adds missing built-in Control bindings, recompiles retired
artifacts with the current compiler, recomputes checksums, and normalizes the
historical execution-mode field to `nemo_only`. Deployments remain pinned to the
same Guardrail Version and rollback stays entirely within the NeMo registry.
