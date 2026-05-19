# GitHub deployment setup — Telegram AI newsroom

**VPS:** `213.171.3.133` · Ubuntu 24.04 · Timeweb  
**Deploy path:** `/opt/newsroom`  
**Repository:** `https://github.com/alexandrov500-crypto/telegram-newsroom`

---

## Production files verification (items 5–8)

| Check | Status | Detail |
|-------|--------|--------|
| Compose build `context` | OK | `../..` → repo root `/opt/newsroom` |
| Compose `dockerfile` | OK | `deploy/timeweb/Dockerfile` (relative to context) |
| Bind mounts | OK | `/opt/newsroom/data`, `logs`, `sessions` → `/data`, `/data/logs`, `/data/sessions` |
| Health (compose) | OK | `http_ready_probe.py` → `GET /ready` on port 8080 |
| Health (image) | OK | `docker/healthcheck.py` (DB + env) |
| Graceful shutdown | OK | `STOPSIGNAL SIGTERM`, `tini`, `stop_grace_period: 45s`, `app.main` → `lifecycle.graceful_shutdown` |
| Secrets in git | OK | `.env` in `.gitignore` |

Run locally before push:

```bash
cd "/path/to/telegram newsroom"
bash deploy/timeweb/scripts/verify-production-files.sh
```

---

## Part A — Mac: Git + GitHub push (новичок)

### A1. Один раз: GitHub CLI или сайт

Создайте репозиторий (если ещё нет):  
`https://github.com/alexandrov500-crypto/telegram-newsroom`

### A2. В каталоге проекта на Mac

```bash
cd "/Users/markusgronholm/telegram newsroom"
```

**Если git уже инициализирован** (у вас есть `origin`):

```bash
git status
git remote -v
```

**Если git ещё НЕ инициализирован:**

```bash
git init
git branch -M main
git remote add origin git@github.com:alexandrov500-crypto/telegram-newsroom.git
```

### A3. Проверить, что секреты не попадут в commit

```bash
git check-ignore -v deploy/timeweb/.env .env
# должны показать правила из .gitignore

ls deploy/timeweb/.env 2>/dev/null && echo "WARN: .env exists — не добавляйте в git"
```

### A4. Добавить файлы и push

```bash
git add .gitignore .dockerignore deploy/timeweb/ .github/workflows/deploy-timeweb-vps.yml
git add docker/http_ready_probe.py .env.example
# или всё проект (без .env):
git add -A
git status
# убедитесь: НЕТ .env, *.db, *.session в staged

git commit -m "Add Timeweb production deploy pack and GitHub Actions workflow"
git push -u origin main
```

Если ветка называется иначе (например `v3-live-telegram-validation`):

```bash
git push -u origin HEAD
```

### A5. SSH ключ для GitHub (если `Permission denied`)

```bash
ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Вставьте ключ: GitHub → **Settings → SSH and GPG keys → New SSH key**.

```bash
ssh -T git@github.com
```

---

## Part B — GitHub Actions secrets

GitHub → репозиторий → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Exact value |
|--------|-------------|
| `VPS_HOST` | `213.171.3.133` |
| `VPS_USER` | `newsroom` |
| `VPS_SSH_KEY` | содержимое `~/.ssh/id_ed25519` **с сервера или deploy-ключа** (private key, целиком) |
| `VPS_APP_DIR` | `/opt/newsroom` |

**Deploy key на VPS** (под пользователем `newsroom`):

```bash
ssh newsroom@213.171.3.133
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C "newsroom-deploy-read"
cat ~/.ssh/id_ed25519.pub
```

GitHub → Repo → **Settings → Deploy keys → Add** (read-only достаточно для pull).

**Ключ для Actions → VPS** (отдельный ключ, public на VPS):

На Mac:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/newsroom-vps-deploy -C "github-actions"
cat ~/.ssh/newsroom-vps-deploy.pub
```

На VPS (`root` или `newsroom`):

```bash
mkdir -p /home/newsroom/.ssh
echo "PASTE_PUBLIC_KEY_LINE" >> /home/newsroom/.ssh/authorized_keys
chmod 700 /home/newsroom/.ssh
chmod 600 /home/newsroom/.ssh/authorized_keys
chown -R newsroom:newsroom /home/newsroom/.ssh
```

Private key `~/.ssh/newsroom-vps-deploy` → secret `VPS_SSH_KEY` в GitHub.

---

## Part C — VPS: first deploy (до Actions)

См. также [DEPLOY_WALKTHROUGH.md](./DEPLOY_WALKTHROUGH.md). Кратко:

