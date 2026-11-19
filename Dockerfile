FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Сначала только зависимости — этот слой кэшируется и не пересобирается при правке кода.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY cocbot ./cocbot
COPY scripts ./scripts

# Не запускаем бота от root.
RUN useradd --create-home --uid 1000 bot && mkdir -p /app/data && chown bot:bot /app/data
USER bot

ENV DATABASE_PATH=/app/data/cocbot.db
VOLUME ["/app/data"]

CMD ["python", "-m", "cocbot"]
