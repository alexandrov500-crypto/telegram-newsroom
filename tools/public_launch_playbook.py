#!/usr/bin/env python3
"""Generate public launch playbook text artifact."""

from __future__ import annotations

import os
from pathlib import Path


def build_playbook() -> str:
    stage = os.getenv("ROLLOUT_STAGE", "STAGE_0_PRIVATE_QA")
    return "\n".join(
        [
            "PUBLIC LAUNCH PLAYBOOK",
            "",
            "Launch checklist:",
            "- make final-release-check",
            "- make public-go-check",
            "- make release-readiness",
            "- /go_status and /continuity in Telegram",
            "",
            f"Rollout stage checklist: {stage}",
            "- STAGE_0: QA mirror + manual supervision",
            "- STAGE_1: limited auto publish, monitor alerts each hour",
            "- STAGE_2: observed public, watch continuity + quality",
            "- STAGE_3: full autonomous, strict incident response discipline",
            "",
            "Rollback instructions:",
            "- /pause_autopublish",
            "- Enable LIVE_ROLLBACK_MODE=true",
            "- make incident-report",
            "- Investigate before /resume_autopublish",
            "",
            "Operator monitoring commands:",
            "- /runtime_state /continuity /last_alerts /recent_failures /go_status",
            "",
            "First 24h watch targets:",
            "- publish continuity score > threshold",
            "- no CRITICAL runtime without alert",
            "- no duplicate publish IDs",
            "",
            "First-week burn-in guidance:",
            "- make autonomous-weekly-report daily",
            "- review burnin_validation + post_quality_report",
            "",
            "Escalation workflow:",
            "- critical alert -> freeze autopublish -> collect diagnostics -> recover -> resume",
        ]
    )


def main() -> int:
    runtime_dir = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    out = runtime_dir / "public_launch_playbook.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = build_playbook()
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
