# ADR 0001: NeMo-native runtime lanes

Status: Accepted

## Decision

TaskLattice uses NVIDIA NeMo Guardrails as the only production policy
orchestrator. A compiled Guardrail Version selects exactly one explicit runtime
lane:

```text
Guardrail Version
├── IORails fast lane
│   └── Colang 1.0 native flows without dynamically registered Actions
└── LLMRails programmable lane
    └── Colang 2.x custom Controls and versioned TaskLattice Actions
```

The compiler never falls back between lanes. A custom Control or Action binding
always selects LLMRails. Input and output calls resolve the same immutable
Guardrail Version through the call context.

## Colang compatibility

- Native IORails artifacts remain Colang 1.0 because that is the runtime's
  native configuration surface.
- Custom Controls use Colang 2.x so `start`, `await`, and `match` express
  concurrency inside NeMo.
- One compiled Guardrail Version has one Colang version and one engine.
- Unsupported rail types and incompatible Colang versions fail compilation.
- Colang 2.x does not accept dots in executable flow identifiers. TaskLattice
  preserves the canonical audit identifier `tl.<control>.<version>.<flow>` and
  compiles it to an equivalent collision-free underscore identifier.

## Ordering and latency

Detection-only flows may share a parallel group. Mutating flows require an
explicit priority and execute after detection barriers. Multiple mutations may
not share an unordered parallel group. Action deadlines and failure modes are
versioned with each Rail binding.

Gate A is covered by `tests/test_nemo_native_vertical_slice.py` and the existing
Colang concurrency suite. The acceptance suite constructs `RailsConfig` and a
real NeMo Runtime, executes the same version on input and output over the HTTP
adapter, verifies Control/Rail/Flow/Action trace evidence, and asserts that two
independent 100 ms Actions complete in less than 180 ms.
