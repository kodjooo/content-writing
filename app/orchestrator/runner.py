"""Каркас оркестратора обработки строк."""

from app.config import Settings
from app.logging import get_logger

logger = get_logger(__name__)


def run_once(settings: Settings) -> None:
    """Заглушка для основного прохода обработки."""
    logger.info(
        "Обработчик готов к работе: вкладок в конфигурации %s", len(settings.sheets)
    )
