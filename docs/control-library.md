# Control Library architecture

TaskLattice models reusable safety behavior with one composition chain:

```text
Rule -> Control -> Control Pack -> Guardrail -> Compiled Plan
```

- A **Rule** is the smallest executable detector and action.
- A **Control** owns a versioned set of Rules.
- A **Control Pack** groups reusable Controls and declares Pack parameters.
- A **Guardrail** selects Controls, optional Pack provenance, and concrete
  parameter values.
- A **Compiled Plan** is the immutable runtime artifact produced from a
  Guardrail version.

LiteLLM content-filter files are versioned vendor input. The importer under
`app/control_library/importers` converts that input into TaskLattice Controls
and Control Packs. Runtime and API code consume the Control Library registry;
they do not read vendor files or expose upstream policy-template concepts.

Rules Controls and NeMo-native Controls share `GET /api/v1/controls` and are
distinguished by `implementation` (`rules` or `nemo_native`). Control Packs are
available from `GET /api/v1/control-packs`.

Schema v4 intentionally has no compatibility layer. A v3 database—or any
database whose schema version differs from v4—is rejected and must be replaced
with a freshly initialized database. TaskLattice does not migrate the old
Integration `environment` column or previously compiled artifacts.
