# Deployment quickstart (production-lite)

Single-node deployment ergonomics for operators. This is **not** a platform guide — no Kubernetes, Helm, or cloud abstractions.

**Related:** [START_HERE.md](START_HERE.md) · [DEPLOYMENT.md](DEPLOYMENT.md) (full reference) · [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) · [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)

## 15-minute production-lite deployment walkthrough

| Minute | Step |
|--------|------|
| 0–3 | Clone repo, Python 3.12 venv, `make install-dev` |
| 3–7 | Copy env template, fill Telegram + OpenAI placeholders |
| 7–9 | `bash deploy/bootstrap.sh`, start app (`python -m app.main` or Compose) |
| 9–12 | First nightly: `make runtime-nightly` |
| 12–15 | Inspect: `make runtime-index`, `make verify-runtime`, gate with [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) |

## Minimal installation

```bash
git clone <repo-url> telegram-newsroom
cd telegram-newsroom
python3.12 -m venv .venv
source .venv/bin/activate
make install-dev
bash deploy/bootstrap.sh
```

## Environment setup

1. **Local / venv:** copy root template:

```bash
cp .env.example .env
# Edit: OPENAI_API_KEY, TELEGRAM_*, BOT_TOKEN, SOURCE_CHANNELS
```

2. **Production-lite host / Docker:** copy deployment template:

```bash
cp deploy/example.env.production-lite .env
```

Key paths:

| Variable | Purpose |
|----------|---------|
| `RUNTIME_STATE_DIR` | Live process JSON (`var/runtime` or `/data/runtime`) |
| `NEWSROOM_BACKUP_DIR` | `backup_cli` output |
| `OUTPUT_DIR` (Makefile only) | Nightly ops artifacts (`./runtime_ops_output`) |

Never commit real secrets. Templates use safe placeholders only.

## Docker (optional)

```bash
cp deploy/example.env.production-lite .env
# fill secrets
docker compose -f deploy/docker-compose.production-lite.yml up --build -d
```

- **Single service** `newsroom` — no worker pools or observability stack.
- **Explicit volumes:** `newsroom_data`, `newsroom_runtime` (mounted at `/data` and `/data/runtime`).
- **Restart:** `unless-stopped`, deterministic container name `telegram-newsroom-production-lite`.

## systemd nightly timer (optional)

```bash
sudo cp deploy/systemd/newsroom-nightly.service /etc/systemd/system/
sudo cp deploy/systemd/newsroom-nightly.timer /etc/systemd/system/
# Edit paths (WorkingDirectory, User, OUTPUT_DIR) then:
sudo systemctl daemon-reload
sudo systemctl enable --now newsroom-nightly.timer
journalctl -u newsroom-nightly.service -n 100 --no-pager
```

## First nightly run

```bash
export OUTPUT_DIR=./runtime_ops_output
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR="$OUTPUT_DIR"
```

Artifacts appear under `$OUTPUT_DIR/runtime/` in fixed lifecycle order; `runtime_index.json` is written last.

## Runtime inspection

```bash
make runtime-help
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
make runtime-health OUTPUT_DIR="$OUTPUT_DIR"
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

See [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) and [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

## Recovery validation

```bash
make validate-recovery OUTPUT_DIR="$OUTPUT_DIR"
make replay-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

Walkthrough: [docs/examples/recovery_validation_example.md](examples/recovery_validation_example.md).

## Release checklist usage

Before tagging a release:

1. `make ci-test` (runtime + smoke + contracts).
2. Run inspection sequence from [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).
3. Follow [RELEASE_PROCESS.md](RELEASE_PROCESS.md) for tagging discipline.

## Backup recommendations

- **Before upgrades:** `python tools/backup_cli.py backup-create` (DB + `RUNTIME_STATE_DIR`).
- Store backup zip, git SHA, and `.env` version **outside** the repo.
- Validate: `python tools/backup_cli.py backup-validate <zip>`.
- Details: [BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md), [DEPLOYMENT.md](DEPLOYMENT.md).

## Sample artifacts

Sanitized JSON for demos and doc cross-checks: [examples/runtime_samples/](../examples/runtime_samples/).

## Non-goals

- No in-repo Kubernetes, Terraform, Ansible, or deployment orchestrator.
- No CI-driven production deploy automation — **release discipline is preferred over deployment automation.**
