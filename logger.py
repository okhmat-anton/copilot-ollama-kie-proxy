"""Логирование с ежемесячной ротацией.

Три категории файлов в LOG_DIR:
  - general_YYYY-MM.log  -- общие события
  - error_YYYY-MM.log    -- ошибки
  - request_YYYY-MM.log  -- входящие запросы
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from config import settings


class MonthlyFileHandler(logging.Handler):
    """Пишет в файл вида <prefix>_YYYY-MM.log, переключаясь при смене месяца."""

    def __init__(self, log_dir: Path, prefix: str) -> None:
        super().__init__()
        self.log_dir = log_dir
        self.prefix = prefix
        self._current_month: Optional[str] = None
        self._stream: Optional[object] = None
        self._open_for_now()

    def _current_path(self) -> Path:
        month = datetime.now().strftime("%Y-%m")
        return self.log_dir / f"{self.prefix}_{month}.log"

    def _open_for_now(self) -> None:
        month = datetime.now().strftime("%Y-%m")
        if month == self._current_month and self._stream is not None:
            return
        self._close_stream()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self._current_path()
        self._stream = open(path, "a", encoding="utf-8")
        self._current_month = month

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.flush()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._open_for_now()
            msg = self.format(record)
            assert self._stream is not None
            self._stream.write(msg + "\n")
            self._stream.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        self._close_stream()
        super().close()


_FORMATTER = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _build_logger(name: str, prefix: str, level: int, error_only: bool = False) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not any(isinstance(h, MonthlyFileHandler) and h.prefix == prefix for h in logger.handlers):
        handler = MonthlyFileHandler(settings.log_dir, prefix)
        handler.setFormatter(_FORMATTER)
        if error_only:
            handler.setLevel(logging.ERROR)
        else:
            handler.setLevel(level)
        logger.addHandler(handler)

    return logger


def _build_console_handler(level: int) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(_FORMATTER)
    handler.setLevel(level)
    return handler


def _attach_console(logger: logging.Logger, level: int) -> None:
    if any(isinstance(h, logging.StreamHandler) and not isinstance(h, MonthlyFileHandler) for h in logger.handlers):
        return
    logger.addHandler(_build_console_handler(level))


def setup_logging() -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    dev = settings.dev_mode

    # General logger -- общие события, плюс зеркало в консоль
    general = _build_logger("app", prefix="general", level=level)
    _attach_console(general, level)

    # Error logger -- только ошибки (отдельный файл)
    error = _build_logger("app.error", prefix="error", level=logging.ERROR, error_only=True)
    if dev:
        _attach_console(error, logging.ERROR)

    # Request logger -- входящие запросы. В dev_mode дублируем в консоль.
    request = _build_logger("app.request", prefix="request", level=logging.INFO)
    if dev:
        _attach_console(request, logging.INFO)

    # Шумные сторонние логгеры:
    if level > logging.DEBUG and not dev:
        for noisy in ("httpx", "httpcore", "uvicorn.access"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
    elif dev:
        # В dev оставляем httpx на INFO (видно исходящие запросы), httpcore на WARNING
        logging.getLogger("httpx").setLevel(logging.INFO)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger() -> logging.Logger:
    return logging.getLogger("app")


def get_error_logger() -> logging.Logger:
    return logging.getLogger("app.error")


def get_request_logger() -> logging.Logger:
    return logging.getLogger("app.request")
