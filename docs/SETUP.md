# Setup

There are two ways to run Universal Adaptive Trainer: with Docker, which needs nothing else
installed, or directly on your machine for development. Either way you end up with:

- the app at [http://localhost:3000](http://localhost:3000)
- the API docs at [http://localhost:8000/docs](http://localhost:8000/docs)
- a development login: `dev@local.test` / `devpassword123`

The app runs without a model key. You need one to generate or judge questions; add it to
`.env` (below) or paste it later under **Settings → Providers**.

- [Docker](#docker)
- [Windows](#windows)
- [Linux and macOS](#linux-and-macos)
- [Model providers](#model-providers)
- [Troubleshooting](#troubleshooting)

## Docker

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS) or
Docker Engine with the Compose plugin (Linux), then:

```bash
git clone https://github.com/Amitdutta121/Universal_adaptive_trainer.git
cd Universal_adaptive_trainer
docker compose up --build
```

The first build takes several minutes. When both containers are up, open
[http://localhost:3000](http://localhost:3000).

To give the app a model key, copy `.env.example` to `.env`, fill in a key, and run
`docker compose up --build` again. Compose reads `.env` if it exists.

| Command | What it does |
| --- | --- |
| `docker compose up -d --build` | start in the background |
| `docker compose logs -f backend` | follow the backend log |
| `docker compose down` | stop |
| `docker compose down -v` | stop and delete the database and uploaded books |

The database and uploads live in the `backend-data` volume, so they survive restarts.

## Windows

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python
for you), [Node.js 20 or newer](https://nodejs.org) and [Git](https://git-scm.com). Run these
in PowerShell. To install uv: `winget install astral-sh.uv`.

```powershell
git clone https://github.com/Amitdutta121/Universal_adaptive_trainer.git
cd Universal_adaptive_trainer

# backend
uv venv --python 3.12 .venv
uv pip install -e ".[dev]" --override scripts/uv-overrides.txt
Copy-Item .env.example .env

# frontend
corepack enable
cd frontend
pnpm install
Copy-Item .env.example .env.local
cd ..
```

Start the backend and the frontend in two terminals:

```powershell
.\.venv\Scripts\python.exe -m app
```

```powershell
cd frontend
pnpm dev
```

The first page load compiles the app and can take a minute or two.

## Linux and macOS

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python
for you), Node.js 20 or newer and Git. Install uv with
`curl -LsSf https://astral.sh/uv/install.sh | sh`, and Node from
[nodejs.org](https://nodejs.org) or with [nvm](https://github.com/nvm-sh/nvm).

```bash
git clone https://github.com/Amitdutta121/Universal_adaptive_trainer.git
cd Universal_adaptive_trainer

# backend
uv venv --python 3.12 .venv
uv pip install -e ".[dev]" --override scripts/uv-overrides.txt
cp .env.example .env

# frontend
corepack enable
cd frontend
pnpm install
cp .env.example .env.local
cd ..
```

Start the backend and the frontend in two terminals:

```bash
.venv/bin/python -m app
```

```bash
cd frontend
pnpm dev
```

If `corepack enable` fails with a permission error, run `sudo corepack enable` or install
pnpm with `npm install -g pnpm`.

## Model providers

Set `LLM_ROUTE` in `.env` to the provider you use and fill in its key:

| Provider | `LLM_ROUTE` | Key |
| --- | --- | --- |
| OpenRouter | `openrouter` | `LLM_API_KEY` |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| Azure OpenAI | `azure` | `AZURE_API_KEY`, `AZURE_BASE_URL` |
| xAI | `xai` | `XAI_API_KEY` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` |
| vLLM, Ollama or any OpenAI-compatible server | `custom` | `CUSTOM_BASE_URL`, `CUSTOM_MODEL` |

Restart the backend after editing `.env`. Every other setting is described in [`.env.example`](../.env.example).

### Optional extras

- Better PDF chunking with Docling: rerun the install with `".[dev,parse]"` instead of
  `".[dev]"`, then
  `python -m scripts.download_docling_models`. It pulls in CPU PyTorch and about 500 MB of
  models; without it, PDFs are split by page.
- Sandboxed code execution: by default, question and student code runs in a local process.
  Before you open the app to students, start the [Piston sandbox](../docker/piston/README.md)
  and set `EXECUTOR=piston`.

## Troubleshooting

- **Port already in use.** Change `PORT` in `.env` (backend), then set `API_ORIGIN` in
  `frontend/.env.local` to match. Run the frontend on another port with `pnpm dev -p 3001`.
- **The page loads but every request fails.** The backend isn't running, or `API_ORIGIN` in
  `frontend/.env.local` points at the wrong port.
- **Model calls fail with `PermissionError` on Windows.** An antivirus (Avast, for example)
  may have set `SSLKEYLOGFILE`. Clear it in the backend's terminal with
  `Remove-Item Env:SSLKEYLOGFILE` and restart the backend.
- **Starting over.** Stop the backend and delete `data/adaptive_trainer.db`; it is recreated
  on the next start. With Docker, use `docker compose down -v`.

For tests, linting and the project layout, see [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md).
To put the app on a server with HTTPS, see [DEPLOYMENT.md](DEPLOYMENT.md).
