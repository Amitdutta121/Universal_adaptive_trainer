# Adaptive Trainer

An adaptive Python training platform with two separate systems:

- **Professor content generation** — upload textbooks, approve a Topic → Subtopic curriculum,
  generate and validate assessment questions, review them, and let the generator learn from those
  reviews.
- **Student adaptive training** — BKT topic mastery and subtopic weakness decide what to ask next.

Implemented so far:

- the project foundation — module boundaries, configuration, logging, error handling, persistence,
  tests;
- **textbook ingestion** — import a structured book JSON document, then browse its chapters and
  sections with full source traceability;
- **curriculum taxonomy upload** — import a fixed Topic → Subtopic taxonomy JSON on
  `/curriculum`; a valid upload becomes the approved curriculum version immediately.

Not implemented yet: LLM question generation, question validation, professor preference learning,
and the student adaptive engine — see `docs/DECISIONS.md` (ADR-009).

### Books are imported as JSON

The application accepts **only structured book JSON**: a document that already declares its own
chapters, sections, section text and page ranges. Supply a valid document and it is validated
strictly, then stored.

There is **no parsing or conversion anywhere in this repository** — no PDF, EPUB or HTML reader, and
no converter script. Heuristic extraction was removed because it is not deterministic across books:
rules tuned on one textbook silently mis-segment the next, and the output still looks like a valid
structure, so the mistake goes unnoticed (`docs/DECISIONS.md` ADR-015). Producing the document is
deliberately somebody else's job, because any converter is book-specific in practice (ADR-016).

`docs/book_document_example.json` is a complete, valid example, and the Books
screen plus `GET /api/books/document-guide` expose the same shape. In brief:

```json
{
  "schema_version": "1",
  "title": "Think Python",
  "chapters": [
    { "number": "1", "title": "The Way of the Program", "sections": [
      { "number": "1.1", "title": "What Is a Program?", "start_page": 17,
        "text": "A program is a sequence of instructions ...",
        "structure_source": "pdf_outline" }
    ]}
  ]
}
```

Every chapter needs ≥1 section and every section needs non-empty `text`. `title` may be `null` when
the source printed no heading — never invent one. Unknown fields are rejected rather than ignored,
and an invalid document is refused in full before anything is stored.

### Curriculum is uploaded as JSON

The application accepts **only structured taxonomy JSON**: a document that declares its own
Topic → Subtopic hierarchy. Supply a valid document on `/curriculum` and it is validated
strictly, then stored as an **approved** curriculum version. The application does **not** derive
curriculum from books or through an LLM (`docs/DECISIONS.md` ADR-021).

`docs/taxonomy_document_example.json` is a complete, valid example, and the
Curriculum screen plus `GET /api/curriculum/document-guide` expose the required
shape inline. In brief:

```json
{
  "schema_version": "1",
  "label": "Introductory Python",
  "topics": [
    {
      "name": "Variables",
      "description": "Creating names, assigning values, and understanding types.",
      "subtopics": [
        {
          "name": "Assignment and rebinding",
          "description": "Using = to bind a name to a value and reassign it later."
        }
      ]
    }
  ]
}
```

Every topic needs ≥1 subtopic. Unknown fields are rejected rather than ignored, and an invalid
document is refused in full before anything is stored. Each valid upload creates a new approved
version; the latest approved version is used for question generation.

> **Note:** this stage changed the `books`, `book_chapters` and `book_sections` tables and there is
> no migration tool yet. If you have an older `data/adaptive_trainer.db`, delete it and let it be
> recreated. The app tells you so explicitly at startup rather than failing later (ADR-014).

## Requirements

- Python 3.11+ (the checked-in virtualenv uses 3.12)

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Configuration is optional — the app runs with defaults and no credentials. To customise:

```powershell
Copy-Item .env.example .env
```

### Development login

When `ENVIRONMENT=development`, the app seeds one local professor account with these defaults:

```dotenv
DEV_USER_EMAIL=dev@local.test
DEV_USER_PASSWORD=devpassword123
```

These are development-only credentials for local use. Do not reuse them in staging or production,
and do not keep the default `AUTH_SECRET_KEY` outside local development.

### LLM provider

Question generation (when implemented) needs a provider. Curriculum upload does not. Set these
in `.env`:

| Provider   | `LLM_PROVIDER` | `LLM_MODEL` example      | Key format   |
| ---------- | -------------- | ------------------------ | ------------ |
| OpenRouter | `openrouter`   | `deepseek/deepseek-chat` | `sk-or-v1-…` |
| None       | `none`         | —                        | —            |

The default configuration is **OpenRouter routed to DeepSeek V3**:

```dotenv
LLM_PROVIDER=openrouter
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-or-v1-your-key-here
```

Every OpenRouter request asks upstream providers not to retain prompts for training
(`provider.data_collection: deny`; see `docs/DECISIONS.md` ADR-020). Prefer a non-reasoning route:
`deepseek/deepseek-r1` spends part of `LLM_MAX_OUTPUT_TOKENS` on hidden reasoning tokens, so raise
that budget before using one.

With no key set, the app still starts and the professor console still loads —
the dashboard reports the LLM as unavailable rather than crashing (ADR-010).

## Run

```powershell
# terminal 1: backend API
.\.venv\Scripts\python.exe -m app

# terminal 2: React professor console
cd frontend
pnpm install
pnpm run dev
```

Then open <http://localhost:3000/> for the professor console. The FastAPI API
stays on <http://127.0.0.1:8000/>.

Equivalent, if you prefer driving uvicorn directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Routes

| Route                                             | Purpose                                                     |
| ------------------------------------------------- | ----------------------------------------------------------- |
| [http://localhost:3000/](http://localhost:3000/)  | React professor console                                     |
| [http://localhost:3000/books](http://localhost:3000/books) | Import book JSON; browse chapters and sections     |
| [http://localhost:3000/curriculum](http://localhost:3000/curriculum) | Upload taxonomy JSON; browse versions |
| [http://localhost:3000/questions](http://localhost:3000/questions) | Generated question bank and question detail     |
| [http://localhost:3000/review](http://localhost:3000/review) | Review queue                                         |
| [http://localhost:3000/students](http://localhost:3000/students) | Student enrolment and adaptive progress            |
| [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health) | JSON health check                         |
| [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | OpenAPI docs                                        |

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

## Documentation

- `docs/ADAPTIVE_TUNING_README.md` - simulator-based tuning method and the current adaptive
  defaults chosen on August 18, 2026.
- `CLAUDE.md` — product objective, the fixed adaptive-training decisions, coding conventions and
  working agreements. Read this before changing the architecture.
- `docs/DECISIONS.md` — the architectural decision log.
