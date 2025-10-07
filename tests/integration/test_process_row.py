"""Интеграционные тесты процессора строки с локальными заглушками."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from app.config.settings import Settings, SheetAssistants
from app.orchestrator.processor import ProcessingError, process_row
from app.services.image_generation import ImageGenerationError
from app.services.google_sheets import SheetRow


class DummyRepository:
    """Запоминает обновления строки вместо реального доступа к Google Sheets."""

    def __init__(self) -> None:
        self.updates: list[Dict[str, str]] = []

    def update_row(self, row, updates: Dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
        self.updates.append({key: str(value) for key, value in updates.items()})
        row.values.update({key: str(value) for key, value in updates.items()})


class FakeAssistantsClient:
    """Возвращает заранее заданные ответы для ассистентов."""

    def __init__(self, mapping: Dict[str, Any]) -> None:
        self._mapping: Dict[str, Any] = {}
        for key, value in mapping.items():
            if isinstance(value, list):
                self._mapping[key] = list(value)
            else:
                self._mapping[key] = value
        self.calls: list[tuple[str, str]] = []

    def run_assistant(self, assistant_id: str, message: str) -> str:
        self.calls.append((assistant_id, message))
        if assistant_id not in self._mapping:
            raise AssertionError(f"Неожиданный ассистент {assistant_id}")
        handler = self._mapping[assistant_id]
        if callable(handler):
            return handler(message)
        if isinstance(handler, list):
            if not handler:
                raise AssertionError(f"Для ассистента {assistant_id} закончились ответы")
            return handler.pop(0)
        return str(handler)


class FakeImagePipeline:
    """Эмуляция пайплайна генерации изображений."""

    def __init__(self, url: str | None = None, error: Exception | None = None) -> None:
        self.url = url or "https://drive.example/result.png"
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def generate_and_upload(self, brief_prompt: str, title: str) -> str:
        self.calls.append((brief_prompt, title))
        if self.error:
            raise self.error
        return self.url


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    """Быстро собрать объект Settings для тестов."""
    account_file = tmp_path / "service.json"
    account_file.write_text("{}", encoding="utf-8")
    data: Dict[str, Any] = {
        "openai_api_key": "test-key",
        "openai_org_id": None,
        "openai_project_id": None,
        "spreadsheet_id": "spreadsheet",
        "service_account_file": account_file,
        "per_run_rows": 1,
        "max_revisions": 3,
        "lock_ttl_minutes": 15,
        "sheets": [],
        "global_image_brief_assistant_id": "brief",
        "temp_dir": tmp_path,
        "log_level": "INFO",
        "image_generation_enabled": True,
    }
    data.update(overrides)
    return Settings(**data)


def build_row(repository: DummyRepository) -> SheetRow:
    return SheetRow(
        repository=repository,
        context=None,  # type: ignore[arg-type]
        row_index=2,
        values={
            "Title": "Статья",
            "Content": "",
            "Image URL": "",
            "Status": "Prepared",
            "Iteration": "0",
            "Moderator Note": "",
            "Lock": "",
        },
    )


@pytest.fixture
def base_sheet_cfg() -> SheetAssistants:
    return SheetAssistants(
        tab="Main",
        writer_assistant_id="writer",
        moderator_assistant_id="moderator",
    )


def test_process_row_success(tmp_path: Path, base_sheet_cfg: SheetAssistants) -> None:
    assistants = FakeAssistantsClient(
        {
            "writer": ["Черновик"],
            "moderator": [" Ок "],
            "brief": ["Яркое описание"],
        }
    )
    image_pipeline = FakeImagePipeline(url="https://drive.example/image.png")
    repository = DummyRepository()
    row = build_row(repository)

    settings = make_settings(tmp_path)

    status = process_row(
        row=row,
        sheet_cfg=base_sheet_cfg,
        assistants_client=assistants,
        image_pipeline=image_pipeline,
        brief_assistant_id=settings.global_image_brief_assistant_id,
        settings=settings,
    )

    assert status == "Written"
    assert row.values["Content"] == "Черновик"
    assert row.values["Image URL"] == "https://drive.example/image.png"
    assert row.values["Status"] == "Written"
    assert row.values["Moderator Note"] == " Ок "
    assert image_pipeline.calls == [("Яркое описание", "Статья")]


def test_process_row_hits_revision_limit(tmp_path: Path, base_sheet_cfg: SheetAssistants) -> None:
    assistants = FakeAssistantsClient(
        {
            "writer": ["Черновик 1", "Черновик 2"],
            "moderator": ["нужно доработать", "всё ещё плохо"],
        }
    )
    repository = DummyRepository()
    row = build_row(repository)

    settings = make_settings(
        tmp_path,
        max_revisions=2,
        image_generation_enabled=False,
        global_image_brief_assistant_id=None,
    )

    status = process_row(
        row=row,
        sheet_cfg=base_sheet_cfg,
        assistants_client=assistants,
        image_pipeline=None,
        brief_assistant_id=settings.global_image_brief_assistant_id,
        settings=settings,
    )

    assert status == "Written (not moderated)"
    assert row.values["Content"] == "Черновик 2"
    assert row.values["Iteration"] == "2"
    assert row.values["Moderator Note"] == "всё ещё плохо"
    assert row.values["Status"] == "Written (not moderated)"


def test_process_row_image_failure(tmp_path: Path, base_sheet_cfg: SheetAssistants) -> None:
    assistants = FakeAssistantsClient(
        {
            "writer": ["Черновик"],
            "moderator": ["ок"],
            "brief": ["Описание"],
        }
    )
    image_pipeline = FakeImagePipeline(error=ImageGenerationError("Drive недоступен"))
    repository = DummyRepository()
    row = build_row(repository)

    settings = make_settings(tmp_path)

    with pytest.raises(ProcessingError) as error:
        process_row(
            row=row,
            sheet_cfg=base_sheet_cfg,
            assistants_client=assistants,
            image_pipeline=image_pipeline,
            brief_assistant_id=settings.global_image_brief_assistant_id,
            settings=settings,
        )

    assert "Ошибка генерации изображения" in str(error.value)
    assert row.values["Status"] == "Prepared"
