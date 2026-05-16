# SUSPECTED_SECRET_LEAK

## Detection

- Token in log file, issue ticket, or public paste
- Unexpected API usage on provider dashboard

## Containment

1. Rotate credentials immediately ([TOKEN_ROTATION.md](TOKEN_ROTATION.md))
2. Enable `SECURITY_REDACTION=1` everywhere
3. Stop log shipping to third parties

## Recovery

- Deploy new secrets; monitor provider usage

## Evidence preservation

- Secure copy of affected logs for forensics (encrypted storage)
- Do not attach raw logs to public tickets

## Rollback

N/A — assume compromise until rotated

## Escalation

- Legal/comms if customer data in logs

## Post-incident validation

- Grep archives for old token patterns (redacted search terms)
- [REDACTION_FAILURE.md](REDACTION_FAILURE.md) if logs still leak
