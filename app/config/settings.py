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
    writer_model: str
    moderator_model: str
    writer_system_prompt_path: Optional[Path] = None
    moderator_system_prompt_path: Optional[Path] = None
    brief_system_prompt_path: Optional[Path] = None
    revision_user_template_path: Optional[Path] = None
    max_content_chars: Optional[int] = None
    writer_reasoning_effort: Optional[str] = None
    generate_image: bool = True

    def ensure_complete(self) -> None:
        if not self.writer_model or not self.moderator_model:
            raise ValueError(
                f"Для вкладки {self.tab} должны быть указаны writer_model и moderator_model"
            )


@dataclass(frozen=True)
class Settings:
    """Собранные настройки приложения."""

    openai_api_key: str
    openai_org_id: Optional[str]
    openai_project_id: Optional[str]
    spreadsheet_id: str
    service_account_file: Path
    per_run_rows: int
    max_revisions: int
    lock_ttl_minutes: int
    sheets: List[SheetAssistants] = field(default_factory=list)
    global_image_brief_model: Optional[str] = None
    prompt_writer_system_path: Path = field(default_factory=lambda: Path("./prompts/writer_system.txt"))
    prompt_moderator_system_path: Path = field(default_factory=lambda: Path("./prompts/moderator_system.txt"))
    prompt_brief_system_path: Path = field(default_factory=lambda: Path("./prompts/brief_system.txt"))
    prompt_revision_user_template_path: Path = field(default_factory=lambda: Path("./prompts/revision_user_template.txt"))
    temp_dir: Path = field(default_factory=lambda: Path("./tmp"))
    log_level: str = "INFO"
    image_generation_enabled: bool = True
    image_quality: str = "high"
    image_size: str = "1536x1024"
    image_model: str = "gpt-image-1"
    image_host_api_key: Optional[str] = None
    image_test_mode: bool = False
    image_openai_api_key: Optional[str] = None
    schedule_enabled: bool = False
    run_on_start: bool = False
    schedule_time: str = "08:30"
    schedule_timezone: str = "Europe/Moscow"
    debug_log_text_limit: int = 4500

    @classmethod
    def load(cls) -> "Settings":
        """Загрузить конфигурацию из `.env` и переменных окружения."""
        load_dotenv()

        sheet_configs_raw = os.getenv("SHEETS_CONFIG", "").strip()
        disabled_tabs_raw = os.getenv("IMAGE_DISABLED_TABS", "")
        disabled_tabs = {
            tab.strip().lower()
            for tab in disabled_tabs_raw.split(",")
            if tab.strip()
        }
        sheets: List[SheetAssistants] = []
        if sheet_configs_raw:
            try:
                parsed = json.loads(sheet_configs_raw)
                for item in parsed:
                    tab_name = item["tab"]
                    writer_prompt = item.get("writer_system_prompt_path")
                    moderator_prompt = item.get("moderator_system_prompt_path")
                    brief_prompt = item.get("brief_system_prompt_path")
                    revision_prompt = item.get("revision_user_template_path")
                    sheets.append(
                        SheetAssistants(
                            tab=tab_name,
                            writer_model=item["writer_model"],
                            moderator_model=item["moderator_model"],
                            writer_system_prompt_path=Path(writer_prompt).resolve() if writer_prompt else None,
                            moderator_system_prompt_path=Path(moderator_prompt).resolve() if moderator_prompt else None,
                            brief_system_prompt_path=Path(brief_prompt).resolve() if brief_prompt else None,
                            revision_user_template_path=Path(revision_prompt).resolve() if revision_prompt else None,
                            max_content_chars=_to_optional_int(item.get("max_content_chars")),
                            writer_reasoning_effort=_to_reasoning_effort(item.get("writer_reasoning_effort")),
                            generate_image=item.get(
                                "generate_image",
                                tab_name.strip().lower() not in disabled_tabs,
                            ),
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

        raw_image_quality = os.getenv("IMAGE_QUALITY", "high")
        image_quality = raw_image_quality.lower().strip() if raw_image_quality else "high"
        if not image_quality:
            image_quality = "high"

        raw_image_size = os.getenv("IMAGE_SIZE", "1536x1024") or "1536x1024"
        image_size = raw_image_size.replace(" ", "").replace("X", "x")

        return cls(
            openai_api_key=_require_env("OPENAI_API_KEY"),
            openai_org_id=os.getenv("OPENAI_ORG_ID") or None,
            openai_project_id=os.getenv("OPENAI_PROJECT_ID") or None,
            spreadsheet_id=_require_env("GOOGLE_SHEETS_SPREADSHEET_ID"),
            service_account_file=service_account_file,
            per_run_rows=int(os.getenv("PROCESSING_PER_RUN_ROWS", "1")),
            max_revisions=max_revisions_value,
            lock_ttl_minutes=int(os.getenv("PROCESSING_LOCK_TTL_MINUTES", "15")),
            sheets=sheets,
            global_image_brief_model=os.getenv("GLOBAL_IMAGE_BRIEF_MODEL") or None,
            prompt_writer_system_path=Path(os.getenv("PROMPT_WRITER_SYSTEM_PATH", "./prompts/writer_system.txt")).resolve(),
            prompt_moderator_system_path=Path(os.getenv("PROMPT_MODERATOR_SYSTEM_PATH", "./prompts/moderator_system.txt")).resolve(),
            prompt_brief_system_path=Path(os.getenv("PROMPT_BRIEF_SYSTEM_PATH", "./prompts/brief_system.txt")).resolve(),
            prompt_revision_user_template_path=Path(
                os.getenv("PROMPT_REVISION_USER_TEMPLATE_PATH", "./prompts/revision_user_template.txt")
            ).resolve(),
            temp_dir=temp_dir,
            log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
            image_generation_enabled=_env_flag("IMAGE_GENERATION_ENABLED", True),
            image_quality=image_quality,
            image_size=image_size,
            image_model=os.getenv("IMAGE_MODEL", "gpt-image-1"),
            image_host_api_key=os.getenv("FREEIMAGE_API_KEY") or None,
            image_test_mode=_env_flag("IMAGE_TEST_MODE", False),
            image_openai_api_key=os.getenv("IMAGE_OPENAI_API_KEY") or None,
            schedule_enabled=_env_flag("SCHEDULE_ENABLED", False),
            run_on_start=_env_flag("RUN_ON_START", False),
            schedule_time=os.getenv("SCHEDULE_TIME", "08:30"),
            schedule_timezone=os.getenv("SCHEDULE_TIMEZONE", "Europe/Moscow"),
            debug_log_text_limit=int(os.getenv("DEBUG_LOG_TEXT_LIMIT", "4500")),
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


def _to_optional_int(raw_value: object) -> Optional[int]:
    if raw_value is None:
        return None
    if isinstance(raw_value, int):
        return raw_value if raw_value > 0 else None
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return None
        parsed = int(value)
        return parsed if parsed > 0 else None
    raise ValueError("max_content_chars должен быть положительным числом")


def _to_reasoning_effort(raw_value: object) -> Optional[str]:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise ValueError("writer_reasoning_effort должен быть строкой")
    value = raw_value.strip().lower()
    if not value:
        return None
    allowed = {"minimal", "low", "medium", "high"}
    if value not in allowed:
        raise ValueError(
            f"writer_reasoning_effort должен быть одним из: {', '.join(sorted(allowed))}"
        )
    return value
