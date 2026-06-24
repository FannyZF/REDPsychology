import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_loggers: dict[str, logging.Logger] = {}
_initialized = False


def get_logger(name: str = "psychology_studio") -> logging.Logger:
    global _initialized
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not _initialized:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(fmt)
        logging.getLogger().addHandler(console_handler)

        file_handler = TimedRotatingFileHandler(
            str(LOG_DIR / "app.log"),
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logging.getLogger().addHandler(file_handler)

        _initialized = True

    _loggers[name] = logger
    return logger
