from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import asdict, replace
from typing import Any

import yaml

from runner.toolkit.compiler.nemo_compiler import NeMoConfigCompiler
from runner.toolkit.nemo.builtin_policies import prompt_catalog_yaml

from .generated import runner_control_pb2 as protocol
from .config import RunnerSettings
from .serialization import plan_from_dict


class DefaultRunnerCompiler:
    """The authoritative NeMo compiler hosted by the mandatory Default Runner."""

    def __init__(self, settings: RunnerSettings | None = None) -> None:
        models: list[dict[str, object]] = []
        if settings and settings.nvidia_base_url:
            for model_type, model in (
                ("content_safety", settings.content_safety_model),
                ("topic_control", settings.topic_control_model),
            ):
                if model:
                    models.append({
                        "type": model_type,
                        "engine": "nim",
                        "model": model,
                        "api_key_env_var": settings.nvidia_api_key_env_var,
                        "parameters": {"base_url": settings.nvidia_base_url},
                    })
        self._compiler = NeMoConfigCompiler(
            models=tuple(models),
            builtin_prompts_yaml=prompt_catalog_yaml(),
        )
        self._nemo_version = importlib.metadata.version("nemoguardrails")

    def compile(self, request: protocol.CompileRequest) -> protocol.Artifact:
        payload = json.loads(request.plan_json)
        payload.update({
            "guardrail_id": request.guardrail_id,
            "guardrail_version": request.guardrail_version,
            "compiler_version": "tasklattice-controller-plan-v1",
        })
        plan = plan_from_dict(payload)
        snapshot = self._compiler.compile(plan)
        if request.runtime_profile not in {"", "auto", snapshot.runtime_profile}:
            raise ValueError(
                f"Plan requires {snapshot.runtime_profile}; requested {request.runtime_profile}."
            )
        prompts = (yaml.safe_load(snapshot.prompts_yaml) or {}).get("prompts", [])
        action_bindings = [asdict(item) for item in snapshot.action_bindings]
        dependencies = [list(item) for item in snapshot.dependency_manifest]
        artifact_payload: dict[str, Any] = {
            "guardrailId": request.guardrail_id,
            "guardrailVersion": request.guardrail_version,
            "generation": request.generation,
            "compilerVersion": snapshot.compiler_version,
            "nemoVersion": self._nemo_version,
            "runtimeProfile": snapshot.runtime_profile,
            "plan": payload,
            "configYaml": snapshot.config_yaml,
            "colangContent": snapshot.colang_content,
            "prompts": prompts,
            "actionBindings": action_bindings,
            "dependencyManifest": dependencies,
        }
        checksum = hashlib.sha256(_stable_json(artifact_payload).encode()).hexdigest()
        return protocol.Artifact(
            guardrail_id=request.guardrail_id,
            guardrail_version=request.guardrail_version,
            generation=request.generation,
            compiler_version=snapshot.compiler_version,
            nemo_version=self._nemo_version,
            runtime_profile=snapshot.runtime_profile,
            plan_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            config_yaml=snapshot.config_yaml,
            colang_content=snapshot.colang_content,
            prompts_json=json.dumps(prompts, sort_keys=True, separators=(",", ":")),
            action_bindings_json=json.dumps(action_bindings, sort_keys=True, separators=(",", ":")),
            dependency_manifest_json=json.dumps(dependencies, sort_keys=True, separators=(",", ":")),
            checksum=checksum,
        )


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
