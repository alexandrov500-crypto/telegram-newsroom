#!/usr/bin/env python3
"""In-container readiness probe: GET /ready on HEALTH_HTTP_PORT (running app.main)."""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    port = int(os.getenv("HEALTH_HTTP_PORT", "8080") or "8080")
    url = f"http://127.0.0.1:{port}/ready"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            if resp.status != 200:
                print(f"readiness http {resp.status}", file=sys.stderr)
                return 1
            return 0
    except urllib.error.HTTPError as exc:
        print(f"readiness failed: HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"readiness failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
