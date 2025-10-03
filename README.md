# Контент-пайплайн

Минимальный контур автоматизации генерации текстов и изображений на основе Google Sheets, OpenAI Assistants и FreeImage.host.

## Подготовка окружения
- Скопируйте `.env.example` в `.env` и заполните значения.
- Поместите `google-credentials.json` в каталог `secrets/` и установите `GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/google-credentials.json`.
- При необходимости задайте `FREEIMAGE_API_KEY` (для загрузки в авторизованный альбом FreeImage.host), иначе загрузка будет анонимной.
- Управляйте шагом генерации изображений переменными `IMAGE_GENERATION_ENABLED` (вкл/выкл), `IMAGE_TEST_MODE` (тестовый режим без вызова API), `IMAGE_MODEL`, `IMAGE_QUALITY`, `IMAGE_SIZE` и при необходимости отдельным ключом `IMAGE_OPENAI_API_KEY`. Для `gpt-image-1` доступны значения качества `low/medium/high/auto` и размеры `1024x1024/1024x1536/1536x1024/auto`; для `dall-e-3` — только `standard|hd` и `1024x1024` соответственно.
## Сборка и запуск
```bash
docker compose build
# однократная обработка строк
docker compose run --rm app
```

## Запуск тестов
```bash
docker compose run --rm app python -m pytest
```

## Планирование запуска
Пример cron-задания (ежечасно, с логом):
```
0 * * * * cd /path/to/content-writing && docker compose run --rm app >> /var/log/content-writing.log 2>&1
```
