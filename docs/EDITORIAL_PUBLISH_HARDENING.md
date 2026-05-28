# Editorial publish hardening

Production polish layer for public Telegram posts. Does not change pipeline topology.

## Choke point

All channel HTML goes through `publisher.publish_formatting.build_channel_message_html` → `app.editorial.public_post_formatter.format_public_post_html`.

## Config

- Default: `config/editorial_tuning.yaml`
- Override: `EDITORIAL_TUNING_PATH=/path/to/tuning.yaml`
- Strict metadata block only: `PUBLISH_QUALITY_GATE_STRICT=true`

## Operator commands

- `/draft <id>` — internal moderation view (may show «Источники (внутр.)» JSON)
- `/preview_channel <id>` — **exact** channel HTML before publish

## Rollback

1. Remove `EDITORIAL_TUNING_PATH` (built-in defaults apply).
2. Keep `PUBLISH_QUALITY_GATE_STRICT` unset (log-only).
3. Revert commit touching `app/editorial/publish_*` and `public_post_formatter.py`.

## Validation

```bash
python3 -m pytest tests/test_publish_body_scrubber.py tests/test_publish_quality_gate.py \
  tests/test_public_post_formatter.py tests/test_public_content_sanitizer.py \
  tests/test_publish_formatting.py tests/test_editorial_tuning_loader.py -q
```

After 3–5 staging publishes, grep logs for `publish_quality_gate` and `public_output_lock`.
