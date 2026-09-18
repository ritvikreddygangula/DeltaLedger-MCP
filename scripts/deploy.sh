#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Regenerating infra/requirements.txt (API-only deps; pipeline group excluded)..."
uv export --no-hashes --no-dev --no-group pipeline -o infra/requirements.txt

echo "Building (Makefile fetches manylinux wheels directly, so no Docker/--use-container is needed)..."
sam build -t infra/template.yaml

if [ -f samconfig.toml ]; then
  sam deploy
else
  echo "No samconfig.toml found yet -- running a guided first-time deploy."
  sam deploy --guided
fi
