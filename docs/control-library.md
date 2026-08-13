# Control Library and acceptance tests

TaskLattice treats policy tests as a first-class, versioned part of every
built-in Control. The product model is:

```text
Rule -> Control + Test Suites -> Control Pack -> Guardrail Evaluation -> Release
```

- A **Rule** is the smallest executable detector and action.
- A **Control** owns a versioned set of Rules and their acceptance contract.
- A **Test Suite** groups immutable cases around one validation purpose.
- A **Control Pack** composes Controls and declares the parameters needed to
  make their tests executable in a concrete business context.
- A **Guardrail Evaluation** materializes those test cases with the selected
  Control version and Guardrail parameters, executes them through the same
  runtime used in production, and records the actual Rule matches.

Rules Controls and NeMo-native Controls share `GET /api/v1/controls` and are
distinguished by `implementation` (`rules` or `nemo_native`). Control Packs are
available from `GET /api/v1/control-packs`.

## Two test layers

Every Rules Control has two complementary test layers.

### Rule acceptance

Each published Rule must have at least one required positive case. The case
proves that the concrete regex, keyword, or category implementation can produce
its declared action. The registry rejects a built-in Control when any Rule is
uncovered, a case references an unknown Rule, or identifiers are duplicated.

Rule acceptance protects implementation integrity. It answers: “Can this exact
Rule still activate after a code, data, or compiler change?”

### Policy scenarios

Scenario suites model realistic positive, negative, and ambiguous boundaries.
They can assert Allow, Block, Transform, or Intervene while naming the Rules
whose behavior they validate. These suites protect the product policy rather
than a single detector branch.

Policy scenarios answer: “Does this Control still make the intended business
decision for representative user behavior?”

## Public contract

Each Rules Control returned by `GET /api/v1/controls` contains:

- `test_suites`: named suites with descriptions and cases;
- `test_count`: the total number of cases for the Control;
- for every case: immutable ID, name, phase, content, expected decision,
  required/advisory state, kind, covered Rule IDs, and required parameter names.

Each Control Pack includes aggregate `test_suite_count` and `test_case_count`.
Public product payloads identify these packages as TaskLattice `built_in`
resources. Source licensing and development provenance are maintained separately
in `THIRD_PARTY_NOTICES.md`; they are not part of the product taxonomy.

## Evaluation materialization

When a Rules Control or Control Pack is selected for a Guardrail, TaskLattice
copies all of its cases into that Guardrail's Evaluation suite. It does not run
directly from a mutable catalog asset.

Materialization performs these steps:

1. pin the Control ID and version, Suite ID, Case ID, and covered Rule IDs;
2. resolve placeholders with the reviewed Guardrail parameter values;
3. preserve the case's input/output phase and expected decision;
4. reject unresolved placeholders instead of silently weakening coverage;
5. execute through the compiled Guardrail runtime;
6. record both covered Rule IDs and actual matched Rule IDs in the result.

For an enforcing case, Evaluation passes only when the final decision matches
and at least one declared covered Rule actually matched. For an Allow case, the
declared Rules must not match. This prevents an unrelated blocker from making a
test appear successful.

Generated cases are refreshed from the current Guardrail draft. Custom cases
remain user-owned. A released Guardrail continues to reference the immutable
Control/test identity that was reviewed.

## Product interaction

The Rules Control detail sheet exposes two peer views:

- **Rules** shows the executable implementation. Expanding a Rule also shows
  every acceptance or scenario case that covers it.
- **Tests** groups the complete acceptance contract by Suite. Each case shows
  the prompt, phase, expected outcome, kind, parameters, and covered Rule IDs.

The Library is the inspection surface; Guardrail Evaluation is the execution
surface. The UI therefore explains the handoff instead of offering a misleading
catalog-level Run button without concrete Guardrail parameter values.

## Persistence and upgrades

Database schema v6 adds source Control, version, Suite, Case, and covered Rule
columns to generated Evaluation cases. Schema v5 is upgraded additively. Older
incompatible schemas remain rejected so compiled policy identity cannot be
silently reinterpreted.
