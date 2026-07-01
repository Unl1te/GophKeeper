# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Lean image, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

COPY web /app/web

# Entrypoint applies DB migrations (or create_all fallback) before the API starts.
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
# Default command the entrypoint exec's after migrations. docker-compose may override.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
