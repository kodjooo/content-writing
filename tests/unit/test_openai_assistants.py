"""Юнит-тесты утилит для OpenAI Assistants."""

import pytest

from app.services.openai_assistants import (
    build_revision_prompt,
    is_moderator_approved,
    normalize_moderator_reply,
)


@pytest.mark.parametrize(
    "value, expected",
    [
        (" Ок ", "ок"),
        ("OK", "ok"),
        ("  Хорошо", "хорошо"),
    ],
)
def test_normalize_moderator_reply(value: str, expected: str) -> None:
    """Проверяем, что нормализация убирает пробелы и приводит к нижнему регистру."""
    assert normalize_moderator_reply(value) == expected


@pytest.mark.parametrize(
    "value, approved",
    [
        ("ок", True),
        ("Ок", True),
        ("okay", True),
        ("хорошо", True),
        ("да", False),
        ("", False),
    ],
)
def test_is_moderator_approved(value: str, approved: bool) -> None:
    """Проверяем, что распознаются все допустимые варианты подтверждения."""
    assert is_moderator_approved(value) is approved


def test_build_revision_prompt() -> None:
    """Шаблон доработки должен содержать текст и комментарий на отдельных блоках."""
    prompt = build_revision_prompt("Черновик", "Добавить детали")
    assert prompt.startswith("Текст:\nЧерновик")
    assert "Комментарий:\nДобавить детали" in prompt
