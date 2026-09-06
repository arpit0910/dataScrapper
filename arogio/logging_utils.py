import logging
from pathlib import Path


def configure_logging(path: str | Path = "logs/arogio.log") -> logging.Logger:
    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("arogio")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger
