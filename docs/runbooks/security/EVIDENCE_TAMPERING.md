# EVIDENCE_TAMPERING

## Detection

- `verify-runtime` checksum_mismatches without explanation
- Supplemental integrity report mismatch

## Containment

- Do not use tampered tree for release decisions
- Copy suspect tree aside read-only

## Recovery

- Regenerate: `make runtime-nightly`
- Or restore snapshot from known-good

## Evidence preservation

- Keep tampered copy with timestamp for investigation

## Rollback

- `runtime_restore.sh` from last good snapshot

## Escalation

- If malicious host user suspected → [COMPROMISED_RUNTIME.md](COMPROMISED_RUNTIME.md)

## Post-incident validation

- `verify-runtime --strict` OK on new tree
