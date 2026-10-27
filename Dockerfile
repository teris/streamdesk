FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium ffmpeg fonts-dejavu-core gosu \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/streamdesk
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin streamdesk \
    && useradd --system --uid 10002 --no-create-home --shell /usr/sbin/nologin streamdesk-browser \
    && chmod +x scripts/container-entrypoint.sh
ENTRYPOINT ["scripts/container-entrypoint.sh"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
