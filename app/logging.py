"""Настройки логирования для приложения."""

import logging
from typing import Optional


def configure_logging(level: str) -> None:
    """Инициализировать стандартное логирование с заданным уровнем."""
    normalized_level = level.upper() if level else "INFO"
    logging.basicConfig(
        level=getattr(logging, normalized_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Вернуть логгер с заданным именем."""
    return logging.getLogger(name if name else "app")
