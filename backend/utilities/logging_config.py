import logging
from typing import Optional


DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


def configure(level: int = logging.INFO, log_file: Optional[str] = "app.log") -> logging.Logger:
    """Configure root logging once with console + optional file handlers.

    Safe to call multiple times; it won’t duplicate handlers.
    Returns the root logger.
    """
    root = logging.getLogger()
    if root.handlers:
        # Already configured elsewhere
        return root

    root.setLevel(level)

    formatter = logging.Formatter(DEFAULT_FORMAT)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    root.addHandler(ch)

    # File handler (optional)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)

    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

