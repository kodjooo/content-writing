"""Генерация изображений через OpenAI и выгрузка в Google Drive."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

try:
    from openai import OpenAIError
except ImportError:  # совместимость разных версий SDK
    OpenAIError = Exception  # type: ignore

from app.logging import get_logger
from app.services.google_drive import GoogleDriveClient
from app.utils.retry import create_retrying

logger = get_logger(__name__)


class ImageGenerationError(RuntimeError):
    """Ошибка генерации изображения."""


@dataclass
class ImageGenerationConfig:
    """Настройки генерации изображений."""

    api_key: str
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    model: str = "gpt-image-1"
    size: str = "1536x1024"
    quality: str = "high"
    retry_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 10.0


class ImageGenerator:
    """Обёртка над OpenAI Images API."""

    def __init__(self, config: ImageGenerationConfig) -> None:
        self._config = config
        self._client = OpenAI(
            api_key=config.api_key,
            organization=config.org_id,
            project=config.project_id,
        )
        self._retryer = create_retrying(
            name="image-generation",
            logger=logger,
            exceptions=(OpenAIError, ImageGenerationError),
            attempts=config.retry_attempts,
            base_delay=config.retry_base_delay,
            max_delay=config.retry_max_delay,
        )

    def generate(self, prompt: str, size: Optional[str] = None) -> bytes:
        """Сгенерировать изображение по описанию и вернуть бинарные данные."""
        def _call() -> bytes:
            response = self._client.images.generate(
                model=self._config.model,
                prompt=prompt,
                size=size or self._config.size,
                quality=self._config.quality,
            )
            if not response.data:
                raise ImageGenerationError("Сервис не вернул данных изображения")
            payload = response.data[0].get("b64_json")  # type: ignore[index]
            if not payload:
                raise ImageGenerationError("Ответ не содержит base64 изображения")
            return base64.b64decode(payload)

        try:
            return self._retryer(_call)
        except (OpenAIError, ImageGenerationError) as error:  # type: ignore[arg-type]
            raise ImageGenerationError("Не удалось сгенерировать изображение") from error


class ImagePipeline:
    """Комбинирует генератор и клиент Google Drive."""

    def __init__(self, generator: ImageGenerator, drive_client: GoogleDriveClient) -> None:
        self._generator = generator
        self._drive = drive_client

    def generate_and_upload(
        self,
        prompt: str,
        title: str,
        mime_type: str = "image/png",
        size: Optional[str] = None,
    ) -> str:
        """Сгенерировать изображение и загрузить его в Google Drive."""
        image_bytes = self._generator.generate(prompt, size=size)
        return self._drive.upload_image(image_bytes, title=title, mime_type=mime_type)
