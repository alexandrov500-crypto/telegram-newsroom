# Production Telegram Go-Live Execution

Executable runbook for **real public Telegram channel** launch. Assumes Docker Compose, Redis + Postgres, worker mesh, and BotFather bots already exist.

## Quick start

```bash
cp deploy/production/env.production.example .env.production
# Edit: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_OPERATOR_CHAT_ID, ADMIN_USER_IDS, secrets

chmod +x scripts/production_*.sh deploy/production/health-check-production.sh
bash scripts/production_activate.sh
```

---

## 1. Telegram channel activation

On **operator node** startup (`GO_LIVE_ENABLED=true`, `PRODUCTION_STRICT_STARTUP=true`):

| Check | Behavior |
|-------|----------|
| Bot `getMe` | Operator + publisher use same token |
| Channel binding | `TELEGRAM_CHANNEL_ID` or digest channel |
| Admin verification | `ADMIN_USER_IDS` resolved via `getChat` |
| Permissions | **Hard fail** if any missing: post, edit, delete, invite, manage |
| Discussion group | Detected via `linked_chat_id` when present |
| Publish probe | Send + delete test message on channel |
| Shadow validation | `SHADOW_PUBLISH_ONLY=true` required until ramp |
| Operator ping | Startup message to operator chat |
| Executive dashboard | Stage + rollout summary pushed |

**Fail-hard:** process exits with code 1 if `strict_startup_required` and activation fails.

Telegram commands:

- `/startup_check` — full activation report
- `/channel_status` — permission matrix
- `/production_ready` — GA + certification blockers

HTTP: `GET /go_live`

---

## 2. Real startup commands

### First-time production startup (exact order)

```bash
cd /path/to/newsroom
cp deploy/production/env.production.example .env.production
# fill secrets

# 1. Infra
docker compose -f deploy/production/docker-compose.production.yml \
  --env-file .env.production up -d postgres redis

# 2. Migrate
docker compose -f deploy/production/docker-compose.production.yml \
  --env-file .env.production run --rm migrate

# 3. Worker mesh
docker compose -f deploy/production/docker-compose.production.yml \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file .env.production up -d

# 4. Operator (publisher + commands)
docker compose -f deploy/production/docker-compose.production.yml \
  --env-file .env.production up -d operator ingest-eu signal

# 5. Verify
bash deploy/production/health-check-production.sh
```

Or one shot:

```bash
bash scripts/production_activate.sh
```

### Expected health output

```
=== Production health verification ===
  [PASS] liveness
  [PASS] readiness
  [PASS] startup
  [PASS] go_live
  [PASS] safety
  ...
```

`/go_live` sample:

```json
{
  "status": "ok",
  "activation": { "ready": true, "bot_username": "YourNewsBot" },
  "publication_stage": "INTERNAL_SHADOW",
  "rollout": "INTERNAL_SHADOW"
}
```

### Operator verification (Telegram)

```
/startup_check
/production_ready
/channel_status
/go_live_check
/safety_status
/queues_live
```

### Rollout activation

```bash
# Env promotion (then restart operator)
PRODUCTION_ROLLOUT_STAGE=LIMITED_CHANNELS
RELIABILITY_PUBLISH_MODE=SHADOW
SHADOW_PUBLISH_ONLY=true
docker compose -f deploy/production/docker-compose.production.yml \
  --env-file .env.production up -d --force-recreate operator
```

Telegram:

```
/first_publication_status
/advance_publication
/activate_next_stage
```

### Safe shutdown

```bash
bash scripts/production_shutdown.sh
# full teardown:
docker compose -f deploy/production/docker-compose.production.yml \
  -f deploy/live-ops/docker-compose.workers.yml \
  --env-file .env.production down
```

### Emergency rollback

```bash
bash scripts/production_rollback.sh "floodwait_storm"
```

Telegram: `/rollout_rollback` · `/activation_rollback`

---

## 3. Environment configuration

| File | Role |
|------|------|
| `deploy/production/env.production.example` | Operator + cluster (single file) |
| `deploy/staging/env.staging.example` | Shadow staging reference |

Key production defaults:

| Variable | Production-safe default |
|----------|-------------------------|
| `SHADOW_PUBLISH_ONLY` | `true` until FIRST_REAL_PUBLICATION |
| `PRODUCTION_ROLLOUT_STAGE` | `INTERNAL_SHADOW` |
| `RELIABILITY_PUBLISH_MODE` | `SHADOW` |
| `AUTO_APPROVAL_ENABLED` | `false` |
| `PRODUCTION_STRICT_STARTUP` | `true` |
| `RC1_LOCKDOWN_MODE` | `true` |
| `GA_MAX_PUBLISHES_PER_HOUR` | `40` |

---

## 4. Telegram operator setup

Configured via env:

- `ADMIN_USER_IDS` — allowlist (comma-separated)
- `GO_LIVE_EMERGENCY_CONTACTS` — fallback pager list (defaults to admins)
- `TELEGRAM_OPERATOR_CHAT_ID` — command surface

Startup automatically:

1. Verifies each admin ID
2. Pings operator chat when activation passes
3. Pushes executive dashboard (stage, rollout, shadow)
4. Validates ≥2 emergency contacts recommended

---

## 5. First publication flow

