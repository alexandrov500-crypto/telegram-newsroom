"""Shared flags and exit semantics for runtime inspection CLIs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


STRICT_HELP = "Exit non-zero on WARNING or FAIL (inspection commands)"
JSON_HELP = "Print deterministic JSON (sort_keys=True) to stdout"
PATH_HELP = "Ops output directory or a file under runtime/"


def add_standard_inspection_args(
    parser: argparse.ArgumentParser,
    *,
    supports_write: bool = False,
    extra_help: str | None = None,
) -> None:
    path_help = PATH_HELP if extra_help is None else f"{PATH_HELP}; {extra_help}"
    parser.add_argument("--path", type=Path, default=None, help=path_help)
    parser.add_argument("--json", action="store_true", help=JSON_HELP)
    parser.add_argument("--strict", action="store_true", help=STRICT_HELP)
    if supports_write:
        parser.add_argument(
            "--write",
            action="store_true",
            help="Write latest-only runtime artifact(s) for this command",
        )


def emit_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def strict_tri_state_exit(status: str, *, strict: bool) -> int:
    """Unified exit code for OK / WARNING / FAIL inspection statuses."""
    st = str(status or "FAIL").upper()
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0
