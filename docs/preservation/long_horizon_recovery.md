# Long-horizon recovery strategy

Scenarios for dormant or archival recovery — honest difficulty ratings.

## Scenario matrix

| Scenario | Difficulty | Survivability assumptions | Operator burden | Unsupported |
|----------|------------|---------------------------|-----------------|-------------|
| **Restore after 5 years** | High | Archive has repo tag + OUTPUT_DIR + DB file | Rebuild venv; read stewardship docs | Zero-effort plug-and-play |
| **Restore after dependency drift** | Medium–High | Old tag checkout or pin file preserved | `pip install -r requirements.txt` at tag | Auto-migrate deps silently |
| **Restore after Python EOL** | High | Uplift branch or container with old Python | Port + full CI | Run on EOL Python indefinitely |
| **Restore after API changes** | Medium | Tokens/sessions still valid | Update telethon/openai pins | Telegram/OpenAI unchanged |
| **Restore after maintainer gap** | Medium | Git + ADRs intact | START_HERE → traceability validate | Tribal memory only |
| **Restore from archival backup only** | Medium–High | Complete OUTPUT_DIR + sqlite + `.env` secrets | Quiesce restore; validate-recovery | Partial runtime/ tree |

## Restore after 5 years (recommended path)

1. Checkout known-good **git tag** (not random `main`).
2. Create venv with documented Python floor (see `pyproject.toml`).
3. `pip install -r requirements.txt` from that tag.
4. Restore SQLite file + `OUTPUT_DIR` archive.
5. `make traceability-validate` (modern checkout) or read [release_archaeology.md](../stewardship/release_archaeology.md) at tag.
6. `make validate-recovery` / `verify-runtime` on restored evidence.
7. Enable opt-in flags deliberately.

## Dependency drift recovery

- Prefer **tag-locked installs** over “latest main.”
- If pins fail to resolve: use `requirements.txt` from tag; do not guess versions.

## Python EOL recovery

- Run uplift on branch; fix tests; document in CHANGELOG.
- Not a preservation-phase code change — planning only here.

## API change recovery

- Telethon/aiogram: follow upstream migration guides.
- OpenAI: adjust model env vars and client calls.
- Semantics: [recovery_semantics.md](../semantics/recovery_semantics.md) — no channel undo.

## Maintainer gap recovery

- [ecosystem_continuity.md](../stewardship/ecosystem_continuity.md) — post-dormancy section.
- [adr_lineage_map.md](../stewardship/adr_lineage_map.md) — why decisions exist.

## Archival backup only

**Required bundle (minimum):**

- `newsroom.db` (or configured sqlite path) — quiesced copy
- Complete `OUTPUT_DIR/runtime/` required artifacts (12 files)
- `runtime_manifest.json` + optional bundle zip
- Redacted `.env.example` + operator secret store (out of repo)

**Unsupported:** Redis-only backup without SQLite; incomplete manifest marked PASS.

## Unsupported recovery areas

- Multi-region active-active restore
- Exactly-once job replay without operator review
- Automatic dependency resolution from empty lockfile
- Recovery without reading phase reports
