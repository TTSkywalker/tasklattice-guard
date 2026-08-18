#!/usr/bin/env bash
set -euo pipefail

required_commands=(cp helm sed)
for command_name in "${required_commands[@]}"; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is not installed: $command_name" >&2
    exit 1
  fi
done

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="${1:-0.0.0-dev}"
image_repository="${TALI_GUARD_IMAGE_REPOSITORY:-ghcr.io/tasklattice/tali-guard}"
chart_root="$repository_root/charts/tali-guard"
output_root="$repository_root/dist/runtime-chart"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/tali-guard-chart.XXXXXX")"

cleanup() {
  rm -rf "$work_dir"
}
trap cleanup EXIT

cp -R "$chart_root" "$work_dir/tali-guard"
sed -i.bak \
  "s|repository: ghcr.io/tasklattice/tali-guard|repository: ${image_repository}|" \
  "$work_dir/tali-guard/values.yaml"
rm -f "$work_dir/tali-guard/values.yaml.bak"

mkdir -p "$output_root"
helm lint "$work_dir/tali-guard" --strict
helm package "$work_dir/tali-guard" \
  --version "$version" \
  --app-version "$version" \
  --destination "$work_dir/packaged" >/dev/null
cp "$work_dir/packaged/tali-guard-${version}.tgz" \
  "$output_root/tali-guard.tgz"

echo "Packaged TALI Guard Helm chart at $output_root/tali-guard.tgz"
