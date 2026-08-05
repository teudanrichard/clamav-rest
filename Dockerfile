FROM python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0

ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG APP_VERSION=0.0.0-dev
LABEL org.opencontainers.image.title="ClamAV HTTP Gateway" \
      org.opencontainers.image.description="Bounded asynchronous ClamAV REST gateway" \
      org.opencontainers.image.source="https://gitlab.com/rteudan/rsa/clamav-rest" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    CLAMR_VERSION=${APP_VERSION}

RUN addgroup -S -g 10001 gateway \
    && adduser -S -D -H -u 10001 -G gateway gateway

WORKDIR /app
COPY requirements.lock ./
COPY VERSION ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.lock
COPY --chown=gateway:gateway app ./app

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
