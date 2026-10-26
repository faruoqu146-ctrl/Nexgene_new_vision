# Import path note

Render/Docker must set:

```
PYTHONPATH=/app:/app/backend/app
```

This is set in the Dockerfile. If you run locally:

```bash
export PYTHONPATH=/path/to/repo:/path/to/repo/backend/app
uvicorn backend.app.main:app --reload
```

`main.py` tries relative imports first (`from . import research`), then falls back to `import research`, which requires `/backend/app` on PYTHONPATH.
