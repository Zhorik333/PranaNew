# PranaNew

Telegram-бот бронирования временных слотов для выдачи заказов.

## Текущий статус

Выполнена TASK-001 из бэклога: создана базовая структура проекта.

## Планируемый стек

- Python 3.11+
- aiogram 3.x
- PostgreSQL
- i18n: RU / EN / SR

## Установка зависимостей

```bash
# В WSL предпочтительно через uv, потому что python3 -m venv может быть без ensurepip.
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Альтернатива, если python3-venv установлен:
# python3 -m venv .venv
# source .venv/bin/activate
# python -m pip install -r requirements.txt
```

## Локальные проверки

```bash
.venv/bin/python -m compileall bot tests
.venv/bin/python -m unittest discover -s tests -v
```
