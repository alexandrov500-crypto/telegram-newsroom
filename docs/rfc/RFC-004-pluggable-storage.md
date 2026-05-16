# RFC-004: Pluggable storage

**Status:** Draft · **Target:** v1.2+ opt-in

## Problem

SQLite file + local JSON (`editorial/intelligence_store.py`) assume single-node disk.

## Proposal

- `STORAGE_PROFILE=local|postgres` for SQLAlchemy URL (postgres already partially supported).
- Optional `INTELLIGENCE_BACKEND=file|redis` for editorial memory (default `file`).
- Repository layer keeps async session API; drivers selected at `load_settings()`.

## Non-goals

- S3 object store for media in v1.1
- Changing draft schema without migration ADR

## Migration risk

High for intelligence backend move — requires export/import tool.
