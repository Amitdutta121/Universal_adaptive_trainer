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
  sections with full source traceability.

Not implemented yet: curriculum extraction, LLM question generation, question validation,
professor preference learning, and the student adaptive engine — see `docs/DECISIONS.md` (ADR-009).

### Books are imported as JSON

The application accepts **only structured book JSON**: a document that already declares its own
chapters, sections, section text and page ranges. Supply a valid document and it is validated
strictly, then stored.

There is **no parsing or conversion anywhere in this repository** — no PDF, EPUB or HTML reader, and
no converter script. Heuristic extraction was removed because it is not deterministic across books:
rules tuned on one textbook silently mis-segment the next, and the output still looks like a valid
structure, so the mistake goes unnoticed (`docs/DECISIONS.md` ADR-015). Producing the document is
deliberately somebody else's job, because any converter is book-specific in practice (ADR-016).

`docs/book_document_example.json` is a complete, valid example, and the Books page shows the shape
inline. In brief:

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

### LLM provider

Curriculum proposal (and later question generation) needs a provider. Set these in `.env`:

| Provider     | `LLM_PROVIDER` | `LLM_MODEL` example      | Key format   |
| ------------ | -------------- | ------------------------ | ------------ |
| OpenRouter   | `openrouter`   | `deepseek/deepseek-chat` | `sk-or-v1-…` |
| Anthropic    | `anthropic`    | `claude-sonnet-5`        | `sk-ant-…`   |
| OpenAI       | `openai`       | `gpt-4.1`                | `sk-…`       |
| None         | `none`         | —                        | —            |

The default configuration is **OpenRouter routed to DeepSeek V3**:

```dotenv
LLM_PROVIDER=openrouter
LLM_MODEL=deepseek/deepseek-chat
LLM_API_KEY=sk-or-v1-your-key-here
```

OpenRouter requests are pinned to upstream routes that actually enforce the JSON Schema and that do
not retain prompts for training (`docs/DECISIONS.md` ADR-019). Prefer a non-reasoning route:
`deepseek/deepseek-r1` spends part of `LLM_MAX_OUTPUT_TOKENS` on hidden reasoning tokens, so raise
that budget before using one.

With no key set, the app still starts and every page still renders — the dashboard reports the LLM
as unavailable rather than crashing (ADR-010).

## Run

```powershell
.\.venv\Scripts\python.exe -m app
```

Then open <http://127.0.0.1:8000/>.

Equivalent, if you prefer driving uvicorn directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Sections

| Page                                                     | Purpose                                          |
| -------------------------------------------------------- | ------------------------------------------------ |
| [/](http://127.0.0.1:8000/)                              | Dashboard: counts, environment, LLM status       |
| [/books](http://127.0.0.1:8000/books)                    | Import book JSON; browse chapters and sections   |
| [/curriculum](http://127.0.0.1:8000/curriculum)          | Versioned Topic → Subtopic curriculum            |
| [/questions](http://127.0.0.1:8000/questions)            | Generated question bank                          |
| [/feedback](http://127.0.0.1:8000/feedback)              | Professor approve / reject / edit history         |
| [/students](http://127.0.0.1:8000/students)              | Adaptive training (fixed mechanism, not built)   |
| [/api/health](http://127.0.0.1:8000/api/health)          | JSON health check                                |
| [/docs](http://127.0.0.1:8000/docs)                      | OpenAPI docs                                     |

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

## Documentation

- `CLAUDE.md` — product objective, the fixed adaptive-training decisions, coding conventions and
  working agreements. Read this before changing the architecture.
- `docs/DECISIONS.md` — the architectural decision log.
