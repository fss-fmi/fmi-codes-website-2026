#!/usr/bin/env bash

set -euo pipefail

ENV="${ENV:-staging}"
case "$ENV" in
  prod)    NAMESPACE="${NAMESPACE:-fmi-codes}"; FLUX_KUSTOMIZATION="${FLUX_KUSTOMIZATION:-fmi-codes}" ;;
  staging) NAMESPACE="${NAMESPACE:-fmi-codes-staging}"; FLUX_KUSTOMIZATION="${FLUX_KUSTOMIZATION:-fmi-codes-staging}" ;;
  *)       echo "Error: ENV must be 'prod' or 'staging', got '$ENV'." >&2; exit 1 ;;
esac
CONFIGMAP="${CONFIGMAP:-fmi-codes-backend-config}"
RESTART="${RESTART:-true}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_OVERLAY="${APP_OVERLAY:-$K8S_DIR/overlays/$ENV}"
# shellcheck source=lib/rollout.sh
. "$SCRIPT_DIR/lib/rollout.sh"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$1"; }
die() { echo "Error: $1" >&2; exit 1; }

SECRET_KEYS="SECRET_KEY JWT_SECRET_KEY ADMIN_PASSWORD_HASH MAIL_PASSWORD DISCORD_BUG_WEBHOOK_URL SLACK_BUG_WEBHOOK_URL SLACK_MIGRATIONS_WEBHOOK_URL SLACK_EVENTS_WEBHOOK_URL DB_PASSWORD REDIS_PASSWORD"

usage() {
  cat <<EOF
Usage: $(basename "$0") [KEY VALUE]

Apply a non-secret backend config change and roll the backend so pods pick it up.

When Flux owns the app (its Kustomization '$FLUX_KUSTOMIZATION' exists), git is
the source of truth and Flux reverts any live change within 5 minutes:

  No arguments   : apply git main now (flux reconcile --with-source), then
                   restart the backend. Run it after the config change merges.
  With KEY VALUE : refused, with the file to edit instead. Allowed only while
                   the Kustomization is suspended, for a change that must hold
                   before the merge; resume it once the change is merged.

Without Flux:

  No arguments   : re-apply the overlay for ENV ($ENV) from disk and restart
                   the backend.
  With KEY VALUE : patch that one key in the '$CONFIGMAP' ConfigMap, then
                   restart the backend. Commit the same change to git.

Only non-secret keys are allowed. Secrets do NOT belong here. To rotate
SECRET_KEY / JWT_SECRET_KEY / ADMIN_PASSWORD_HASH / MAIL_PASSWORD /
DISCORD_BUG_WEBHOOK_URL / SLACK_BUG_WEBHOOK_URL / SLACK_MIGRATIONS_WEBHOOK_URL /
SLACK_EVENTS_WEBHOOK_URL use:
    bash $SCRIPT_DIR/rotate-secret.sh <KEY>      (prompts; --generate for a random one)
DB / Redis passwords are PVC-coupled: rotate them with rotate-datastore-password.sh.

Env overrides: ENV (prod|staging — selects the overlay and namespace),
NAMESPACE ($NAMESPACE), CONFIGMAP ($CONFIGMAP),
FLUX_KUSTOMIZATION ($FLUX_KUSTOMIZATION),
RESTART (true|false — skip the rollout restart when false).

Examples:
  $(basename "$0")                       # apply git (Flux) or disk, then restart
  $(basename "$0") REQUIRE_EMAIL_VERIFICATION true
EOF
}

case "${1:-}" in -h|--help) usage; exit 0 ;; esac

command -v kubectl >/dev/null 2>&1 || die "kubectl not found — run install-tools.sh first."
kubectl cluster-info >/dev/null 2>&1 \
  || die "no reachable cluster — bootstrap it with bootstrap-k3s.sh first."
kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 \
  || die "namespace '$NAMESPACE' not found — run deploy-stateful.sh first."

restart_backend() {
  if [ "$RESTART" = "true" ]; then
    log "Restarting backend so pods pick up the change"
    rollout_restart "$NAMESPACE" deployment/backend 120
  else
    echo "RESTART=false — skipping rollout restart. Restart manually to apply:"
    rollout_restart_hint "$NAMESPACE" deployment/backend
  fi
}

STAGING_PATCH_REL="infra/k8s/overlays/staging/backend-config-patch.yaml"

# Prod has no config overlay: its values are the base, which staging inherits for every key its
# own patch doesn't set. So a staging-only change goes in that patch, and a base change can
# reach staging too.
config_source() {
  if [ "$ENV" = "staging" ]; then echo "$STAGING_PATCH_REL"; else echo "infra/k8s/base/app/backend.yaml"; fi
}

# $1 key. Printed after the file to edit.
config_note() {
  local key_re
  key_re="$(printf '%s' "$1" | sed 's/\./\\./g')"
  if [ "$ENV" = "prod" ] && ! grep -qE "^[[:space:]]+$key_re:" "$K8S_DIR/overlays/staging/backend-config-patch.yaml"; then
    echo "Staging inherits the base value of $1.
To leave staging as it is, also set its current value in $STAGING_PATCH_REL."
  fi
}

