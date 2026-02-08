#!/usr/bin/env bash
set -euo pipefail

if ! command -v powershell.exe >/dev/null 2>&1; then
  echo "powershell.exe not found. This script must be run from WSL with Windows integration enabled." >&2
  exit 127
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/pc-crash-kit" "$@"
