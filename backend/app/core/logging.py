"""
Centralized logging configuration for the backend application.
"""
import logging
import sys

from app.core.config import get_settings


def configure_logging() -> None:
    """Configure root logging handlers and format for the application."""
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers when reloaded (e.g. uvicorn --reload)
    if not root_logger.handlers:
        root_logger.addHandler(handler)
    else:
        root_logger.handlers = [handler]

    # Quiet down noisy third-party loggers a bit
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
