# Gate B: Native Runtime Host

Status: Passed

The Runtime Host performs product lifecycle work only: version resolution,
prewarming, admission, deadline propagation, result adaptation, and shutdown.
NeMo remains the policy orchestrator.

| Acceptance | Evidence |
|---|---|
| Golden corpus decisions | `test_default_deterministic_golden_corpus_runs_through_nemo` |
| Input/output version pin | `test_activation_snapshot_version_pinning_and_atomic_rollback` |
| Atomic release and rollback | `test_activation_snapshot_version_pinning_and_atomic_rollback` |
| No active hot-path builds | `test_registry_prewarms_and_never_builds_on_the_active_hot_path` |
| Multi-Guardrail isolation | `test_many_guardrail_entities_are_concurrent_and_request_results_are_isolated` |
| Queue latency | `test_per_guardrail_admission_limit_reports_real_queue_latency` |
| Action timeout fail-closed | `test_required_action_timeout_fails_closed_and_is_observable` |
| Runtime/connection shutdown | `test_registry_shutdown_releases_active_and_retired_runtimes` |
| NeMo root trace | golden corpus and HTTP vertical-slice tests |

The cache key is `(guardrail_id, version, config_checksum)`. Active versions are
prewarmed during registry reload; initialization is serialized and deduplicated.
Evicted runtimes remain in a retired set until async shutdown releases their
NeMo lifecycle and provider resources.
