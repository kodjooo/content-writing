"""Каркас оркестратора обработки строк."""

from __future__ import annotations

from typing import Optional

from gspread.exceptions import GSpreadException

from app.config import Settings
from app.logging import get_logger
from app.orchestrator.processor import ProcessingError, process_row
from app.services import (
    AssistantsClient,
    AssistantsConfig,
    FreeImageHostError,
    ImageGenerationConfig,
    ImageGenerator,
    ImagePipeline,
    create_image_host_client,
    create_sheets_repository,
)

logger = get_logger(__name__)


def _init_assistants(settings: Settings) -> AssistantsClient:
    config = AssistantsConfig(
        api_key=settings.openai_api_key,
        org_id=settings.openai_org_id,
        project_id=settings.openai_project_id,
    )
    return AssistantsClient(config)


def _init_image_pipeline(settings: Settings) -> ImagePipeline:
    generator = ImageGenerator(
        ImageGenerationConfig(
            api_key=settings.image_openai_api_key or settings.openai_api_key,
            org_id=settings.openai_org_id,
            project_id=settings.openai_project_id,
            quality=settings.image_quality,
            size=settings.image_size,
            model=settings.image_model,
        )
    )
    uploader = create_image_host_client(settings.image_host_api_key)
    return ImagePipeline(
        generator,
        uploader,
        test_mode=settings.image_test_mode,
    )


def run_once(settings: Settings) -> None:
    """Обработать до `per_run_rows` строк со статусом Prepared."""
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

    try:
        assistants_client = _init_assistants(settings)
    except Exception as error:  # noqa: BLE001
        logger.error("Не удалось инициализировать клиента Assistants: %s", error)
        return

    image_pipeline: Optional[ImagePipeline] = None
    if settings.image_generation_enabled:
        try:
            image_pipeline = _init_image_pipeline(settings)
        except FreeImageHostError as error:
            logger.error("Не удалось инициализировать клиент загрузки изображений: %s", error)
            return
        except Exception as error:  # noqa: BLE001
            logger.error("Не удалось подготовить генерацию изображений: %s", error)
            return
    else:
        logger.info("Генерация изображений отключена, шаг загрузки будет пропущен")

    max_rows = settings.per_run_rows if settings.per_run_rows > 0 else 1
    processed = 0

    while processed < max_rows:
        row_found = False
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
            if not row:
                continue

            row_found = True
            try:
                status_value = process_row(
                    row=row,
                    sheet_cfg=sheet_cfg,
                    assistants_client=assistants_client,
                    image_pipeline=image_pipeline,
                    brief_assistant_id=settings.global_image_brief_assistant_id,
                    settings=settings,
                )
                processed += 1
                logger.info(
                    "Строка %s вкладки %s завершена со статусом %s",
                    row.row_index,
                    sheet_cfg.tab,
                    status_value,
                )
            except ProcessingError as error:
                logger.error(
                    "Ошибка обработки строки %s вкладки %s: %s",
                    row.row_index,
                    sheet_cfg.tab,
                    error,
                )
                try:
                    row.update({
                        "Status": "Error",
                        "Moderator Note": str(error),
                    })
                except Exception as update_error:  # noqa: BLE001
                    logger.warning(
                        "Не удалось записать ошибку в строку %s: %s",
                        row.row_index,
                        update_error,
                    )
            except Exception as error:  # noqa: BLE001
                logger.exception(
                    "Непредвиденная ошибка при обработке строки %s вкладки %s",
                    row.row_index,
                    sheet_cfg.tab,
                )
                try:
                    row.update({
                        "Status": "Error",
                        "Moderator Note": str(error),
                    })
                except Exception as update_error:  # noqa: BLE001
                    logger.warning(
                        "Не удалось записать непредвиденную ошибку в строку %s: %s",
                        row.row_index,
                        update_error,
                    )
            finally:
                try:
                    sheets_repo.release_lock(row)
                except Exception as release_error:  # noqa: BLE001
                    logger.warning(
                        "Не удалось снять Lock для строки %s: %s",
                        row.row_index,
                        release_error,
                    )
            break

        if not row_found:
            if processed == 0:
                logger.info("Нет строк со статусом Prepared для обработки")
            else:
                logger.info("Новые строки для обработки отсутствуют")
            break
