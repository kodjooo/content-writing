# Контент-пайплайн

Сервис автоматизирует выпуск контента из Google Sheets: генерирует текст через OpenAI Assistants, прогоняет модерацию, при необходимости создает изображение и записывает результат обратно в строку.

## Что делает сервис
- Берет первую доступную строку со статусом `Prepared` и ставит `Lock` с TTL.
- Вызывает ассистента-писателя по `Title` и сохраняет черновик в `Content`.
- Запускает цикл модерации до одобрения (`ok/ок/okay/хорошо`) или достижения лимита итераций.
- При включенной генерации изображений вызывает ассистента брифа, генерирует изображение и загружает его на FreeImage.host.
- Выставляет финальный статус:
  - `Written`
  - `Written (not moderated)`
  - `Error` (при исключении на уровне оркестратора)
- Всегда снимает `Lock` после попытки обработки.

## Контракт таблицы Google Sheets
Обязательные столбцы для всех вкладок:
- `Title`
- `Content`
- `Image URL`
- `Status`
- `Iteration`
- `Moderator Note`
- `Lock`
- `Post Link`

Для вкладки `vk` (без учета регистра имени вкладки) дополнительно обязательны:
- `Status Dzen`
- `Publish Note`

## Переменные окружения
Обязательные:
- `OPENAI_API_KEY`
- `GOOGLE_SHEETS_SPREADSHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_FILE`

Ключевые опциональные:
- OpenAI: `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`, `IMAGE_OPENAI_API_KEY`
- Обработка: `PROCESSING_PER_RUN_ROWS`, `PROCESSING_LOCK_TTL_MINUTES`
- Лимит итераций: `MODERATOR_MAX_ITERATIONS` (fallback: `PROCESSING_MAX_REVISIONS`)
- Конфиг вкладок: `SHEETS_CONFIG`, `IMAGE_DISABLED_TABS`, `GLOBAL_IMAGE_BRIEF_ASSISTANT_ID`
- Изображения: `IMAGE_GENERATION_ENABLED`, `IMAGE_TEST_MODE`, `IMAGE_MODEL`, `IMAGE_QUALITY`, `IMAGE_SIZE`, `FREEIMAGE_API_KEY`
- Планировщик: `SCHEDULE_ENABLED`, `RUN_ON_START`, `SCHEDULE_TIME`, `SCHEDULE_TIMEZONE`
- Прочее: `TEMP_DIR`, `LOG_LEVEL`

`SHEETS_CONFIG` задается JSON-массивом объектов:
```json
[
  {
    "tab": "VK",
    "writer_assistant_id": "asst_writer",
    "moderator_assistant_id": "asst_moderator"
  }
]
```

`IMAGE_DISABLED_TABS` — список вкладок через запятую, где генерация изображения будет отключена даже при `IMAGE_GENERATION_ENABLED=true`.

## Поведение генерации изображений
- Глобально включается/выключается через `IMAGE_GENERATION_ENABLED`.
- В тестовом режиме `IMAGE_TEST_MODE=true` внешний вызов генерации/загрузки не выполняется, возвращается тестовая ссылка.
- Используется модель из `IMAGE_MODEL`:
  - `gpt-image-1`: качество `low|medium|high|auto`, размеры `1024x1024|1024x1536|1536x1024|auto`
  - `dall-e-3`: качество `standard|hd`, размер `1024x1024`

## Подготовка
1. Заполните `.env` по примеру `.env.example`.
2. Положите `google-credentials.json` в `secrets/`.
3. Убедитесь, что путь в `GOOGLE_SERVICE_ACCOUNT_FILE` доступен внутри контейнера (обычно `/app/secrets/google-credentials.json`).

## Запуск через Docker
```bash
docker compose build
```

Разовый запуск:
```bash
docker compose run --rm app
```

Непрерывный запуск с планировщиком:
```bash
docker compose up -d app
```

Логи:
```bash
docker compose logs -f app
```

## Тесты
```bash
docker compose run --rm app python -m pytest
```

## Режимы расписания
- `SCHEDULE_ENABLED=false`: только один запуск и выход.
- `SCHEDULE_ENABLED=true`: ежедневный запуск в `SCHEDULE_TIME`/`SCHEDULE_TIMEZONE`.
- `RUN_ON_START=true`: в режиме расписания сначала выполняется немедленный запуск, потом ежедневный цикл.
