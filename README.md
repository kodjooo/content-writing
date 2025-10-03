# Контент-пайплайн

Минимальный контур автоматизации генерации текстов и изображений на основе Google Sheets, OpenAI Assistants и Google Drive.

## Подготовка окружения
- Скопируйте `.env.example` в `.env` и заполните значения.
- Поместите `google-credentials.json` в каталог `secrets/` и установите `GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/google-credentials.json`.
- Управляйте шагом генерации изображений переменными `IMAGE_GENERATION_ENABLED` (вкл/выкл) и `IMAGE_QUALITY` (`low`/`medium`/`high`/`auto`).
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
