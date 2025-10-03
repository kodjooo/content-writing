# Контент-пайплайн

Минимальный контур автоматизации генерации текстов и изображений на основе Google Sheets, OpenAI Assistants и Google Drive.

## Подготовка окружения
- Скопируйте `.env.example` в `.env` и заполните значения.
- Поместите `google-credentials.json` в каталог `secrets/` и установите `GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/google-credentials.json`.
- Управляйте шагом генерации изображений переменными `IMAGE_GENERATION_ENABLED` (вкл/выкл), `IMAGE_MODEL` (например, `gpt-image-1`, `dall-e-3`), `IMAGE_QUALITY` (`low`/`medium`/`high`/`auto`) и `IMAGE_SIZE` (`1024x1024`/`1024x1536`/`1536x1024`/`auto`).
- Для моделей семейства `dall-e` допускаются только `IMAGE_QUALITY=standard|hd` и `IMAGE_SIZE=1024x1024`.
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
