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
    generate_image: bool = True

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
    schedule_enabled: bool = False
    schedule_time: str = "08:30"
    schedule_timezone: str = "Europe/Moscow"
    rss_schedule_times: tuple[str, ...] = field(default_factory=lambda: ("08:00", "20:00"))
    vk_schedule_days: tuple[int, ...] = field(default_factory=tuple)
    setka_schedule_days: tuple[int, ...] = field(default_factory=tuple)
    vk_schedule_time: str = "18:00"
    setka_schedule_time: str = "18:00"

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
                    sheets.append(
                        SheetAssistants(
                            tab=tab_name,
                            writer_assistant_id=item["writer_assistant_id"],
                            moderator_assistant_id=item["moderator_assistant_id"],
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

        rss_schedule_raw = os.getenv("RSS_SCHEDULE_TIMES", "08:00,20:00")
        rss_schedule_times = tuple(
            time.strip()
            for time in rss_schedule_raw.split(",")
            if time.strip()
        ) or ("08:00", "20:00")

        vk_days = _parse_schedule_days(os.getenv("VK_SCHEDULE_DAYS", ""))
        setka_days = _parse_schedule_days(os.getenv("SETKA_SCHEDULE_DAYS", ""))

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
            global_image_brief_assistant_id=os.getenv("GLOBAL_IMAGE_BRIEF_ASSISTANT_ID") or None,
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
            schedule_time=os.getenv("SCHEDULE_TIME", "08:30"),
            schedule_timezone=os.getenv("SCHEDULE_TIMEZONE", "Europe/Moscow"),
            rss_schedule_times=rss_schedule_times,
            vk_schedule_days=vk_days,
            setka_schedule_days=setka_days,
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


def _parse_schedule_days(raw_value: str) -> tuple[int, ...]:
    if not raw_value:
        return tuple()
    mapping = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }
    result = []
    for token in raw_value.split(","):
        key = token.strip().lower()
        if not key:
            continue
        if key not in mapping:
            raise ValueError(f"Неизвестный день недели в расписании: {token}")
        result.append(mapping[key])
    return tuple(sorted(set(result)))
