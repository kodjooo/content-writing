"""Генерация изображений через OpenAI и выгрузка на внешний хостинг."""

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
from app.services.image_hosting import FreeImageHostClient
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
                response_format="b64_json",
            )
            if not response.data:
                raise ImageGenerationError("Сервис не вернул данных изображения")
            first_item = response.data[0]
            payload = getattr(first_item, "b64_json", None)
            if not payload:
                raise ImageGenerationError("Ответ не содержит base64 изображения")
            return base64.b64decode(payload)

        try:
            return self._retryer(_call)
        except (OpenAIError, ImageGenerationError) as error:  # type: ignore[arg-type]
            raise ImageGenerationError("Не удалось сгенерировать изображение") from error


class ImagePipeline:
    """Комбинирует генератор и клиент загрузки изображений."""

    def __init__(
        self,
        generator: ImageGenerator,
        uploader: FreeImageHostClient,
        *,
        test_mode: bool = False,
    ) -> None:
        self._generator = generator
        self._uploader = uploader
        self._test_mode = test_mode

    def generate_and_upload(
        self,
        prompt: str,
        title: str,
        mime_type: str = "image/png",
        size: Optional[str] = None,
    ) -> str:
        """Сгенерировать изображение и загрузить его на внешний хостинг."""
        if self._test_mode:
            return self._uploader.upload_image(
                b"", title=title, mime_type=mime_type, test_mode=True
            )

        image_bytes = self._generator.generate(prompt, size=size)
        return self._uploader.upload_image(
            image_bytes, title=title, mime_type=mime_type, test_mode=False
        )
