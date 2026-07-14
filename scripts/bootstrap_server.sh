#!/usr/bin/env bash
set -euo pipefail

# Legacy-compatible entry. It deliberately delegates to the shared Cloud Deploy installer.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/deploy/cloud/install.sh" "$@"
