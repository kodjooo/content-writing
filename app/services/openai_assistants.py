"""Функции и клиент для работы с OpenAI Assistants."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

try:
    from openai import OpenAIError
except ImportError:  # fallback для совместимости версий
    OpenAIError = Exception  # type: ignore

from app.logging import get_logger
from app.utils.retry import create_retrying

logger = get_logger(__name__)

APPROVAL_RESPONSES = {"ok", "ок", "okay", "хорошо"}


class AssistantRunError(RuntimeError):
    """Ошибка при взаимодействии с ассистентом."""


@dataclass
class AssistantsConfig:
    """Параметры клиента Assistants."""

    api_key: str
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    poll_interval: float = 1.0
    timeout: Optional[float] = None
    retry_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 10.0


class AssistantsClient:
    """Высокоуровневый клиент для вызовов Assistants API."""

    def __init__(self, config: AssistantsConfig) -> None:
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            organization=config.org_id,
            project=config.project_id,
        )
        self._retryer = create_retrying(
            name="assistants",
            logger=logger,
            exceptions=(OpenAIError, AssistantRunError),
            attempts=config.retry_attempts,
            base_delay=config.retry_base_delay,
            max_delay=config.retry_max_delay,
        )

    def run_assistant(self, assistant_id: str, message: str) -> str:
        """Отправить сообщение ассистенту и вернуть текст ответа."""
        logger.debug("Запуск ассистента %s", assistant_id)
        def _call() -> str:
            thread = self._client.beta.threads.create()
            self._client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=message,
            )
            run = self._client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id,
            )
            response_status = self._wait_for_completion(thread.id, run.id)
            if response_status != "completed":
                raise AssistantRunError(
                    f"Ассистент завершился со статусом {response_status}"
                )
            return self._extract_text(thread.id)

        try:
            return self._retryer.call(_call)
        except (OpenAIError, AssistantRunError) as error:  # type: ignore[arg-type]
            raise AssistantRunError(
                "Не удалось получить ответ от ассистента"
            ) from error

    def _wait_for_completion(self, thread_id: str, run_id: str) -> str:
        started = time.monotonic()
        while True:
            run = self._client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run_id,
            )
            status = run.status
            if status in {"completed", "failed", "cancelled", "expired", "requires_action"}:
                return status
            if self._config.timeout is not None and (
                time.monotonic() - started
            ) > self._config.timeout:
                raise AssistantRunError("Превышено время ожидания ответа ассистента")
            time.sleep(self._config.poll_interval)

    def _extract_text(self, thread_id: str) -> str:
        messages = self._client.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",
            limit=5,
        )
        for message in messages.data:
            if message.role != "assistant":
                continue
            chunks = []
            for block in message.content:
                if getattr(block, "type", None) == "text":
                    text_value = getattr(getattr(block, "text", None), "value", None)
                    if text_value:
                        chunks.append(text_value)
            if chunks:
                return "\n\n".join(chunks).strip()
        raise AssistantRunError("Ассистент не вернул текстовый ответ")


def normalize_moderator_reply(reply: str) -> str:
    """Привести ответ модератора к канонической форме."""
    return reply.strip().lower()


def is_moderator_approved(reply: str) -> bool:
    """Проверить, является ли ответ модератора подтверждением."""
    normalized = normalize_moderator_reply(reply)
    return normalized in APPROVAL_RESPONSES


def build_revision_prompt(draft: str, feedback: str) -> str:
    """Сформировать запрос для повторного обращения к писателю."""
    return f"Текст:\n{draft}\n\nКомментарий:\n{feedback}"
