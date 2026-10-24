FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend
COPY mobile /app/mobile
COPY scripts /app/scripts
WORKDIR /app
# Demo seed runs only when DEV_MODE=true (or ALLOW_DEMO_SEED=true is set by the seed script guards).
# Production containers must not auto-create demonstration accounts.
# ensure_schema adds missing observation/profile columns on Postgres (create_all does not alter existing tables).
CMD ["sh", "-c", "python -m backend.app.ensure_schema || python backend/app/ensure_schema.py || true; if [ \"${DEV_MODE}\" = \"true\" ] || [ \"${ALLOW_DEMO_SEED}\" = \"true\" ]; then python -m scripts.seed_average_profile; else echo 'Skipping demo seed (production-safe startup)'; fi; exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
