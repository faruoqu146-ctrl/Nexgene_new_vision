FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY mobile /app/mobile
COPY scripts /app/scripts
WORKDIR /app
# Seed demo profile (no-op if already present), then serve the API.
CMD ["sh", "-c", "python -m scripts.seed_average_profile; exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
