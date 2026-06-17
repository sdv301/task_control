"""
Сервис интеграции с Яндекс.Диском.
Сканирует указанную папку, определяет отправителя и дату получения отчёта,
сохраняет в БД и обновляет статусы задач.
"""
import os
import re
import logging
import hashlib
import io
import json
from datetime import datetime
from difflib import SequenceMatcher

import requests

# ─── Настройки ────────────────────────────────────────────────────────────────
YANDEX_API_BASE = "https://cloud-api.yandex.net/v1/disk/resources"
YANDEX_TOKEN = os.environ.get("YANDEX_DISK_TOKEN", "")
YANDEX_FOLDER = os.environ.get("YANDEX_DISK_FOLDER", "/SmartControl/Отчёты")
SUPPORTED_EXTENSIONS = ('.pdf', '.docx', '.doc', '.xlsx', '.xls', '.jpg', '.png', '.zip')
RE_KCHS_DOC = re.compile(
    r'(?:кчс|протокол)\s*№?\s*(\d+)(?:.{0,30}?(?:от\s*)?(\d{1,2}[./]\d{1,2}[./]\d{2,4}))?',
    re.IGNORECASE,
)
RE_KCHS_FILENAME = re.compile(
    r'(?:отч[её]т\s+)?кчс\s*(\d+)(?:[_\s]+(\d+))?(?:\s|$|[_\.])',
    re.IGNORECASE,
)
RE_ITEM_NUM = re.compile(
    r'(?:пункт|п\.)\s*(\d+(?:\s*\.\s*\d+)*)|(?:^|\n)\s*(\d+(?:\s*\.\s*\d+)*)[.)]?\s+[А-ЯЁA-Z]',
    re.IGNORECASE,
)
RE_RESPONSE_ITEMS = re.compile(
    r'(?:пункт[уае]?\s+|п\.?\s*|п\.?\s*п\.?\s*)(\d{1,2}(?:\s*\.\s*\d+)+|\d{1,2})',
    re.IGNORECASE,
)
RE_ITEM_DECIMAL = r'\d{1,2}(?:\s*\.\s*\d+)+|\d{1,2}'
RE_KCHS_NUMBER = re.compile(
    r'(?:к\s*ч\s*с|протокол|'
    r'р\s*е\s*ш\s*е\s*н\s*и\s*е|решени[ея]|протокол|'
    r'б\s*ы\s*[һх]\s*а\s*а\s*р\s*ы\s*ы|быҺаарыы)'
    r'[^\n\d]{0,40}(?:№|n\s*o?\.?\s*)?\s*(\d{1,3})',
    re.IGNORECASE,
)
RE_FILENAME_KCHS_HINT = re.compile(r'(?:кчс|протокол|реш)[^\d]{0,10}(\d{1,3})', re.IGNORECASE)
RE_FILENAME_ITEM_HINT = re.compile(
    r'(?:пункт|п\.|[_\s-])(\d{1,2}(?:\s*\.\s*\d+)+|\d{1,2})(?:[_\s.-]|$)',
    re.IGNORECASE,
)
# Строка «4.3 Обеспечить …» / «4. 3 Обеспечить …»
RE_DECIMAL_ITEM_LINE = re.compile(
    rf'(?:^|\n)\s*({RE_ITEM_DECIMAL})\s+(?=[А-ЯЁA-Z])',
    re.MULTILINE,
)
# «2. Пункт 4.1», «Е Пункт 4.1» (OCR), «Пункт 4. 3», «Пункт4.1»
RE_PUNKT_ITEM_LINE = re.compile(
    rf'(?:^|\n)\s*(?:\d+[\.)]\s*)?(?:[^\n]{{0,8}}\s+)?[Пп][уy]?нкт\s+({RE_ITEM_DECIMAL})\s*(?:[.:])?\s+(?=[А-ЯЁA-Z])',
    re.MULTILINE,
)
# «п. 4.1», «п.4. 2»
RE_ABBR_ITEM_LINE = re.compile(
    rf'(?:^|\n)\s*[Пп]\.?\s*({RE_ITEM_DECIMAL})\s+(?=[А-ЯЁA-Z])',
    re.MULTILINE,
)
TITLE_MATCH_MIN_RATIO = 0.52


