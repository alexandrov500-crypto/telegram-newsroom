# Publish policy

## Modes

| Mode | Env | Behavior |
|------|-----|----------|
| Manual | default staging | Operator `/approve` + publish |
| Starvation auto | `DESK_STARVATION_AUTO_PUBLISH=true` | One pending → schedule when starved |
| Autonomous | `AUTO_PUBLISH_ENABLED=true` | Policy gate → approve + schedule |

## Quality gates (always)

- `publish_pipeline_guards` / sanitizer on HTML  
- Duplicate window via `duplicate_intel`  
- Auto-publish rejects: short text, debug markers, low confidence, blocked category  

## Rate limits

- `FINAL_STAGING_MAX_PUBLISHES_PER_HOUR`  
- `publish_channel_min_interval_sec`  
- Canary: `LIVE_CANARY_MAX_PER_HOUR`

## Media

- Publish proceeds text-only if media missing  
- Preferred: source → OG → fallback card  
- Log: `media.publish_mode`

## Idempotency

- `publish.idempotent_skip` on replay  
- `published_posts` records `telegram_message_id`
