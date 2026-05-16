#!/usr/bin/env python3
"""Build deterministic repository fingerprint (offline)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.repository_fingerprint import write_fingerprint_outputs


def main() -> int:
    paths = write_fingerprint_outputs(REPO)
    print(json.dumps(paths, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
