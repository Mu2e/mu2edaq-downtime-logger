"""
Periodically writes a small file inside a directory so the
DiskActivityDetector sees fresh modifications. Useful for verifying that
a watched path is reachable, that the recursive flag matters, etc.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Disk-activity diagnostic")
    p.add_argument("--path", required=True, help="directory to write into")
    p.add_argument("--interval", type=float, default=5.0,
                   help="seconds between writes")
    p.add_argument("--filename", default=".heartbeat",
                   help="filename to update inside --path")
    p.add_argument("--once", action="store_true")
    args = p.parse_args(argv)

    target_dir = Path(args.path)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / args.filename

    print(f"touching {target} every {args.interval:.1f}s (Ctrl-C to stop)")
    while True:
        with open(target, "a") as f:
            f.write(f"{time.time():.3f}\n")
        os.utime(target, None)
        if args.once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
