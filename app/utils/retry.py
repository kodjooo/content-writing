"""Утилиты для настройки повторов сетевых операций."""

from __future__ import annotations

from typing import Iterable, Tuple, Type

from tenacity import (  # type: ignore
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)


def create_retrying(
    *,
    name: str,
    logger,
    exceptions: Iterable[Type[BaseException]] | Tuple[Type[BaseException], ...] = (Exception,),
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
) -> Retrying:
    """Создать настроенный ретраер для сетевых операций."""

    exc_tuple = tuple(exceptions)

    def _log_retry(state: RetryCallState) -> None:  # pragma: no cover - логирование
        if state.outcome is None:
            return
        exception = state.outcome.exception()
        if exception is None:
            return
        logger.warning(
            "%s: повтор %s/%s после ошибки: %s",
            name,
            state.attempt_number,
            attempts,
            exception,
        )

    return Retrying(
        retry=retry_if_exception_type(exc_tuple),
        stop=stop_after_attempt(attempts),
        wait=wait_random_exponential(multiplier=base_delay, max=max_delay),
        before_sleep=_log_retry,
        reraise=True,
    )
