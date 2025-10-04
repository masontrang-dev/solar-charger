import argparse
import logging
import signal
import sys
import threading
import time
import yaml

from scheduler import Scheduler
from utils.logging_config import configure_logging


def load_config(path: str) -> dict:
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Solar Charger Controller")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Override config to dry-run")
    parser.add_argument("--verbose", action="store_true", help="Set log level to DEBUG")
    args = parser.parse_args()

    config = load_config(args.config)

    # CLI overrides
    if args.dry_run:
        config["dry_run"] = True
    if args.verbose:
        config["logging"] = config.get("logging", {})
        config["logging"]["level"] = "DEBUG"

    configure_logging(config)
    logger = logging.getLogger("run")

    stop_event = threading.Event()

    def handle_sig(sig, frame):
        logger.info("Shutdown signal received. Stopping...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    scheduler = Scheduler(config)

    try:
        scheduler.run(stop_event)
    except Exception:
        logger.exception("Fatal error in scheduler")
        sys.exit(1)


if __name__ == "__main__":
    main()
