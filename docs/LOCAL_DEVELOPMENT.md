# Local Development

## Backend Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Frontend Setup

```powershell
cd frontend
pnpm install
```

## Run The App

```powershell
# terminal 1: backend
.\.venv\Scripts\python.exe -m app

# terminal 2: frontend
cd frontend
pnpm run dev
```

- Instructor Studio: [http://localhost:3000](http://localhost:3000)
- FastAPI docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health endpoint: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

## Run With Docker

The repository includes:

- `Dockerfile` for the FastAPI backend
- `frontend/Dockerfile` for the Next.js frontend
- `docker-compose.yml` to run both services together

Start everything with:

```powershell
docker compose up --build
```

Then open:

- Instructor Studio: [http://localhost:3000](http://localhost:3000)
- FastAPI docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Useful commands:

```powershell
docker compose down
docker compose down -v
```

- `docker compose down` stops the app
- `docker compose down -v` also removes the named SQLite data volume

Notes:

- The compose setup keeps backend data in a Docker volume mounted at `/app/data`.
- The frontend container rewrites `/api/*` traffic to the backend container over the internal
  Docker network.
- The backend runs in `ENVIRONMENT=development` so the seeded local professor account is available.

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

## Notes

- There is no migration system yet; local schema changes may require recreating `data/adaptive_trainer.db`.
