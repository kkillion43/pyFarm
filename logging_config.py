"""
Configures the root logger for the entire project.
Call setup_logging() once at startup (in main.py) before importing other modules.
"""
import logging
import logging.handlers
from pathlib import Path

from config_loader import cfg


def setup_logging() -> None:
    log_cfg = cfg["logging"]
    log_path = Path(log_cfg["log_file"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_cfg["level"].upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — 5 MB × 3 backups
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=log_cfg["max_bytes"],
        backupCount=log_cfg["backup_count"],
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # Console handler for development / systemd journal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper — use in every module instead of logging.getLogger."""
    return logging.getLogger(name)
