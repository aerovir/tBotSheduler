from __future__ import annotations

import logging
import sys
from pathlib import Path

from tbot_sheduler.core.config import LOG_DIR, LOG_LEVEL


def setup_logging() -> None:
    """Configure logging: stdout + file with rotation."""
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    stdout_handler.setFormatter(formatter)

    # Error log file handler
    error_handler = logging.FileHandler(
        LOG_DIR / "error.log", encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # Info log file handler
    info_handler = logging.FileHandler(
        LOG_DIR / "app.log", encoding="utf-8"
    )
    info_handler.setLevel(log_level)
    info_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(info_handler)

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
