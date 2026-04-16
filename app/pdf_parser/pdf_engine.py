import re
import io
import hashlib
import logging
from datetime import datetime

# ─── Движки извлечения текста ─────────────────────────────────────────────────
try:
    import pdfplumber
    USE_PDFPLUMBER = True
except ImportError:
    USE_PDFPLUMBER = False

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image
    USE_OCR = True
except ImportError:
    USE_OCR = False
    logging.warning("[PDF-PARSER] pytesseract/pdf2image недоступны — OCR отключён.")

# ─── Словарь месяцев ──────────────────────────────────────────────────────────
MONTHS = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
}

# ─── Регулярные выражения ─────────────────────────────────────────────────────
# Исполнитель в скобках: (Лепчиков Д.Н.) или (Иванов Иван Иванович)
RE_EXECUTOR_PARENS = re.compile(
    r'\(([А-ЯЁ][а-яё\-]+\s+[А-ЯЁ][А-ЯЁа-яё\-\.\s]+)\)'
)

# Исполнитель — ФИО ЗАГЛАВНЫМИ БУКВАМИ (жирный шрифт в PDF)
# ИВАНОВ И.О. или ИВАНОВ ИВАН ИВАНОВИЧ
RE_EXECUTOR_CAPS = re.compile(
    r'([А-ЯЁ]{2,}(?:\s+[А-ЯЁ]\.?){1,2}(?:\s+[А-ЯЁ]\.?)?)'
)

# Исполнитель через метку: "Ответственный: Иванов И.О."
RE_EXECUTOR_LABEL = re.compile(
    r'(?:ответственн\w*|исполнител\w*|поруч\w+)\s*[:–—-]\s*'
    r'([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё.]+){1,3})',
    re.IGNORECASE
)

# Срок: "до DD month YYYY" или "с DD month YYYY"
RE_DEADLINE_WORDS = re.compile(
    r'[Сс]рок[\s\-–—]*(?:исполнения)?[\s:-]*(?:до|с|по)\s+(\d{1,2})\s+([а-яё]+)\s+(\d{4})'
)
RE_DEADLINE_DOT = re.compile(
    r'[Сс]рок[\s\-–—]*(?:исполнения)?[\s:-]*(?:до|с|по)\s+(\d{1,2})[./](\d{1,2})[./](\d{4})'
)
RE_DEADLINE_ISO = re.compile(
    r'[Сс]рок[\s\-–—]*(?:исполнения)?[\s:-]*(?:до|с|по)\s+(\d{4})-(\d{2})-(\d{2})'
)

# Номера пунктов: "1.", "5.2.", "10.4.2." (с точкой в конце) ИЛИ пробел и заглавная буква
RE_ITEM_HEADER = re.compile(r'(?:^|\n)\s*(\d+(?:\.\d+)*)(?:\.\s+|\s+(?=[А-ЯЁ]))')
# Доп. regex для OCR-артефактов без точки: "1 Ввести" (число без точки + заглавная буква)
RE_ITEM_NO_DOT = re.compile(r'(?:^|\n)\s*(\d+)\s+(?=[А-ЯЁ])')

# Номер документа: "Решение № 5", "РЕШЕНИЕ №5", "решение No 123", "Протокол № 4"
RE_DOC_NUMBER = re.compile(
    r'(?:решени[ея]|протокол|постановлени[ея]|распоряжени[ея])'
    r'\s*(?:№|No\.?|N)\s*(\d+[\w/.-]*)',
    re.IGNORECASE
)

# Дата документа: "от 15 января 2026", "от 15.01.2026", "15 января 2026 г."
RE_DOC_DATE = re.compile(
    r'(?:от\s+)?(\d{1,2})\s+([а-яё]+)\s+(\d{4})\s*(?:г\.?|года)?',
    re.IGNORECASE
)
RE_DOC_DATE_DOT = re.compile(
    r'(?:от\s+)?(\d{1,2})[./](\d{1,2})[./](\d{4})',
    re.IGNORECASE
)

