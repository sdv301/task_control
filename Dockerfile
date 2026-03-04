FROM python:3.10-slim

WORKDIR /

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

# Запускаем Flask из папки /app
WORKDIR /app
CMD ["flask", "run", "--host=0.0.0.0"]
