from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from bot.platform.repository import PlatformRepository


@dataclass
class WorkflowStep:
    name: str
    action: str
    retry_max: int = 3
    timeout_sec: float = 300.0
    requires_approval: bool = False
    compensate: str | None = None


@dataclass
class PlatformWorkflowRuntime:
    """Declarative workflows with checkpoints — integrates workflow_runs table."""

    repository: PlatformRepository
    _definitions: dict[str, list[WorkflowStep]] = field(default_factory=dict)

    def register_builtin_workflows(self) -> None:
        builtins = {
            "publish_approval": [
                WorkflowStep("quality_check", "validate_quality"),
                WorkflowStep("safety_gate", "production_safety", requires_approval=True),
                WorkflowStep("publish", "telegram_publish", compensate="rollback_publish"),
            ],
            "maintenance_plan": [
                WorkflowStep("propose", "generate_plan"),
                WorkflowStep("approve", "operator_approve", requires_approval=True),
                WorkflowStep("execute", "run_tasks", compensate="abort_maintenance"),
            ],
            "rollback_execution": [
                WorkflowStep("snapshot", "create_rollback_snapshot"),
                WorkflowStep("dry_run", "rollback_dry_run"),
                WorkflowStep("apply", "apply_rollback", requires_approval=True),
            ],
            "certification_flow": [
                WorkflowStep("precheck", "config_validate"),
                WorkflowStep("certify", "run_certification"),
                WorkflowStep("signoff", "operator_signoff", requires_approval=True),
            ],
        }
        for name, steps in builtins.items():
            self._definitions[name] = steps
            self.repository.save_workflow_def(
                name,
                {
                    "steps": [
                        {
                            "name": s.name,
                            "action": s.action,
                            "retry_max": s.retry_max,
                            "requires_approval": s.requires_approval,
                        }
                        for s in steps
                    ],
                },
            )

    async def start(self, workflow_name: str, *, context: dict[str, Any] | None = None) -> str:
        wf_id = str(uuid.uuid4())
        import sqlite3

        with self.repository._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_runs
                (workflow_id, workflow_type, status, context_json, created_at, updated_at)
                VALUES (?, ?, 'running', ?, datetime('now'), datetime('now'))
                """,
                (wf_id, workflow_name, __import__("json").dumps(context or {})),
            )
            conn.commit()
        return wf_id

    def trace_text(self, workflow_id: str) -> str:
        run = self.repository.workflow_run_status(workflow_id)
        if not run:
            return f"No workflow <code>{workflow_id[:12]}</code>"
        import sqlite3

        with self.repository._conn() as conn:
            conn.row_factory = sqlite3.Row
            steps = conn.execute(
                "SELECT * FROM workflow_checkpoints WHERE workflow_id = ? ORDER BY id",
                (workflow_id,),
            ).fetchall()
        lines = [
            f"<b>Workflow trace</b> <code>{workflow_id[:12]}</code>",
            f"Type: {run.get('workflow_type')} · {run.get('status')}",
        ]
        for s in steps:
            lines.append(f"• {s['step_name']}: {s.get('state', '?')}")
        if not steps:
            lines.append("(no checkpoints yet)")
        return "\n".join(lines)

    def live_text(self) -> str:
        import sqlite3

        with self.repository._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT workflow_type, status, COUNT(*) AS c
                FROM workflow_runs GROUP BY workflow_type, status
                ORDER BY c DESC LIMIT 12
                """,
            ).fetchall()
        lines = ["<b>Workflows live</b>"]
        for r in rows:
            lines.append(f"• {r['workflow_type']}: {r['status']} ×{r['c']}")
        defs = len(self._definitions) or 4
        lines.append(f"Definitions: {defs} builtin")
        return "\n".join(lines)
