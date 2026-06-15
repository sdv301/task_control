# По умолчанию — offline (см. Dockerfile.offline).
# Полная сборка с apt: Dockerfile.online

FROM my_portal-task-app:latest

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
RUN mkdir -p /data /app/logs

RUN pip install --no-cache-dir supervisor
COPY app/supervisord.conf /app/supervisord.conf

CMD ["supervisord", "-c", "/app/supervisord.conf"]
