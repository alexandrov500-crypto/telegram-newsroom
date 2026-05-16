# Quickstart (local)

Production-lite stack: one Python process (or split workers), SQLite by default, optional Redis. This guide is **deterministic** and avoids cloud-specific tooling.

## Prerequisites

- Python **3.12+** (see `Dockerfile` and `pyproject.toml`).
- Outbound HTTPS (OpenAI) and Telegram (Bot API + Telethon).

## 1. Clone and virtualenv

```bash
git clone <your-fork-or-mirror> newsroom
cd newsroom
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

## 2. Install

Either editable install (metadata only; runtime deps from `requirements.txt`):

```bash
pip install -r requirements.txt
pip install -e . --no-deps
```

Or `make install-dev` (same steps).

## 3. Minimal `.env`

```bash
cp .env.example .env
```

Fill **at least** (see comments in `.env.example`):

- `OPENAI_API_KEY`
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
- `TELETHON_SESSION_STRING` **or** `TELETHON_SESSION_PATH`
- `BOT_TOKEN`, `ADMIN_USER_ID`, `TARGET_CHANNEL_ID`, `SOURCE_CHANNELS`
- `DATABASE_URL` (default SQLite file path is fine for dev)

Never commit `.env`.

## 4. First run (paper mode recommended)

```bash
# In .env: DRY_RUN=true
python -m app.main
```

Optional directory bootstrap:

```bash
bash deploy/bootstrap.sh
python -m tools.admin_cli config-doctor --preview-missing
```

## 5. Quick runtime checks

```bash
python -m tools.admin_cli config-doctor
python -m tools.admin_cli runtime-integrity-check
make runtime-preflight RUNTIME_DIR=./var/runtime
```

## 6. Quick soak (bounded simulation)

Short bounded run (no long daemon soak here):

```bash
python tools/soak_runner.py --help
```

For a packaged nightly-style pass (preflight → benchmark → …), see `docs/RUNTIME_OPS.md` and `make runtime-nightly`.

## 7. Operational dashboard (static HTML)

From existing artifacts (paths are examples):

```bash
mkdir -p var/reports
make runtime-dashboard DASHBOARD_OUT=var/reports/operational_dashboard.html RUNTIME_BUNDLE=runtime_ops_output/runtime_bundle.zip
```

See `docs/OPERATIONAL_DASHBOARD.md` and `docs/OPERATIONS.md`.

## Next steps

- Deployment layout: `docs/DEPLOYMENT.md`
- Day-2 operations: `docs/OPERATIONS.md`
- Self-hosting context: `docs/SELF_HOSTING.md`
