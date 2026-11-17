# shellcheck shell=bash
# Sourced by the scripts that restart workloads or change the backend's config.

# On every apply Flux strips the fields owned by managers whose names start with "kubectl", so
# a plain `kubectl rollout restart` of a Flux-applied Deployment loses its restartedAt
# annotation and rolls a second time (#187). Fields owned by any other name survive.
ROLLOUT_FIELD_MANAGER="fmi-codes-scripts"

# $1 namespace, $2 workload (e.g. deployment/backend), $3 timeout in seconds
rollout_restart() {
  kubectl -n "$1" rollout restart "$2" --field-manager="$ROLLOUT_FIELD_MANAGER"
  kubectl -n "$1" rollout status "$2" --timeout="${3}s"
}

# $1 namespace, $2 workload
rollout_restart_hint() {
  echo "  kubectl -n $1 rollout restart $2 --field-manager=$ROLLOUT_FIELD_MANAGER"
}

# $1 Flux Kustomization name. True when Flux applies that env's app from git.
flux_owns_app() {
  kubectl -n flux-system get kustomizations.kustomize.toolkit.fluxcd.io "$1" >/dev/null 2>&1
}

flux_app_suspended() {
  [ "$(kubectl -n flux-system get kustomizations.kustomize.toolkit.fluxcd.io "$1" \
    -o jsonpath='{.spec.suspend}' 2>/dev/null)" = "true" ]
}
