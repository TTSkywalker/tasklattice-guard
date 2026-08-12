# Native Control migration

The legacy Guardrail shape embeds built-in risks and custom regex/keyword Rules.
Migration is versioned and never rewrites an active Guardrail in place.

```text
Legacy Guardrail draft
├── controls[] risk
│   └── bind the matching source=built-in Control Version 1
└── control_configurations[] custom/template Rules
    └── generate a source=custom Control Package
        ├── translate deterministic Rules into a Colang flow
        ├── preserve parameters and tests
        ├── validate dependencies
        └── publish Version 1 and pin a Guardrail ControlBinding
```

The migration command will create a new Guardrail draft revision, run the same
Evaluation corpus against legacy and native snapshots, and require an explicit
release. Existing Guardrail Versions and Assignments remain unchanged until the
new version passes evaluation and is activated. Phase 7 removes the legacy
fields only after every active version has an equivalent native snapshot.
