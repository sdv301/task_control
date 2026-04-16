FROM python:3.10-slim

# Системные зависимости для OCR (Tesseract) и рендеринга PDF (poppler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    poppler-utils \
    libpoppler-cpp-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё приложение
COPY app/ /app/

# Копируем файл светофоры.xlsx в корень рабочей директории
COPY светофоры.xlsx /app/светофоры.xlsx

# Создаём директории для данных и логов
RUN mkdir -p /data /app/logs

# Запускаем Flask приложение
CMD ["python", "main.py"]
