#!/usr/bin/env bash
set -euo pipefail

PLUGIN_DIR="${HERMES_PLUGIN_DIR:-$HOME/.hermes/plugins/dreamcycle}"
mkdir -p "$PLUGIN_DIR"

cat > "$PLUGIN_DIR/__init__.py" <<'PY'
"""DreamCycle Hermes plugin shim.

This shim delegates to the installed dreamcycle package. Configure
DREAMCYCLE_BASE_URL and DREAMCYCLE_API_KEY in the Hermes environment.
"""

from dreamcycle.hermes.plugin import rollback, status

__all__ = ["rollback", "status"]
PY

echo "Installed DreamCycle Hermes plugin shim at $PLUGIN_DIR"
echo "Use status() for read-only adapter state and rollback(confirm=True) only after operator approval."
