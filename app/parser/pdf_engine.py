import re
import io
import hashlib
import logging
from datetime import datetime

# pdfplumber даёт значительно лучшее качество распознавания текста, чем PyPDF2.
# При недоступности - fallback на PyPDF2
try:
    import pdfplumber
    USE_PDFPLUMBER = True
except ImportError:
    import PyPDF2
    USE_PDFPLUMBER = False
    logging.warning("pdfplumber недоступен, используется PyPDF2 (качество ниже). Установите: pip install pdfplumber")


# ─── словарь месяцев ─────────────────────────────────────────────────────────
MONTHS = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
}

# ─── Регулярные выражения ─────────────────────────────────────────────────────

# Исполнитель:  (Иванов И.О.) | (Иванов Иван Иванович) | (Иванов И.О., Петров П.П.)
RE_EXECUTOR = re.compile(
    r'\(([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё.]+){1,3}(?:,\s*[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё.]+){1,3})*)\)'
)

# Срок: "Срок до 28 февраля 2026" / "до 01.03.2026" / "до 2026-03-01" / "до 28/02/2026"
RE_DEADLINE_WORDS = re.compile(
    r'[Сс]рок\s*(?:исполнения)?[\s:-]*до\s+(\d{1,2})\s+([а-яё]+)\s+(\d{4})'
)
RE_DEADLINE_DOT = re.compile(
    r'[Сс]рок\s*(?:исполнения)?[\s:-]*до\s+(\d{1,2})[./](\d{1,2})[./](\d{4})'
)
RE_DEADLINE_ISO = re.compile(
    r'[Сс]рок\s*(?:исполнения)?[\s:-]*до\s+(\d{4})-(\d{2})-(\d{2})'
)

# Номер пункта:  «5.», «5.1.», «10.4.2.»  (в начале строки или после \n)
RE_ITEM_HEADER = re.compile(r'(?:^|\n)(\d+(?:\.\d+)*\.)\s+')


def _extract_text_pdfplumber(file_bytes: bytes) -> str:
    """Извлекает текст через pdfplumber — наилучшее качество."""
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text(x_tolerance=2, y_tolerance=3)
            if page_text:
                text += page_text + "\n"
    return text


def _extract_text_pypdf2(file_bytes: bytes) -> str:
    """Fallback-извлечение через PyPDF2."""
    import PyPDF2
    text = ""
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text


def _parse_deadline(content: str):
    """Пробует распознать дату дедлайна из текста блока."""
    # 1) «до 28 февраля 2026»
    m = RE_DEADLINE_WORDS.search(content)
    if m:
        day, m_name, year = m.groups()
        month = MONTHS.get(m_name.lower())
        if month:
            try:
                return datetime(int(year), month, int(day))
            except ValueError:
                pass

    # 2) «до 28.02.2026» или «до 28/02/2026»
    m = RE_DEADLINE_DOT.search(content)
    if m:
        day, month, year = m.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass

    # 3) «до 2026-02-28» (ISO)
    m = RE_DEADLINE_ISO.search(content)
    if m:
        year, month, day = m.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass

    return None


def _parse_executor(content: str) -> str:
    """Возвращает первого исполнителя найденного в тексте блока."""
    m = RE_EXECUTOR.search(content)
    return m.group(1).strip() if m else "Ответственное лицо"


def parse_pdf(file_path=None, file_bytes=None, filename=""):
    """
    Парсит PDF-файл с поручениями.
    Возвращает список словарей задач или None при ошибке.
    """
    source_name = filename or file_path or "Unknown stream"
    logging.info(f"[PDF-PARSER] Начат парсинг: {source_name} (pdfplumber={USE_PDFPLUMBER})")

    try:
        # ── 1. Загрузка байтов ───────────────────────────────────────────────
        if file_bytes is None and file_path:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()

        if not file_bytes:
            logging.error("[PDF-PARSER] Нет данных для разбора")
            return None

        file_hash = hashlib.md5(file_bytes).hexdigest()

        # ── 2. Извлечение текста ─────────────────────────────────────────────
        try:
            text = _extract_text_pdfplumber(file_bytes) if USE_PDFPLUMBER else _extract_text_pypdf2(file_bytes)
        except Exception as e:
            logging.warning(f"[PDF-PARSER] Основной метод не сработал: {e}, пробуем PyPDF2")
            text = _extract_text_pypdf2(file_bytes)

        if not text.strip():
            logging.error(f"[PDF-PARSER] Текст не извлечён из {source_name}")
            return None

        logging.info(f"[PDF-PARSER] Извлечено {len(text)} символов")

        # ── 3. Разбивка на пункты ────────────────────────────────────────────
        # Разбиваем текст по заголовкам пунктов (5.1., 10.4.2. и т.д.)
        segments = RE_ITEM_HEADER.split(text)
        # segments[0] — преамбула до первого пункта
        # Дальше чередуются: номер, текст, номер, текст...

        tasks = []

        # Если пунктов не нашли — пробуем создать одну задачу из всего текста
        if len(segments) < 3:
            logging.warning(f"[PDF-PARSER] Структурированные пункты не найдены, создаётся одна запись")
            deadline = _parse_deadline(text) or datetime.utcnow()
            executor = _parse_executor(text)
            tasks.append({
                "title": filename or "Поручение из PDF",
                "text": text[:2000].strip(),
                "executor": executor,
                "deadline": deadline,
                "file_hash": file_hash,
                "is_report": "отчет" in filename.lower() or "исполнено" in text.lower(),
            })
            return tasks

        # Парсим каждый пункт
        for i in range(1, len(segments) - 1, 2):
            item_num = segments[i].strip().rstrip('.')
            content = segments[i + 1].strip()

            if len(content) < 5:  # пустой блок — пропускаем
                continue

            executor = _parse_executor(content)
            deadline = _parse_deadline(content) or datetime.utcnow()

            # Первая непустая строка как заголовок
            first_line = next((l.strip() for l in content.split('\n') if l.strip()), content[:120])

            tasks.append({
                "title": f"Пункт {item_num}",
                "text": first_line,
                "executor": executor,
                "deadline": deadline,
                "file_hash": file_hash,
                "is_report": "отчет" in filename.lower() or "исполнено" in content.lower(),
            })

        logging.info(f"[PDF-PARSER] Найдено пунктов: {len(tasks)}")
        return tasks if tasks else None

    except Exception as e:
        logging.error(f"[PDF-PARSER] Критическая ошибка при разборе {source_name}: {e}", exc_info=True)
        return None