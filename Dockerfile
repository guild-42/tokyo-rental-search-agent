FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV FETCH_INTERVAL_MINUTES=30
ENV FETCH_MAX_PAGES=10
ENV FETCH_WARD_CODES=13104,13113,13114
ENV MAX_AGE_DAYS=30
ENV DB_PATH=/app/data/rental.db
ENV PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["python", "main.py", "serve", "--port", "8080"]
