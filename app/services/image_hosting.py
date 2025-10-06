"""Клиент загрузки изображений на FreeImage.host."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import requests

from app.logging import get_logger
from app.utils.retry import create_retrying

logger = get_logger(__name__)

FREEIMAGE_ENDPOINT = "https://freeimage.host/api/1/upload"


class FreeImageHostError(RuntimeError):
    """Ошибка при обращении к FreeImage.host."""


class FreeImageHostClient:
    """Минимальный клиент FreeImage.host."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        *,
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._retryer = create_retrying(
            name="freeimage-upload",
            logger=logger,
            exceptions=(FreeImageHostError,),
            attempts=retry_attempts,
            base_delay=retry_base_delay,
            max_delay=retry_max_delay,
        )

    def _build_filename(self, title: str, extension: str = ".png") -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title).strip("_") or "image"
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return f"{slug}_{timestamp}{extension}"

    def upload_image(
        self,
        data: bytes,
        title: str,
        mime_type: str = "image/png",
        *,
        test_mode: bool = False,
    ) -> str:
        if test_mode:
            logger.info("Тестовый режим загрузки — возвращаем заглушку для %s", title)
            return "https://freeimage.host/images/test-placeholder.png"
        filename = self._build_filename(title, ".png" if mime_type == "image/png" else "")
        files = {"source": (filename, data, mime_type)}
        payload = {"type": "file"}
        if self._api_key:
            payload["key"] = self._api_key

        def _call() -> str:
            try:
                response = requests.post(
                    FREEIMAGE_ENDPOINT,
                    data=payload,
                    files=files,
                    timeout=self._timeout,
                )
            except requests.Timeout as error:
                raise FreeImageHostError(
                    "Превышено время ожидания ответа FreeImage.host"
                ) from error
            except requests.RequestException as error:
                raise FreeImageHostError(
                    "Не удалось выполнить запрос к FreeImage.host"
                ) from error

            try:
                response.raise_for_status()
            except requests.HTTPError as error:
                raise FreeImageHostError(
                    "Запрос к FreeImage.host завершился ошибкой"
                ) from error

            try:
                payload_json = response.json()
            except ValueError as error:
                raise FreeImageHostError(
                    "FreeImage.host вернул некорректный ответ"
                ) from error

            success_flag = payload_json.get("success")
            if isinstance(success_flag, str):
                success_flag_bool = success_flag.lower() == "true"
            elif isinstance(success_flag, dict):
                success_flag_bool = success_flag.get("code") == 200 or success_flag.get("message")
            else:
                success_flag_bool = bool(success_flag)
            success = payload_json.get("status_code") == 200 and bool(success_flag_bool)
            if not success:
                logger.warning("FreeImage.host error payload: %s", payload_json)
                error_info = payload_json.get("error")
                if isinstance(error_info, dict):
                    message = error_info.get("message") or str(error_info)
                elif error_info:
                    message = str(error_info)
                else:
                    message = "FreeImage.host вернул ошибку"
                logger.warning("FreeImage.host error: %s", message)
                raise FreeImageHostError(message)

            image_info = payload_json.get("image", {})
            link = image_info.get("url") or image_info.get("display_url")
            if not link:
                raise FreeImageHostError("FreeImage.host не вернул ссылку на изображение")
            return link

        return self._retryer(_call)


def create_image_host_client(api_key: Optional[str]) -> FreeImageHostClient:
    """Фабрика клиента FreeImage.host."""
    return FreeImageHostClient(api_key=api_key)
