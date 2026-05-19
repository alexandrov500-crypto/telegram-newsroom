# Pilot Activation — Real Telegram Channel

Controlled public observation in **canary** mode.

## How to get channel IDs

### Helper script (recommended)

After the bot is added to your channels/groups and you have sent `/start` in private chat:

```bash
python3 scripts/list_telegram_channels.py --env-file .env
```

Probe one ID directly (no updates required):

```bash
python3 scripts/list_telegram_channels.py --env-file .env --chat-id -1001234567890
```

Example output:

```
Pilot News Channel (configured public / TELEGRAM_CHANNEL)
  ID:          -1001234567890
  Type:        channel
  Permissions: admin: post, edit, delete, invite, manage
  Source:      env LIVE_PUBLIC_CHANNEL_ID

Ops Alerts (configured ops / OPERATOR_CHAT)
  ID:          -1009876543210
  Type:        supergroup
  Permissions: admin: post, edit, delete
  Source:      getUpdates
```

Copy the IDs into `.env`:

```bash
LIVE_PUBLIC_CHANNEL_ID=-1001234567890
LIVE_OPS_CHANNEL_ID=-1009876543210
TELEGRAM_CHANNEL_ID=-1001234567890
TELEGRAM_OPERATOR_CHAT_ID=-1009876543210
```

If the list is empty: message the bot, add it to channel as admin, post once in the channel, then re-run the script.

### Public / shadow channels (manual)

1. Create a Telegram channel (or use existing test channel).
2. Add your bot as **Administrator** with:
   - Post messages
   - Edit messages of others
   - Delete messages of others
   - Add members (optional)
3. Forward any message from the channel to [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot), or use Telethon — ID looks like `-1001234567890`.
4. Set `LIVE_PUBLIC_CHANNEL_ID` and mirror to `TELEGRAM_CHANNEL_ID`.

### Ops channel

Use a private group or dedicated ops channel where:
- Only operators and the bot are members
- Bot can **send messages** (member is enough; admin not required)

Set `LIVE_OPS_CHANNEL_ID` and `TELEGRAM_OPERATOR_CHAT_ID`.

### Verify connectivity

```bash
python3 scripts/pilot_preflight.py --env-file .env.production --strict
python3 scripts/pilot_preflight.py --env-file .env.production --strict --send-test-message
```

`--send-test-message` sends to **shadow + ops only** — never to the public channel.

Expected output when ready:

```
[OK] BOT_TOKEN valid
[OK] Public channel accessible (post/edit/delete/media)
[OK] Ops channel accessible
...
PILOT STATUS: READY
```

On failure:

```
[FAIL] Public channel accessible (post/edit/delete/media)
      Reason: Missing permissions: post_messages
```

## Bot admin permissions (public channel)

| Permission | Required |
|------------|----------|
| Post messages | Yes (includes media) |
| Edit messages | Yes |
| Delete messages | Yes |

In Telegram: Channel → Manage → Administrators → your bot → enable rights.

## Configure `.env.production`

```bash
cp deploy/production/env.pilot.example .env.production
```

```bash
BOT_TOKEN=...
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
ADMIN_USER_IDS=your_telegram_user_id

LIVE_PUBLIC_CHANNEL_ID=-100...
LIVE_OPS_CHANNEL_ID=-100...
LIVE_SHADOW_CHANNEL_ID=-100...    # optional

TELEGRAM_CHANNEL_ID=$LIVE_PUBLIC_CHANNEL_ID
TELEGRAM_OPERATOR_CHAT_ID=$LIVE_OPS_CHANNEL_ID

CONTROLLED_LIVE_ENABLED=true
LIVE_MODE=canary
LIVE_CANARY_MAX_PER_HOUR=3
LIVE_SUPERVISED_APPROVAL=true
LIVE_FREEZE_ON_ANOMALY=true
LIVE_ENABLE_ROLLBACK=true
SHADOW_PUBLISH_ONLY=false
```

## STEP 1 — Ops group (recommended)

1. Create a **private Telegram group**
2. Add `@newsroom_ai_bot`
3. Post any message in the group
4. Run:

```bash
python3 scripts/list_telegram_channels.py --env-file .env
```

5. Update `.env`:

```bash
LIVE_OPS_CHANNEL_ID=-100...
TELEGRAM_OPERATOR_CHAT_ID=-100...
```

Until then, alerts go to your private chat (`167395657`) — OK for the first hour.

## Activate (steps 2–8)

```bash
# STEP 2 — strict preflight (must show PILOT STATUS: READY)
python3 scripts/pilot_preflight.py --env-file .env --strict --send-test-message

# Or guided launcher (preflight + optional activate)
bash scripts/pilot_launch.sh

# STEP 4 — operator node
bash scripts/pilot_activate.sh
# uses .env by default; falls back to .env.production if missing
```

After start, check ops chat for:

```
🟢 CONTROLLED PUBLIC PILOT ACTIVE
```

Telegram: `/freeze_publishing` → `/resume_live` → `/live_status`

First post: one item, manual approval, then `/publish_trace <id>` and `/mark_good_post <id>`.

On preflight failure:

```
PILOT ACTIVATION ABORTED
```

Operator startup sends to ops channel:

```
🟢 CONTROLLED PUBLIC PILOT ACTIVE
Mode: canary
...
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Invalid BOT_TOKEN` | Regenerate token via @BotFather, update `.env` |
| `Bot cannot access channel` | Add bot as admin to channel |
| `Missing permissions: post_messages` | Enable Post messages in channel admin rights |
| `Forbidden: bot was blocked by the user` | Operator must `/start` the bot in private chat |
| `Chat not found` | Wrong channel ID (must include `-100` prefix) |
| `FloodWait` | Wait `retry_after` seconds; reduce probe frequency |
| `PILOT STATUS: NOT READY` + startup failed | Check DB path, run migrate, inspect logs |
| Ops alerts missing | Set `LIVE_OPS_CHANNEL_ID`, ensure bot can post there |
| Shadow routing fails | Set `LIVE_SHADOW_CHANNEL_ID`, `SHADOW_PUBLISH_ONLY` or guard route_shadow |

## First live checklist

| Step | Command / check |
|------|-----------------|
| Preflight green | `pilot_preflight.py --strict` |
| Safety commands | `/freeze_publishing` → `/resume_live` |
| One approved publish | operator approval + review |
| Trace written | `/publish_trace <id>` |
| Calibration | `/mark_good_post` or `/mark_bad_post` |

## Monitor

- `/live_status` `/live_dashboard` `/pilot_preflight`
- `GET /pilot_readiness` `GET /live_metrics_timeline`
- `bash scripts/live_watch.sh`

## Policy

- First 48h: `LIVE_MODE=canary`, max **3 posts/hour**
- **Freeze first · analyze second · resume later**
- No `autonomous_live` during pilot

## Success

7+ stable days → `LIVE_MODE=supervised_live`.
