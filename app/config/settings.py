"""Объекты и функции для загрузки конфигурации приложения."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv


def _require_env(name: str) -> str:
    """Получить обязательную переменную окружения или выбросить исключение."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Переменная окружения {name} обязательна")
    return value


@dataclass(frozen=True)
class SheetAssistants:
    """Конфигурация ассистентов для отдельной вкладки Google Sheets."""

    tab: str
    writer_assistant_id: str
    moderator_assistant_id: str

    def ensure_complete(self) -> None:
        if not self.writer_assistant_id or not self.moderator_assistant_id:
            raise ValueError(
                f"Для вкладки {self.tab} должны быть указаны writer_assistant_id и moderator_assistant_id"
            )


@dataclass(frozen=True)
class Settings:
    """Собранные настройки приложения."""

    openai_api_key: str
    openai_org_id: Optional[str]
    openai_project_id: Optional[str]
    spreadsheet_id: str
    service_account_file: Path
    drive_folder_id: str
    per_run_rows: int
    max_revisions: int
    lock_ttl_minutes: int
    sheets: List[SheetAssistants] = field(default_factory=list)
    global_image_brief_assistant_id: Optional[str] = None
    temp_dir: Path = field(default_factory=lambda: Path("./tmp"))
    log_level: str = "INFO"
    image_generation_enabled: bool = True
    image_quality: str = "high"
    image_size: str = "1536x1024"
    image_model: str = "gpt-image-1"
    image_host_api_key: Optional[str] = None
    image_test_mode: bool = False
    image_openai_api_key: Optional[str] = None

    @classmethod
    def load(cls) -> "Settings":
        """Загрузить конфигурацию из `.env` и переменных окружения."""
        load_dotenv()

        sheet_configs_raw = os.getenv("SHEETS_CONFIG", "").strip()
        sheets: List[SheetAssistants] = []
        if sheet_configs_raw:
            try:
                parsed = json.loads(sheet_configs_raw)
                for item in parsed:
                    sheets.append(
                        SheetAssistants(
                            tab=item["tab"],
                            writer_assistant_id=item["writer_assistant_id"],
                            moderator_assistant_id=item["moderator_assistant_id"],
                        )
                    )
            except (json.JSONDecodeError, KeyError) as error:
                raise ValueError("Не удалось разобрать переменную SHEETS_CONFIG") from error

        temp_dir = Path(os.getenv("TEMP_DIR", "./tmp")).resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)

        service_account_file = Path(_require_env("GOOGLE_SERVICE_ACCOUNT_FILE")).expanduser().resolve()

        max_revisions_value = _get_int_env(
            primary="MODERATOR_MAX_ITERATIONS",
            fallback="PROCESSING_MAX_REVISIONS",
            default=5,
        )

        return cls(
            openai_api_key=_require_env("OPENAI_API_KEY"),
            openai_org_id=os.getenv("OPENAI_ORG_ID") or None,
            openai_project_id=os.getenv("OPENAI_PROJECT_ID") or None,
            spreadsheet_id=_require_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
            service_account_file=service_account_file,
            drive_folder_id=_require_env("GOOGLE_DRIVE_FOLDER_ID"),
            per_run_rows=int(os.getenv("PROCESSING_PER_RUN_ROWS", "1")),
            max_revisions=max_revisions_value,
            lock_ttl_minutes=int(os.getenv("PROCESSING_LOCK_TTL_MINUTES", "15")),
            sheets=sheets,
            global_image_brief_assistant_id=os.getenv("GLOBAL_IMAGE_BRIEF_ASSISTANT_ID") or None,
            temp_dir=temp_dir,
            log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
            image_generation_enabled=_env_flag("IMAGE_GENERATION_ENABLED", True),
            image_quality=os.getenv("IMAGE_QUALITY", "high"),
            image_size=os.getenv("IMAGE_SIZE", "1536x1024"),
            image_model=os.getenv("IMAGE_MODEL", "gpt-image-1"),
            image_host_api_key=os.getenv("FREEIMAGE_API_KEY") or None,
            image_test_mode=_env_flag("IMAGE_TEST_MODE", False),
            image_openai_api_key=os.getenv("IMAGE_OPENAI_API_KEY") or None,
        )

    def get_assistants_for_tab(self, tab_name: str) -> SheetAssistants:
        for item in self.sheets:
            if item.tab == tab_name:
                item.ensure_complete()
                return item
        raise KeyError(f"Конфигурация ассистентов для вкладки {tab_name} не найдена")
def _env_flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int_env(*, primary: str, fallback: str, default: int) -> int:
    """Получить целое значение из переменных окружения с запасным именем."""

    raw_value = os.getenv(primary)
    if raw_value is None or raw_value.strip() == "":
        raw_value = os.getenv(fallback)

    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        return int(raw_value)
    except ValueError as error:  # pragma: no cover - защитное приведение типов
        raise ValueError(
            f"Некорректное числовое значение для переменной {primary}"
        ) from error
