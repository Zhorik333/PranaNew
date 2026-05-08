# PranaNew

Telegram-бот бронирования временных слотов для выдачи заказов.

Проект использует Python, aiogram 3 и PostgreSQL. Клиент выбирает один или несколько соседних слотов, подтверждает бронь, а администратор управляет слотами, заказами, отзывами, пользователями, текстами и настройками через Telegram.

## Что уже есть

- aiogram polling runtime с безопасным `delete_webhook(drop_pending_updates=True)`.
- PostgreSQL pool lifecycle.
- Клиентское меню, выбор языка RU/EN/SR, просмотр и выбор свободных слотов.
- Атомарное бронирование нескольких соседних слотов.
- Отмена, завершение заказа, уведомления админ-чата.
- Отзывы клиентов, модерация и публичная пагинация отзывов.
- Админские команды для слотов, заказов, пользователей, расписания и i18n-текстов.
- Структурированные JSON-логи без секретов.

## Быстрый локальный запуск

Все команды ниже рассчитаны на WSL и текущий локальный путь проекта:

```bash
cd /mnt/d/PranaNew
```

### 1. Установка зависимостей

В WSL предпочтительно использовать `uv`, потому что стандартный `python3 -m venv` может быть собран без `ensurepip`.

```bash
cd /mnt/d/PranaNew
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Если `python3-venv` доступен, можно использовать стандартный вариант:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Как создать .env

Скопируйте пример и отредактируйте файл локально. Не вставляйте токен бота в чат и не коммитьте `.env`.

```bash
cd /mnt/d/PranaNew
cp .env.example .env
nano .env
```

Переменные окружения:

- `BOT_TOKEN` — токен Telegram-бота из BotFather. Хранить только локально.
- `DATABASE_URL` — строка подключения к PostgreSQL. Пример формы: `postgresql://[REDACTED]:***@127.0.0.1:5432/[REDACTED]`.
- `ADMIN_CHAT_ID` — id Telegram-группы или чата администратора.
- `DEFAULT_LANGUAGE` — язык по умолчанию, обычно `ru`.
- `DEFAULT_TZ` — timezone, например `Europe/Belgrade`.
- `REVIEW_DELAY_MINUTES` — задержка перед запросом отзыва после завершения заказа.
- `LOG_LEVEL` — уровень логов, например `INFO`.

### 3. Создание базы данных

Проверьте, что `psql` доступен:

```bash
psql --version
```

Если `psql` не находится в `PATH`, используйте путь к своей локальной установке PostgreSQL или добавьте её `bin`-папку в `PATH`.

Создайте роль и базу под проект. Используйте свои локальные значения и не публикуйте пароль:

```bash
psql -h 127.0.0.1 -p 5432 -U postgres -d postgres
```

В открывшейся консоли PostgreSQL выполните команды с локальными именем роли, базы и паролем. Пароль ниже — только пример-заполнитель, замените его своим локальным значением:

```sql
CREATE ROLE your_role LOGIN PASSWORD '<your_local_password>';
CREATE DATABASE your_database OWNER your_role;
\q
```

После этого пропишите соответствующий `DATABASE_URL` в `.env`. В документации и коммитах используйте только безопасную форму без реального пароля.

### 4. Применение миграции

Миграция находится в `migrations/001_init.sql`. Применяйте её к пустой базе один раз:

```bash
cd /mnt/d/PranaNew
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_init.sql
```

Если `DATABASE_URL` не экспортирован в shell, можно временно загрузить его из `.env` локально, не печатая значение:

```bash
set -a
# Используйте этот способ только для локального `.env`, который вы создали сами.
source .env
set +a
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_init.sql
```

### 5. Как узнать ADMIN_CHAT_ID

1. Запустите бота локально.
2. Добавьте бота в админскую Telegram-группу.
3. Отправьте в этой группе команду `/chatid`.
4. Скопируйте полученный id в `.env` как `ADMIN_CHAT_ID`.
5. Перезапустите бота.

До настройки `ADMIN_CHAT_ID` админские команды не будут доступны в нужной группе.

### 6. Локальные проверки

Перед запуском и перед каждым коммитом выполняйте:

```bash
cd /mnt/d/PranaNew
.venv/bin/python -m compileall bot tests
.venv/bin/python -m unittest discover -s tests -v
```

### 7. Запуск бота

Запуск бота выполняется polling-командой:

```bash
cd /mnt/d/PranaNew
.venv/bin/python -m bot.main
```

Остановить локальный запуск можно через `Ctrl+C`.

## Основные команды в Telegram

Клиент:

- `/start` — открыть клиентское меню.
- Кнопка свободных слотов — выбрать время выдачи.
- Кнопка языка — переключить RU/EN/SR.
- Кнопка отзывов — посмотреть опубликованные отзывы.

Админ:

- `/chatid` — узнать id текущего чата.
- `/admin` — открыть админское меню.
- `/generate DATE STEP START END [CAPACITY]` — сгенерировать слоты.
- `/admin_slots DATE` — посмотреть слоты за дату.
- `/block_slot ID` и `/unblock_slot ID` — заблокировать или разблокировать слот.
- `/set_capacity ID CAPACITY` — изменить capacity слота.
- `/bookings DATE [active|completed|cancelled|all]` — список броней.
- `/booking ID` — детали брони.
- `/booking_status ID completed|cancelled` — изменить статус активной брони.
- `/users [search] [limit]` — список пользователей.
- `/user TG_ID` — карточка пользователя.
- `/user_history TG_ID [limit]` — история пользователя.
- `/reviews [pending|published|rejected|all] [limit]` — отзывы для модерации.
- `/review ID` — детали отзыва.
- `/review_status ID published|rejected` — опубликовать или отклонить отзыв.
- `/set_active_date YYYY-MM-DD`, `/active_date`, `/clear_active_date` — активная дата.
- `/set_schedule HH:MM HH:MM STEP_MINUTES CAPACITY` — настройки расписания.
- `/schedule_settings` — показать настройки расписания.
- `/set_text LANGUAGE KEY VALUE`, `/get_text LANGUAGE KEY`, `/clear_text LANGUAGE KEY` — редактирование i18n-текстов.

## Безопасность

- `.env` должен оставаться локальным и не попадать в git.
- Не публикуйте `BOT_TOKEN`, реальный `DATABASE_URL`, пароль БД и приватные chat id.
- В документации, тестах и логах используйте `[REDACTED]` или `***` вместо секретов.
- Перед пушем проверяйте `git status` и diff.

## Полезные файлы

- `.env.example` — пример переменных окружения без реальных секретов.
- `migrations/001_init.sql` — начальная миграция БД.
- `docs/database_schema.sql` — схема БД как дизайн-артефакт.
- `bot/main.py` — точка входа.
- `bot/config.py` — загрузка конфигурации.
- `bot/routers/` — Telegram handlers.
- `bot/services/` — бизнес-логика.
- `bot/repositories/` — SQL-доступ к данным.
- `tests/` — unittest-набор.
