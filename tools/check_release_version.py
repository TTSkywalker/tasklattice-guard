from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _match(path: str, pattern: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise ValueError(f"Could not find version metadata in {path}.")
    return match.group(1)


def versions() -> dict[str, str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        python_version = tomllib.load(handle)["project"]["version"]
    with (ROOT / "web/package.json").open(encoding="utf-8") as handle:
        web_version = json.load(handle)["version"]
    with (ROOT / "web/package-lock.json").open(encoding="utf-8") as handle:
        web_lock = json.load(handle)
    with (ROOT / "uv.lock").open("rb") as handle:
        packages = tomllib.load(handle)["package"]
    uv_version = next(
        item["version"]
        for item in packages
        if item["name"] == "tasklattice-model-guardrails"
    )
    return {
        "pyproject.toml": python_version,
        "uv.lock": uv_version,
        "web/package.json": web_version,
        "web/package-lock.json": web_lock["version"],
        "web/package-lock.json packages['']": web_lock["packages"][""]["version"],
        "charts/tasklattice-guard/Chart.yaml version": _match(
            "charts/tasklattice-guard/Chart.yaml", r"^version:\s*[\"']?([^\s\"']+)"
        ),
        "charts/tasklattice-guard/Chart.yaml appVersion": _match(
            "charts/tasklattice-guard/Chart.yaml", r"^appVersion:\s*[\"']?([^\s\"']+)"
        ),
        "app/main.py": _match("app/main.py", r"^\s*version=\"([^\"]+)\",$")
    }


def main(tag: str) -> int:
    match = SEMVER.fullmatch(tag)
    if match is None:
        print(f"Release tag {tag!r} must use the form vMAJOR.MINOR.PATCH.", file=sys.stderr)
        return 1
    expected = tag.removeprefix("v")
    mismatches = {
        source: version
        for source, version in versions().items()
        if version != expected
    }
    if mismatches:
        print(f"Release tag {tag} does not match repository version metadata:", file=sys.stderr)
        for source, version in mismatches.items():
            print(f"- {source}: {version}", file=sys.stderr)
        return 1
    print(f"Release metadata is consistent for {tag}.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: check_release_version.py vMAJOR.MINOR.PATCH", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
