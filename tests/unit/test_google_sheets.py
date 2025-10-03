"""Юнит-тесты логики Google Sheets."""

from __future__ import annotations

from datetime import datetime, timezone
from types import MethodType
from typing import Dict, List

import pytest

from app.services import google_sheets
from app.services.google_sheets import SheetRow, WorksheetContext, _lock_expired


class DummyRetryer:
    """Минимальный ретраер, исполняющий функцию без повторов."""

    def call(self, func):  # type: ignore[no-untyped-def]
        return func()


class FakeWorksheet:
    """Заглушка для Worksheet с предопределённым набором строк."""

    def __init__(self, rows: List[List[str]]) -> None:
        self._rows = rows

    def get_values(self, _range: str) -> List[List[str]]:
        return list(self._rows)


class FixedDatetime(datetime):
    """Детерминированный datetime.now для тестов."""

    fixed_now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return cls.fixed_now.replace(tzinfo=None)
        return cls.fixed_now


@pytest.mark.parametrize(
    "raw_value, expired",
    [
        ("", True),
        ("2023-01-01T00:00:00Z", True),
        ("3024-01-01T00:00:00Z", False),
        ("invalid", False),
    ],
)
def test_lock_expired(raw_value: str, expired: bool) -> None:
    """Функция корректно определяет просрочку Lock."""
    assert _lock_expired(raw_value) is expired


def test_acquire_prepared_row_sets_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Строка со статусом Prepared получает новый Lock и возвращается пользователю."""
    monkeypatch.setattr(google_sheets, "datetime", FixedDatetime)

    headers = [
        "Title",
        "Content",
        "Image URL",
        "Status",
        "Iteration",
        "Moderator Note",
        "Lock",
    ]
    rows = [["Заголовок", "", "", "Prepared", "0", "", ""]]
    worksheet = FakeWorksheet(rows)
    context = WorksheetContext(worksheet=worksheet, headers=headers)

    repo = google_sheets.SheetsRepository.__new__(google_sheets.SheetsRepository)
    repo._retryer = DummyRetryer()

    def _get_context(self, tab_name: str) -> WorksheetContext:  # type: ignore[override]
        return context

    def _apply_updates(
        self, ctx: WorksheetContext, row_index: int, updates: Dict[str, str]
    ) -> None:  # type: ignore[override]
        self.last_updates = (row_index, dict(updates))  # type: ignore[attr-defined]

    repo._get_context = MethodType(_get_context, repo)
    repo._apply_updates = MethodType(_apply_updates, repo)

    row = google_sheets.SheetsRepository.acquire_prepared_row(repo, "Main", ttl_minutes=10)
    assert row is not None
    assert isinstance(row, SheetRow)
    assert row.row_index == 2
    assert row.values["Lock"].endswith("Z")
    assert repo.last_updates[0] == 2  # type: ignore[index]
    assert repo.last_updates[1]["Lock"] == row.values["Lock"]  # type: ignore[index]


def test_acquire_prepared_row_skips_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Строка с актуальным Lock пропускается."""
    monkeypatch.setattr(google_sheets, "datetime", FixedDatetime)

    headers = [
        "Title",
        "Content",
        "Image URL",
        "Status",
        "Iteration",
        "Moderator Note",
        "Lock",
    ]
    future_lock = "3024-01-01T00:00:00Z"
    rows = [["Заголовок", "", "", "Prepared", "0", "", future_lock]]
    worksheet = FakeWorksheet(rows)
    context = WorksheetContext(worksheet=worksheet, headers=headers)

    repo = google_sheets.SheetsRepository.__new__(google_sheets.SheetsRepository)
    repo._retryer = DummyRetryer()

    def _get_context(self, tab_name: str) -> WorksheetContext:  # type: ignore[override]
        return context

    repo._get_context = MethodType(_get_context, repo)

    row = google_sheets.SheetsRepository.acquire_prepared_row(repo, "Main", ttl_minutes=10)
    assert row is None
