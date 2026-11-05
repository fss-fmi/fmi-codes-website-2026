#!/usr/bin/env bash
# Runs promtool's rule unit tests against the `fmi-codes` rules in the kps HelmRelease.
# The rules live inside Helm values, so they are extracted to a plain rules file first.
# Needs Docker; CI runs this same script.
set -euo pipefail

YQ_IMAGE="mikefarah/yq:4.45.1"
PROMETHEUS_IMAGE="prom/prometheus:v3.5.0"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
obs_dir="$repo_root/infra/k8s/base/observability"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# mktemp makes it 0700, and the prometheus image runs as `nobody`.
chmod 755 "$work"

# Git Bash would rewrite the container paths below into Windows paths, and Docker Desktop
# needs the Windows form of the host paths.
export MSYS_NO_PATHCONV=1
host_path() {
  if pwd -W >/dev/null 2>&1; then (cd "$1" && pwd -W); else echo "$1"; fi
}

docker run --rm -v "$(host_path "$obs_dir"):/obs:ro" "$YQ_IMAGE" \
  'select(.kind == "HelmRelease") | .spec.values.additionalPrometheusRulesMap."fmi-codes"' \
  /obs/helmrelease.yaml > "$work/rules.yaml"

grep -q 'alert:' "$work/rules.yaml" || {
  echo "no fmi-codes rules found in $obs_dir/helmrelease.yaml" >&2
  exit 1
}

tests=()
for f in "$obs_dir/tests/"*.test.yaml; do
  cp "$f" "$work/"
  tests+=("$(basename "$f")")
done

docker run --rm -v "$(host_path "$work"):/work:ro" -w /work --entrypoint promtool "$PROMETHEUS_IMAGE" \
  test rules "${tests[@]}"
