# 📋 Smart Control — Система контроля поручений

Веб-платформа для автоматизации контроля исполнения поручений. Загружайте PDF-протоколы, система автоматически распознаёт пункты, исполнителей и сроки, а затем отображает всё на наглядном дашборде.

---

## ✨ Возможности

- 📄 **Автоматический парсинг PDF** — загрузите протокол, система извлечёт пункты, ФИО исполнителей и сроки
- 📊 **Дашборд** — визуализация статусов через Chart.js (В работе / Просрочено / Выполнено)
- ➕ **Ручное добавление поручений** — форма для добавления задач без PDF
- 📥 **Экспорт в Excel** — красиво оформленная таблица с цветовым выделением строк
- 🔴 **Автоматические статусы** — задачи с истёкшим сроком автоматически помечаются «Просрочено»
- 🐳 **Docker-развёртывание** — Flask + PostgreSQL в контейнерах

---

## 🚀 Быстрый старт

### Требования

- [Docker](https://www.docker.com/) + Docker Compose

### Запуск

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd task_control

# 2. Запустить контейнеры
docker compose up -d

# 3. Открыть в браузере
http://localhost:5200
```

### Остановка

```bash
docker compose down
```

---

## 🗂️ Структура проекта

```
task_control/
├── app/
│   ├── main.py              # Flask приложение, все маршруты
│   ├── models.py            # SQLAlchemy модели (Task, Executor, FileDocument)
│   ├── routes.py            # Дополнительные Blueprint маршруты
│   ├── parser/
│   │   └── pdf_engine.py    # Движок парсинга PDF (pdfplumber + PyPDF2 fallback)
│   ├── services/
│   │   ├── watcher.py       # Мониторинг папки для автоматической загрузки
│   │   └── notifier.py      # SMTP-уведомления о дедлайнах
│   └── templates/
│       ├── index.html       # Страница загрузки PDF (с прогресс-баром)
│       ├── dashboard.html   # Дашборд с таблицей и графиком
│       └── add_task.html    # Форма ручного добавления поручения
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .gitignore
```

---

## 📡 API Маршруты

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/` | Страница загрузки PDF |
| `POST` | `/upload` | Загрузка и парсинг PDF (JSON ответ) |
| `GET` | `/dashboard` | Дашборд |
| `GET` | `/task/add` | Форма ручного добавления |
| `POST` | `/task/add` | Сохранить поручение вручную |
| `POST` | `/task/<id>/status` | Обновить статус задачи |
| `GET` | `/export/excel` | Скачать Excel-отчёт |
| `GET` | `/api/stats` | JSON-статистика |

---

## ⚙️ Конфигурация

Настройки задаются через переменные окружения в `docker-compose.yml`:

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `DATABASE_URL` | `postgresql://user:password@db:5432/taskdb` | Строка подключения к БД |
| `SECRET_KEY` | `dev-secret-key-change-in-prod` | Flask Secret Key |
| `FLASK_ENV` | `development` | Режим Flask |

> ⚠️ **В production** обязательно смените `SECRET_KEY` и пароли БД!

---

## 📤 Формат PDF для парсинга

Парсер ищет в документе:

- **Пункты** по шаблону: `5.1.`, `10.4.2.` (номер с точками в начале строки)
- **Исполнителя** в скобках: `(Иванов И.О.)` или `(Иванов Иван Иванович)`
- **Срок** по шаблонам:
  - `Срок до 28 февраля 2026`
  - `Срок до 28.02.2026`
  - `Срок до 2026-02-28`

---

## 🐳 Полезные Docker команды

```bash
# Посмотреть логи Flask
docker compose logs web -f

# Пересобрать после изменений в requirements.txt
docker compose down
docker compose build web
docker compose up -d

# Подключиться к PostgreSQL
docker compose exec db psql -U user -d taskdb

# Выполнить SQL напрямую
docker compose exec db psql -U user -d taskdb -c "SELECT * FROM tasks LIMIT 5;"
```

---

## 🛠️ Локальная разработка (без Docker)

```bash
# Установить зависимости
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Запустить с SQLite
set DATABASE_URL=sqlite:///tasks.db
cd app
flask run --host=0.0.0.0 --port=5000
```

---

## 📦 Зависимости

| Пакет | Назначение |
|-------|-----------|
| `Flask` | Веб-фреймворк |
| `Flask-SQLAlchemy` | ORM для работы с БД |
| `psycopg2-binary` | Драйвер PostgreSQL |
| `pdfplumber` | Высококачественное извлечение текста из PDF |
| `PyPDF2` | Fallback-парсер PDF |
| `openpyxl` | Генерация Excel-файлов |
| `watchdog` | Мониторинг папки с файлами |

---

## 📝 Лицензия

MIT License — свободное использование и модификация.
