# RFC-008: Secrets management

**Status:** Draft · **Target:** v1.2 opt-in

## Problem

Secrets load from `.env` on disk ([SECURITY.md](../../SECURITY.md)); no hook for vault or cloud secret managers.

## Proposal

- `SECRETS_PROVIDER=env|file|exec` (default `env` — current `load_settings()`).
- Optional `SECRETS_EXEC_CMD` returning JSON key map (timeout-bounded).
- Never log secret values; redact in ops bundle export.

## Non-goals

- Bundling HashiCorp Vault client as required dependency

## Migration risk

Low — default path unchanged.
