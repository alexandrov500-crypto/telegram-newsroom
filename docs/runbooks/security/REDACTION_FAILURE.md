# REDACTION_FAILURE

## Detection

- Plaintext tokens in logs with `SECURITY_REDACTION=1` set
- Missing mask patterns for new secret format

## Containment

- Stop log aggregation; rotate leaked secret

## Recovery

- Extend `utils/security_redaction.py` patterns (maintainer)
- Patch release; enable flag on all processes

## Evidence preservation

- Sample redacted vs unredacted line for bug report (truncate heavily)

## Rollback

- Disable broken release tag; redeploy previous

## Escalation

- Private security report per [SECURITY.md](../../../SECURITY.md)

## Post-incident validation

- `tests/test_security_redaction.py` extended
- Manual log sample review
