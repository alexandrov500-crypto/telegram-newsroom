from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from bot.config import project_root


class OpsObservationStore:
    """Append-only observation artifacts under var/ops/."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (project_root() / "var" / "ops")
        self.pulses_dir = self.root / "pulses"
        self.daily_dir = self.root / "daily"
        self.baseline_path = self.root / "baseline.json"
        self.source_notes_path = self.root / "source_calibration.json"
        for d in (self.pulses_dir, self.daily_dir):
            d.mkdir(parents=True, exist_ok=True)

    def append_pulse(self, pulse: dict[str, Any]) -> Path:
        day = date.fromisoformat(pulse.get("date", datetime.now(timezone.utc).date().isoformat()))
        path = self.pulses_dir / f"{day.isoformat()}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(pulse, default=str) + "\n")
        return path

    def load_baseline(self) -> dict[str, Any]:
        if not self.baseline_path.is_file():
            return {}
        try:
            return json.loads(self.baseline_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def save_baseline(self, baseline: dict[str, Any]) -> None:
        self.baseline_path.write_text(
            json.dumps(baseline, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    def save_daily(self, snapshot: dict[str, Any]) -> Path:
        day = snapshot.get("date") or datetime.now(timezone.utc).date().isoformat()
        path = self.daily_dir / f"{day}.json"
        path.write_text(json.dumps(snapshot, indent=2, default=str) + "\n", encoding="utf-8")
        return path

    def load_source_notes(self) -> dict[str, Any]:
        if not self.source_notes_path.is_file():
            return {"sources": {}, "updated_at": None}
        try:
            return json.loads(self.source_notes_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"sources": {}, "updated_at": None}

    def list_pulse_days(self) -> list[str]:
        return sorted(p.stem for p in self.pulses_dir.glob("*.jsonl"))
