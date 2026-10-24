"""PLACEHOLDER — replace this file with the full NexGene backend main.py.

This stub keeps the service importable until the real file is restored.
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

APP_VERSION = "0.0.0-placeholder"

app = FastAPI(title="NexGene API (placeholder)", version=APP_VERSION)


@app.get("/")
def root():
    return JSONResponse(
        {
            "status": "placeholder",
            "message": "backend/app/main.py is a placeholder. Replace with the full main.py and redeploy.",
            "version": APP_VERSION,
        }
    )


@app.get("/api/v1/health")
def health():
    return {"status": "placeholder", "version": APP_VERSION}
