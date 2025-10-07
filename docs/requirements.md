1) Цель и общий принцип

При каждом запуске скрипт обрабатывает ровно одну строку со статусом Prepared в выбранной вкладке Google Sheets: берёт Title, отправляет его «писателю» (GPT-ассистент №1), результат — «модератору» (GPT-ассистент №2). Если модератор ответил «Ок», текст фиксируется в столбце Content. Если ответ не «Ок», скрипт формирует уточняющий запрос (оригинальный текст + комментарий модератора) и повторяет цикл до 5 раз. После финальной версии текст отправляется «художественному брифу» (GPT-ассистент №3), его ответ — в генерацию изображения, картинка загружается на FreeImage.host, ссылка записывается в строку. Статус проставляется в самом конце: либо Written, либо Written (not moderated).

2) Архитектура решения

Компоненты:
- Google Sheets: чтение/запись строк, выбор следующей строки со статусом Prepared.
- FreeImage.host: загрузка сгенерированного изображения и получение публичной ссылки.
- OpenAI (текст): вызовы Chat Completions API для трёх ролей (писатель, модератор, бриф).
- OpenAI (картинка): генерация через gpt-image-1.

Основные библиотеки Python: openai, gspread, google-auth, requests, tenacity, python-dotenv.

3) Конфигурация

Хранится в .env файле. Там задаются:
- openai: ключ
- google: spreadsheet_id, путь до service_account.json
- image_hosting: API-ключ FreeImage.host (опционально)
- processing: per_run_rows, max_revisions, lock_ttl_minutes
- schedule: флаг включения, время `HH:MM`, часовой пояс (по умолчанию Europe/Moscow)
- sheets: список вкладок и id ассистентов для каждой
- global_assistants: один ассистент для брифа

4) Структура таблицы

Обязательные столбцы: Title, Content, Image URL, Status, Iteration, Moderator Note, Lock.

5) Алгоритм обработки одной строки

1. Загрузка конфига и инициализация клиентов.
2. Поиск первой строки со статусом Prepared и пустым Lock, установка Lock.
3. Отправка Title писателю → draft.
4. Отправка draft модератору. Если ответ «Ок» → шаг 6. Иначе: собрать запрос в формате

Текст:
<ответ писателя>

Комментарий:
<ответ модератора>

отправить писателю, увеличить Iteration. Повторять пока не «Ок» или не 5 итераций.
5. Если лимит итераций достигнут — статус Written (not moderated).
6. Финальный текст отправить бриф-ассистенту.
7. На основании ответа бриф-ассистента генерировать картинку, загрузить на FreeImage.host, получить ссылку.
8. Записать Content и Image URL, очистить Lock, выставить финальный Status.

7) Вызовы OpenAI

Агентский вызов для текста делается через Assistants API. У каждого агента есть свой assistant_id, и чтобы получить ответ, нужно создать thread, добавить в него сообщение, запустить run и дождаться завершения. 

Пример функций:

from openai import OpenAI
import time

client = OpenAI()

def run_assistant(assistant_id: str, user_content: str, poll_interval: float = 1.0) -> str:
    # создаём тред
    thread = client.beta.threads.create()
    
    # добавляем сообщение пользователя
    client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=user_content
    )
    
    # запускаем ран
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id
    )
    
    # опрос до завершения
    while True:
        run_status = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        if run_status.status in ["completed", "failed", "cancelled", "expired"]:
            break
        time.sleep(poll_interval)
    
    # читаем последнее сообщение
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        return messages.data[0].content[0].text.value.strip()
    return ""

Использование:
draft = run_assistant(writer_assistant_id, title)
moderator_reply = run_assistant(moderator_assistant_id, draft)
brief = run_assistant(image_brief_assistant_id, draft)

images.generate используется для картинки.

def generate_image(model, prompt):
    img = client.images.generate(model=model, prompt=prompt, size="1792x1024")
    import base64
    return base64.b64decode(img.data[0].b64_json)

8) Google Sheets

Через gspread: открыть таблицу, найти Prepared + пустой Lock, поставить Lock. После завершения работы снять Lock и обновить Status.

9) FreeImage.host

Через HTTP API `https://freeimage.host/api/1/upload`: отправить изображение в формате multipart/form-data, передать ключ (если есть), получить из ответа публичную ссылку (`image.url` или `image.display_url`).

10) Детали модерации

Проверка ответа: приводим к нижнему регистру, обрезаем пробелы, принимаем ok/ок/okay/хорошо.

11) Управление итерациями

Каждый новый запрос писателю формируем в виде:

Текст:
<draft>

Комментарий:
<feedback>

12) Идемпотентность

Lock защищает от параллельных запусков. Использовать ретраи для API. Записи в Sheets делать батчами.

13) Каркас кода

def process_one_row(ctx):
    row = acquire_row(...)
    if not row: return
    draft = call_writer(...)
    iteration = 0
    while iteration <= max_rev:
        mod = call_moderator(...)
        if is_ok(mod): break
        iteration += 1
        if iteration > max_rev: break
        draft = call_writer(..., f"Текст:\n{draft}\n\nКомментарий:\n{mod}")
    brief = call_image_brief(...)
    img = generate_image(..., brief)
    link = upload_to_drive(..., img)
    write_cells(..., {"Content": draft, "Image URL": link})
    status = "Written" if is_ok(mod) else "Written (not moderated)"
    write_cells(..., {"Status": status})

14) Доступы

- OpenAI: ключ в переменной окружения.
- Google: сервис-аккаунт, доступ к таблице.
- FreeImage.host: API-ключ (если требуется привязка к аккаунту).

15) Имя файла

Формировать по Title + дата, хранить временные файлы в ./tmp и чистить после загрузки.

16) Тест-план

- Нет Prepared строк → скрипт завершает работу.
- Разные варианты написания «Ок».
- Комментарий модератора корректно вставляется.
- Лимит 5 итераций → Written (not moderated).
- Ошибки загрузки на хостинг → запись в Error и снятие Lock.

17) Рекомендации

Температура 0.4–0.8, короткие системные промты, строго проверять формат ответа модератора, использовать ретраи, батч-запись в Sheets.
