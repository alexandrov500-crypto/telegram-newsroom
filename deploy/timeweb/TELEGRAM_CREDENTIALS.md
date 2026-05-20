# Telegram credentials (operator checklist)

## Уже есть в проекте (`.env`)

| Variable | Value |
|----------|--------|
| `BOT_TOKEN` | @newsroom_ai_bot (id 8883114886) |
| `OPENAI_API_KEY` | set in `.env` |
| `ADMIN_USER_ID` | `167395657` |
| `TARGET_CHANNEL_ID` | `-1003934479919` |

## Нет в репозитории — взять один раз

| Variable | Where |
|----------|--------|
| `TELEGRAM_API_ID` | https://my.telegram.org/apps → **api_id** (digits only) |
| `TELEGRAM_API_HASH` | same page → **api_hash** |
| `TELETHON_SESSION_STRING` | `python3 tools/export_telethon_session.py` after API_ID/HASH set |
| `SOURCE_CHANNELS` | real Telegram channels: `@name1,@name2` |

**Do not** use `8883114886` (bot id) as `TELEGRAM_API_ID` — that is a different number.

## Fill `.env` on Mac

```bash
nano "/Users/markusgronholm/telegram newsroom/.env"
```

Set only these two lines (your real values):

```text
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef0123456789abcdef012345678
```

## Export Telethon session

```bash
cd "/Users/markusgronholm/telegram newsroom"
source /tmp/tg-sess/bin/activate
set -a && source .env && set +a
python3 tools/export_telethon_session.py
```

Paste printed `TELETHON_SESSION_STRING=...` back into `.env`.
