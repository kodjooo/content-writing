# Контент-пайплайн

Минимальный контур автоматизации генерации текстов и изображений на основе Google Sheets, OpenAI Assistants и FreeImage.host.

## Подготовка окружения
- Скопируйте `.env.example` в `.env` и заполните значения.
- Поместите `google-credentials.json` в каталог `secrets/` и установите `GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/google-credentials.json`.
- При необходимости задайте `FREEIMAGE_API_KEY` (для загрузки в авторизованный альбом FreeImage.host), иначе загрузка будет анонимной.
- Управляйте шагом генерации изображений переменными `IMAGE_GENERATION_ENABLED` (вкл/выкл), `IMAGE_TEST_MODE` (тестовый режим без вызова API), `IMAGE_MODEL`, `IMAGE_QUALITY`, `IMAGE_SIZE` и при необходимости отдельным ключом `IMAGE_OPENAI_API_KEY`. Для `gpt-image-1` доступны значения качества `low/medium/high/auto` и размеры `1024x1024/1024x1536/1536x1024/auto`; для `dall-e-3` — только `standard|hd` и `1024x1024` соответственно.
- Для отключения генерации изображений на конкретных вкладках укажите их в `IMAGE_DISABLED_TABS` (список через запятую, имена вкладок без учёта регистра).
- Для управления расписанием публикаций используйте:
  - `RSS_SCHEDULE_TIMES` — времена (через запятую) для обработки вкладки RSS, ежедневно (по умолчанию `08:00,20:00`).
  - `VK_SCHEDULE_DAYS` — дни недели (`Mon,Tue,...`) для запуска вкладки VK в 18:00 по МСК.
  - `SETKA_SCHEDULE_DAYS` — аналогично для вкладки Setka (также 18:00 по МСК).
- Для автоматического ежедневного запуска установите `SCHEDULE_ENABLED=true` (по умолчанию время `SCHEDULE_TIME=08:30`, часовой пояс `SCHEDULE_TIMEZONE=Europe/Moscow`).

## Развёртывание на удалённом сервере
1. Подготовьте сервер:
   - Установите Git, Docker и Docker Compose (version 2+).
   - Убедитесь, что пользователь добавлен в группу `docker` или запускайте команды с `sudo`.
2. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/kodjooo/content-writing.git
   cd content-writing
   ```
3. Настройте переменные окружения:
   - Скопируйте `.env.example` в `.env` и заполните значения (ключи OpenAI, Google Sheets, FreeImage.host, расписание).
   - Поместите файл сервисного аккаунта Google (`google-credentials.json`) в каталог `secrets/`.
4. Соберите Docker-образ и проверьте:
   ```bash
   docker compose build
   docker compose run --rm app python -m pytest
   ```
5. Запуск в разовом режиме:
   ```bash
   docker compose run --rm app
   ```
6. Запуск в режиме планировщика (ежедневно в заданное время):
   ```bash
   docker compose up -d app
   ```
   Приложение останется в фоне и будет выполнять обработку автоматически. Логи можно смотреть командой `docker compose logs -f app`.
7. Обновление версии:
   ```bash
   git pull
   docker compose build
   docker compose up -d app
   ```

## Сборка и запуск
```bash
docker compose build
# однократная обработка строк
docker compose run --rm app
# непрерывный режим с внутренним планировщиком
docker compose up app
```

## Запуск тестов
```bash
docker compose run --rm app python -m pytest
```

## Планирование запуска
При `SCHEDULE_ENABLED=true` приложение запускается ежедневно в указанное время (по умолчанию 08:30 Europe/Moscow) без использования cron. Достаточно выполнить `docker compose up app` и оставить сервис запущенным.
