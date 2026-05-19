#!/usr/bin/env python3
"""Trust calibration report — subsystem reliability and operator agreement."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.trust_calibration.service import trust_calibration_html, trust_calibration_payload
from bot.storage.db import default_db_path, init_database


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    p.add_argument("--db", type=Path, default=None)
    args = p.parse_args()

    db_path = init_database(args.db or default_db_path())
    if args.json:
        print(json.dumps(trust_calibration_payload(db_path=db_path), indent=2, default=str))
    else:
        print(trust_calibration_html(db_path=db_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
