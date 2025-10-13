"""Точка входа в приложение автоматизации контент-пайплайна."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dt_time

import pytz
from pytz.tzinfo import BaseTzInfo

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
    """Запускать обработку по заданным расписаниям."""
    logger = get_logger(__name__)
    timezone = pytz.timezone(settings.schedule_timezone)

    jobs = _build_schedule_jobs(settings)
    if not jobs:
        logger.warning("Расписание пустое — запусков не будет")
        return

    logger.info("Планировщик активирован. Временная зона: %s", settings.schedule_timezone)

    while True:
        now_utc = datetime.now(pytz.utc)
        local_now = now_utc.astimezone(timezone)

        next_runs = []
        for job in jobs:
            next_time = _next_run_time(job, timezone, local_now)
            if next_time is not None:
                next_runs.append((next_time, job))

        if not next_runs:
            logger.warning("Не удалось вычислить ближайшее время запуска — ожидаем 1 час")
            time.sleep(3600)
            continue

        next_time, job = min(next_runs, key=lambda item: item[0])
        sleep_seconds = max((next_time.astimezone(pytz.utc) - now_utc).total_seconds(), 0.0)
        logger.info(
            "Следующий запуск (%s) запланирован на %s",
            job.description,
            next_time.isoformat(),
        )
        time.sleep(sleep_seconds)
        logger.info("Запуск %s начат", job.description)
        try:
            run_once(settings, allowed_tabs=job.tabs)
        except Exception as error:  # noqa: BLE001
            logger.exception("Сбой при выполнении запуска %s: %s", job.description, error)
        else:
            logger.info("Запуск %s завершён", job.description)


@dataclass(frozen=True)
class ScheduledJob:
    tabs: tuple[str, ...]
    time_of_day: dt_time
    days: tuple[int, ...] | None
    description: str


def _build_schedule_jobs(settings: Settings) -> list[ScheduledJob]:
    logger = get_logger(__name__)
    tab_map: dict[str, set[str]] = {}
    for sheet in settings.sheets:
        tab_map.setdefault(sheet.tab.lower(), set()).add(sheet.tab)

    jobs: list[ScheduledJob] = []

    rss_tabs = tab_map.get("rss")
    if rss_tabs:
        for time_str in settings.rss_schedule_times:
            time_obj = _parse_time_or_raise(time_str, "RSS_SCHEDULE_TIMES")
            jobs.append(
                ScheduledJob(
                    tabs=tuple(rss_tabs),
                    time_of_day=time_obj,
                    days=None,
                    description=f"RSS {time_str}",
                )
            )
    else:
        logger.warning("В конфигурации отсутствует вкладка RSS — расписание RSS пропущено")

    vk_tabs = tab_map.get("vk")
    if vk_tabs and settings.vk_schedule_days:
        time_obj = _parse_time_or_raise(settings.vk_schedule_time, "VK schedule time")
        jobs.append(
            ScheduledJob(
                tabs=tuple(vk_tabs),
                time_of_day=time_obj,
                days=settings.vk_schedule_days,
                description="VK",
            )
        )
    elif settings.vk_schedule_days:
        logger.warning("Указаны VK_SCHEDULE_DAYS, но вкладка VK не найдена")

    setka_tabs = tab_map.get("setka")
    if setka_tabs and settings.setka_schedule_days:
        time_obj = _parse_time_or_raise(settings.setka_schedule_time, "Setka schedule time")
        jobs.append(
            ScheduledJob(
                tabs=tuple(setka_tabs),
                time_of_day=time_obj,
                days=settings.setka_schedule_days,
                description="Setka",
            )
        )
    elif settings.setka_schedule_days:
        logger.warning("Указаны SETKA_SCHEDULE_DAYS, но вкладка Setka не найдена")

    if not jobs:
        all_tabs = tuple(sheet.tab for sheet in settings.sheets)
        if all_tabs:
            try:
                fallback_time = _parse_time_or_raise(settings.schedule_time, "SCHEDULE_TIME")
            except ValueError as error:
                logger.error("%s", error)
            else:
                jobs.append(
                    ScheduledJob(
                        tabs=all_tabs,
                        time_of_day=fallback_time,
                        days=None,
                        description="Default",
                    )
                )
    return jobs


def _parse_time_or_raise(value: str, label: str) -> dt_time:
    try:
        hour, minute = [int(part) for part in value.split(":", 1)]
        return dt_time(hour=hour, minute=minute)
    except ValueError as error:
        raise ValueError(f"Некорректное время '{value}' для {label}, ожидался формат HH:MM") from error


def _next_run_time(job: ScheduledJob, timezone: pytz.BaseTzInfo, local_now: datetime) -> Optional[datetime]:
    for offset in range(0, 8):
        candidate_date = (local_now + timedelta(days=offset)).date()
        weekday = (local_now.weekday() + offset) % 7
        if job.days and weekday not in job.days:
            continue
        candidate_naive = datetime.combine(candidate_date, job.time_of_day)
        candidate_local = timezone.localize(candidate_naive)
        if candidate_local <= local_now:
            continue
        return candidate_local
    return None


if __name__ == "__main__":
    main()
