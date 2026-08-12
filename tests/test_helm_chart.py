from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
CHART = ROOT / "charts" / "tasklattice-guard"


def test_helm_chart_configures_schema_v5_and_public_runtime_url():
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
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    environment = {item["name"]: item for item in container["env"]}

    assert environment["MODEL_GUARDRAILS_DATABASE_PATH"]["value"].endswith(
        "/tasklattice-guard-schema-v5.db"
    )
    assert environment["MODEL_GUARDRAILS_PUBLIC_RUNTIME_BASE_URL"]["value"] == (
        "https://guard.example.com"
    )
