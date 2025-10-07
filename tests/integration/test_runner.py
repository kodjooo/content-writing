"""Интеграционные тесты оркестратора."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import Settings, SheetAssistants
from app.orchestrator import runner


class FakeSheetsRepository:
    """Имитирует репозиторий Google Sheets без строк для обработки."""

    def __init__(self) -> None:
        self.calls = 0

    def acquire_prepared_row(self, tab_name: str, ttl_minutes: int):  # type: ignore[no-untyped-def]
        self.calls += 1
        return None

    def release_lock(self, row) -> None:  # type: ignore[no-untyped-def]
        raise AssertionError("release_lock не должен вызываться")


class FakeAssistantsClient:
    """Заглушка клиента Assistants."""

    def run_assistant(self, assistant_id: str, message: str) -> str:  # type: ignore[no-untyped-def]
        raise AssertionError("run_assistant не должен вызываться")


def make_settings(tmp_path: Path) -> Settings:
    account_file = tmp_path / "service.json"
    account_file.write_text("{}", encoding="utf-8")
    return Settings(
        openai_api_key="test-key",
        openai_org_id=None,
        openai_project_id=None,
        spreadsheet_id="spreadsheet",
        service_account_file=account_file,
        per_run_rows=1,
        max_revisions=3,
        lock_ttl_minutes=15,
        sheets=[
            SheetAssistants(
                tab="Main",
                writer_assistant_id="writer",
                moderator_assistant_id="moderator",
            )
        ],
        global_image_brief_assistant_id=None,
        temp_dir=tmp_path,
        log_level="INFO",
        image_generation_enabled=False,
    )


def test_run_once_without_prepared_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    repo = FakeSheetsRepository()

    monkeypatch.setattr(runner, "create_sheets_repository", lambda **_: repo)
    monkeypatch.setattr(runner, "_init_assistants", lambda _: FakeAssistantsClient())

    runner.run_once(settings)

    assert repo.calls == 1
