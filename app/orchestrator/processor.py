"""Логика обработки одной строки контент-пайплайна."""

from __future__ import annotations

from typing import Optional

from app.config.settings import Settings, SheetAssistants
from app.logging import get_logger
from app.services import (
    AssistantsClient,
    ImagePipeline,
    AssistantRunError,
    ImageGenerationError,
    build_revision_prompt,
    is_moderator_approved,
)
from app.services.google_sheets import SheetRow

logger = get_logger(__name__)


class ProcessingError(RuntimeError):
    """Ошибка во время обработки строки."""


def _parse_iteration(raw_value: Optional[str]) -> int:
    try:
        return int(raw_value) if raw_value is not None and raw_value != "" else 0
    except (TypeError, ValueError):
        return 0


def process_row(
    row: SheetRow,
    sheet_cfg: SheetAssistants,
    assistants_client: AssistantsClient,
    image_pipeline: Optional[ImagePipeline],
    brief_assistant_id: Optional[str],
    settings: Settings,
) -> str:
    """Полностью обработать строку: текст, модерация, бриф и изображение."""
    if not row.title:
        raise ProcessingError("Столбец Title пустой, невозможно начать обработку")
    if settings.image_generation_enabled:
        if not brief_assistant_id:
            raise ProcessingError("Не задан ассистент художественного брифа")
        if not image_pipeline:
            raise ProcessingError("Клиент генерации изображений недоступен")

    iteration = _parse_iteration(row.values.get("Iteration"))
    row.update({"Iteration": str(iteration)})

    logger.info(
        "Старт обработки строки %s на вкладке %s", row.row_index, sheet_cfg.tab
    )

    try:
        draft = assistants_client.run_assistant(sheet_cfg.writer_assistant_id, row.title)
    except AssistantRunError as error:
        raise ProcessingError(f"Ошибка писателя: {error}") from error

    moderator_note = ""
    approved = False

    while True:
        try:
            moderator_reply = assistants_client.run_assistant(
                sheet_cfg.moderator_assistant_id, draft
            )
        except AssistantRunError as error:
            raise ProcessingError(f"Ошибка модератора: {error}") from error

        moderator_note = moderator_reply
        row.update({"Moderator Note": moderator_note})

        if is_moderator_approved(moderator_reply):
            approved = True
            break

        iteration += 1
        row.update({"Iteration": str(iteration)})
        if iteration >= settings.max_revisions:
            logger.warning(
                "Достигнут лимит итераций (%s) для строки %s",
                settings.max_revisions,
                row.row_index,
            )
            break

        revision_prompt = build_revision_prompt(draft, moderator_reply)
        try:
            draft = assistants_client.run_assistant(
                sheet_cfg.writer_assistant_id, revision_prompt
            )
        except AssistantRunError as error:
            raise ProcessingError(f"Ошибка писателя при доработке: {error}") from error

    image_url = ""
    if settings.image_generation_enabled:
        try:
            brief_prompt = assistants_client.run_assistant(brief_assistant_id, draft)
        except AssistantRunError as error:
            raise ProcessingError(f"Ошибка ассистента брифа: {error}") from error

        try:
            image_url = image_pipeline.generate_and_upload(brief_prompt, row.title)
        except ImageGenerationError as error:
            raise ProcessingError(f"Ошибка генерации изображения: {error}") from error
    else:
        logger.info(
            "Генерация изображений отключена настройкой, шаг пропускается для строки %s",
            row.row_index,
        )

    status_value = "Written" if approved else "Written (not moderated)"
    row.update(
        {
            "Content": draft,
            "Image URL": image_url,
            "Status": status_value,
            "Iteration": str(iteration),
            "Moderator Note": moderator_note,
        }
    )

    logger.info(
        "Строка %s обработана, статус: %s", row.row_index, status_value
    )
    return status_value
