# Restart readiness declaration

**Date:** 2026-05-16  
**Status:** Framework ready — **no active restart approved**

## Declarations

1. The repository **remains frozen by default** after `v3.2-archival-baseline`.
2. The **restart framework** (ADR-037) exists for **exceptional** evaluation only.
3. **No active restart** is approved as of this document.
4. **Stewardship** remains the canonical operational mode ([stewardship_state_declaration.md](stewardship_state_declaration.md)).
5. The **archival baseline** remains the authoritative state for v3.2 artifacts and governance.

## What operators should do

- Follow [stewardship_operations_calendar.md](../governance/stewardship_operations_calendar.md)
- Use `make archival-freeze-validate` on stewardship/tooling doc PRs only
- Escalate expansion ideas via [restart_evaluation_template.md](../governance/restart_evaluation_template.md) — expect default reject

## What engineers should not do

- Open `feature/v4-*` implementation branches without approved program
- Add validation Makefile targets without restart approval
- Treat ADR-037 as permission to code

## Sign-off

| Role | Acknowledged | Date |
|------|--------------|------|
| Engineering | ☑ framework only | 2026-05-16 |
| Governance | ☐ | |
| Operator | ☐ | |