# Слова, которые НЕ являются именами людей (фильтрация CAPS)
CAPS_BLACKLIST = {
    'ПРОТОКОЛ', 'ПОРУЧЕНИЕ', 'ПРИЛОЖЕНИЕ', 'УТВЕРЖДАЮ', 'СОГЛАСОВАНО',
    'РЕШЕНИЕ', 'СОВЕЩАНИЕ', 'ЗАСЕДАНИЕ', 'СЛУШАЛИ', 'РЕШИЛИ',
    'ПОСТАНОВИЛИ', 'ВЫСТУПИЛИ', 'СРОК', 'ПУНКТ', 'РАЗДЕЛ',
    'РЕСПУБЛИКА', 'РОССИЙСКОЙ', 'ФЕДЕРАЦИИ', 'ГОСУДАРСТВЕННЫЙ',
    'МИНИСТЕРСТВО', 'ДЕПАРТАМЕНТ', 'УПРАВЛЕНИЕ', 'КОМИССИЯ',
    'КЧС', 'ОПБ', 'ГО', 'ЧС', 'МЧС', 'РФ', 'РС', 'ПРАВИТЕЛЬСТВО',
    'АДПИ', 'АППГ', 'ГБУ', 'ГУ', 'РСИЯ', 'ОБЖН',
    'МИНГОИОБЖН', 'САХА', 'ЯКУТИЯ', 'РОССИИ',
    'ПОДЛЕЖИТ', 'ОБЯЗАТЕЛЬНОМУ', 'ИСПОЛНЕНИЮ',
    'ПРЕДСЕДАТЕЛЬСТВОВАЛ', 'ПРЕДУПРЕЖДЕНИЮ',
    'ЛИКВИДАЦИИ', 'ОБЕСПЕЧЕНИЮ',
    'ПОЖАРНОЙ', 'БЕЗОПАСНОСТИ',
}


# ─────────────────────────────────────────────────────────────────────────────
def _extract_text_pdfplumber(file_bytes: bytes) -> str:
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text(x_tolerance=2, y_tolerance=3)
            if page_text:
                text += page_text + "\n"
    return text.strip()


def _extract_text_pypdf2(file_bytes: bytes) -> str:
    try:
        import PyPDF2
        text = ""
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text.strip()
    except Exception as e:
        logging.warning(f"[PDF-PARSER] PyPDF2 ошибка: {e}")
        return ""


def _extract_text_ocr(file_bytes: bytes) -> str:
    if not USE_OCR:
        return ""
    logging.info("[PDF-PARSER] Запуск OCR (сканированный PDF)...")
    text = ""
    try:
        images = convert_from_bytes(file_bytes, dpi=200)
        for i, img in enumerate(images):
            page_text = pytesseract.image_to_string(
                img, lang='rus+eng', config='--psm 6'
            )
            text += page_text + "\n"
            logging.info(f"[PDF-PARSER] OCR страница {i+1}/{len(images)}: {len(page_text)} символов")
    except Exception as e:
        logging.error(f"[PDF-PARSER] OCR ошибка: {e}")
    return text.strip()


def _parse_deadline(content: str):
    m = RE_DEADLINE_WORDS.search(content)
    if m:
        day, m_name, year = m.groups()
        month = MONTHS.get(m_name.lower())
        if month:
            try:
                return datetime(int(year), month, int(day))
            except ValueError:
                pass

    m = RE_DEADLINE_DOT.search(content)
    if m:
        day, month, year = m.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass

    m = RE_DEADLINE_ISO.search(content)
    if m:
        year, month, day = m.groups()
        try:
            return datetime(int(year), int(month), int(day))
        except ValueError:
            pass

    return None


def _is_valid_person_name(name: str) -> bool:
    """Проверяет, что строка похожа на ФИО, а не на аббревиатуру/заголовок."""
    words = name.strip().split()
    if len(words) < 2:
        return False
    # Первое слово (фамилия) >= 3 букв и не в чёрном списке
    if len(words[0]) < 3:
        return False
    if words[0].upper() in CAPS_BLACKLIST:
        return False
    return True