def _normalize_item_number(raw):
    """«4. 1», «4 .1», «4.1» → «4.1»; убирает мусор OCR."""
    if raw is None:
        return None
    s = str(raw).strip().strip(".")
    s = re.sub(r'\s+', '', s)
    s = re.sub(r'[^\d.]', '', s)
    parts = [p for p in s.split('.') if p.isdigit()]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return '.'.join(parts)


def _normalize_title_text(text):
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r'пункт\s*\d+(?:\.\d+)*\.?\s*', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()


def _title_similarity(left, right):
    a = _normalize_title_text(left)
    b = _normalize_title_text(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return max(SequenceMatcher(None, a, b).ratio(), 0.75)
    return SequenceMatcher(None, a, b).ratio()


def _iter_report_item_hits(text):
    """Все вхождения пунктов в отчёте: (item, start, end)."""
    if not text:
        return []

    hits = []
    seen_spans = set()
    for regex in (RE_DECIMAL_ITEM_LINE, RE_PUNKT_ITEM_LINE, RE_ABBR_ITEM_LINE):
        for match in regex.finditer(text):
            span = match.span()
            if span in seen_spans:
                continue
            seen_spans.add(span)
            item = _normalize_item_number(match.group(1))
            if item:
                hits.append((item, match.start(), match.end()))
    hits.sort(key=lambda x: x[1])
    return hits


def _extract_report_sections(text):
    """Из отчёта: номер пункта + фрагмент названия для сверки с базой."""
    sections = []
    seen = set()
    for item, _start, end in _iter_report_item_hits(text):
        if item in seen:
            continue
        tail = text[end:]
        title_match = re.match(r'([^\n]{12,500})', tail)
        if not title_match:
            continue
        title = title_match.group(1).strip()
        title = re.split(
            r'\n\s*(?:Срок исполнения|Обеспечено|В адрес|ФИО\b)',
            title,
            maxsplit=1,
        )[0].strip()
        if len(title) < 12:
            continue
        seen.add(item)
        section_deadline = None
        try:
            from pdf_parser.pdf_engine import _parse_deadline
            section_deadline = _parse_deadline(tail[:800])
        except Exception:
            pass
        entry = {"item_number": item, "title": title}
        if section_deadline and section_deadline.year < 2099:
            entry["deadline"] = section_deadline.strftime('%d.%m.%Y')
        sections.append(entry)
    return sections


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
                from concurrent.futures import ThreadPoolExecutor, as_completed
                from services.districts import DISTRICTS

                with ThreadPoolExecutor(max_workers=8) as pool:
                    futures = {
                        pool.submit(self.get_public_files, link, name): name
                        for name, link in DISTRICTS.items()
                    }
                    for future in as_completed(futures):
                        district_name = futures[future]
                        try:
                            files.extend(future.result())
                        except Exception as e:
                            logging.error(f"Ошибка загрузки папки {district_name}: {e}")
            except Exception as e:
                logging.error(f"Ошибка загрузки публичных ссылок: {e}")

        # Если нет токена и никто не вернул файлы из паблик папок, сообщаем
        if not self.token and not files and folder_path is None:
             logging.warning("Токен не задан. Сканирование приватных папок отключено, публичные папки пусты.")

        return files

    def get_public_files(self, public_key, sender_name, inner_path="/", depth=0):
        """Получить файлы из публичной папки, включая вложенные подпапки (до 2 уровней)."""
        import hashlib
        url = "https://cloud-api.yandex.net/v1/disk/public/resources"
        headers = self.headers if self.token else {}
        files = []
        offset = 0
        limit = 100
        max_depth = 2

        while True:
            params = {
                "public_key": public_key,
                "path": inner_path,
                "limit": limit,
                "offset": offset,
                "fields": "_embedded.items.name,_embedded.items.path,_embedded.items.type,"
                          "_embedded.items.size,_embedded.items.created,_embedded.items.modified,"
                          "_embedded.items.md5,_embedded.items.file",
            }
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code != 200:
                logging.error(
                    f"Ошибка Яндекс.Диска для {sender_name} ({public_key}, path={inner_path}): {resp.text}"
                )
                break

            items = resp.json().get("_embedded", {}).get("items", [])
            if not items:
                break

            for item in items:
                item_type = item.get("type")
                if item_type == "dir" and depth < max_depth:
                    sub_path = item.get("path") or f"{inner_path.rstrip('/')}/{item.get('name', '')}"
                    files.extend(
                        self.get_public_files(public_key, sender_name, sub_path, depth + 1)
                    )
                    continue
                if item_type != "file":
                    continue

                name_lower = item.get("name", "").lower()
                if not any(name_lower.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                    continue

                item["_folder_sender"] = sender_name
                rel_folder = inner_path if inner_path != "/" else ""
                item["path"] = f"/public/{sender_name}{rel_folder}/{item['name']}"
                if not item.get("md5"):
                    item["md5"] = hashlib.md5(
                        f"{sender_name}:{inner_path}:{item['name']}:{item.get('size', '')}:{item.get('modified', '')}".encode()
                    ).hexdigest()
                files.append(item)

            if len(items) < limit:
                break
            offset += limit

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
    for executor in executors:
        if executor.name.lower().strip() == sender_lower:
            return executor

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


def _extract_item_numbers(text):
    if not text:
        return set()
    found = re.findall(
        r'(?:пункт|п\.)\s*(\d+(?:\s*\.\s*\d+)*)|(?:^|[\s_])(\d+(?:\s*\.\s*\d+)*)(?:[\s_.)]|$)',
        text.lower(),
    )
    values = set()
    for first, second in found:
        number = _normalize_item_number(first or second)
        if number:
            values.add(number)
    return values


def _is_list_prefix_line(body, start):
    """«2. Пункт 4.1» — двойка это нумерация списка, не пункт протокола."""
    line_start = body.rfind('\n', 0, start) + 1
    line_end = body.find('\n', start)
    if line_end == -1:
        line_end = len(body)
    line = body[line_start:line_end]
    return bool(re.search(r'^\s*\d+[\.)]\s+[Пп][уy]?нкт\s+\d', line, re.IGNORECASE))


def _extract_pdf_text(file_bytes, use_ocr=True):
    """Извлечь текст из PDF: pdfplumber → PyPDF2 → OCR (как в pdf_engine)."""
    if not file_bytes:
        return ""
    text = ""
    try:
        from pdf_parser.pdf_engine import (
            USE_PDFPLUMBER,
            USE_OCR,
            _extract_text_pdfplumber,
            _extract_text_pypdf2,
            _extract_text_ocr,
        )
        if USE_PDFPLUMBER:
            text = _extract_text_pdfplumber(file_bytes)
        if not text:
            text = _extract_text_pypdf2(file_bytes)
        if not text and use_ocr and USE_OCR:
            text = _extract_text_ocr(file_bytes)
        return text.strip()
    except Exception as e:
        logging.warning(f"Не удалось извлечь текст из PDF: {e}")
        return ""


def _normalize_doc_number(value):
    if not value:
        return None
    match = re.search(r'(\d+)', str(value))
    return match.group(1) if match else None


def _parse_filename_kchs(file_name):
    stem = os.path.splitext(file_name or "")[0]
    match = RE_KCHS_FILENAME.search(stem)
    if not match:
        return None, None
    # «КЧС 13_2» — номер протокола/версия файла, а не пункт 2
    return match.group(1), None


def _refine_item_numbers(items, kchs_number=None):
    cleaned = set()
    for i in (items or []):
        n = _normalize_item_number(i)
        if n:
            cleaned.add(n)
    if kchs_number:
        cleaned.discard(str(kchs_number))

    dotted = {x for x in cleaned if '.' in x}
    if dotted:
        major_nums = {x.split('.')[0] for x in dotted}
        cleaned = {
            x for x in cleaned
            if '.' in x or (x.isdigit() and x in major_nums)
        }

    for parent in list(cleaned):
        if any(child.startswith(f"{parent}.") for child in cleaned if child != parent):
            cleaned.discard(parent)

    if any("." in item for item in cleaned):
        cleaned = {
            item for item in cleaned
            if "." in item or not any(other.startswith(f"{item}.") for other in cleaned)
        }
    return cleaned


def _extract_kchs_number(text, file_name=""):
    combined = f"{file_name}\n{text or ''}"
    for pattern in (RE_KCHS_DOC, RE_KCHS_NUMBER, RE_FILENAME_KCHS_HINT):
        match = pattern.search(combined)
        if match:
            return match.group(1).strip()
    return None


def _extract_report_item_numbers(text, file_name=""):
    """Извлечь номера пунктов: приоритет — текст PDF, затем слабые подсказки из имени."""
    items = set()
    body = text or ""

    for match in RE_RESPONSE_ITEMS.finditer(body):
        val = _normalize_item_number(match.group(1))
        if val:
            items.add(val)

    for item, _start, _end in _iter_report_item_hits(body):
        items.add(item)

    for match in RE_ITEM_NUM.finditer(body):
        val = _normalize_item_number(match.group(1) or match.group(2))
        if not val:
            continue
        if not match.group(1) and _is_list_prefix_line(body, match.start()):
            continue
        items.add(val)

    for match in re.finditer(
        rf'(?:^|\n)\s*({RE_ITEM_DECIMAL})\.\s+[А-ЯЁA-Z]', body
    ):
        if _is_list_prefix_line(body, match.start()):
            continue
        val = _normalize_item_number(match.group(1))
        if val:
            items.add(val)

    for section in _extract_report_sections(body):
        items.add(section["item_number"])

    # Имя файла — только подсказка, если в тексте ничего не нашли
    if not items and file_name:
        for match in RE_FILENAME_ITEM_HINT.finditer(file_name):
            items.add(match.group(1).strip("."))
        _, filename_item = _parse_filename_kchs(file_name)
        if filename_item:
            items.add(filename_item.strip("."))

    return items


def _parse_response_metadata(file_name, raw_text):
    kchs_number = _extract_kchs_number(raw_text, file_name)
    kchs_date = None
    match = RE_KCHS_DOC.search(f"{file_name}\n{raw_text or ''}")
    if match and match.group(2):
        kchs_date = match.group(2)

    item_numbers = _extract_report_item_numbers(raw_text, file_name if not raw_text else "")
    if not item_numbers and file_name:
        item_numbers = _extract_report_item_numbers("", file_name)

    if kchs_number:
        item_numbers.discard(str(kchs_number))

    item_numbers = _refine_item_numbers(item_numbers, kchs_number)
    sections = _extract_report_sections(raw_text)

    return {
        "kchs_number": kchs_number,
        "kchs_date": kchs_date,
        "item_numbers": item_numbers,
        "sections": sections,
    }


def _download_file_bytes(client, file_info):
    # Публичная ссылка может уже содержать прямой URL файла.
    direct_url = file_info.get("file")
    if direct_url:
        try:
            resp = requests.get(direct_url, timeout=20)
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            logging.warning(f"Ошибка загрузки public file URL: {e}")

    # Для приватного диска пробуем получить download href по path.
    if client.token and file_info.get("path"):
        try:
            dl = client.get_download_link(file_info["path"])
            if dl:
                resp = requests.get(dl, timeout=20)
                if resp.status_code == 200:
                    return resp.content
        except Exception as e:
            logging.warning(f"Ошибка загрузки файла по path: {e}")
    return None


def _task_matches_item_number(task, item_numbers):
    if not item_numbers:
        return False
    normalized_items = {_normalize_item_number(x) for x in item_numbers}
    normalized_items.discard(None)
    task_items = _extract_item_numbers(f"{task.item_number or ''} {task.title or ''}")
    if task_items & normalized_items:
        return True
    plain_item = _normalize_item_number(task.item_number)
    return plain_item in normalized_items


def _task_matches_by_title(task, sections, min_ratio=TITLE_MATCH_MIN_RATIO):
    """Сверка отчёта с поручением по названию пункта из базы."""
    if not sections:
        return False, 0.0

    task_item = (task.item_number or "").strip().strip(".")
    task_blob = f"{task.title or ''} {task.text or ''}"

    best_ratio = 0.0
    for section in sections:
        sec_item = (section.get("item_number") or "").strip().strip(".")
        if task_item and sec_item and task_item != sec_item:
            continue
        ratio = _title_similarity(task_blob, section.get("title", ""))
        if ratio > best_ratio:
            best_ratio = ratio

    return best_ratio >= min_ratio, best_ratio


def _task_matches_report(task, item_numbers, sections):
    if _task_matches_item_number(task, item_numbers):
        return True, "number"
    ok, ratio = _task_matches_by_title(task, sections)
    if ok:
        return True, f"title:{ratio:.0f}%"
    return False, None


def _filter_tasks_by_kchs_document(tasks, kchs_number):
    if not kchs_number:
        return tasks

    from models import FileDocument

    doc_ids = set()
    kchs_text = str(kchs_number)
    for doc in FileDocument.query.all():
        norm = _normalize_doc_number(doc.doc_number)
        if norm == kchs_text:
            doc_ids.add(doc.id)
            continue
        haystack = f"{doc.filename or ''} {doc.doc_number or ''}".lower()
        if kchs_text in haystack or f"№{kchs_text}" in haystack or f"№ {kchs_text}" in haystack:
            doc_ids.add(doc.id)

    if not doc_ids:
        return tasks

    scoped = [task for task in tasks if task.document_id in doc_ids]
    return scoped or tasks


def _build_response_meta(file_name, client, file_info, download_pdf=True):
    """Разбор отчёта: для PDF всегда читаем содержимое (OCR), имя файла — только подсказка."""
    if not download_pdf or not file_name.lower().endswith(".pdf"):
        return _parse_response_metadata(file_name, "")

    file_bytes = _download_file_bytes(client, file_info)
    raw_text = _extract_pdf_text(file_bytes, use_ocr=True)
    meta = _parse_response_metadata(file_name, raw_text)

    if not meta.get("item_numbers"):
        fallback = _parse_response_metadata(file_name, "")
        if fallback.get("item_numbers"):
            meta["item_numbers"] = fallback["item_numbers"]
        if not meta.get("kchs_number"):
            meta["kchs_number"] = fallback.get("kchs_number")

    logging.info(
        f"PDF-ответ '{file_name}': КЧС №{meta.get('kchs_number')} "
        f"от {meta.get('kchs_date')}, пункты={sorted(meta.get('item_numbers', []))}"
    )
    return meta


def _parse_received_at(file_info):
    received_str = file_info.get("modified") or file_info.get("created")
    if not received_str:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(received_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _apply_report_to_task(task, received_at):
    from services.task_timing import format_late_label, safe_deadline

    task.report_submitted = True
    task.status = "Выполнено"
    deadline = safe_deadline(task)
    if received_at and deadline:
        if received_at <= deadline:
            logging.info(f"Задача #{task.id} выполнена в срок ({received_at.date()} <= {deadline.date()})")
        else:
            late_days = (received_at.date() - deadline.date()).days
            late_label = format_late_label(late_days) or f"на {late_days} дн."
            logging.info(
                f"Задача #{task.id} выполнена с опозданием {late_label} "
                f"({received_at.date()} > {deadline.date()})"
            )


def _store_report_metadata(report, response_meta, matched_count):
    report.kchs_number = response_meta.get("kchs_number")
    items = sorted(response_meta.get("item_numbers") or [])
    report.parsed_item_numbers = json.dumps(items, ensure_ascii=False)
    report.items_matched = matched_count


def _task_has_yandex_link(task):
    from models import YandexReport, YandexReportTaskLink

    if YandexReport.query.filter_by(task_id=task.id).first():
        return True
    return YandexReportTaskLink.query.filter_by(task_id=task.id).first() is not None


def _match_tasks_for_report(matched_executor, file_info, response_meta=None):
    """Найти все поручения, которые закрывает один отчёт."""
    from models import Task
    if not matched_executor:
        return []

    response_meta = response_meta or {}
    kchs_number = response_meta.get("kchs_number")
    item_numbers = set(response_meta.get("item_numbers") or set())
    sections = response_meta.get("sections") or []

    if not item_numbers and not sections:
        logging.warning(
            f"Отчёт '{file_info.get('name', '')}' ({matched_executor.name}): "
            f"пункты не распознаны — нужен текст в PDF или OCR"
        )
        return []

    candidate_tasks = Task.query.filter_by(
        executor_id=matched_executor.id,
    ).order_by(Task.deadline.asc()).all()
    open_tasks = [t for t in candidate_tasks if not _task_has_yandex_link(t)]
    if not open_tasks:
        return []

    candidates = _filter_tasks_by_kchs_document(open_tasks, kchs_number)
    matched = []
    match_details = []
    for task in candidates:
        ok, how = _task_matches_report(task, item_numbers, sections)
        if ok:
            matched.append(task)
            match_details.append(f"{task.item_number}({how})")

    if matched:
        logging.info(
            f"Отчёт '{file_info.get('name', '')}': КЧС={kchs_number or '?'}, "
            f"распознано пунктов={sorted(item_numbers)}, "
            f"секций с текстом={len(sections)}, закрыто={match_details}"
        )
    else:
        logging.warning(
            f"Отчёт '{file_info.get('name', '')}' ({matched_executor.name}): "
            f"пункты {sorted(item_numbers)} / секций {len(sections)} "
            f"не совпали с открытыми поручениями (КЧС={kchs_number or '?'})"
        )
    return matched


def _link_report_to_tasks(report, matched_executor, file_info, response_meta):
    from services.report_matcher import auto_link_report

    result = auto_link_report(
        report, matched_executor, file_info, response_meta, include_suggestions=True
    )
    logging.info(
        f"Отчёт '{file_info.get('name', report.filename)}': "
        f"авто={result['auto_count']}, предложено={result['suggest_count']}, "
        f"закрыто={result['linked']}, не хватает={result['missing_count']}"
    )
    return result["linked"]


def _next_file_version(executor_id, filename):
    from models import YandexReport

    if not executor_id:
        return 1
    prev = (
        YandexReport.query.filter_by(executor_id=executor_id, filename=filename)
        .order_by(YandexReport.file_version.desc())
        .first()
    )
    return (prev.file_version or 1) + 1 if prev else 1


def _mark_superseded(executor_id, filename, new_report_id):
    from models import YandexReport, db

    if not executor_id or not new_report_id:
        return
    older = (
        YandexReport.query.filter(
            YandexReport.executor_id == executor_id,
            YandexReport.filename == filename,
            YandexReport.id != new_report_id,
            YandexReport.superseded_by_id.is_(None),
        )
        .order_by(YandexReport.synced_at.desc())
        .all()
    )
    for old in older:
        old.superseded_by_id = new_report_id


def _report_needs_linking(report):
    from models import YandexReportTaskLink
    if report.superseded_by_id:
        return False
    if report.completeness_status == "full":
        return False
    if (report.items_matched or 0) > 0:
        return False
    return YandexReportTaskLink.query.filter_by(report_id=report.id).count() == 0


def scan_districts_status(client=None):
    """Проверить все публичные папки районов: есть ли файлы отчётов."""
    from services.districts import DISTRICTS

    client = client or YandexDiskClient()
    rows = []
    for name, url in DISTRICTS.items():
        try:
            files = client.get_public_files(url, name)
            filenames = [f.get("name", "") for f in files]
            rows.append({
                "name": name,
                "url": url,
                "file_count": len(files),
                "files": filenames[:10],
                "status": "ok" if files else "empty",
            })
        except Exception as e:
            rows.append({
                "name": name,
                "url": url,
                "file_count": 0,
                "files": [],
                "status": "error",
                "error": str(e),
            })
    rows.sort(key=lambda x: (0 if x["status"] == "ok" else 1, x["name"]))
    return rows


def _report_status_label(items_matched, parsed_items):
    matched = items_matched or 0
    if matched > 0:
        return "linked", "Закрыл пункты"
    if parsed_items:
        return "unmatched", "Пункты не совпали"
    return "unknown", "Не распознан"


def scan_reports(app):
    """
    Основная функция сканирования отчётов с Яндекс.Диска.
    Возвращает словарь с результатами синхронизации.
    """
    from models import db, Executor, Task, YandexReport

    client = YandexDiskClient()
    results = {
        "new": 0,
        "skipped": 0,
        "linked": 0,
        "items_closed": 0,
        "unmatched": 0,
        "errors": [],
        "total_scanned": 0,
        "districts_status": [],
    }

    try:
        files = client.list_files()
        results["districts_status"] = scan_districts_status(client)
    except ValueError as e:
        results["errors"].append(str(e))
        return results
    except Exception as e:
        results["errors"].append(f"Ошибка подключения: {str(e)}")
        logging.error(f"Ошибка сканирования Яндекс.Диска: {e}")
        return results

    results["total_scanned"] = len(files)
    files_by_hash = {}
    for file_info in files:
        file_path = file_info.get("path", "")
        file_md5 = file_info.get("md5", "")
        file_hash = file_md5 or hashlib.md5(file_path.encode()).hexdigest()
        files_by_hash[file_hash] = file_info

    with app.app_context():
        try:
            db.session.rollback()
            executors = Executor.query.all()

            for file_info in files:
                try:
                    file_path = file_info.get("path", "")
                    file_name = file_info.get("name", "")
                    file_md5 = file_info.get("md5", "")

                    file_hash = file_md5 or hashlib.md5(file_path.encode()).hexdigest()

                    sender_name = file_info.get("_folder_sender")
                    if not sender_name:
                        sender_name = _extract_sender_from_filename(file_name)
                    matched_executor = _fuzzy_match_executor(sender_name, executors)

                    existing = YandexReport.query.filter_by(file_hash=file_hash).first()
                    if existing:
                        results["skipped"] += 1
                        if matched_executor and _report_needs_linking(existing):
                            response_meta = _build_response_meta(
                                file_name, client, file_info, download_pdf=True
                            )
                            closed = _link_report_to_tasks(
                                existing, matched_executor, file_info, response_meta
                            )
                            if closed:
                                results["linked"] += 1
                                results["items_closed"] += closed
                            else:
                                results["unmatched"] += 1
                        continue

                    received_at = _parse_received_at(file_info)
                    response_meta = _build_response_meta(
                        file_name, client, file_info, download_pdf=True
                    )

                    file_version = _next_file_version(
                        matched_executor.id if matched_executor else None, file_name
                    )
                    report = YandexReport(
                        filename=file_name,
                        yandex_path=file_path,
                        sender_name=sender_name or "Не определён",
                        received_at=received_at,
                        file_hash=file_hash,
                        executor_id=matched_executor.id if matched_executor else None,
                        file_version=file_version,
                    )
                    db.session.add(report)
                    db.session.flush()
                    if matched_executor:
                        _mark_superseded(matched_executor.id, file_name, report.id)

                    closed = 0
                    if matched_executor:
                        closed = _link_report_to_tasks(report, matched_executor, file_info, response_meta)
                        if closed:
                            results["linked"] += 1
                            results["items_closed"] += closed
                        else:
                            results["unmatched"] += 1

                    results["new"] += 1
                    logging.info(
                        f"Яндекс.Диск: новый отчёт '{file_name}' "
                        f"от {sender_name or 'неизвестно'} "
                        f"({received_at or 'дата не определена'})"
                    )

                    if results["new"] % 25 == 0:
                        db.session.commit()

                except Exception as e:
                    db.session.rollback()
                    results["errors"].append(f"Ошибка обработки '{file_info.get('name', '?')}': {str(e)}")
                    logging.error(f"Ошибка обработки файла с Яндекс.Диска: {e}")

            # Повторная привязка отчётов, которые есть на диске, но ещё без связей
            for report in YandexReport.query.all():
                if not _report_needs_linking(report):
                    continue
                fresh_info = files_by_hash.get(report.file_hash)
                if not fresh_info:
                    continue
                try:
                    executor = report.executor or (
                        Executor.query.get(report.executor_id) if report.executor_id else None
                    )
                    if not executor and report.sender_name and report.sender_name != "Не определён":
                        executor = _fuzzy_match_executor(report.sender_name, executors)
                    if not executor:
                        continue
                    response_meta = _build_response_meta(
                        report.filename, client, fresh_info, download_pdf=True
                    )
                    closed = _link_report_to_tasks(report, executor, fresh_info, response_meta)
                    if closed:
                        results["linked"] += 1
                        results["items_closed"] += closed
                except Exception as e:
                    db.session.rollback()
                    logging.warning(f"Не удалось повторно привязать отчёт #{report.id}: {e}")

            db.session.commit()

            try:
                from services.report_matcher import auto_link_pending_reports, notify_incomplete_after_sync

                retry = auto_link_pending_reports(app, include_suggestions=True)
                results["auto_link_retry"] = retry
                results["linked"] += retry.get("linked", 0)
                results["notifications_sent"] = notify_incomplete_after_sync(app)
            except Exception as e:
                logging.warning(f"Пост-обработка синхронизации: {e}")
                results["post_sync_warning"] = str(e)

        except Exception as e:
            db.session.rollback()
            results["errors"].append(f"Критическая ошибка синхронизации: {str(e)}")
            logging.error(f"Критическая ошибка синхронизации: {e}", exc_info=True)

    return results
