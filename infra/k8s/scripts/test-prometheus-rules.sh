#!/usr/bin/env bash
# Runs promtool's rule unit tests against the `fmi-codes` rules in the kps HelmRelease.
# The rules live inside Helm values, so they are extracted to a plain rules file first.
# Needs Docker; CI runs this same script.
set -euo pipefail

YQ_IMAGE="mikefarah/yq:4.45.1"
PROMETHEUS_IMAGE="prom/prometheus:v3.5.0"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
obs_dir="infra/k8s/base/observability"
work="$(mktemp -d "$repo_root/.promtool-XXXXXX")"
trap 'rm -rf "$work"' EXIT

# Git Bash would rewrite the container paths below into Windows paths.
export MSYS_NO_PATHCONV=1
host_root="$repo_root"
if pwd -W >/dev/null 2>&1; then
  host_root="$(cd "$repo_root" && pwd -W)"
fi
work_rel="${work#"$repo_root"/}"

docker run --rm -v "$host_root:/repo" -w /repo "$YQ_IMAGE" \
  'select(.kind == "HelmRelease") | .spec.values.additionalPrometheusRulesMap."fmi-codes"' \
  "$obs_dir/helmrelease.yaml" > "$work/rules.yaml"

grep -q 'alert:' "$work/rules.yaml" || {
  echo "no fmi-codes rules found in $obs_dir/helmrelease.yaml" >&2
  exit 1
}

tests=()
for f in "$repo_root/$obs_dir/tests/"*.test.yaml; do
  cp "$f" "$work/"
  tests+=("$(basename "$f")")
done

docker run --rm -v "$host_root:/repo" -w "/repo/$work_rel" --entrypoint promtool "$PROMETHEUS_IMAGE" \
  test rules "${tests[@]}"