def _parse_executor(content: str, context_before: str = "") -> str:
    """Извлекает ФИО исполнителя из текста пункта.
    Приоритет:
    1. Метка: 'Ответственный: Фамилия И.О.'
    2. В скобках: (Фамилия И.О.)
    3. CAPS внутри пункта
    4. Ведомство через двоеточие
    """
    content_clean = content.replace('\n', ' ').lower()
    if 'органам местного самоуправления' in content_clean:
        return '__ALL_DISTRICTS__'

    # 1. По метке
    m = RE_EXECUTOR_LABEL.search(content)
    if m:
        name = m.group(1).strip()
        if _is_valid_person_name(name):
            return name

    # 2. В скобках — (Лепчиков Д.Н.), (Гарин П.С.)
    parens_matches = list(RE_EXECUTOR_PARENS.finditer(content))
    if parens_matches:
        # Берём последнее совпадение — обычно ФИО ответственного ближе к началу
        # Но если их несколько, первое — это главный
        name = parens_matches[0].group(1).strip()
        return name

    # 3. CAPS внутри пункта
    caps_matches = list(RE_EXECUTOR_CAPS.finditer(content))
    for m in caps_matches:
        name = m.group(1).strip()
        if _is_valid_person_name(name):
            parts = name.split()
            return parts[0].capitalize() + ' ' + ' '.join(parts[1:])

    # 4. Ведомство через двоеточие
    if ':' in content:
        org_part = content.split(':')[0].strip()
        org_part = re.sub(r'(?i)^(рекомендовать|поручить|предложить|обязать)\s+', '', org_part).strip()
        if 10 < len(org_part) < 150:
            return org_part.capitalize()

    return 'Ответственное лицо'

def _parse_doc_header(text: str):
    """Извлекает номер и дату документа из шапки PDF."""
    # Берём первые 1500 символов — шапка документа
    header = text[:1500]

    doc_number = None
    doc_date = None

    # Номер
    m = RE_DOC_NUMBER.search(header)
    if m:
        doc_number = m.group(1).strip()
        # Определяем тип документа для полного номера
        full_match = m.group(0).strip()
        doc_type = full_match.split()[0] if full_match else ''
        doc_number = doc_type.capitalize() + ' №' + doc_number
        logging.info(f"[PDF-PARSER] Номер документа: {doc_number}")

    # Дата (словами)
    m = RE_DOC_DATE.search(header)
    if m:
        day, m_name, year = m.groups()
        month = MONTHS.get(m_name.lower())
        if month:
            doc_date = f"{int(day):02d}.{month:02d}.{year}"
            logging.info(f"[PDF-PARSER] Дата документа: {doc_date}")

    # Дата (цифрами)
    if not doc_date:
        m = RE_DOC_DATE_DOT.search(header)
        if m:
            day, month, year = m.groups()
            doc_date = f"{int(day):02d}.{int(month):02d}.{year}"
            logging.info(f"[PDF-PARSER] Дата документа (цифры): {doc_date}")

    return doc_number, doc_date


