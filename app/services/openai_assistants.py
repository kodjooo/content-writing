"""Клиент Responses API и утилиты работы с текстовыми пайплайнами."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
    """Ошибка при взаимодействии с OpenAI."""


@dataclass
class AssistantsConfig:
    """Параметры клиента Responses API."""

    api_key: str
    default_model: str
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    retry_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 10.0


class AssistantsClient:
    """Высокоуровневый клиент для вызовов OpenAI Responses API."""

    def __init__(self, config: AssistantsConfig) -> None:
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            organization=config.org_id,
            project=config.project_id,
        )
        self._retryer = create_retrying(
            name="responses",
            logger=logger,
            exceptions=(OpenAIError, AssistantRunError),
            attempts=config.retry_attempts,
            base_delay=config.retry_base_delay,
            max_delay=config.retry_max_delay,
        )

    def run_assistant(self, assistant_id: str, message: str, system_prompt: str = "") -> str:
        """Сохранено для совместимости: assistant_id используется как model."""
        return self.run_response(model=assistant_id, user_message=message, system_prompt=system_prompt)

    def run_response(
        self,
        model: Optional[str],
        user_message: str,
        system_prompt: str = "",
        reasoning_effort: Optional[str] = None,
    ) -> str:
        """Отправить запрос в Responses API и вернуть текст ответа."""
        target_model = model or self._config.default_model
        logger.debug("Запуск модели %s через Responses API", target_model)

        def _call() -> str:
            input_parts = []
            if system_prompt.strip():
                input_parts.append({"role": "system", "content": system_prompt})
            input_parts.append({"role": "user", "content": user_message})

            params = {
                "model": target_model,
                "input": input_parts,
            }
            if reasoning_effort:
                params["reasoning"] = {"effort": reasoning_effort}
            response = self._client.responses.create(**params)

            text = getattr(response, "output_text", "")
            if text and text.strip():
                return text.strip()
            raise AssistantRunError("Модель не вернула текстовый ответ")

        try:
            return self._retryer(_call)
        except (OpenAIError, AssistantRunError) as error:  # type: ignore[arg-type]
            raise AssistantRunError("Не удалось получить ответ от Responses API") from error


@dataclass(frozen=True)
class PromptSet:
    writer_system: str
    moderator_system: str
    brief_system: str
    revision_user_template: str

    def build_revision_prompt(self, draft: str, feedback: str) -> str:
        return self.revision_user_template.format(draft=draft, feedback=feedback)


def load_prompt_set(
    writer_system_path: Path,
    moderator_system_path: Path,
    brief_system_path: Path,
    revision_template_path: Path,
) -> PromptSet:
    return PromptSet(
        writer_system=writer_system_path.read_text(encoding="utf-8").strip(),
        moderator_system=moderator_system_path.read_text(encoding="utf-8").strip(),
        brief_system=brief_system_path.read_text(encoding="utf-8").strip(),
        revision_user_template=revision_template_path.read_text(encoding="utf-8").strip(),
    )


def normalize_moderator_reply(reply: str) -> str:
    return reply.strip().lower()


def is_moderator_approved(reply: str) -> bool:
    normalized = normalize_moderator_reply(reply)
    return normalized in APPROVAL_RESPONSES


def build_revision_prompt(draft: str, feedback: str) -> str:
    return f"Текст:\n{draft}\n\nКомментарий:\n{feedback}"
