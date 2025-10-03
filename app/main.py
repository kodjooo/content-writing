"""Точка входа в приложение автоматизации контент-пайплайна."""

from __future__ import annotations

import logging

from app.config import Settings
from app.logging import configure_logging, get_logger
from app.orchestrator.runner import run_once


def main() -> None:
    """Запустить приложение с инициализацией конфигурации и логированием."""
    configure_logging("INFO")
    logger = get_logger(__name__)

    try:
        settings = Settings.load()
    except ValueError as error:
        logger.error("Ошибка загрузки конфигурации: %s", error)
        raise

    logging.getLogger().setLevel(settings.log_level)
    logger.info("Конфигурация успешно загружена, запуск оркестратора")
    run_once(settings)
    logger.info("Базовая инициализация завершена")


if __name__ == "__main__":
    main()
