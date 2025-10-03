"""Клиент Google Drive для загрузки изображений."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.logging import get_logger
from app.services.google_auth import load_credentials

logger = get_logger(__name__)

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


class GoogleDriveError(RuntimeError):
    """Ошибка при работе с Google Drive."""


class GoogleDriveClient:
    """Высокоуровневый клиент Google Drive для загрузки файлов."""

    def __init__(
        self,
        service_account_file: Path,
        folder_id: str,
        temp_dir: Path,
    ) -> None:
        self._credentials = load_credentials(
            service_account_file, scopes=[DRIVE_SCOPE]
        )
        self._folder_id = folder_id
        self._temp_dir = temp_dir
        self._service = None

    def _get_service(self):
        if self._service is None:
            try:
                self._service = build(
                    "drive",
                    "v3",
                    credentials=self._credentials,
                    cache_discovery=False,
                )
            except HttpError as error:
                raise GoogleDriveError("Не удалось создать клиент Google Drive") from error
        return self._service

    def generate_filename(self, title: str, extension: str = ".png") -> str:
        """Сформировать имя файла на основе заголовка и времени."""
        normalized = "_".join(title.strip().split()) or "content"
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        salt = hashlib.sha1(f"{title}{timestamp}{random.random()}".encode()).hexdigest()[:6]
        return f"{normalized}_{timestamp}_{salt}{extension}"

    def _save_temp(self, data: bytes, filename: str) -> Path:
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._temp_dir / filename
        temp_path.write_bytes(data)
        return temp_path

    def _cleanup_file(self, path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError as error:
            logger.warning("Не удалось удалить временный файл %s: %s", path, error)

    def cleanup_temp_dir(self) -> None:
        """Удалить все файлы во временном каталоге."""
        if not self._temp_dir.exists():
            return
        for item in self._temp_dir.iterdir():
            if item.is_file():
                self._cleanup_file(item)

    def upload_image(
        self,
        data: bytes,
        title: str,
        mime_type: str = "image/png",
        filename: Optional[str] = None,
    ) -> str:
        """Загрузить изображение и вернуть публичную ссылку."""
        service = self._get_service()
        name = filename or self.generate_filename(title)
        temp_path = self._save_temp(data, name)

        try:
            media = MediaFileUpload(str(temp_path), mimetype=mime_type, resumable=False)
            metadata = {"name": name, "parents": [self._folder_id]}
            created = (
                service.files()
                .create(body=metadata, media_body=media, fields="id, webViewLink")
                .execute()
            )
            file_id = created.get("id")
            if not file_id:
                raise GoogleDriveError("Google Drive не вернул идентификатор файла")

            try:
                service.permissions().create(
                    fileId=file_id,
                    body={"type": "anyone", "role": "reader"},
                    fields="id",
                ).execute()
            except HttpError as error:
                logger.warning(
                    "Не удалось выставить публичный доступ для файла %s: %s", file_id, error
                )

            link = created.get("webViewLink")
            if not link:
                link_response = (
                    service.files()
                    .get(fileId=file_id, fields="webViewLink")
                    .execute()
                )
                link = link_response.get("webViewLink")
            if not link:
                raise GoogleDriveError("Не удалось получить ссылку на изображение")
            return link
        except HttpError as error:
            raise GoogleDriveError("Ошибка при загрузке изображения в Google Drive") from error
        finally:
            self._cleanup_file(temp_path)


def create_drive_client(
    service_account_file: Path,
    folder_id: str,
    temp_dir: Path,
) -> GoogleDriveClient:
    """Фабрика клиента Google Drive."""
    return GoogleDriveClient(
        service_account_file=service_account_file,
        folder_id=folder_id,
        temp_dir=temp_dir,
    )
