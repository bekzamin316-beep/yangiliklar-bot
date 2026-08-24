FROM python:3.12-slim

WORKDIR /app

# Install system deps needed by psycopg2-binary + feedparser
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY pyproject.toml .

# Always-on hosts (HF Spaces) reach the app on this port
EXPOSE 7860

# Run
CMD ["python", "-m", "src.main"]
