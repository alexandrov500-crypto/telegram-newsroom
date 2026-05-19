from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.adaptive.policies import PolicyEngine
from bot.replay.engine import ReplayEngine
from bot.storage.db import default_db_path, init_database
from bot.storage.learning_repository import LearningRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay newsroom event history")
    parser.add_argument("--from", dest="from_ts", required=True, help="ISO start timestamp")
    parser.add_argument("--to", dest="to_ts", required=True, help="ISO end timestamp")
    parser.add_argument("--label", default="cli", help="Run label")
    parser.add_argument("--db", default=None, help="Database path")
    args = parser.parse_args()

    db_path = init_database(Path(args.db) if args.db else default_db_path())
    learning = LearningRepository(db_path)
    policies = PolicyEngine(learning)
    engine = ReplayEngine(db_path, learning=learning, policies=policies)
    result = engine.run(
        from_ts=args.from_ts,
        to_ts=args.to_ts,
        run_label=args.label,
    )
    print(
        f"Replay run #{result.run_id}: events={result.events_processed} "
        f"matched_signals={result.signals_matched} policy={result.policy_name}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
