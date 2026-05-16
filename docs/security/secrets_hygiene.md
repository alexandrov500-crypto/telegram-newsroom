# Secrets hygiene

Operational security for credentials in a production-lite single-node deployment.

## Secret sources

| Source | Examples | Trust |
|--------|----------|-------|
| Environment | `BOT_TOKEN`, `OPENAI_API_KEY`, `TELETHON_*`, `REDIS_URL` | Host `.env` only |
| Config load | `app.config.load_settings()` | In-memory process |
| Files | `.env`, Telethon session file | Filesystem permissions |
| CI | `.github/ci-minimal.env` | Placeholders only — never production |

## Secret exposure risks

| Surface | Risk | Mitigation |
|---------|------|------------|
| Git commits | Critical | `.gitignore`, review, no secrets in fixtures |
| Logs | High | `SECURITY_REDACTION=1`, truncate long fields |
| DLQ / worker traceback | High | Redaction when flag on |
| Evidence JSON | Medium | Inspection artifacts should not embed tokens; review exporters |
| Snapshots / backup zip | Medium | DB may contain content; not session strings by default |
| Ops HTTP | Medium | `OPS_HTTP_TOKEN` when `/ops` exposed |
| Retry payloads | Low | Job payloads should not include raw secrets |
| Diagnostics | Medium | `config_fingerprint` uses booleans not values |

## Safe storage guidance

- Permissions `600` on `.env` and session files
- Separate staging/production `.env`
- Rotate after personnel change ([runbooks/security/TOKEN_ROTATION.md](../runbooks/security/TOKEN_ROTATION.md))
- No secrets in `OUTPUT_DIR` or `ci-artifacts` uploads

## Logging redaction rules

When `SECURITY_REDACTION=1`:

- `utils/security_redaction.py` masks OpenAI keys, bot tokens, Bearer headers, Redis passwords
- `log_event` applies `redact_mapping` before JSON serialization
- Redaction is **one-way** — logs cannot be un-redacted

## Snapshot redaction expectations

- `runtime_snapshot.sh` copies inspection JSON — must not contain secrets (operators must not paste tokens into artifacts)
- `backup_cli` includes DB — treat zip as confidential
- Supplemental integrity reports contain checksums only

## Incident response guidance

1. Rotate affected tokens immediately
2. Enable `SECURITY_REDACTION=1` on new processes
3. Purge or restrict access to leaked log files
4. Follow [SUSPECTED_SECRET_LEAK.md](../runbooks/security/SUSPECTED_SECRET_LEAK.md)

## Related

- [trust_boundaries.md](trust_boundaries.md) · [SECURITY.md](../../SECURITY.md)