```bash
ssh root@213.171.3.133
# bootstrap docker, user newsroom, ufw — см. walkthrough

mkdir -p /opt/newsroom/{data/runtime,data/backups,logs,sessions}
chown -R 1000:1000 /opt/newsroom/data /opt/newsroom/logs /opt/newsroom/sessions
chown newsroom:newsroom /opt/newsroom

su - newsroom
cd /opt/newsroom
git clone git@github.com:alexandrov500-crypto/telegram-newsroom.git .

cd deploy/timeweb
cp .env.example .env
chmod 600 .env
nano .env

docker compose -f docker-compose.yml up -d --build
docker ps
curl -sS http://127.0.0.1:8080/health
```

`.env` **только на сервере**, в git не коммитится.

---

## Part D — Deploy via GitHub Actions

1. Push код в `main` (Part A).
2. GitHub → **Actions** → **Deploy Timeweb VPS** → **Run workflow**.
3. Input `ref`: `main` (или ваш tag).
4. Дождаться зелёного job.

Workflow делает: `git pull` → backup SQLite → `docker compose build` → `up -d` → проверка health/ready.

---

## Part E — First deploy checklist

- [ ] `bash deploy/timeweb/scripts/verify-production-files.sh` на Mac
- [ ] `.env` не в `git status`
- [ ] Push на GitHub успешен
- [ ] VPS: `/opt/newsroom` cloned, `deploy/timeweb/.env` заполнен
- [ ] `chown 1000:1000` на data/logs/sessions
- [ ] `docker ps` → `healthy`
- [ ] `curl http://127.0.0.1:8080/ready` → `"ok": true`
- [ ] Бот `/start` отвечает
- [ ] `DRY_RUN=false` только когда готовы к публикации

---

## Part F — Troubleshooting

### Unhealthy container

```bash
ssh newsroom@213.171.3.133
docker ps -a
docker inspect --format='{{json .State.Health}}' telegram-newsroom | python3 -m json.tool
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml logs --tail=200 newsroom
curl -v http://127.0.0.1:8080/ready
```

Подождите **120s** после старта (`start_period`). Частая причина: неверный `.env` или приложение падает до bind :8080.

### Telegram auth

```bash
grep -E '^(BOT_TOKEN|TELEGRAM_API|TELETHON)' /opt/newsroom/deploy/timeweb/.env
ls -la /opt/newsroom/sessions/
```

Исправить `.env` →:

```bash
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml up -d --force-recreate
```

### SQLite locked

```bash
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml down
ls -la /opt/newsroom/data/newsroom.db*
# при остановленном контейнере, если зависло:
# rm -f /opt/newsroom/data/newsroom.db-wal /opt/newsroom/data/newsroom.db-shm
chown 1000:1000 /opt/newsroom/data/newsroom.db
docker compose -f docker-compose.yml up -d
```

Не запускайте два контейнера с одной БД.

### Permissions

```bash
sudo chown -R 1000:1000 /opt/newsroom/data /opt/newsroom/logs /opt/newsroom/sessions
chmod 700 /opt/newsroom/sessions
```

---

## Part G — Production update workflow

### Вариант 1: GitHub Actions (рекомендуется)

1. На Mac: изменения → commit → push `main`
2. Actions → Run workflow → `ref: main`

### Вариант 2: вручную на VPS

```bash
ssh newsroom@213.171.3.133
cd /opt/newsroom

cp /opt/newsroom/data/newsroom.db \
  /opt/newsroom/data/backups/newsroom.db.bak.$(date +%Y%m%d-%H%M%S)

git fetch origin
git pull origin main

cd deploy/timeweb
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d

docker ps
curl -sS http://127.0.0.1:8080/ready | python3 -m json.tool
docker compose -f docker-compose.yml logs --tail=50 newsroom
```

### Вариант 3: Makefile на VPS

```bash
cd /opt/newsroom/deploy/timeweb
make rebuild
make health
```

Downtime: ~30–60 с (graceful `stop_grace_period: 45s`).

---

## Quick reference

| Action | Command |
|--------|---------|
| Verify files | `bash deploy/timeweb/scripts/verify-production-files.sh` |
| Push | `git push origin main` |
| Manual deploy | `cd /opt/newsroom/deploy/timeweb && docker compose up -d --build` |
| Logs | `make -C /opt/newsroom/deploy/timeweb logs` |
| Rollback code | `git checkout <tag> && docker compose up -d --build` |
| Rollback DB | restore from `/opt/newsroom/data/backups/` |
