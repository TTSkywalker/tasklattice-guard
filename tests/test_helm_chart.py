from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "charts" / "tali-guard"
DEV_VALUES = CHART / "values-dev.yaml"
REQUIRED = (
    "--set", "database.url=postgresql://guard:guard@postgres:5432/guard",
    "--set", "security.artifactSigning.existingSecret=artifact-signing",
    "--set", "security.controlTls.existingSecret=control-tls",
    "--set", "security.bootstrapAdmin.existingSecret=bootstrap-admin",
    "--set", "runner.callContextRedisUrl=redis://redis:6379/0",
)


def render(*values: str) -> list[dict]:
    output = subprocess.run(
        ["helm", "template", "contract", str(CHART), *REQUIRED, *values],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [item for item in yaml.safe_load_all(output) if item]


def render_dev(*values: str) -> list[dict]:
    output = subprocess.run(
        ["helm", "template", "tali-guard", str(CHART), "--namespace", "tali", "--values", str(DEV_VALUES), *values],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [item for item in yaml.safe_load_all(output) if item]


def test_minimum_install_has_controller_and_two_stable_guardrails_zero_runners():
    documents = render()
    deployments = [item for item in documents if item.get("kind") == "Deployment"]
    stateful_sets = [item for item in documents if item.get("kind") == "StatefulSet"]

    assert [item["metadata"]["name"] for item in deployments] == ["contract-tali-guard-controller"]
    assert [item["metadata"]["name"] for item in stateful_sets] == ["contract-tali-guard-runner"]
    runner = stateful_sets[0]
    assert runner["spec"]["replicas"] == 2
    assert runner["spec"]["serviceName"] == "contract-tali-guard-runner-headless"
    assert runner["spec"]["podManagementPolicy"] == "Parallel"
    assert runner["spec"]["minReadySeconds"] == 5
    runner_pod_spec = runner["spec"]["template"]["spec"]
    assert runner_pod_spec["terminationGracePeriodSeconds"] == 30
    assert runner_pod_spec["containers"][0]["lifecycle"]["preStop"]["exec"]["command"] == [
        "/bin/sh", "-c", "sleep 5",
    ]
    assert deployments[0]["spec"]["replicas"] + runner["spec"]["replicas"] == 3
    pdb = next(item for item in documents if item.get("kind") == "PodDisruptionBudget")
    assert pdb["metadata"]["name"] == "contract-tali-guard-runner-availability"
    assert pdb["spec"]["minAvailable"] == 1


def test_controller_and_runner_have_distinct_images_ports_and_responsibilities():
    documents = render()
    controller_workload = next(item for item in documents if item.get("kind") == "Deployment")
    runner_workload = next(item for item in documents if item.get("kind") == "StatefulSet")
    controller = controller_workload["spec"]["template"]["spec"]["containers"][0]
    runner = runner_workload["spec"]["template"]["spec"]["containers"][0]
    controller_env = {item["name"]: item for item in controller["env"]}
    runner_env = {item["name"]: item for item in runner["env"]}

    assert controller["image"].startswith("ghcr.io/tasklattice/tali-guard-controller:")
    assert runner["image"].startswith("ghcr.io/tasklattice/tali-guard-runner:")
    assert {item["name"] for item in controller["ports"]} == {"http", "grpc"}
    assert {item["name"] for item in runner["ports"]} == {"runtime"}
    assert "CONTROLLER_DATABASE_URL" in controller_env
    assert controller_env["CONTROLLER_RUNTIME_SERVICE_URL"]["value"] == (
        "http://contract-tali-guard-runtime.default.svc.cluster.local:8091"
    )
    assert controller_env["BETTER_AUTH_MIN_PASSWORD_LENGTH"]["value"] == "12"
    assert controller_env["CONTROLLER_ALLOW_LOCAL_DEFAULT_CREDENTIALS"]["value"] == "false"
    assert "GUARD_CONTROLLER_TARGET" in runner_env
    assert "CONTROLLER_DATABASE_URL" not in runner_env
    assert runner_env["GUARD_RUNNER_COMPILER_CAPABLE"]["value"] == "true"
    assert runner_env["GUARD_RUNNER_ID"]["valueFrom"]["fieldRef"]["fieldPath"] == "metadata.name"
    assert runner_env["GUARD_RUNNER_CALL_CONTEXT_REDIS_URL"]["value"] == "redis://redis:6379/0"


def test_control_plane_authoring_model_is_optional_and_credential_is_secret_backed():
    baseline = render()
    baseline_controller = next(
        item for item in baseline
        if item.get("kind") == "Deployment"
        and item["metadata"]["labels"]["app.kubernetes.io/component"] == "controller"
    )
    baseline_env = {
        item["name"]: item
        for item in baseline_controller["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert baseline_env["MODEL_GUARDRAILS_CONTROL_PLANE_AI_PROVIDER"]["value"] == "DeepSeek"
    assert baseline_env["MODEL_GUARDRAILS_CONTROL_PLANE_AI_MODEL"]["value"] == "deepseek-v4-flash"
    assert "MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY" not in baseline_env

    configured = render(
        "--set", "controlPlaneAgent.deepseek.existingSecret=provider-keys",
        "--set", "controlPlaneAgent.deepseek.secretKey=DEEPSEEK_API_KEY",
    )
    configured_controller = next(
        item for item in configured
        if item.get("kind") == "Deployment"
        and item["metadata"]["labels"]["app.kubernetes.io/component"] == "controller"
    )
    configured_env = {
        item["name"]: item
        for item in configured_controller["spec"]["template"]["spec"]["containers"][0]["env"]
    }
    assert configured_env["MODEL_GUARDRAILS_CONTROL_PLANE_AI_API_KEY"]["valueFrom"]["secretKeyRef"] == {
        "name": "provider-keys",
        "key": "DEEPSEEK_API_KEY",
    }


def test_inline_control_plane_authoring_key_creates_a_dedicated_secret():
    documents = render("--set-string", "controlPlaneAgent.deepseek.apiKey=test-key")
    secret = next(
        item for item in documents
        if item.get("kind") == "Secret"
        and item["metadata"]["name"] == "contract-tali-guard-control-plane-ai"
    )

    assert secret["stringData"] == {"api-key": "test-key"}


def test_nvidia_models_and_shared_provider_secret_are_wired_to_every_runner():
    documents = render(
        "--set", "evaluators.nvidia.baseUrl=https://integrate.api.nvidia.com/v1",
        "--set", "evaluators.nvidia.existingSecret=provider-keys",
        "--set", "evaluators.nvidia.secretKey=NVAPI_API_KEY",
        "--set", "runner.pools[0].name=gpu",
        "--set", "runner.pools[0].replicaCount=1",
        "--set", "runner.pools[0].maxConcurrency=128",
        "--set", "runner.pools[0].resources.requests.cpu=1",
        "--set", "runner.pools[0].resources.requests.memory=2Gi",
        "--set", "runner.pools[0].resources.limits.memory=8Gi",
    )
    runners = [
        item for item in documents
        if item.get("kind") == "StatefulSet"
        and item["metadata"]["labels"]["app.kubernetes.io/component"] == "runner"
    ]

    assert len(runners) == 2
    for runner in runners:
        environment = {
            item["name"]: item
            for item in runner["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        assert environment["MODEL_GUARDRAILS_NVIDIA_BASE_URL"]["value"] == "https://integrate.api.nvidia.com/v1"
        assert environment["MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL"]["value"] == "nvidia/llama-3.1-nemotron-safety-guard-8b-v3"
        assert environment["MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL"]["value"] == "nvidia/llama-3.1-nemoguard-8b-topic-control"
        assert environment["MODEL_GUARDRAILS_JAILBREAK_MODEL"]["value"] == "nvidia/nvidia-nemotron-nano-9b-v2"
        assert environment["MODEL_GUARDRAILS_NVIDIA_API_KEY"]["valueFrom"]["secretKeyRef"] == {
            "name": "provider-keys",
            "key": "NVAPI_API_KEY",
        }
        assert "MODEL_GUARDRAILS_JAILBREAK_NIM_BASE_URL" not in environment
        assert "MODEL_GUARDRAILS_JAILBREAK_API_KEY" not in environment


def test_integration_endpoint_tracks_runner_service_namespace_and_port():
    documents = render(
        "--namespace", "guard-system",
        "--set", "runner.service.port=8091",
    )
    controller = next(
        item for item in documents
        if item.get("kind") == "Deployment"
        and item["metadata"]["labels"]["app.kubernetes.io/component"] == "controller"
    )
    controller_env = {
        item["name"]: item
        for item in controller["spec"]["template"]["spec"]["containers"][0]["env"]
    }

    assert controller_env["CONTROLLER_RUNTIME_SERVICE_URL"]["value"] == (
        "http://contract-tali-guard-runtime.guard-system.svc.cluster.local:8091"
    )


def test_guardrails_zero_cannot_drop_below_two_replicas():
    result = subprocess.run(
        ["helm", "template", "contract", str(CHART), *REQUIRED, "--set", "runner.default.replicaCount=1"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "GuardRails 0" in result.stderr or "minimum: got 1, want 2" in result.stderr


def test_controller_is_singleton_in_this_release():
    result = subprocess.run(
        ["helm", "template", "contract", str(CHART), *REQUIRED, "--set", "controller.replicaCount=2"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "controller.replicaCount" in result.stderr or "maximum: got 2, want 1" in result.stderr


def test_control_channel_mtls_secret_is_mandatory():
    required_without_tls = REQUIRED[:4] + REQUIRED[6:]
    result = subprocess.run(
        ["helm", "template", "contract", str(CHART), *required_without_tls],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "configure controlTls existingSecret" in result.stderr


def test_development_values_are_self_contained_and_keep_two_app_components():
    documents = render_dev()
    deployments = [item for item in documents if item.get("kind") == "Deployment"]
    deployments_by_name = {item["metadata"]["name"]: item for item in deployments}
    stateful_sets = [item for item in documents if item.get("kind") == "StatefulSet"]
    secrets = {item["metadata"]["name"]: item for item in documents if item.get("kind") == "Secret"}

    assert {item["metadata"]["name"] for item in deployments} == {
        "tali-guard-controller", "tali-guard-redis",
    }
    assert {item["metadata"]["name"] for item in stateful_sets} == {
        "tali-guard-postgresql", "tali-guard-runner",
    }
    controller_pod = deployments_by_name["tali-guard-controller"]["spec"]["template"]["spec"]
    runner_workload = next(item for item in stateful_sets if item["metadata"]["name"] == "tali-guard-runner")
    runner_pod = runner_workload["spec"]["template"]["spec"]
    assert runner_workload["spec"]["serviceName"] == "tali-guard-runner-headless"
    assert runner_workload["spec"]["replicas"] == 2
    assert runner_pod["containers"][0]["image"].endswith(":dev")
    assert controller_pod["containers"][0]["image"].endswith(":dev")
    controller_env = {item["name"]: item for item in controller_pod["containers"][0]["env"]}
    assert controller_env["CONTROLLER_RUNTIME_SERVICE_URL"]["value"] == (
        "http://tali-guard-runtime.tali.svc.cluster.local:8091"
    )
    assert controller_env["BETTER_AUTH_MIN_PASSWORD_LENGTH"]["value"] == "12"
    assert controller_env["CONTROLLER_ALLOW_LOCAL_DEFAULT_CREDENTIALS"]["value"] == "true"
    assert controller_pod["initContainers"][0]["name"] == "wait-for-postgresql"
    services = {item["metadata"]["name"]: item for item in documents if item.get("kind") == "Service"}
    controller_service = services["tali-guard-controller"]
    controller_public_service = services["tali-guard-controller-public"]
    runner_service = services["tali-guard-runtime"]
    runner_headless_service = services["tali-guard-runner-headless"]
    runner_public_service = services["tali-guard-runtime-public"]
    assert controller_service["spec"]["type"] == "ClusterIP"
    assert {item["port"] for item in controller_service["spec"]["ports"]} == {8080, 9090}
    assert controller_public_service["spec"]["type"] == "LoadBalancer"
    assert [item["port"] for item in controller_public_service["spec"]["ports"]] == [38081]
    assert runner_service["spec"]["type"] == "ClusterIP"
    assert runner_service["spec"]["sessionAffinity"] == "None"
    assert runner_service["spec"]["ports"][0]["port"] == 8091
    assert runner_headless_service["spec"]["clusterIP"] == "None"
    assert runner_headless_service["spec"]["publishNotReadyAddresses"] is True
    redis_service = services["tali-guard-redis"]
    assert redis_service["spec"]["type"] == "ClusterIP"
    assert redis_service["spec"]["ports"][0]["port"] == 6379
    runner_env = {item["name"]: item for item in runner_pod["containers"][0]["env"]}
    assert runner_env["GUARD_RUNNER_CALL_CONTEXT_REDIS_URL"]["value"] == "redis://tali-guard-redis:6379/0"
    assert runner_public_service["spec"]["type"] == "LoadBalancer"
    assert runner_public_service["spec"]["sessionAffinity"] == "None"
    assert runner_public_service["spec"]["ports"][0]["port"] == 38082
    assert "tali-guard-bootstrap-admin" in secrets
    assert secrets["tali-guard-bootstrap-admin"]["stringData"] == {
        "email": "admin@tasklattice.local",
        "password": "admin",
        "name": "Local Administrator",
    }
    assert "tali-guard-artifact-signing" in secrets
    assert set(secrets["tali-guard-control-tls"]["stringData"]) == {
        "ca.crt", "tls.crt", "tls.key", "runner.crt", "runner.key",
    }


def test_production_profile_does_not_install_development_postgresql():
    documents = render()

    stateful_sets = [item for item in documents if item.get("kind") == "StatefulSet"]
    assert [item["metadata"]["name"] for item in stateful_sets] == ["contract-tali-guard-runner"]
    assert all(not item["metadata"]["name"].endswith("postgresql") for item in stateful_sets)
    controller = next(item for item in documents if item.get("kind") == "Deployment" and item["metadata"]["name"].endswith("controller"))
    assert "initContainers" not in controller["spec"]["template"]["spec"]


def test_rollout_revision_updates_controller_and_every_runner_pool():
    documents = render(
        "--set", "rolloutRevision=dev-build-42",
        "--set", "runner.pools[0].name=gpu",
        "--set", "runner.pools[0].replicaCount=1",
        "--set", "runner.pools[0].maxConcurrency=128",
        "--set", "runner.pools[0].resources.requests.cpu=1",
        "--set", "runner.pools[0].resources.requests.memory=2Gi",
        "--set", "runner.pools[0].resources.limits.memory=8Gi",
    )
    workloads = [
        item for item in documents
        if item.get("kind") in {"Deployment", "StatefulSet"}
        and item["metadata"]["labels"].get("app.kubernetes.io/component") in {"controller", "runner"}
    ]

    assert len(workloads) == 3
    assert all(
        item["spec"]["template"]["metadata"]["annotations"]["tasklattice.io/rollout-revision"] == "dev-build-42"
        for item in workloads
    )


def test_extension_pool_is_an_additional_runner_not_a_new_component_type():
    documents = render(
        "--set", "runner.pools[0].name=gpu",
        "--set", "runner.pools[0].replicaCount=3",
        "--set", "runner.pools[0].maxConcurrency=128",
        "--set", "runner.pools[0].resources.requests.cpu=1",
        "--set", "runner.pools[0].resources.requests.memory=2Gi",
        "--set", "runner.pools[0].resources.limits.memory=8Gi",
        "--set", "runner.callContextRedisUrl=redis://redis:6379/0",
    )
    stateful_sets = [item for item in documents if item.get("kind") == "StatefulSet"]

    assert len(stateful_sets) == 2
    extension = next(item for item in stateful_sets if item["metadata"]["name"].endswith("runner-gpu"))
    assert extension["metadata"]["labels"]["app.kubernetes.io/component"] == "runner"
    assert extension["spec"]["replicas"] == 3
    assert extension["spec"]["serviceName"] == "contract-tali-guard-runner-gpu-headless"
    services = {item["metadata"]["name"]: item for item in documents if item.get("kind") == "Service"}
    assert "contract-tali-guard-runtime" in services
    assert "contract-tali-guard-runtime-gpu" in services
    assert "contract-tali-guard-runner-default" not in services
    assert "contract-tali-guard-runner-headless" in services
    assert "contract-tali-guard-runner-gpu-headless" in services
    assert services["contract-tali-guard-runtime"]["spec"]["sessionAffinity"] == "None"


def test_multiple_runner_replicas_require_shared_call_context():
    required_without_redis = REQUIRED[:-2]
    result = subprocess.run(
        ["helm", "template", "contract", str(CHART), *required_without_redis],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "shared Redis is required" in result.stderr
