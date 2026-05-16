# Security policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |

Runtime governance and inspection contracts are frozen for 1.0.x (see [docs/STABILITY_GUARANTEES.md](docs/STABILITY_GUARANTEES.md)).

## Reporting

If you believe you found a security issue:

1. **Do not** open a public issue with exploit details.
2. Contact maintainers privately with: affected version, reproduction steps, impact assessment.
3. Allow reasonable time for a fix before disclosure.

## Operational scope

This project is **production-lite** single-node software. Reports should distinguish:

- **Application security** (credentials, injection, auth bypass) — in scope.
- **Missing platform features** (K8s policies, service mesh, centralized SIEM) — out of scope by design.

Secrets belong in `.env` on the host — never commit `BOT_TOKEN`, `OPENAI_API_KEY`, or session strings.

## Non-goals

- No in-repo vulnerability scanning platform or automated pen-test orchestration.
- No guarantee of multi-tenant isolation (single-writer SQLite model).
