FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Berlin

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# config/ holds config.json (mount it as a volume to persist API keys)
RUN mkdir -p config artifacts/cache
VOLUME ["/app/config"]

EXPOSE 8000

CMD ["python", "-m", "src.main"]
