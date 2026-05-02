"""Appends lines to a log file so the LogfileDetector picks them up."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Logfile diagnostic")
    p.add_argument("--path", required=True, help="logfile to append to")
    p.add_argument("--message", required=True,
                   help="line text (matched against detector regex patterns)")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--interval", type=float, default=1.0)
    args = p.parse_args(argv)

    target = Path(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)

    print(f"writing {args.count} lines to {target}")
    for i in range(args.count):
        line = f"{datetime.now(timezone.utc).isoformat()} {args.message}\n"
        with open(target, "a") as f:
            f.write(line)
        if i < args.count - 1:
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
