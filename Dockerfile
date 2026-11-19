FROM python:3.13-slim

LABEL org.opencontainers.image.title="Clan Warden" \
      org.opencontainers.image.description="Self-hosted Clash of Clans Telegram bot" \
      org.opencontainers.image.source="https://github.com/SeredaVitaliy/clan-warden" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is cached and isn't rebuilt when only the code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY clanwarden ./clanwarden
COPY scripts ./scripts

# Don't run the bot as root.
RUN useradd --create-home --uid 1000 bot && mkdir -p /app/data && chown bot:bot /app/data
USER bot

ENV DATABASE_PATH=/app/data/clanwarden.db
VOLUME ["/app/data"]

CMD ["python", "-m", "clanwarden"]
