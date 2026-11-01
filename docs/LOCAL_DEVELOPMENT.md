# Local Development

Installing and starting the app on Windows, Linux, macOS or Docker is covered in
[SETUP.md](SETUP.md). This page covers working on the code.

- FastAPI docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health endpoint: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

## Development Login

When `ENVIRONMENT=development`, the backend seeds a local professor account:

```dotenv
DEV_USER_EMAIL=dev@local.test
DEV_USER_PASSWORD=devpassword123
```

These credentials are for local development only.

## Checks

### Backend

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

### Frontend

```powershell
cd frontend
pnpm run check
pnpm run build
```

## Schema changes

Every schema change is an Alembic revision in `app/persistence/migrations/versions/`. The
backend runs `alembic upgrade head` on startup.
