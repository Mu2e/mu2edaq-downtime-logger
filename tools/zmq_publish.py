"""ZMQ PUB diagnostic: emits messages the ZmqDetector understands."""
from __future__ import annotations

import argparse
import time

import zmq


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ZMQ PUB diagnostic for ZmqDetector")
    p.add_argument("--endpoint", default="tcp://*:5555",
                   help="bind endpoint (default: tcp://*:5555)")
    p.add_argument("--topic", default="",
                   help="topic prefix (default: empty)")
    p.add_argument("--state", default="running",
                   choices=["running", "stopped", "heartbeat"])
    p.add_argument("--interval", type=float, default=1.0,
                   help="seconds between publishes")
    p.add_argument("--once", action="store_true",
                   help="publish a single message then exit")
    p.add_argument("--message",
                   help="override message body (otherwise built from --state)")
    args = p.parse_args(argv)

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.PUB)
    sock.bind(args.endpoint)
    # Slow-joiner: PUB drops messages until subscribers handshake.
    time.sleep(0.3)

    body = args.message or {
        "running": "RUN STATE running",
        "stopped": "RUN STATE stopped",
        "heartbeat": "heartbeat tick",
    }[args.state]
    payload = (args.topic + body) if args.topic else body

    print(f"publishing to {args.endpoint!r} topic={args.topic!r} body={body!r}")
    while True:
        sock.send_string(payload)
        if args.once:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
