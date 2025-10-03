"""Загрузка учётных данных сервисного аккаунта Google."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from google.oauth2.service_account import Credentials


SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)


def load_credentials(service_account_file: Path, scopes: Sequence[str] | None = None) -> Credentials:
    """Прочитать файл сервисного аккаунта и вернуть Credentials."""
    target_scopes = list(scopes) if scopes else list(SCOPES)
    return Credentials.from_service_account_file(
        str(service_account_file), scopes=target_scopes
    )
