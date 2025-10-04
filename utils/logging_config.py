import logging


def configure_logging(config: dict):
    lvl = (config.get("logging", {}).get("level") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, lvl, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
