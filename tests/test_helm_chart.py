from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "charts" / "tasklattice-guard"


def test_helm_chart_configures_schema_v6_and_public_runtime_url():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "contract-test",
            str(CHART),
            "--set",
            "runtime.publicBaseUrl=https://guard.example.com",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    documents = [item for item in yaml.safe_load_all(rendered) if item]
    deployment = next(
        item for item in documents if item.get("kind") == "Deployment"
    )
    service = next(item for item in documents if item.get("kind") == "Service")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert environment["MODEL_GUARDRAILS_DATABASE_PATH"]["value"].endswith(
        "/tasklattice-guard-policy-schema-v3.db"
    )
    assert environment["MODEL_GUARDRAILS_PUBLIC_RUNTIME_BASE_URL"]["value"] == (
        "https://guard.example.com"
    )
    assert deployment["metadata"]["name"] == "tali-guard"
    assert service["metadata"]["name"] == "tali-guard"
    assert service["spec"]["ports"] == [
        {
            "name": "http",
            "port": 38081,
            "targetPort": "http",
            "protocol": "TCP",
        }
    ]
    assert container["ports"] == [
        {"name": "http", "containerPort": 8091, "protocol": "TCP"}
    ]
    assert service["spec"]["selector"] == deployment["spec"]["selector"]["matchLabels"]
    workload_labels = {
        "app.kubernetes.io/name": "tali",
        "app.kubernetes.io/instance": "contract-test",
        "app.kubernetes.io/component": "guard",
    }
    assert deployment["spec"]["selector"]["matchLabels"] == workload_labels
    assert workload_labels.items() <= deployment["metadata"]["labels"].items()
    assert workload_labels.items() <= service["metadata"]["labels"].items()


def test_default_persistence_uses_the_tali_guard_claim():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "tasklattice-guard",
            str(CHART),
            "--namespace",
            "tali",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    documents = [item for item in yaml.safe_load_all(rendered) if item]
    deployment = next(
        item for item in documents if item.get("kind") == "Deployment"
    )
    persistent_volume_claim = next(
        item for item in documents if item.get("kind") == "PersistentVolumeClaim"
    )
    data_volume = next(
        item
        for item in deployment["spec"]["template"]["spec"]["volumes"]
        if item["name"] == "data"
    )

    assert deployment["metadata"]["name"] == "tali-guard"
    assert persistent_volume_claim["metadata"]["name"] == "tali-guard"
    assert persistent_volume_claim["metadata"]["annotations"] == {
        "helm.sh/resource-policy": "keep"
    }
    assert persistent_volume_claim["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert persistent_volume_claim["spec"]["resources"]["requests"]["storage"] == "1Gi"
    assert data_volume["persistentVolumeClaim"]["claimName"] == "tali-guard"


def test_external_database_secret_enables_rolling_multi_replica_deployment():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "postgres-test",
            str(CHART),
            "--set",
            "replicaCount=3",
            "--set",
            "database.existingSecret=tasklattice-guard-database",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    documents = [item for item in yaml.safe_load_all(rendered) if item]
    deployment = next(
        item for item in documents if item.get("kind") == "Deployment"
    )
    environment = {
        item["name"]: item
        for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    }

    assert deployment["spec"]["replicas"] == 3
    assert deployment["spec"]["strategy"]["type"] == "RollingUpdate"
    assert environment["MODEL_GUARDRAILS_DATABASE_URL"]["valueFrom"] == {
        "secretKeyRef": {
            "name": "tasklattice-guard-database",
            "key": "database-url",
        }
    }
    assert "MODEL_GUARDRAILS_DATABASE_PATH" not in environment
    assert all(item.get("kind") != "Job" for item in documents)


def test_sqlite_fallback_rejects_multiple_replicas():
    result = subprocess.run(
        [
            "helm",
            "template",
            "sqlite-test",
            str(CHART),
            "--set",
            "replicaCount=2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "database.url or database.existingSecret" in result.stderr


def test_helm_routes_runtime_checks_to_nvidia_guard_models_only():
    rendered = subprocess.run(
        [
            "helm",
            "template",
            "nvidia-runtime",
            str(CHART),
            "--set-string",
            "evaluators.nvidia.baseUrl=https://integrate.api.nvidia.com/v1",
            "--set-string",
            "evaluators.nvidia.contentSafetyModel=nvidia/content-safety",
            "--set-string",
            "evaluators.nvidia.topicControlModel=nvidia/topic-control",
            "--set-string",
            "evaluators.nvidia.existingSecret=nvidia-key",
            "--set-string",
            "evaluators.jailbreakDetection.nimBaseUrl=https://ai.api.nvidia.com",
            "--set-string",
            "evaluators.jailbreakDetection.serverEndpoint=/v1/security/nvidia/nemoguard-jailbreak-detect",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    documents = [item for item in yaml.safe_load_all(rendered) if item]
    deployment = next(
        item for item in documents if item.get("kind") == "Deployment"
    )
    environment = {
        item["name"]: item
        for item in deployment["spec"]["template"]["spec"]["containers"][0]["env"]
    }

    assert environment["MODEL_GUARDRAILS_CONTENT_SAFETY_MODEL"]["value"] == (
        "nvidia/content-safety"
    )
    assert environment["MODEL_GUARDRAILS_TOPIC_CONTROL_MODEL"]["value"] == (
        "nvidia/topic-control"
    )
    assert environment["MODEL_GUARDRAILS_JAILBREAK_NIM_SERVER_ENDPOINT"]["value"].endswith(
        "nemoguard-jailbreak-detect"
    )
    assert environment["MODEL_GUARDRAILS_NVIDIA_API_KEY"]["valueFrom"] == {
        "secretKeyRef": {"name": "nvidia-key", "key": "api-key"}
    }
