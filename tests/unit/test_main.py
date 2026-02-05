"""Тесты запуска основного модуля и планировщика."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import main as app_main
from app.config.settings import Settings, SheetAssistants


def make_settings(tmp_path: Path, *, run_on_start: bool) -> Settings:
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
        schedule_enabled=True,
        run_on_start=run_on_start,
        schedule_time="00:00",
        schedule_timezone="UTC",
    )


def test_run_on_start_runs_before_schedule_sleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path, run_on_start=True)
    calls: list[str] = []

    monkeypatch.setattr(app_main, "run_once", lambda _: calls.append("run"))
    monkeypatch.setattr(app_main.time, "sleep", lambda _: (_ for _ in ()).throw(RuntimeError("stop")))

    with pytest.raises(RuntimeError, match="stop"):
        app_main._run_with_schedule(settings)

    assert calls == ["run"]


def test_run_on_start_false_skips_initial_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = make_settings(tmp_path, run_on_start=False)
    calls: list[str] = []

    monkeypatch.setattr(app_main, "run_once", lambda _: calls.append("run"))
    monkeypatch.setattr(app_main.time, "sleep", lambda _: (_ for _ in ()).throw(RuntimeError("stop")))

    with pytest.raises(RuntimeError, match="stop"):
        app_main._run_with_schedule(settings)

    assert calls == []