| Stage | Env rollout | Reliability mode | Operator focus |
|-------|-------------|------------------|----------------|
| `INTERNAL_SHADOW` | `INTERNAL_SHADOW` | `SHADOW` | `/go_live_check` |
| `SHADOW_TRAFFIC` | `INTERNAL_SHADOW` | `SHADOW` | `/go_live_certify` |
| `LIMITED_PUBLIC` | `LIMITED_CHANNELS` | `SHADOW` | `/activate_next_stage` |
| `FIRST_REAL_PUBLICATION` | `LOW_FREQUENCY_PUBLIC` | `LIMITED_PRODUCTION` | Manual approve first publish |
| `CONTROLLED_RAMP` | `LOW_FREQUENCY_PUBLIC` | `LIMITED_PRODUCTION` | `/ga_status` |
| `GENERAL_AVAILABILITY` | `NORMAL_PRODUCTION` | `FULL_PRODUCTION` | `/platform_health` |

Advance:

```
/first_publication_status
/advance_publication
```

Requirements: operator sign-off, certification, GA confidence ≥ 0.75, SLO OK.

**Safety confirmations before FIRST_REAL_PUBLICATION:**

1. `/production_ready` → YES
2. `/go_live_certify` → CERTIFIED
3. `SHADOW_PUBLISH_ONLY=false` only after sign-off
4. First publish via editorial approval card

**Rollback checkpoint:** each advance stored in `go_live_state` table.

---

## 6. Production health verification

### curl

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/go_live | jq .
curl -s http://127.0.0.1:8080/live_ops | jq .go_live
curl -s http://127.0.0.1:8080/reliability | jq .
curl -s http://127.0.0.1:8080/metrics | grep -E 'queue_|publish_|poison'
```

### Verify matrix

| Signal | Pass criteria | Escalation |
|--------|---------------|------------|
| Event bus | Redis PING, streams lag < threshold | Restart redis, check `EVENT_BUS_BACKEND` |
| Workers | `/live_ops` mesh healthy | `docker compose ... restart *-worker` |
| Telegram delivery | `/channel_status` all ✓ | Re-add bot as admin with full rights |
| OpenAI latency | p95 < budget in `/reliability` | Lower ingest rate, `RELIABILITY_PUBLISH_MODE=SHADOW` |
| Queues | `/queues_live` draining | Throttle ingest |
| Poison queue | metric flat 1h | `/rollout_rollback` |
| SLO | `/certification_status` | Pause advance |
| GA readiness | `/production_ready` | Hold ramp |

---

## 7. Safe rollback procedures

| Scenario | Immediate action | Verify |
|----------|------------------|--------|
| Telegram publish failure | `/rollout_rollback` + `bash scripts/production_rollback.sh` | `/channel_status` |
| FloodWait storm | `production_rollback.sh` + lower `GA_MAX_PUBLISHES_PER_HOUR` | publish metrics flat |
| OpenAI degradation | `RELIABILITY_PUBLISH_MODE=SHADOW` | `/reliability` |
| Worker crashes | restart worker compose services | `/live_ops` |
| Replay corruption | `LIVE_OPS_RECOVERY` + pause ingest | event lag metrics |
| Bad cognition | governance freeze `/governance_freeze` | hold queue |
| Quality collapse | `/rollout_rollback` | GA score recovery |
| Operator emergency | `/rollout_rollback` · `AUTO_APPROVAL_ENABLED=false` | shadow publishes only |

**Emergency sequence (60 seconds):**

```bash
bash scripts/production_rollback.sh "emergency"
# Telegram: /rollout_rollback
# Telegram: /activation_rollback
bash deploy/production/health-check-production.sh
```

---

## 8. Systemd / process management

- **Docker:** `restart: unless-stopped` on all production services
- **Systemd unit:** `deploy/systemd/newsroom-operator.service`
- **Health probe:** compose healthcheck → `/health`
- **Logs:** `LOG_JSON_FILE` + `deploy/production/logrotate-newsroom.conf`
- **Graceful stop:** `scripts/production_shutdown.sh` (SIGTERM via compose stop)

Install systemd:

```bash
sudo cp deploy/systemd/newsroom-operator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now newsroom-operator
```

---

## 9. Final go-live checklist

### Pre-launch

- [ ] `.env.production` filled (no placeholder tokens)
- [ ] Bot is **admin** on channel with post/edit/delete/invite/manage
- [ ] `curl /go_live` → `"ready": true`
- [ ] `/startup_check` → READY
- [ ] Workers healthy (`/live_ops`)
- [ ] `PRODUCTION_ROLLOUT_STAGE=INTERNAL_SHADOW`
- [ ] `SHADOW_PUBLISH_ONLY=true`
- [ ] `/go_live_certify` → CERTIFIED
- [ ] `/production_ready` reviewed

### Launch

```bash
bash scripts/production_activate.sh
bash deploy/production/health-check-production.sh
```

Telegram: `/startup_check` → `/production_ready` → `/first_publication_status`

### Post-launch

**First hour:** `/queues_live` every 15m · watch `publish_*` metrics · no poison growth

**First day:** `/platform_health` · `/ecosystem_risk` · compare shadow vs public counts

**Rollback triggers:**

- Publish failure rate > 5%
- Queue backlog > 2× threshold 30m
- GA confidence < 0.7
- Open fatal incident

---

## Related docs

- `docs/PRODUCTION_GO_LIVE_CHECKLIST.md`
- `docs/PRODUCTION_SAFETY_RUNBOOK.md`
- `docs/RC1_ACTIVATION.md`
- `docs/OPS_CERTIFICATION.md`