FLUX=false
if flux_owns_app "$FLUX_KUSTOMIZATION"; then FLUX=true; fi

if [ $# -eq 0 ]; then
  if [ "$FLUX" = "true" ]; then
    if flux_app_suspended "$FLUX_KUSTOMIZATION"; then
      die "Flux Kustomization '$FLUX_KUSTOMIZATION' is suspended. Once the config change is merged, resume it (that applies git main, reverting any live patch), then run this again to restart:
  flux resume kustomization $FLUX_KUSTOMIZATION -n flux-system"
    fi
    command -v flux >/dev/null 2>&1 || die "flux not found — run install-tools.sh first."
    # Only a pod template change rolls new pods; a replica change alone doesn't.
    pod_template() { kubectl -n "$NAMESPACE" get deployment/backend -o jsonpath='{.spec.template}' 2>/dev/null || true; }
    before="$(pod_template)"
    log "Flux owns the app: applying git main (not the files on disk)"
    flux reconcile kustomization "$FLUX_KUSTOMIZATION" -n flux-system --with-source
    if [ -n "$before" ] && [ "$(pod_template)" != "$before" ]; then
      log "main also changed the backend's pod template, so Flux is rolling it; the new pods read the new config"
      kubectl -n "$NAMESPACE" rollout status deployment/backend --timeout=120s
    else
      restart_backend
    fi
    log "Done. The cluster runs the config on main."
    exit 0
  fi
  [ -f "$APP_OVERLAY/kustomization.yaml" ] || die "missing $APP_OVERLAY/kustomization.yaml"
  log "Re-applying manifests from disk (overlay: $ENV)"
  kubectl apply -k "$APP_OVERLAY"
  restart_backend
  log "Done. The manifests on disk are now applied to the cluster."
  exit 0
fi

[ $# -eq 2 ] || { usage; exit 1; }
KEY="$1"
VALUE="$2"

case "$KEY" in
  *[!A-Za-z0-9._-]*|"") die "invalid ConfigMap key '$KEY' — allowed characters are letters, digits, '.', '_', '-'." ;;
esac

for s in $SECRET_KEYS; do
  if [ "$KEY" = "$s" ]; then
    die "'$KEY' is a secret — it does not belong in the ConfigMap. Use rotate-secret.sh (app secrets) or rotate-datastore-password.sh (DB/Redis)."
  fi
done
case "$KEY" in
  REGISTRATION_OPEN|RANKINGS_LIVE|MENTORS_STAY_TUNED)
    die "'$KEY' is no longer read from config: switch it in Mission Control (SITE tab). See docs/deployment.md." ;;
esac
# The staging backend reads it from the app secret, which overrides the ConfigMap.
if [ "$ENV" = "staging" ] && [ "$KEY" = "FRONTEND_ORIGIN" ]; then
  die "staging's FRONTEND_ORIGIN lives in its SOPS app secret; a ConfigMap value would be ignored. Use: ENV=staging bash $SCRIPT_DIR/rotate-secret.sh FRONTEND_ORIGIN"
fi

SOURCE="$(config_source "$KEY")"
NOTE="$(config_note "$KEY")"
[ -z "$NOTE" ] || NOTE=$'\n'"$NOTE"
if [ "$FLUX" = "true" ] && ! flux_app_suspended "$FLUX_KUSTOMIZATION"; then
  die "Flux owns the app in '$NAMESPACE', so a live patch would revert to git within 5 minutes.
Set $KEY in $SOURCE.$NOTE
Merge it to main, then apply it with:
  ENV=$ENV bash $SCRIPT_DIR/apply-config.sh
If the change must hold before the merge, suspend Flux for this env first (that also pauses
its image deploys), run this again, and resume once the change is merged:
  flux suspend kustomization $FLUX_KUSTOMIZATION -n flux-system"
fi

command -v python3 >/dev/null 2>&1 || die "python3 not found — needed to safely JSON-encode the value."
VALUE_JSON="$(VALUE="$VALUE" python3 -c 'import json,os;print(json.dumps(os.environ["VALUE"]))')"

log "Patching $CONFIGMAP: $KEY"
kubectl -n "$NAMESPACE" patch configmap "$CONFIGMAP" \
  --type merge -p "{\"data\":{\"$KEY\":$VALUE_JSON}}"

restart_backend

if [ "$FLUX" = "true" ]; then
  log "Done. The patch holds while Flux Kustomization '$FLUX_KUSTOMIZATION' stays suspended."
  echo "Set $KEY in $SOURCE and merge it to main, then resume Flux.${NOTE}"
  echo "Resuming applies main: before the merge it puts the old value back in the ConfigMap"
  echo "and the backend's next restart, whatever causes it, picks that up."
  echo "  flux resume kustomization $FLUX_KUSTOMIZATION -n flux-system"
else
  log "Done. Live ConfigMap updated. Set $KEY in $SOURCE too and commit it, so a"
  echo "re-apply from disk won't revert this.${NOTE}"
fi
