# Production runbook (novice-friendly)

Project: `/Users/markusgronholm/telegram newsroom`  
VPS: `newsroom@213.171.3.133` · path `/opt/newsroom`

---

## Phase A — Mac: Telethon session

```bash
cd "/Users/markusgronholm/telegram newsroom"
source .venv/bin/activate
python gen_session.py --write-env
python gen_session.py --verify
python tools/validate_production_env.py
```

## Phase B — Mac: build VPS env

```bash
bash deploy/timeweb/scripts/build-vps-env.sh
scp deploy/timeweb/.env.vps newsroom@213.171.3.133:/opt/newsroom/deploy/timeweb/.env
```

## Phase C — VPS: deploy

```bash
ssh newsroom@213.171.3.133
cd /opt/newsroom && git pull origin v3-live-telegram-validation
bash deploy/timeweb/scripts/vps-full-deploy.sh
```

See main chat guide for troubleshooting.
