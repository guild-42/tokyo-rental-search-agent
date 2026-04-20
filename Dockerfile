FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV FETCH_INTERVAL_MINUTES=10
ENV FETCH_MAX_PAGES=10
ENV FETCH_WARD_CODES=13104,13113,13114,13115
ENV MAX_AGE_DAYS=30
ENV DB_PATH=/app/data/rental.db
ENV PORT=8080

# メール通知 (NOTIFY_SMTP_PASSWORD は Coolify UI の env で設定)
ENV NOTIFY_ENABLED=1
ENV NOTIFY_EMAIL_TO=bibimsoba@gmail.com,sakura199635@gmail.com
ENV NOTIFY_SMTP_USER=bibimsoba@gmail.com
ENV NOTIFY_CONDITIONS={"rent_max":80000,"walk_max":10,"size_min":20,"layouts":["1K","1DK","1LDK"],"age_max":20}

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["python", "main.py", "serve", "--port", "8080"]
