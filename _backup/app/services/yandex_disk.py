"""
Сервис интеграции с Яндекс.Диском.
Сканирует указанную папку, определяет отправителя и дату получения отчёта,
сохраняет в БД и обновляет статусы задач.
"""
import os
import re
import logging
import hashlib
from datetime import datetime
from difflib import SequenceMatcher

import requests

# ─── Настройки ────────────────────────────────────────────────────────────────
YANDEX_API_BASE = "https://cloud-api.yandex.net/v1/disk/resources"
YANDEX_TOKEN = os.environ.get("YANDEX_DISK_TOKEN", "")
YANDEX_FOLDER = os.environ.get("YANDEX_DISK_FOLDER", "/SmartControl/Отчёты")
SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.jpg', '.png', '.zip')


class YandexDiskClient:
    """Обёртка над REST API Яндекс.Диска"""

    def __init__(self, token=None):
        self.token = token or YANDEX_TOKEN
        self.headers = {"Authorization": f"OAuth {self.token}"}

    def _check_token(self):
        if not self.token:
            raise ValueError("Токен Яндекс.Диска не задан. "
                             "Укажите переменную окружения YANDEX_DISK_TOKEN")

    def test_connection(self):
        """Проверить подключение к Яндекс.Диску"""
        self._check_token()
        try:
            resp = requests.get(
                "https://cloud-api.yandex.net/v1/disk",
                headers=self.headers, timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True,
                    "user": data.get("user", {}).get("display_name", "Неизвестно"),
                    "total_space": data.get("total_space", 0),
                    "used_space": data.get("used_space", 0),
                }
            else:
                return {"ok": False, "error": f"Код ответа: {resp.status_code}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_files(self, folder_path=None, limit=100):
        """Получить список файлов в папке на Яндекс.Диске и по публичным ссылкам"""
        files = []
        
        # Сканируем приватную папку только если есть токен
        if self.token:
            folder = folder_path or YANDEX_FOLDER
            params = {
                "path": folder,
                "limit": limit,
                "fields": "_embedded.items.name,_embedded.items.path,"
                          "_embedded.items.type,_embedded.items.size,"
                          "_embedded.items.created,_embedded.items.modified,"
                          "_embedded.items.md5,_embedded.items.mime_type"
            }
            resp = requests.get(YANDEX_API_BASE, headers=self.headers, params=params, timeout=15)
            if resp.status_code != 200:
                logging.error(f"Ошибка Яндекс.Диска ({resp.status_code}): {resp.text}")
            else:
                data = resp.json()
                items = data.get("_embedded", {}).get("items", [])
        
                # Рекурсивный обход подпапок
                for item in items:
                    if item["type"] == "dir":
                        # Обход подпапок (например: /Отчёты/Иванов/)
                        sub_files = self.list_files(item["path"], limit)
                        # Добавляем имя подпапки как возможного отправителя
                        for sf in sub_files:
                            if not sf.get("_folder_sender"):
                                sf["_folder_sender"] = item["name"]
                        files.extend(sub_files)
                    elif item["type"] == "file":
                        name_lower = item["name"].lower()
                        if any(name_lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                            files.append(item)

        # Подгружаем публичные папки районов (РАБОТАЕТ БЕЗ ТОКЕНА)
        if folder_path is None:
            try:
                from services.districts import DISTRICTS
                for district_name, public_link in DISTRICTS.items():
                    files.extend(self.get_public_files(public_link, district_name))
            except Exception as e:
                logging.error(f"Ошибка загрузки публичных ссылок: {e}")

        # Если нет токена и никто не вернул файлы из паблик папок, сообщаем
        if not self.token and not files and folder_path is None:
             logging.warning("Токен не задан. Сканирование приватных папок отключено, публичные папки пусты.")

        return files

    def get_public_files(self, public_key, sender_name):
        """Получить список файлов из публичной папки (Яндекс.Диск)"""
        import hashlib
        # _check_token() ЗДЕСЬ НЕ НУЖЕН, так как API публичное
        url = "https://cloud-api.yandex.net/v1/disk/public/resources"
        params = {
            "public_key": public_key,
            "limit": 100,
            "fields": "_embedded.items.name,_embedded.items.path,_embedded.items.type,_embedded.items.size,_embedded.items.created,_embedded.items.modified,_embedded.items.md5"
        }
        
        headers = {}
        if self.token:
            headers = self.headers

        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            logging.error(f"Ошибка Яндекс.Диска для публичной ссылки {public_key}: {resp.text}")
            return []

        data = resp.json()
        items = data.get("_embedded", {}).get("items", [])
        
        files = []
        for item in items:
            if item.get("type") == "file":
                name_lower = item.get("name", "").lower()
                if any(name_lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                    # Проставляем отправителя по названию публичной папки
                    item["_folder_sender"] = sender_name
                    # Искусственный путь, так как у публичных файлов он может быть скрыт
                    item["path"] = f"/public/{sender_name}/{item['name']}"
                    if not item.get("md5"):
                        item["md5"] = hashlib.md5(f"{sender_name}:{item['name']}".encode()).hexdigest()
                    files.append(item)
        return files

    def get_download_link(self, path):
        """Получить ссылку для скачивания файла"""
        self._check_token()
        resp = requests.get(
            f"{YANDEX_API_BASE}/download",
            headers=self.headers,
            params={"path": path},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("href")
        return None


def _extract_sender_from_filename(filename):
    """
    Извлечь имя отправителя из имени файла.
    Поддерживаемые паттерны:
      - Иванов_отчет_2026.pdf
      - Иванов И.И._отчет.pdf
      - отчет_Иванов.pdf
      - Иванов Иван Иванович_отчет.pdf
    """
    # Убираем расширение
    name = os.path.splitext(filename)[0]

    # Паттерн 1: ФИО в начале (до _, -, пробела+отчёт/отч/report)
    match = re.match(
        r'^([А-ЯЁа-яё]+(?:\s+[А-ЯЁ]\.?[А-ЯЁа-яё]?\.?)?(?:\s+[А-ЯЁа-яё]+)*?)[\s_\-]+'
        r'(?:отч[её]т|report|отч)',
        name, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    # Паттерн 2: ФИО после "отчёт_" или "отчет от"
    match = re.search(
        r'(?:отч[её]т|report|отч)[\s_\-]+(?:от[\s_\-]+)?'
        r'([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.?[А-ЯЁа-яё]?\.?)*)',
        name, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    # Паттерн 3: Кириллическое слово с заглавной буквы в начале файла
    match = re.match(r'^([А-ЯЁ][а-яё]{2,})', name)
    if match:
        return match.group(1).strip()

    return None


def _fuzzy_match_executor(sender_name, executors):
    """
    Нечёткое сопоставление имени отправителя с исполнителями в БД.
    Возвращает лучшее совпадение (executor) или None.
    """
    if not sender_name:
        return None

    sender_lower = sender_name.lower().strip()
    best_match = None
    best_ratio = 0.0

    for executor in executors:
        executor_lower = executor.name.lower().strip()

        # Точное совпадение фамилии
        sender_surname = sender_lower.split()[0] if sender_lower else ""
        executor_surname = executor_lower.split()[0] if executor_lower else ""

        if sender_surname and executor_surname and sender_surname == executor_surname:
            return executor

        # Нечёткое сравнение
        ratio = SequenceMatcher(None, sender_lower, executor_lower).ratio()
        if ratio > best_ratio and ratio >= 0.6:
            best_ratio = ratio
            best_match = executor

    return best_match


def scan_reports(app):
    """
    Основная функция сканирования отчётов с Яндекс.Диска.
    Возвращает словарь с результатами синхронизации.
    """
    from models import db, Executor, Task, YandexReport

    client = YandexDiskClient()
    results = {"new": 0, "skipped": 0, "errors": [], "total_scanned": 0}

    try:
        files = client.list_files()
    except ValueError as e:
        results["errors"].append(str(e))
        return results
    except Exception as e:
        results["errors"].append(f"Ошибка подключения: {str(e)}")
        logging.error(f"Ошибка сканирования Яндекс.Диска: {e}")
        return results

    results["total_scanned"] = len(files)

    with app.app_context():
        executors = Executor.query.all()

        for file_info in files:
            try:
                file_path = file_info.get("path", "")
                file_name = file_info.get("name", "")
                file_md5 = file_info.get("md5", "")

                # Используем MD5 от Яндекса или генерируем хеш из пути
                file_hash = file_md5 or hashlib.md5(file_path.encode()).hexdigest()

                # Проверка на дубликат
                existing = YandexReport.query.filter_by(file_hash=file_hash).first()
                if existing:
                    results["skipped"] += 1
                    continue

                # Определяем отправителя
                sender_name = None

                # Приоритет 1: имя подпапки (если файл в /Отчёты/Иванов/файл.pdf)
                folder_sender = file_info.get("_folder_sender")
                if folder_sender:
                    sender_name = folder_sender

                # Приоритет 2: из имени файла
                if not sender_name:
                    sender_name = _extract_sender_from_filename(file_name)

                # Сопоставляем с исполнителем в БД
                matched_executor = _fuzzy_match_executor(
                    sender_name or folder_sender, executors
                )

                # Дата получения файла
                received_str = file_info.get("modified") or file_info.get("created")
                received_at = None
                if received_str:
                    try:
                        # Яндекс.Диск возвращает ISO 8601
                        received_at = datetime.fromisoformat(
                            received_str.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        received_at = datetime.utcnow()

                # Создаём запись
                report = YandexReport(
                    filename=file_name,
                    yandex_path=file_path,
                    sender_name=sender_name or "Не определён",
                    received_at=received_at or datetime.utcnow(),
                    file_hash=file_hash,
                    executor_id=matched_executor.id if matched_executor else None,
                )

                # Пытаемся привязать к задаче (по исполнителю, берём последнюю незакрытую)
                if matched_executor:
                    open_task = Task.query.filter_by(
                        executor_id=matched_executor.id,
                        report_submitted=False
                    ).order_by(Task.deadline.asc()).first()

                    if open_task:
                        report.task_id = open_task.id
                        open_task.report_submitted = True
                        open_task.status = "Выполнено"
                        logging.info(
                            f"Отчёт '{file_name}' привязан к задаче #{open_task.id} "
                            f"({matched_executor.name})"
                        )

                db.session.add(report)
                results["new"] += 1
                logging.info(
                    f"Яндекс.Диск: новый отчёт '{file_name}' "
                    f"от {sender_name or 'неизвестно'} "
                    f"({received_at or 'дата не определена'})"
                )

            except Exception as e:
                results["errors"].append(f"Ошибка обработки '{file_info.get('name', '?')}': {str(e)}")
                logging.error(f"Ошибка обработки файла с Яндекс.Диска: {e}")

        db.session.commit()

    return results
