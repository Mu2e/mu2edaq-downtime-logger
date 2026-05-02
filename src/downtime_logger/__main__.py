from __future__ import annotations

import argparse
import logging
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .app import Controller
from .config import AppConfig


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mu2edaq-downtime-logger")
    p.add_argument("--config", "-c", required=True, help="Path to YAML config")
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = AppConfig.load(args.config)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray keeps app alive when window closed

    controller = Controller(config, app)  # noqa: F841 — owned by app event loop

    # Allow Ctrl-C in the terminal to actually stop the Qt event loop.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    timer = QTimer()
    timer.start(250)
    timer.timeout.connect(lambda: None)  # wakes the loop so signals are delivered

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
