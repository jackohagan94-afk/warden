FROM python:3.13-slim

ARG VERSION=dev
ARG VCS_REF

LABEL org.opencontainers.image.title="Warden"
LABEL org.opencontainers.image.description="Automated media library management for *Arr ecosystems"
LABEL org.opencontainers.image.source="https://github.com/johagan94/warden"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.licenses="MIT"

RUN groupadd -r nonroot -g 65532 && useradd -r -g nonroot -u 65532 -d /app nonroot

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod -R a+rX /app

USER nonroot:nonroot

ENTRYPOINT ["python", "-m", "warden.main"]
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=10s \
    CMD ["python", "-c", "import warden"]
