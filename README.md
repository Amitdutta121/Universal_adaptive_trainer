<p align="center">
  <img src="docs/images/logo.svg" alt="Universal Adaptive Trainer logo" width="96">
</p>

<h1 align="center">Universal Adaptive Trainer</h1>

<p align="center">
  Turn your course material into reviewed practice questions,<br>
  and give every student the question they need next.
</p>

<p align="center">
  <a href="#getting-started">Getting started</a> ·
  <a href="docs/LOCAL_DEVELOPMENT.md">Local development</a> ·
  <a href="../../issues">Issues</a>
</p>

<p align="center">
  <img src="docs/images/review-queue.png" alt="Review queue showing a generated question next to the judges' verdicts" width="900">
</p>

## Features

- Import books, PDFs, slides and YouTube lectures, and organize them into topics and subtopics.
- Generate questions from your own material: multiple choice, true/false, Parsons problems,
  code completion, coding, debugging, output prediction, numeric and equation answers.
- Check every question automatically. Code is run, numeric answers are compared with units,
  formulas are compared symbolically, and a panel of AI judges rates difficulty and topic fit.
- Review questions in one queue. Your accept and reject decisions teach the generator and the
  judges for the next round.
- Share a link with your class. Students sign in with a name and email, and each answer
  updates their mastery of that topic, which decides the next question.
- Live tutorials and a coverage view show which topics a question set teaches and tests.
- Works with intro Python, physics, machine learning and biology courses out of the box,
  or any subject you define.

<p align="center">
  <img src="docs/images/dashboard.png" alt="Course dashboard with the setup checklist" width="440">
  <img src="docs/images/coverage.png" alt="Coverage map showing how many questions each topic has" width="440">
</p>

## Getting started

You need Python 3.11 or newer, Node.js with [pnpm](https://pnpm.io), and an API key for one
model provider. The commands below are for PowerShell.

```powershell
git clone https://github.com/Amitdutta121/Universal_adaptive_trainer.git
cd Universal_adaptive_trainer

py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env

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
pnpm run dev
```

Open [http://localhost:3000](http://localhost:3000) and sign in with `dev@local.test` /
`devpassword123`. This account exists only in development. The first page load compiles the
app and can take a few minutes.

### Model providers

Add your key to `.env`, or paste it later under **Settings → Providers** in the app.
OpenRouter, OpenAI, Anthropic, Azure OpenAI, xAI and DeepSeek are supported, as is any
OpenAI-compatible server such as vLLM or Ollama. Every other setting is described in
[`.env.example`](.env.example).

### Running student code safely

By default, code from questions and student answers runs in a local process. Before you
open the app to students, start the [Piston sandbox](docker/piston/README.md) and set
`EXECUTOR=piston`.

## Development

```powershell
# backend tests and lint
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

# frontend type check, lint and tests
cd frontend
pnpm tsc --noEmit
pnpm biome lint src
pnpm vitest run
```

Tests that call a real model are skipped by default because they cost money. Run them with
`pytest -m integration`.

## Built with

FastAPI, SQLAlchemy and Alembic on the backend; Next.js, React, TanStack Query and Tailwind on
the frontend. It uses SQLite locally and is written to run on PostgreSQL.

## License

No license has been chosen yet. PDF import uses PyMuPDF, which is licensed under AGPL-3.0.
