FROM python:3.10-slim

# Системные зависимости для OCR (Tesseract) и рендеринга PDF (poppler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-rus \
    poppler-utils \
    libpoppler-cpp-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

# Запускаем Flask из папки /app
WORKDIR /app
CMD ["flask", "run", "--host=0.0.0.0"]
