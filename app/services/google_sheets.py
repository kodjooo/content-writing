"""Обёртка для работы с Google Sheets через gspread."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import gspread
from gspread import Worksheet
from gspread.exceptions import GSpreadException

from app.logging import get_logger
from app.services.google_auth import load_credentials
from app.utils.retry import create_retrying

logger = get_logger(__name__)

REQUIRED_COLUMNS = [
    "Title",
    "Content",
    "Image URL",
    "Status",
    "Iteration",
    "Moderator Note",
    "Lock",
]


def _column_to_a1(index: int) -> str:
    """Преобразовать индекс столбца (1-based) в буквенное представление A1."""
    result = []
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def _lock_expired(lock_value: str) -> bool:
    """Проверить, просрочена ли блокировка."""
    if not lock_value:
        return True
    try:
        if lock_value.endswith("Z"):
            lock_value = lock_value[:-1] + "+00:00"
        locked_until = datetime.fromisoformat(lock_value)
        return locked_until <= datetime.now(timezone.utc)
    except ValueError:
        return False


@dataclass
class WorksheetContext:
    """Кэш сведений о конкретной вкладке."""

    worksheet: Worksheet
    headers: List[str]

    def __post_init__(self) -> None:
        self.column_map: Dict[str, int] = {
            name: idx + 1 for idx, name in enumerate(self.headers)
        }
        self.last_column: str = _column_to_a1(len(self.headers))


@dataclass
class SheetRow:
    """Представление строки в Google Sheets."""

    repository: "SheetsRepository"
    context: WorksheetContext
    row_index: int
    values: Dict[str, str]

    def update(self, updates: Mapping[str, str]) -> None:
        """Обновить ячейки строки и локальные данные."""
        self.repository.update_row(self, updates)

    @property
    def title(self) -> str:
        return self.values.get("Title", "")

    @property
    def status(self) -> str:
        return self.values.get("Status", "")


class SheetsRepository:
    """Высокоуровневый клиент Google Sheets."""

    def __init__(self, spreadsheet_id: str, service_account_file: str | Path) -> None:
        credentials = load_credentials(
            Path(service_account_file),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
            ],
        )
        client = gspread.authorize(credentials)
        self._spreadsheet = client.open_by_key(spreadsheet_id)
        self._contexts: Dict[str, WorksheetContext] = {}
        self._retryer = create_retrying(
            name="google-sheets",
            logger=logger,
            exceptions=(GSpreadException,),
            attempts=3,
            base_delay=1.0,
            max_delay=10.0,
        )

    def _get_context(self, tab_name: str) -> WorksheetContext:
        if tab_name in self._contexts:
            return self._contexts[tab_name]
        worksheet = self._spreadsheet.worksheet(tab_name)
        headers = self._retryer(lambda: worksheet.row_values(1))
        missing = [col for col in REQUIRED_COLUMNS if col not in headers]
        if missing:
            raise ValueError(
                f"Во вкладке {tab_name} отсутствуют обязательные столбцы: {', '.join(missing)}"
            )
        context = WorksheetContext(worksheet=worksheet, headers=headers)
        self._contexts[tab_name] = context
        return context

    def acquire_prepared_row(
        self, tab_name: str, ttl_minutes: int
    ) -> Optional[SheetRow]:
        """Найти строку со статусом Prepared, установить Lock и вернуть."""
        context = self._get_context(tab_name)
        range_start = "A2"
        range_end = context.last_column
        raw_rows = self._retryer(
            lambda: context.worksheet.get_values(f"{range_start}:{range_end}")
        )
        logger.debug("Получено %s строк для вкладки %s", len(raw_rows), tab_name)

        for offset, raw_row in enumerate(raw_rows, start=2):
            values = {
                header: value.strip()
                for header, value in zip_longest(
                    context.headers, raw_row, fillvalue=""
                )
            }
            status = values.get("Status", "")
            lock_value = values.get("Lock", "")
            if status != "Prepared":
                continue
            if not _lock_expired(lock_value):
                continue

            new_lock = (
                datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
            ).isoformat().replace("+00:00", "Z")
            self._apply_updates(context, offset, {"Lock": new_lock})
            values["Lock"] = new_lock
            logger.info(
                "Строка %s вкладки %s заблокирована до %s", offset, tab_name, new_lock
            )
            return SheetRow(
                repository=self,
                context=context,
                row_index=offset,
                values=values,
            )
        return None

    def update_row(self, row: SheetRow, updates: Mapping[str, str]) -> None:
        """Обновить указанные столбцы и синхронизировать локальные значения."""
        if not updates:
            return
        self._apply_updates(row.context, row.row_index, updates)
        row.values.update({key: str(value) for key, value in updates.items()})

    def batch_update(
        self, tab_name: str, row_index: int, updates: Mapping[str, str]
    ) -> None:
        """Обновить значения без объекта строки."""
        context = self._get_context(tab_name)
        self._apply_updates(context, row_index, updates)

    def _apply_updates(
        self, context: WorksheetContext, row_index: int, updates: Mapping[str, str]
    ) -> None:
        for column, value in updates.items():
            column_index = context.column_map.get(column)
            if not column_index:
                raise KeyError(f"Столбец {column} отсутствует на вкладке")
            cell_range = f"{_column_to_a1(column_index)}{row_index}"
            self._retryer(lambda cr=cell_range, v=value: context.worksheet.update(cr, v))

    def release_lock(self, row: SheetRow) -> None:
        """Снять блокировку у строки."""
        self.update_row(row, {"Lock": ""})


def create_sheets_repository(spreadsheet_id: str, service_account_file: str) -> SheetsRepository:
    """Фабричный метод для единообразного создания репозитория."""
    return SheetsRepository(spreadsheet_id, service_account_file)
