#!/usr/bin/env bash
# Append missing staging keys from deploy/staging/env.staging.example into .env (never overwrites existing keys).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXAMPLE="$ROOT/deploy/staging/env.staging.example"
ENV="$ROOT/.env"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "Missing $EXAMPLE"
  exit 1
fi

touch "$ENV"
added=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ -z "${line// }" ]] && continue
  key="${line%%=*}"
  key="${key//[[:space:]]/}"
  [[ -z "$key" ]] && continue
  if ! grep -q "^${key}=" "$ENV" 2>/dev/null; then
    echo "$line" >>"$ENV"
    echo "  + $key"
    added=$((added + 1))
  fi
done <"$EXAMPLE"

echo "Done. Added $added key(s). Edit .env and set TELEGRAM_* secrets before starting."
