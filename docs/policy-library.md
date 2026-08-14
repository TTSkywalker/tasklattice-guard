# Policy Library, Rules, and Test Cases

TaskLattice exposes one product taxonomy regardless of the implementation used
underneath it:

```text
Policy Library
└── Policy
    ├── Rule
    └── Test Case

Guardrail
└── version-pinned Policy Binding
    ├── enabled Rules
    ├── reviewed parameters
    └── enforcement overrides
```

- A **Policy** is the reusable unit people discover, review, and bind to a
  Guardrail.
- A **Rule** is the smallest product behavior that can be configured and
  verified. Its implementation can be a regex, keyword matcher, category
  matcher, Colang Flow, Python Action, or model-backed check.
- A **Test Case** contains realistic input or output, the expected decision,
  the Rule IDs whose behavior it verifies, and optional grouping metadata for
  display. A group is not another product entity or selectable layer.

There is no Control, Control Pack, or implementation-specific product type.
Implementation provenance is metadata on a Rule and remains visible for
inspection without creating another hierarchy.

## Validation contract

Every built-in Rule must be covered by at least one required
`rule_acceptance` Test Case. The Policy Library refuses to load a Policy when:

- a Rule has no required acceptance case;
- a Test Case references an unknown Rule or parameter;
- Policy, Rule, or Test Case identifiers are duplicated;
- a stage or expected decision is unsupported; or
- a Policy has no Rules or no Test Cases.

Rule acceptance answers: “Can this exact Rule still produce its declared
behavior after a code, data, compiler, or dependency change?”

`scenario` Test Cases cover realistic positive, negative, and ambiguous
boundaries across one or more Rules. They answer: “Does this Policy still make
the intended business decision?”

For a user-authored Colang Policy, every Flow-backed Rule has the canonical ID
`flow/{rail}/{flow_name}`. The same ID is stored in the Policy Test Case,
Guardrail Policy Binding, compiled NeMo Action binding, runtime finding, and
Validation Run result. Selecting or overriding a Rule in a Guardrail therefore
changes the exact Flow that NeMo executes; Rules on the same Rail are never
collapsed into one product identity.

## Public API and inspection

`GET /api/v1/policies` and `GET /api/v1/policies/{policy_id}` return the same
shape for built-in and user-authored Policies:

- immutable Policy identity, version, source, tags, and parameters;
- Rules with their form, stages, effect, and technical implementation metadata;
- Test Cases and optional display-group metadata; and
- aggregate Rule and Test Case counts.

The Policy Library detail view has three product views:

1. **Policy** — purpose, tags, stages, effects, and parameters;
2. **Rules** — executable behaviors and their implementation provenance; and
3. **Test Cases** — every reviewed Test Case, including its display group,
   expected decision and covered Rule IDs.

This makes a Rule's acceptance contract inspectable before the Policy is added
to a Guardrail.

## Document-assisted Guardrail drafting

The first step of guided Guardrail creation can extract a review draft from up
to three compliance documents. The initial supported formats are legacy Word
(`.doc`), modern Word (`.docx`), and plain text (`.txt`); PDF is intentionally
not accepted in this release. Each file is limited to 5 MB and one request is
limited to 10 MB in total.

The server extracts bounded text sections, assigns stable source references,
and asks the configured policy analyst for:

- a proposed business purpose and topic boundaries;
- individual allow, block, transform, or review requirements with source
  references; and
- recommendations drawn only from Policy IDs that already exist in the Policy
  Library.

Document text is treated as untrusted source material rather than as
instructions. Extracted text is sent to the configured policy analyst; the UI
identifies its provider and model before analysis. The API returns hashes and
extraction metadata but does not store or return the original file or its full
text. Analysis results stay in the creation draft until the user explicitly
applies them, and all extracted requirements remain visible for review before
the Guardrail is saved.

## Guardrail materialization

A Guardrail stores a `GuardrailPolicyBinding` for every selected Policy. The
binding pins the Policy Version, enabled Rule IDs, parameter values, enabled
Rails, and any approved Policy- or Rule-level action override.

TaskLattice materializes the selected Policy Test Cases into the Guardrail
draft by:

1. pinning Policy, version, Test Case, and covered Rule IDs;
2. resolving placeholders from reviewed binding parameters;
3. preserving input/output phase and expected decision;
4. rejecting unresolved placeholders;
5. executing through the compiled Guardrail runtime; and
6. recording both declared covered Rule IDs and actual matched Rule IDs.

When a Guardrail enables only part of a Policy, only those Rule bindings are
compiled and only Test Cases covering enabled Rules are materialized. A
Rule-level action override is applied to that Rule's NeMo binding, while the
published Policy Version remains immutable.

For an enforcing case, a result passes only when the final decision matches and
at least one declared covered Rule actually matched. For an Allow case, the
declared Rules must not match. This prevents an unrelated blocker from making a
case appear successful.

Generated cases follow the current Guardrail draft. User-created cases remain
user-owned. Passing a **Validation Run** approves the current draft and records
immutable Evidence, but does not release it. A separate explicit **Publish**
action creates or confirms the immutable Guardrail Version that Deployments can
reference. A failed run remains Evidence and cannot be published.

## NeMo execution mapping

Product concepts compile into NeMo concepts without renaming the product model:

```text
Policy Binding
      ↓ compiler
RailsConfig
└── Rail
    └── Flow
        ├── Python Action
        └── Model
```

Colang and Python Actions are implementation choices recorded on Rules. NeMo
owns runtime lifecycle and final enforcement; TaskLattice owns Policy discovery,
versioning, Test Cases, Validation Runs, Deployments, and Evidence.
