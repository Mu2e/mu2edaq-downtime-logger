"""UDP diagnostic: sends datagrams the UdpDetector understands."""
from __future__ import annotations

import argparse
import socket
import time


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="UDP diagnostic for UdpDetector")
    p.add_argument("--host", default="255.255.255.255",
                   help="target host or broadcast address")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--state", default="running",
                   choices=["running", "stopped", "heartbeat"])
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--once", action="store_true")
    p.add_argument("--message", help="override message body")
    args = p.parse_args(argv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    body = args.message or {
        "running": "DAQ STATE running",
        "stopped": "DAQ STATE stopped",
        "heartbeat": "heartbeat tick",
    }[args.state]
    payload = body.encode()

    print(f"sending to udp://{args.host}:{args.port} body={body!r}")
    while True:
        sock.sendto(payload, (args.host, args.port))
        if args.once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
