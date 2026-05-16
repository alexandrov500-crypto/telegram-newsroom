# RFC-007: Multi-channel publishing

**Status:** Draft · **Target:** v1.3+ product decision

## Problem

`TARGET_CHANNEL_ID` is singular; `publish_service.py` assumes one destination.

## Proposal

- `TARGET_CHANNELS` comma-separated or JSON list in settings (opt-in).
- Draft metadata field `target_channel_id` overrides default.
- Publish lock key includes channel id: `{prefix}:publish_lock:{draft_id}:{channel_id}`.
- Metrics: `publishes{channel="..."}` only in extended metrics mode (RFC-001).

## Breaking change policy

Default remains single channel; multi-channel requires explicit env + ADR-028.

## Migration risk

Medium — moderation UI and bot keyboards need channel selection UX.
