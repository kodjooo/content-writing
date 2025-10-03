"""Каркас оркестратора обработки строк."""

from __future__ import annotations

from gspread.exceptions import GSpreadException

from app.config import Settings
from app.logging import get_logger
from app.services.google_sheets import create_sheets_repository

logger = get_logger(__name__)


def run_once(settings: Settings) -> None:
    """Минимальный проход: проверяем доступность таблицы и блокируем строку."""
    if not settings.service_account_file.exists():
        logger.warning(
            "Файл сервисного аккаунта %s не найден, пропускаем обращение к Google Sheets",
            settings.service_account_file,
        )
        return

    try:
        sheets_repo = create_sheets_repository(
            spreadsheet_id=settings.spreadsheet_id,
            service_account_file=settings.service_account_file,
        )
    except (FileNotFoundError, GSpreadException) as error:
        logger.error("Не удалось инициализировать клиента Google Sheets: %s", error)
        return

    if not settings.sheets:
        logger.info("Список вкладок не задан, нечего обрабатывать")
        return

    for sheet_cfg in settings.sheets:
        try:
            sheet_cfg.ensure_complete()
        except ValueError as error:
            logger.error("%s", error)
            continue
        row = sheets_repo.acquire_prepared_row(
            tab_name=sheet_cfg.tab,
            ttl_minutes=settings.lock_ttl_minutes,
        )
        if row:
            logger.info(
                "Найдена строка %s на вкладке %s со статусом %s",
                row.row_index,
                sheet_cfg.tab,
                row.status,
            )
            return

    logger.info("Нет доступных строк со статусом Prepared во всех вкладках")
