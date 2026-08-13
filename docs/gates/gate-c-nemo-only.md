# Gate C: NeMo-only Production Runtime

Status: Passed

NVIDIA NeMo Guardrails is the only production policy orchestrator. TaskLattice
provides versioning, deployment resolution, Action providers, runtime isolation,
Validation Runs and observability around that engine.

| Acceptance | Evidence |
|---|---|
| All released snapshots are current and `nemo_only` | `test_gate_c_every_released_version_and_deployment_is_current_nemo_only` |
| Incompatible database schemas are rejected | `test_nonempty_database_without_schema_metadata_is_rejected` and schema-version tests |
| Built-in Policies have immutable native mappings | `test_gate_c_every_builtin_policy_is_versioned_and_nemo_auditable` |
| Deterministic corpus remains 100% consistent | `test_default_deterministic_golden_corpus_runs_through_nemo` |
| Semantic Policies meet their Validation Run baselines | Policy, provider, and HTTP validation suites |
| Input/output version pinning and NeMo-only rollback | `test_activation_snapshot_version_pinning_and_atomic_rollback` |
| Parallelism, admission, timeout, fail-closed, and isolation | Gate B runtime suite |
| Trace and privacy-safe metrics | Phase 6 vertical-slice and metrics suites |
| Representative P95/P99 load stays inside configured budgets | `test_gate_c_representative_load_stays_inside_configured_p95_p99` |
| No Python policy DAG, Stage scheduler, or retired engine package | `test_gate_c_has_one_production_orchestrator_and_no_retired_engine_package` |
| Developer UI creates, validates, and publishes Colang Policies | Policy Studio tests and browser verification |
| Full application regression | Full Python and web suites; typecheck and production build passed |
| Source and dependency security | Bandit high-severity scan, `pip-audit`, and production `npm audit` passed with no known vulnerabilities |

The schema stores `execution_mode=nemo_only` as an explicit runtime invariant;
the API exposes no runtime-mode switch. This early-development release does not
migrate retired schemas or compiled artifacts.
