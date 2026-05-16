"""Stable monkeypatch targets for publication e2e tests."""

# Patch the name bound inside ``publish_service`` (it imports the function at load time).
PUBLISH_DRAFT_TO_CHANNEL = "publisher.publish_service.publish_draft_to_channel"
