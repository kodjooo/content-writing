"""Клиент загрузки изображений на FreeImage.host."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import requests

from app.logging import get_logger

logger = get_logger(__name__)

FREEIMAGE_ENDPOINT = "https://freeimage.host/api/1/upload"


class FreeImageHostError(RuntimeError):
    """Ошибка при обращении к FreeImage.host."""


class FreeImageHostClient:
    """Минимальный клиент FreeImage.host."""

    def __init__(self, api_key: Optional[str] = None, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def _build_filename(self, title: str, extension: str = ".png") -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title).strip("_") or "image"
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        return f"{slug}_{timestamp}{extension}"

    def upload_image(self, data: bytes, title: str, mime_type: str = "image/png") -> str:
        filename = self._build_filename(title, ".png" if mime_type == "image/png" else "")
        files = {"source": (filename, data, mime_type)}
        payload = {"type": "file"}
        if self._api_key:
            payload["key"] = self._api_key

        response = requests.post(
            FREEIMAGE_ENDPOINT,
            data=payload,
            files=files,
            timeout=self._timeout,
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise FreeImageHostError("Запрос к FreeImage.host завершился ошибкой") from error

        payload_json = response.json()
        success = payload_json.get("status_code") == 200 and payload_json.get("success") in {True, "true"}
        if not success:
            message = payload_json.get("error", {}).get("message") or "FreeImage.host вернул ошибку"
            raise FreeImageHostError(message)

        image_info = payload_json.get("image", {})
        link = image_info.get("url") or image_info.get("display_url")
        if not link:
            raise FreeImageHostError("FreeImage.host не вернул ссылку на изображение")
        return link


def create_image_host_client(api_key: Optional[str]) -> FreeImageHostClient:
    """Фабрика клиента FreeImage.host."""
    return FreeImageHostClient(api_key=api_key)
