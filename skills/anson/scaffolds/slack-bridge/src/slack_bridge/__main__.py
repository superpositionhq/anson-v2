"""Entry point: `python -m slack_bridge` or `slack-bridge`."""
from __future__ import annotations

import logging
import signal
import sys
import threading

from .config import load
from .slack_listener import run


def main() -> int:
    try:
        config = load()
    except RuntimeError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(config.log_dir / "slack-bridge.log"),
        ],
    )

    shutdown = threading.Event()

    def on_signal(signum, _frame):
        logging.info("caught signal %d", signum)
        shutdown.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    try:
        run(config, shutdown)
    except Exception:
        logging.exception("fatal")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
