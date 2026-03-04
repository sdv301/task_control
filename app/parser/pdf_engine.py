import re
import PyPDF2
from datetime import datetime
import hashlib
import logging

def parse_pdf(file_path):
    """
    Парсинг PDF для извлечения сущностей: Исполнитель, Срок (Deadline), Текст
    """
    logging.info(f"Начат парсинг файла {file_path}")
    text = ""
    try:
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
                    
        # Вычисление хеша файла для проверки дубликатов
        with open(file_path, 'rb') as file:
            file_hash = hashlib.md5(file.read()).hexdigest()

        # Простая эвристика / Регулярки для извлечения:
        # Исполнитель: Иванов И.И.
        # Срок: до 31.12.2025
        
        executor_match = re.search(r"Исполнитель:\s*([А-Яа-яA-Za-z\s.]+)", text)
        deadline_match = re.search(r"Срок:\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", text)
        title_match = re.search(r"Поручение:\s*(.+)", text)
        
        executor_name = executor_match.group(1).strip() if executor_match else "Неизвестный исполнитель"
        title = title_match.group(1).strip() if title_match else "Новое поручение"
        
        deadline_date = datetime.utcnow()
        if deadline_match:
            try:
                deadline_date = datetime.strptime(deadline_match.group(1), "%d.%m.%Y")
            except ValueError:
                logging.error(f"Ошибка парсинга даты: {deadline_match.group(1)}")

        return {
            "title": title,
            "text": text,
            "executor": executor_name,
            "deadline": deadline_date,
            "file_hash": file_hash
        }
    except Exception as e:
        logging.error(f"Ошибка при парсинге {file_path}: {str(e)}")
        return None
