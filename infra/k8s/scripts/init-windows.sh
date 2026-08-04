#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
echo "bootstrap.sh is now the single entry point for both Linux and WSL2." >&2
echo "Delegating to: $REPO_ROOT/bootstrap.sh" >&2
exec bash "$REPO_ROOT/bootstrap.sh" "$@"