# ─────────────────────────────────────────────────────────────────────────────
def parse_pdf(file_path=None, file_bytes=None, filename=""):
    try:
        from services.districts import DISTRICTS
    except ImportError:
        DISTRICTS = {}

    source_name = filename or file_path or "Unknown"
    logging.info(f"[PDF-PARSER] Начат парсинг: {source_name} "
                 f"(pdfplumber={USE_PDFPLUMBER}, ocr={USE_OCR})")

    try:
        if file_bytes is None and file_path:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()

        if not file_bytes:
            logging.error("[PDF-PARSER] Нет данных для разбора")
            return None

        file_hash = hashlib.md5(file_bytes).hexdigest()

        # ── Каскад извлечения текста ──────────────────────────────────────
        text = ""

        if USE_PDFPLUMBER:
            try:
                text = _extract_text_pdfplumber(file_bytes)
                if text:
                    logging.info(f"[PDF-PARSER] pdfplumber: извлечено {len(text)} символов")
            except Exception as e:
                logging.warning(f"[PDF-PARSER] pdfplumber не сработал: {e}")

        if not text:
            text = _extract_text_pypdf2(file_bytes)
            if text:
                logging.info(f"[PDF-PARSER] PyPDF2: извлечено {len(text)} символов")

        if not text and USE_OCR:
            text = _extract_text_ocr(file_bytes)
            if text:
                logging.info(f"[PDF-PARSER] OCR: извлечено {len(text)} символов")

        if not text:
            logging.error(f"[PDF-PARSER] Текст не извлечён из {source_name} ни одним методом")
            return None

        # ── Номер и дата документа ─────────────────────────────────────────
        doc_number, doc_date = _parse_doc_header(text)

        # ── Разбивка на пункты ────────────────────────────────────────────
        # Основной split по пунктам с точкой
        segments = RE_ITEM_HEADER.split(text)
        tasks = []

        # Если основной regex не нашёл пунктов, пробуем без точки (OCR)
        if len(segments) < 3:
            segments = RE_ITEM_NO_DOT.split(text)

        if len(segments) < 3:
            logging.warning("[PDF-PARSER] Структурированные пункты не найдены -> одна запись")
            tasks.append({
                "title": filename or "Поручение из PDF",
                "text": text[:2000].strip(),
                "executor": _parse_executor(text),
                "deadline": _parse_deadline(text) or datetime.utcnow(),
                "file_hash": file_hash,
            })
            return {"doc_number": doc_number, "doc_date": doc_date, "tasks": tasks}

        # Словари для хранения "наследования" исполнителей и сроков
        executor_hierarchy = {}
        deadline_hierarchy = {}
        
        # Режим массового назначения всем районам
        mass_district_mode = False

        # Парсим каждый пункт
        for i in range(1, len(segments) - 1, 2):
            item_num = segments[i].strip().rstrip('.')
            content = segments[i + 1].strip()

            # Фильтр ложных срабатываний: числа > 30 без точки — это не пункты
            if '.' not in item_num and item_num.isdigit() and int(item_num) > 30:
                continue

            if len(content) < 5:
                continue

            # Плюс проверяем, нет ли массового поручения в предшествующем тексте
            context_before = segments[i - 1].strip() if i >= 1 else ""
            
            # Проверяем на массовое поручение районам
            if 'органам местного самоуправления' in content.replace('\n', ' ').lower():
                mass_district_mode = True
            elif 'органам местного самоуправления' in context_before.replace('\n', ' ').lower():
                mass_district_mode = True

            current_executor = _parse_executor(content)
            
            # Если мы в режиме массового поручения, и локальный парсер ничего специфичного не нашел 
            # (или нашел только по первым 50 символам, что скорее просто текст абзаца),
            # применяем массовый режим.
            #_parse_executor возвращает как fallback: content[:50].strip() + '...'
            is_fallback_executor = current_executor.endswith('...') or current_executor == 'Ответственное лицо'
            
            if mass_district_mode and (is_fallback_executor or current_executor == '__ALL_DISTRICTS__'):
                current_executor = '__ALL_DISTRICTS__'
            elif current_executor and not is_fallback_executor and current_executor != '__ALL_DISTRICTS__':
                # Если явно найден другой настоящий исполнитель (ведомство/ФИО), отключаем массовый режим,
                # если только это не подпункт массовой задачи.
                if '.' not in item_num:
                    mass_district_mode = False
                
            current_deadline = _parse_deadline(content)

            # 2. Логика наследования
            parts = item_num.split('.')

            # Наследуем исполнителя от родительского пункта
            if current_executor == 'Ответственное лицо' or not current_executor:
                for depth in range(len(parts) - 1, 0, -1):
                    parent_num = '.'.join(parts[:depth])
                    if parent_num in executor_hierarchy:
                        current_executor = executor_hierarchy[parent_num]
                        break

            # Наследуем дату от родительского пункта
            if not current_deadline:
                for depth in range(len(parts) - 1, 0, -1):
                    parent_num = '.'.join(parts[:depth])
                    if parent_num in deadline_hierarchy:
                        current_deadline = deadline_hierarchy[parent_num]
                        break

            # 3. Сохраняем для наследования потомками
            executor_hierarchy[item_num] = current_executor
            if current_deadline:
                deadline_hierarchy[item_num] = current_deadline

            # 4. Формируем заголовок
            first_line = next((l.strip() for l in content.split('\n') if l.strip()), '')
            short_title = first_line if len(first_line) < 80 else first_line[:77] + '...'

            if current_executor == '__ALL_DISTRICTS__':
                for district_name in DISTRICTS.keys():
                    tasks.append({
                        'item_number': item_num,
                        'title': f'П. {item_num} {short_title}',
                        'text': content,
                        'executor': district_name,
                        'deadline': current_deadline or datetime.utcnow(),
                        'file_hash': file_hash,
                    })
                logging.info(f"[PDF-PARSER] П.{item_num}: развёрнут на все {len(DISTRICTS)} районов")
            else:
                tasks.append({
                    'item_number': item_num,
                    'title': f'П. {item_num} {short_title}',
                    'text': content,
                    'executor': current_executor,
                    'deadline': current_deadline or datetime.utcnow(),
                    'file_hash': file_hash,
                })
                logging.info(f"[PDF-PARSER] П.{item_num}: исп={current_executor}, срок={current_deadline}")

        logging.info(f"[PDF-PARSER] Итого найдено пунктов: {len(tasks)}")
        if tasks:
            return {'doc_number': doc_number, 'doc_date': doc_date, 'tasks': tasks}
        return None

    except Exception as e:
        logging.error(f"[PDF-PARSER] Критическая ошибка при разборе {source_name}: {e}", exc_info=True)
        return None