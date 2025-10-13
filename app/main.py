"""Точка входа в приложение автоматизации контент-пайплайна."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pytz

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

    if settings.schedule_enabled:
        _run_with_schedule(settings)
    else:
        logger.info("Конфигурация успешно загружена, запуск оркестратора")
        run_once(settings)
        logger.info("Базовая инициализация завершена")


def _run_with_schedule(settings: Settings) -> None:
    """Запускать обработку ежедневно по расписанию."""
    logger = get_logger(__name__)
    try:
        target_hour, target_minute = [int(part) for part in settings.schedule_time.split(":", 1)]
    except ValueError as error:
        raise ValueError("Некорректное значение SCHEDULE_TIME, ожидался формат HH:MM") from error

    timezone = pytz.timezone(settings.schedule_timezone)
    logger.info(
        "Планировщик активирован: ежедневно в %02d:%02d (%s)",
        target_hour,
        target_minute,
        settings.schedule_timezone,
    )

    while True:
        now_utc = datetime.now(pytz.utc)
        local_now = now_utc.astimezone(timezone)
        target_local = timezone.localize(
            datetime(
                local_now.year,
                local_now.month,
                local_now.day,
                target_hour,
                target_minute,
            )
        )
        if local_now >= target_local:
            target_local += timedelta(days=1)
        sleep_seconds = max((target_local.astimezone(pytz.utc) - now_utc).total_seconds(), 0.0)
        logger.info("Следующий запуск запланирован на %s", target_local.isoformat())
        time.sleep(sleep_seconds)
        logger.info("Запланированный запуск начат")
        try:
            run_once(settings)
        except Exception as error:  # noqa: BLE001
            logger.exception("Сбой при выполнении запланированного запуска: %s", error)
        else:
            logger.info("Запланированный запуск завершён")


if __name__ == "__main__":
    main()
