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
    PromptSet,
    is_moderator_approved,
    load_prompt_set,
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


def _build_shorten_prompt(text: str, max_chars: int) -> str:
    return (
        f"Сократи текст до не более {max_chars} символов с пробелами. "
        "Сохрани смысл, факты и читаемость. Верни только итоговый текст.\n\n"
        f"Текст:\n{text}"
    )


def process_row(
    row: SheetRow,
    sheet_cfg: SheetAssistants,
    assistants_client: AssistantsClient,
    image_pipeline: Optional[ImagePipeline],
    brief_model: Optional[str],
    prompts: Optional[PromptSet],
    settings: Settings,
) -> str:
    """Полностью обработать строку: текст, модерация, бриф и изображение."""
    if not row.title:
        raise ProcessingError("Столбец Title пустой, невозможно начать обработку")
    image_needed = settings.image_generation_enabled and sheet_cfg.generate_image

    if image_needed:
        if not brief_model:
            raise ProcessingError("Не задан ассистент художественного брифа")
        if not image_pipeline:
            raise ProcessingError("Клиент генерации изображений недоступен")
    content_limit = sheet_cfg.max_content_chars

    iteration = _parse_iteration(row.values.get("Iteration"))
    row.update({"Iteration": str(iteration)})

    logger.info(
        "Старт обработки строки %s на вкладке %s", row.row_index, sheet_cfg.tab
    )

    try:
        active_prompts = prompts
        if sheet_cfg.writer_system_prompt_path:
            active_prompts = load_prompt_set(
                writer_system_path=sheet_cfg.writer_system_prompt_path,
                moderator_system_path=sheet_cfg.moderator_system_prompt_path or settings.prompt_moderator_system_path,
                brief_system_path=sheet_cfg.brief_system_prompt_path or settings.prompt_brief_system_path,
                revision_template_path=sheet_cfg.revision_user_template_path or settings.prompt_revision_user_template_path,
            )
        writer_system = active_prompts.writer_system if active_prompts else ""
        draft = assistants_client.run_response(
            sheet_cfg.writer_model,
            row.title,
            writer_system,
            reasoning_effort=sheet_cfg.writer_reasoning_effort,
        )
    except AssistantRunError as error:
        raise ProcessingError(f"Ошибка писателя: {error}") from error

    # сохраняем текущий черновик сразу, чтобы его можно было увидеть рядом с комментарием
    row.update({"Content": draft})

    moderator_note = ""
    approved = False

    while True:
        try:
            moderator_system = active_prompts.moderator_system if active_prompts else ""
            moderator_reply = assistants_client.run_response(
                sheet_cfg.moderator_model, draft, moderator_system
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

        revision_prompt = (
            active_prompts.build_revision_prompt(draft, moderator_reply)
            if active_prompts
            else f"Текст:\n{draft}\n\nКомментарий:\n{moderator_reply}"
        )
        try:
            draft = assistants_client.run_response(
                sheet_cfg.writer_model,
                revision_prompt,
                writer_system,
                reasoning_effort=sheet_cfg.writer_reasoning_effort,
            )
        except AssistantRunError as error:
            raise ProcessingError(f"Ошибка писателя при доработке: {error}") from error

        row.update({"Content": draft})

    image_url = row.values.get("Image URL", "")
    if approved and content_limit and len(draft) > content_limit:
        for _ in range(settings.max_revisions):
            shorten_prompt = _build_shorten_prompt(draft, content_limit)
            try:
                draft = assistants_client.run_response(
                    sheet_cfg.writer_model,
                    shorten_prompt,
                    writer_system,
                    reasoning_effort=sheet_cfg.writer_reasoning_effort,
                )
            except AssistantRunError as error:
                raise ProcessingError(f"Ошибка писателя при сокращении: {error}") from error
            row.update({"Content": draft})
            if len(draft) <= content_limit:
                break
        if len(draft) > content_limit:
            raise ProcessingError(
                f"Не удалось уложить текст в лимит {content_limit} символов"
            )

    if image_needed:
        try:
            brief_system = active_prompts.brief_system if active_prompts else ""
            brief_prompt = assistants_client.run_response(brief_model, draft, brief_system)
        except AssistantRunError as error:
            raise ProcessingError(f"Ошибка ассистента брифа: {error}") from error

        try:
            image_url = image_pipeline.generate_and_upload(brief_prompt, row.title)
        except ImageGenerationError as error:
            raise ProcessingError(f"Ошибка генерации изображения: {error}") from error
    else:
        logger.info(
            "Генерация изображений отключена для вкладки %s, строка %s",
            sheet_cfg.tab,
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
