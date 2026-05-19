FROM python:3.13-slim

RUN groupadd -r nonroot -g 65532 && useradd -r -g nonroot -u 65532 -d /app nonroot

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER nonroot:nonroot

ENTRYPOINT ["python", "-m", "warden.main"]
HEALTHCHECK --interval=60s --timeout=10s --retries=3 --start-period=10s \
    CMD ["python", "-c", "import warden"]
