# RFC-009: CI runtime matrix

**Status:** Draft · **Target:** v1.1 CI only

## Problem

`make ci-test` runs contracts + smoke on one Python version; Postgres and Redis paths are partially tested off-matrix.

## Proposal

GitHub Actions matrix (additive workflow, does not replace `tests.yml`):

| Dimension | Values |
|-----------|--------|
| Python | 3.12, 3.13 |
| Redis | off, on (service container) |
| Database | sqlite, postgres (optional job) |

- Nightly workflow keeps short soak; matrix runs on `workflow_dispatch` or weekly.
- No new mandatory dependencies in `requirements.txt`.

## Acceptance

- Default PR gate unchanged: `make ci-test` + `make release-check`
