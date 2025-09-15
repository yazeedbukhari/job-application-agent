import logging
from typing import Optional


DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"


def configure(
    level: int = logging.INFO,
    log_file: Optional[str] = "app.log",
    add_console: bool = False,
) -> logging.Logger:
    """Configure root logging once.

    - Always adds a file handler if ``log_file`` is provided.
    - Adds a console handler only when ``add_console`` is True.
    - Safe to call multiple times; it won’t duplicate handlers.
    Returns the root logger.
    """
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(DEFAULT_FORMAT)

    # Track existing handler types/targets to avoid duplicates
    existing = {
        (type(h).__name__, getattr(h, 'baseFilename', None))
        for h in root.handlers
    }

    # Optional console handler
    if add_console and ("StreamHandler", None) not in existing:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        root.addHandler(ch)

    # File handler
    if log_file and ("FileHandler", log_file) not in existing:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)

    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
