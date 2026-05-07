# Архитектура контент-пайплайна

## 1. Обзор
Приложение состоит из модулей пакета `app` и запускается через `python -m app.main`.
Главный сценарий: найти строку `Prepared`, выполнить цепочку Responses API, при необходимости сгенерировать и загрузить изображение, записать итог в Google Sheets.

## 2. Точка входа и режимы запуска
Файл: `app/main.py`
- Загружает настройки через `Settings.load()`.
- Настраивает логирование.
- Выбирает режим:
  - разовый запуск (`run_once`) при `SCHEDULE_ENABLED=false`;
  - ежедневный встроенный планировщик при `SCHEDULE_ENABLED=true`.
- Планировщик:
  - интерпретирует `SCHEDULE_TIME` в формате `HH:MM`;
  - использует `SCHEDULE_TIMEZONE` через `pytz`;
  - при `RUN_ON_START=true` выполняет немедленный запуск перед циклом ожидания.

## 3. Конфигурация
Файл: `app/config/settings.py`
- Источник конфигурации: `.env` + переменные окружения.
- Обязательные поля:
  - `OPENAI_API_KEY`
  - `GOOGLE_SHEETS_SPREADSHEET_ID`
  - `GOOGLE_SERVICE_ACCOUNT_FILE`
- Парсит `SHEETS_CONFIG` (JSON-массив) в список `SheetAssistants`.
- Применяет `IMAGE_DISABLED_TABS` для отключения генерации по вкладкам.
- `max_revisions` читается из `MODERATOR_MAX_ITERATIONS` с fallback на `PROCESSING_MAX_REVISIONS`.
- Нормализует параметры генерации изображений (`IMAGE_MODEL`, `IMAGE_QUALITY`, `IMAGE_SIZE`).

## 4. Оркестратор
Файл: `app/orchestrator/runner.py`

### 4.1 Инициализация
- Проверяет существование файла сервисного аккаунта.
- Инициализирует:
  - `SheetsRepository`
  - `AssistantsClient` (обертка над Responses API)
  - `PromptSet` (загрузка промптов из файлов)
  - `ImagePipeline` (если `IMAGE_GENERATION_ENABLED=true`)

### 4.2 Цикл `run_once`
- Обходит вкладки из `settings.sheets`.
- Для каждой вкладки вызывает `acquire_prepared_row(...)`.
- Обрабатывает максимум `per_run_rows` строк (`<=0` означает без ограничения).
- При ошибке `process_row` записывает в строку:
  - `Status=Error`
  - `Moderator Note=<ошибка>`
- В блоке `finally` всегда вызывает `release_lock(row)`.

## 5. Процессор строки
Файл: `app/orchestrator/processor.py`

### 5.1 Поток обработки
1. Проверяет `Title`.
2. Определяет, нужна ли генерация изображения (`IMAGE_GENERATION_ENABLED` + `sheet_cfg.generate_image`).
3. Инициализирует `Iteration` и записывает в таблицу.
4. Вызывает писателя и сохраняет черновик в `Content`.
5. Запускает цикл модерации:
- пишет `Moderator Note` после каждой проверки;
- при неуспехе увеличивает `Iteration`;
- строит prompt доработки через шаблон `prompts/revision_user_template.txt`;
- останавливается на одобрении или лимите итераций.
6. После одобрения модератора, если задан `max_content_chars` для вкладки, дополнительно проверяет длину текста (символы с пробелами) и при превышении отправляет писателю запрос на сокращение до лимита без повторной модерации.
6. При включенной генерации:
- вызывает модель брифа;
- генерирует изображение;
- загружает его на FreeImage.host.
7. Финально обновляет: `Content`, `Image URL`, `Status`, `Iteration`, `Moderator Note`.

### 5.2 Статусы
- `Written` — если модератор одобрил.
- `Written (not moderated)` — если лимит итераций достигнут без одобрения.

## 6. Работа с Google Sheets
Файл: `app/services/google_sheets.py`
- Авторизация через сервисный аккаунт (`google_auth.load_credentials`).
- Кеширует контекст вкладки (worksheet + headers).
- Валидирует обязательные столбцы:
  - базовые для всех вкладок;
  - дополнительные `Status Dzen`, `Publish Note` для вкладки `vk`.
- `acquire_prepared_row(...)`:
  - ищет первую строку `Status=Prepared`;
  - проверяет `Lock` на просрочку;
  - выставляет новый `Lock` с TTL (`PROCESSING_LOCK_TTL_MINUTES`).
- `release_lock(...)` очищает `Lock`.

## 7. OpenAI Responses API
Файл: `app/services/openai_assistants.py`
- `AssistantsClient.run_response(...)`:
  - отправляет `system` + `user` сообщения в `client.responses.create(...)`;
  - получает итоговый текст из `output_text`;
  - выполняет ретраи на ошибках OpenAI.
- Промпты вынесены в отдельные файлы:
  - `prompts/writer_system.txt`
  - `prompts/moderator_system.txt`
  - `prompts/brief_system.txt`
  - `prompts/revision_user_template.txt`
- Загрузка промптов выполняется через `load_prompt_set(...)`.

## 8. Пайплайн изображений
Файлы:
- `app/services/image_generation.py`
- `app/services/image_hosting.py`

### 8.1 Генерация
- `ImageGenerator` вызывает `client.images.generate(...)`.
- Поддерживает модели и параметры из env.
- Обрабатывает разные форматы payload (`b64_json`) и декодирует bytes.
- Сетевые ошибки оборачиваются в `ImageGenerationError`.

### 8.2 Загрузка
- `FreeImageHostClient.upload_image(...)` отправляет `multipart/form-data` на FreeImage.host.
- Формирует имя файла из `title + timestamp`.
- Валидирует структуру ответа и извлекает `image.url` или `image.display_url`.
- В `test_mode` возвращает заглушку без сетевого вызова.

### 8.3 Композиция
- `ImagePipeline.generate_and_upload(...)` объединяет генерацию и загрузку.

## 9. Надежность и ретраи
Файл: `app/utils/retry.py`
- Единая фабрика `create_retrying(...)` на `tenacity`.
- Применяется в сервисах Google Sheets, Assistants, Images и FreeImage.host.

## 10. Тестовая структура
- `tests/unit`:
  - утилиты модерации/ревизий;
  - логика lock/required columns;
  - планировщик (`RUN_ON_START`).
- `tests/integration`:
  - сценарии `process_row` с фейковыми клиентами;
  - сценарий `run_once` без строк для обработки.

## 11. Docker-контур
- `Dockerfile`: базовый образ `python:3.12-slim`, установка зависимостей из `requirements.txt`, запуск `python -m app.main`.
- `docker-compose.yml`: сервис `app`, подключение `.env`, volume для `tmp` и `secrets`.
