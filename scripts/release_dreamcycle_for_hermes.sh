#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <VERSION>" >&2
  exit 2
fi

VERSION="$1"

python -m pytest
python -m ruff check .
python -m build
python -m twine check dist/*
python scripts/verify_distribution.py dist/*

echo "Hermes-ready DreamCycle release checks passed for $VERSION"
echo "Create and push the release tag only after reviewing the working tree."
