# Контент-пайплайн

Минимальный контур автоматизации генерации текстов и изображений на основе Google Sheets, OpenAI Assistants и Google Drive.

## Подготовка окружения
- Скопируйте `.env.example` в `.env` и заполните значения.
- Поместите `service_account.json` в каталог `secrets/` и установите `GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/service_account.json`.
- При необходимости отключите генерацию изображений переменной `IMAGE_GENERATION_ENABLED=false`.

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
