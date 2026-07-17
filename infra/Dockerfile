FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fontconfig libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY clipfactory ./clipfactory
COPY dashboard ./dashboard
COPY engine ./engine
COPY config ./config
COPY assets ./assets
COPY infra ./infra

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[local]" \
    && fc-cache -f

ENTRYPOINT ["python", "-m", "clipfactory.run"]
