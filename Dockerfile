FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    DATA_DIR=/data

WORKDIR ${APP_HOME}

RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx supervisor curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --system --create-home --uid 10001 appuser && \
    rm -f /etc/nginx/sites-enabled/default

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY sources.example.json ./sources.example.json
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/supervisord.conf /etc/supervisor/conf.d/app.conf
COPY deploy/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && \
    mkdir -p /data /var/cache/nginx /var/run && \
    chown -R appuser:appuser /app /data /var/cache/nginx /var/run

EXPOSE 8080
VOLUME ["/data"]
ENTRYPOINT ["/entrypoint.sh"]
