# Exact VPS deployment walkthrough — Timeweb Cloud

**Server:** `213.171.3.133` · Ubuntu 24.04 · hostname `kvmnvm-449`  
**Layout:** `/opt/newsroom` + `deploy/timeweb/` (Dockerfile, compose, Makefile, `.env`)

Выполняйте команды **по порядку**, копируя блоки целиком. Замените только помеченные места: `YOUR_GITHUB_USER`, `YOUR_REPO`, секреты в `.env`.

---

## 0. Что понадобится заранее (на вашем Mac)

1. SSH-доступ к VPS (пароль root или ключ Timeweb).
2. Секреты:
   - `OPENAI_API_KEY`
   - `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` (https://my.telegram.org)
   - `BOT_TOKEN` (BotFather)
   - `ADMIN_USER_ID` (ваш Telegram user id)
   - `TARGET_CHANNEL_ID` (канал публикации, обычно `-100…`)
   - `SOURCE_CHANNELS` (источники через запятую)
3. **Telethon-сессия** (один из вариантов):
   - **Рекомендуется:** экспорт `TELETHON_SESSION_STRING` локально, вставить в `.env` на сервере; **или**
   - один раз залогиниться на сервере и сохранить файл в `/opt/newsroom/sessions/telethon.session`
4. URL репозитория GitHub (приватный → deploy key или PAT).

---

## 1. Первый вход по SSH

На **вашем Mac** в Terminal:

```bash
ssh root@213.171.3.133
```

При первом подключении ответьте `yes` на fingerprint.  
Дальнейшие команды — **на сервере**, если не указано иное.

Проверка ОС:

```bash
hostname
cat /etc/os-release | head -5
```

Ожидаете: `kvmnvm-449`, Ubuntu 24.04.

---

## 2. Bootstrap сервера (apt, Docker, git, ufw, fail2ban)

### 2.1 Обновление пакетов

```bash
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y
apt-get install -y ca-certificates curl git gnupg ufw fail2ban
```

### 2.2 Установка Docker (официальный репозиторий)

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker --version
docker compose version
```

### 2.3 Пользователь для приложения (не работать от root постоянно)

```bash
adduser --disabled-password --gecos "" newsroom
usermod -aG docker newsroom
```

### 2.4 UFW (файрвол)

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
# Порт 8080 НЕ открываем в интернет — health только на localhost
ufw --force enable
ufw status verbose
```

### 2.5 fail2ban

```bash
systemctl enable --now fail2ban
fail2ban-client status
```

### 2.6 SSH (рекомендуция после настройки ключа)

Когда на Mac настроен вход по ключу для `newsroom` или root:

```bash
cat >> /etc/ssh/sshd_config.d/99-newsroom-hardening.conf <<'EOF'
PermitRootLogin prohibit-password
PasswordAuthentication no
MaxAuthTries 3
EOF
systemctl reload sshd
```

> Не отключайте пароли, пока не проверили вход по ключу в **второй** сессии SSH.

---

## 3. Файловая структура на диске

```bash
mkdir -p /opt/newsroom
mkdir -p /opt/newsroom/data
mkdir -p /opt/newsroom/logs
mkdir -p /opt/newsroom/sessions
mkdir -p /opt/newsroom/data/runtime
mkdir -p /opt/newsroom/data/backups

# В контейнере процесс работает от uid 1000 (appuser)
chown -R 1000:1000 /opt/newsroom/data /opt/newsroom/logs /opt/newsroom/sessions
chmod 700 /opt/newsroom/sessions
```

Итоговая схема:

```text
/opt/newsroom/                      ← git clone (код проекта)
/opt/newsroom/deploy/timeweb/
  ├── .env                          ← секреты (chmod 600)
  ├── docker-compose.yml
  ├── Dockerfile
  ├── Makefile
  └── .env.example
/opt/newsroom/data/                 ← SQLite, runtime, backups (bind → /data)
/opt/newsroom/data/newsroom.db      ← появится после первого запуска
/opt/newsroom/data/runtime/
/opt/newsroom/data/backups/
/opt/newsroom/logs/                 ← bind → /data/logs
/opt/newsroom/sessions/             ← Telethon session file
```

---

## 4. Git clone

### 4.1 От root — подготовить каталог

```bash
chown newsroom:newsroom /opt/newsroom
```

### 4.2 Переключиться на пользователя newsroom

```bash
su - newsroom
cd /opt/newsroom
```

### 4.3 Клонировать репозиторий

**Публичный репозиторий:**

```bash
git clone https://github.com/YOUR_GITHUB_USER/YOUR_REPO.git .
```

**Приватный (SSH deploy key на GitHub):**

```bash
# один раз на сервере под newsroom:
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 -C "newsroom@kvmnvm-449"
cat ~/.ssh/id_ed25519.pub
# → добавьте ключ в GitHub: Repo → Settings → Deploy keys (read-only достаточно)

git clone git@github.com:YOUR_GITHUB_USER/YOUR_REPO.git .
```

Проверка:

```bash
ls -la /opt/newsroom/deploy/timeweb/
```

Должны быть: `Dockerfile`, `docker-compose.yml`, `Makefile`, `.env.example`.

---

## 5. Настройка `.env`

```bash
cd /opt/newsroom/deploy/timeweb
cp .env.example .env
chmod 600 .env
nano .env
```

В `nano`: заполните минимум:

| Переменная | Что вписать |
|------------|-------------|
| `OPENAI_API_KEY` | ключ OpenAI |
| `TELEGRAM_API_ID` | число с my.telegram.org |
| `TELEGRAM_API_HASH` | hash |
| `BOT_TOKEN` | токен бота |
| `ADMIN_USER_ID` | ваш Telegram ID |
| `TARGET_CHANNEL_ID` | ID канала публикации |
| `SOURCE_CHANNELS` | `@ch1,@ch2` |
| `DRY_RUN` | `false` для реальной публикации |
| `TELETHON_SESSION_STRING` | раскомментируйте, если используете string session |

Пути хоста (уже в `.env.example`, проверьте):

```bash
grep NEWSROOM_HOST /opt/newsroom/deploy/timeweb/.env
```

Ожидаете:

```text
NEWSROOM_HOST_DATA=/opt/newsroom/data
NEWSROOM_HOST_LOGS=/opt/newsroom/logs
NEWSROOM_HOST_SESSIONS=/opt/newsroom/sessions
```

Проверка прав на данные:

```bash
sudo chown -R 1000:1000 /opt/newsroom/data /opt/newsroom/logs /opt/newsroom/sessions
```

---

## 6. Деплой (build + up + logs)

Оставаясь в `/opt/newsroom/deploy/timeweb` под пользователем `newsroom`:

```bash
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml up -d --build
```

Или через Makefile:

```bash
make up
```

Проверка контейнеров:

```bash
docker ps
docker compose -f docker-compose.yml ps
```

Ожидаете контейнер `telegram-newsroom` со статусом `Up` (через 1–2 минуты — `healthy`).

Логи (Ctrl+C чтобы выйти):

```bash
docker compose -f docker-compose.yml logs -f --tail=200 newsroom
```

или:

```bash
make logs
```

---

## 7. Rollback (откат)

### 7.1 Быстрый откат — остановить сервис

```bash
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml down
```

Данные в `/opt/newsroom/data` **останутся**.

### 7.2 Откат кода на предыдущий коммит

```bash
cd /opt/newsroom
git log --oneline -5
git checkout <COMMIT_SHA_ИЛИ_TAG>
cd deploy/timeweb
docker compose -f docker-compose.yml up -d --build
```

Вернуться на main:

```bash
cd /opt/newsroom
git checkout main
git pull
cd deploy/timeweb
docker compose -f docker-compose.yml up -d --build
```

### 7.3 Откат базы (если делали backup)

```bash
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml down
cp /opt/newsroom/data/backups/newsroom.db.bak.YYYYMMDD /opt/newsroom/data/newsroom.db
chown 1000:1000 /opt/newsroom/data/newsroom.db
docker compose -f docker-compose.yml up -d
```

Создать backup вручную **до** обновления:

```bash
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml down
cp /opt/newsroom/data/newsroom.db /opt/newsroom/data/backups/newsroom.db.bak.$(date +%Y%m%d-%H%M%S)
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml up -d
```

---

## 8. Update workflow (git pull + rebuild, минимальный downtime)

Рекомендуемый порядок под `newsroom`:

```bash
cd /opt/newsroom
git fetch origin
git status
git pull origin main

# backup DB (10 секунд простоя не будет, если cp при работающем контейнере — лучше через docker cp)
docker cp telegram-newsroom:/data/newsroom.db /opt/newsroom/data/backups/newsroom.db.bak.$(date +%Y%m%d-%H%M%S) || true

cd deploy/timeweb
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
```

**Минимальный downtime:** `up -d` пересоздаёт контейнер с `stop_grace_period: 45s` — обычно 30–60 с пауза polling. Для zero-downtime нужен второй инстанс (вне scope production-lite).

Через Makefile:

```bash
cd /opt/newsroom/deploy/timeweb
make rebuild
```

---

## 9. Healthcheck verification

### 9.1 Docker health status

```bash
docker ps
docker inspect --format='{{.State.Health.Status}}' telegram-newsroom
```

Ожидаете: `healthy` (подождите до 2 мин после старта).

### 9.2 HTTP с хоста (только localhost)

```bash
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8080/ready | python3 -m json.tool
```

`/health` → `{"status":"ok",...}`  
`/ready` → JSON с `"ok": true`.

### 9.3 Скрипты health внутри контейнера

```bash
cd /opt/newsroom/deploy/timeweb
make health
```

или:

```bash
docker compose -f docker-compose.yml exec newsroom python /app/docker/healthcheck.py
docker compose -f docker-compose.yml exec newsroom python /app/docker/healthcheck.py --readiness
docker compose -f docker-compose.yml exec newsroom python /app/docker/http_ready_probe.py
echo $?
```

Последняя команда должна завершиться с кодом `0`.

---

## 10. Troubleshooting

### Container `unhealthy`

```bash
docker ps -a
docker inspect telegram-newsroom | grep -A 20 '"Health"'
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml logs --tail=300 newsroom
```

Частые причины:

- Неверный `.env` (пустой `BOT_TOKEN`, нет session).
- Старт < 120 с — подождите `start_period`.
- `HEALTH_HTTP_PORT` не 8080 или процесс упал до bind порта.

```bash
curl -v http://127.0.0.1:8080/ready
```

### Telegram auth issues

```bash
grep -E 'TELETHON|BOT_TOKEN|TELEGRAM_API' /opt/newsroom/deploy/timeweb/.env
ls -la /opt/newsroom/sessions/
```

- **String session:** `TELETHON_SESSION_STRING=...` в `.env`, закомментируйте конфликтующие пути.
- **File session:** файл `telethon.session` в `/opt/newsroom/sessions/`, владелец `1000:1000`.
- `BOT_TOKEN` без пробелов; бот добавлен админом в `TARGET_CHANNEL_ID`.

Перезапуск после правки `.env`:

```bash
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml up -d --force-recreate
```

### SQLite locked

```bash
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml down
ls -la /opt/newsroom/data/newsroom.db*
# удалите -wal/-shm только при остановленном контейнере, если зависли:
# rm -f /opt/newsroom/data/newsroom.db-wal /opt/newsroom/data/newsroom.db-shm
chown 1000:1000 /opt/newsroom/data/newsroom.db
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml up -d
```

Не запускайте второй контейнер с той же БД.

### Restart loops

```bash
docker events --filter container=telegram-newsroom &
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml logs --tail=500 newsroom
```

Ищите `startup_validation`, `ConfigurationError`, OpenAI 401, Telethon auth.

Временно снизить нагрузку в `.env`:

```text
PIPELINE_INTERVAL_MINUTES=30
DRY_RUN=true
```

### Permission issues

```bash
ls -lan /opt/newsroom/data /opt/newsroom/logs /opt/newsroom/sessions
# uid/gid должны быть 1000 для файлов, созданных контейнером
sudo chown -R 1000:1000 /opt/newsroom/data /opt/newsroom/logs /opt/newsroom/sessions
```

---

## 11. Production verification checklist

Выполните после деплоя (галочки):

- [ ] `docker ps` — контейнер `Up`, health `healthy`
- [ ] `curl http://127.0.0.1:8080/health` — OK
- [ ] `curl http://127.0.0.1:8080/ready` — `"ok": true`
- [ ] В логах нет повторяющихся traceback каждые 30 с
- [ ] В Telegram бот отвечает на `/start` (от `ADMIN_USER_ID`)
- [ ] В логах есть `startup.banner` / scheduler started (без fatal)
- [ ] Файл `/opt/newsroom/data/newsroom.db` существует и растёт
- [ ] `DRY_RUN=false` только если готовы к реальной публикации
- [ ] Через 1–2 цикла pipeline в логах есть collect/cluster activity
- [ ] В боте видны черновики / очередь (если настроено)
- [ ] Канал `TARGET_CHANNEL_ID` — бот админ с правом post

Команды одним блоком:

```bash
docker ps
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8080/ready | python3 -m json.tool
ls -lh /opt/newsroom/data/newsroom.db
docker compose -f /opt/newsroom/deploy/timeweb/docker-compose.yml logs --tail=80 newsroom | tail -40
```

---

## 12. First production publish checklist (newsroom)

Production-lite публикует **одобренные** черновики. Первый выход в эфир:

### Перед включением

- [ ] `.env`: `DRY_RUN=false`
- [ ] `TARGET_CHANNEL_ID` — правильный канал
- [ ] `SOURCE_CHANNELS` — живые источники
- [ ] `ADMIN_USER_ID` — ваш аккаунт
- [ ] `PUBLISH_CHANNEL_MIN_INTERVAL_SEC` — не слишком агрессивно (например `120`)
- [ ] Backup: `cp /opt/newsroom/data/newsroom.db /opt/newsroom/data/backups/pre-first-publish.db`

### Первый запуск

```bash
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml up -d --build
make logs
```

### В Telegram (от ADMIN)

1. Откройте бота → `/start` — должен ответить.
2. Дождитесь pipeline (смотрите логи `pipeline` / `collect`).
3. Когда появится черновик → **approve** (команда/кнопка вашего editorial flow).
4. Убедитесь, что пост появился в `TARGET_CHANNEL_ID`.
5. Проверьте интервал — не более burst-лимитов в логах `publish`.

### Первые 30–60 минут наблюдения

```bash
watch -n 30 'docker inspect --format={{.State.Health.Status}} telegram-newsroom; curl -s http://127.0.0.1:8080/ready | head -c 200'
```

- [ ] Нет restart loop
- [ ] Health остаётся `healthy`
- [ ] В канале появился минимум 1 пост (или осознанно ждёте approve)
- [ ] OpenAI ошибок 401/429 в логах нет (или единичные 429)

### Если постов нет, но pipeline работает

Чаще всего: черновики ждут **ручного approve**. Проверьте в боте очередь drafts. Временно для диагностики можно `DRY_RUN=true`, перезапуск, убедиться что collect идёт.

```bash
cd /opt/newsroom/deploy/timeweb
# nano .env → DRY_RUN=true
docker compose -f docker-compose.yml up -d --force-recreate
```

---

## Шпаргалка (ежедневные команды)

```bash
ssh newsroom@213.171.3.133
cd /opt/newsroom/deploy/timeweb
docker compose -f docker-compose.yml ps
make logs
make restart
make health
```

---

## GitHub Actions (опционально)

Секреты в репозитории: `VPS_HOST=213.171.3.133`, `VPS_USER=newsroom`, `VPS_SSH_KEY`, `VPS_APP_DIR=/opt/newsroom`.  
Workflow: `.github/workflows/deploy-timeweb-vps.yml` → Run workflow.

---

## Безопасность (кратко)

- Не коммитьте `.env`.
- Не открывайте порт 8080 в UFW.
- Работайте под `newsroom`, не root.
- `chmod 600` на `.env`.
- Регулярный backup `/opt/newsroom/data/newsroom.db`.
