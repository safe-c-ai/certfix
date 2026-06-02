FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/certfix

COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src ./src
COPY docker/certfix-entrypoint.sh /usr/local/bin/certfix-entrypoint

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir . \
    && chmod +x /usr/local/bin/certfix-entrypoint

WORKDIR /workspace

ENTRYPOINT ["certfix-entrypoint"]
CMD ["--help"]
