# CLAUDE.md

Guidance for any AI agent or developer working in this repository.

## Product objective

An **adaptive Python training platform** made of two conceptually separate systems.

### A. Professor content-generation system

A professor should eventually be able to:

1. upload several introductory Python textbooks;
2. inspect the extracted textbook structure;
3. upload a fixed Topic → Subtopic taxonomy JSON;
4. inspect the approved curriculum hierarchy;
5. generate Python assessment questions grounded in the approved books and curriculum;
6. have those questions validated automatically;
7. approve, reject or edit generated questions;
8. have the system learn the professor's preferences from those reviews;
9. progressively receive questions that better match those preferences;
10. later optimize the generator using accumulated feedback.

### B. Student adaptive-training system

Adapts what a student is asked next, based on their measured mastery.

## Fixed adaptive-training decisions

**This mechanism is settled. Do not redesign it unless explicitly asked in a later task.**

- Topic mastery is tracked using **BKT** (Bayesian Knowledge Tracing).
- Each **subtopic** has a **weakness** value.
- All subtopic weaknesses **begin equally**.
- **Weakness-weighted roulette selection** chooses the subtopic. This gives exploitation of
  weak areas while retaining exploration.
- BKT topic mastery initially determines difficulty:
  - low mastery → easy;
  - medium mastery → medium;
  - high mastery → hard.
- Questions are selected using: **desired subtopic**, **desired difficulty**, **question priority**.
- When a question is used, its **priority becomes lowest**, so other questions are preferred.
- **Question reuse is allowed** once other questions have also been used.
- Student question scores range **0 to 100**.
  - Testable programming questions: `passed_tests / total_tests * 100`.
  - Naturally discrete questions may use `0` or `100`.
- Student scores update **BKT** and the **weaknesses associated with the question**.

Where this lives in code:

- shared value objects and the mastery → difficulty mapping: `app/domain/mastery.py`;
- priority constants: `app/domain/questions.py`;
- the engine boundary (not implemented): `app/adaptive/__init__.py`.

## Fixed curriculum decisions

**Settled. See `docs/DECISIONS.md` ADR-021 for the reasoning.**

- A professor supplies a **fixed Topic → Subtopic taxonomy as structured JSON**.
- Taxonomy validation is strict and total. An invalid document is rejected before any row is
  written.
- A valid taxonomy upload creates an **approved** curriculum version immediately.
- The application does **not** derive or propose curriculum with an LLM. The former Stage A/B
  pipeline is deleted and must not be reintroduced.
- Stable ids are assigned at import and survive later display-name edits.
- Taxonomy uploads do not claim textbook evidence, candidate labels, grouping rationales or model
  metadata that the input did not provide.

The two loops are **separate**: student adaptation reacts to student scores, professor content
optimization reacts to professor reviews. Neither may feed the other beyond the shared question
bank.

## Fixed book-ingestion decisions

**Settled. See `docs/DECISIONS.md` ADR-012 to ADR-016 for the reasoning.**

- **Structure is declared by the input, never extracted by the application.** The app imports
  **structured book JSON** (`.json` only) and validates it. There is **no heading detection, no
  regular expressions over text, no font-size heuristics, no segmentation** anywhere under `app/`.
  Heuristic extraction was removed because it is not deterministic across books: it mis-segments
  the next textbook while still producing output that looks valid.
- **Producing a book document is out of scope for this repository.** There is no PDF/EPUB/HTML
  parser and no converter script; `pypdf` is not a dependency and is not installed. Assume the
  professor supplies a valid document. `tests/test_boundaries.py` enforces all of this: deleted
  modules stay deleted, and no PDF parser may be imported, installed or declared. Do not add one —
  it would be book-specific, and it would drag book-specific maintenance into a book-agnostic
  codebase.
- The **instructional section is the unit** of the source model. A section is a whole semantic
  section and is **never split on a token, character or page budget**. Downstream code may chunk a
  long section to fit a model context window, but that chunking is never persisted.
- **Never fabricate a heading.** No heading in the source means `title` is `null`; the UI labels
  the unit by its printed number, then by page location. `is_unlabelled` — not
  `has_detected_heading` — is what the UI warns about.
- Validation is strict and total: unknown fields are rejected, every section needs non-empty
  `text`, every chapter needs ≥1 section, page ranges must not run backwards, and
  `schema_version` is checked first. An invalid document is rejected **in full, before any row or
  file is written** — hence there is no `FAILED` book status.
- A document that declares caveats imports as `PARTIAL`, never as a clean `IMPORTED`. Warnings
  carry a severity: only `DEFECT` warnings make a book `PARTIAL`; `INFO` warnings state a fact
  without implying a fault.
- Section text is stored **verbatim**, including leading whitespace, because a section may open
  with an indented code listing. Only label fields are trimmed.
- Every section is traceable to book → chapter → section → pages. `SectionSource.citation()` is
  the sanctioned way to cite one.
- The uploaded document is always retained, so an import is reproducible from its exact input.

## Working agreements

These apply to every change in this repository.

### Inspect existing code before modifying architecture

Read the relevant modules, `docs/DECISIONS.md`, and this file **before** introducing a new
framework, database, architectural pattern or major dependency. This project already has a
stack (see below); follow its conventions rather than importing habits from elsewhere. If a
change to the architecture seems necessary, record it in `docs/DECISIONS.md` with the reasoning.

### Preserve working functionality

Do not break, remove or silently rewrite behaviour that currently works. Prefer additive change.
If something must change incompatibly, say so explicitly and update its tests in the same change.

### Run tests after meaningful changes

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

All three must pass. Add tests alongside new behaviour, not afterwards.

### Never claim a feature works unless it was actually verified

Do not report a feature as working based on the code looking correct. Run it. If a claim rests
on a test, name the test; if it rests on a request to a running server, name the URL and the
status code. When something is unverified, unfinished or deferred, say so plainly. Placeholder
implementations must raise `FeatureNotAvailableError` rather than returning empty or invented
data that reads as success.

## Technology stack

| Concern              | Choice                                                        |
| -------------------- | ------------------------------------------------------------- |
| Backend              | FastAPI (ASGI), uvicorn                                       |
| Frontend             | Server-rendered Jinja2 templates + one plain CSS file. No JS build step, no SPA framework. |
| Persistence          | SQLite via SQLAlchemy 2.0 ORM                                 |
| Book input           | Structured book JSON, validated by Pydantic. No parsing anywhere. |
| LLM access           | Instructor + OpenAI SDK → OpenRouter. Structured output only — Pydantic model in, validated instance out. |
| Configuration        | pydantic-settings, environment variables / `.env`             |
| Validation / schemas | Pydantic v2                                                   |
| Dependencies         | `pyproject.toml`, installed into the local `.venv`            |
| Tests                | pytest + `fastapi.testclient`                                 |
| Lint / format        | ruff                                                          |
| Python               | 3.12 in `.venv` (project requires ≥ 3.11)                     |

## Module map

```
app/
  config.py           Typed settings (LLM provider, model, credentials, dev settings)
  logging_config.py   Process-wide logging setup
  errors.py           Error types + FastAPI handlers (JSON for /api, HTML elsewhere)
  main.py             create_app() and the ASGI `app`
  __main__.py         `python -m app` development server
  domain/             Foundational shared entities. Pure; no IO.
  persistence/        Engine, session, ORM tables, repositories. The only DB access.
  ingestion/          Book JSON import                          (IMPLEMENTED)
    schema.py         The book JSON contract, and its validation
    storage.py        Upload validation and retention of the document
    service.py        The workflow: validate, store, persist
    retrieval.py      Reading sections back out, with citations
  curriculum/         Fixed taxonomy JSON import                 (IMPLEMENTED)
    taxonomy_schema.py  The strict taxonomy JSON contract
    taxonomy_ids.py     Stable identity assigned during import
    taxonomy_import.py  The workflow: validate and persist approved versions
    display.py          Safe display decoding for current and legacy rows
  generation/         Section-first base question generation    (IMPLEMENTED)
  validation/         Automatic question validation             (boundary only)
  feedback/           Professor approve/reject/edit records     (recording implemented)
  personalization/    Professor preference learning             (boundary only)
  adaptive/           Student adaptive engine                   (boundary only, by instruction)
  llm/                All outbound LLM traffic                  (STRUCTURED OUTPUT IMPLEMENTED)
  web/                Routers, templates, static assets, middleware
tests/                pytest suite mirroring the modules above
docs/DECISIONS.md     Architectural decision log
docs/book_document_example.json     A valid book document, kept valid by a test
docs/taxonomy_document_example.json A valid taxonomy document, kept valid by a test
```

Dependency direction: `web` → subsystems → `domain` / `persistence` / `config`. `domain` imports
nothing from the application. Subsystems do not import each other except where documented in
their module docstring.

## Coding conventions

- **Line length 100**; ruff's formatter is authoritative. Do not hand-format against it.
- `from __future__ import annotations` at the top of every module.
- Full type annotations on public functions. `StrEnum` for enumerations so values serialise
  readably.
- Every module starts with a docstring stating its responsibility. Boundary packages also state
  their allowed dependencies and what is deferred.
- Comments explain **why**, not what. Do not narrate obvious code.
- **Configuration**: only `app/config.py` reads the environment. Everything else calls
  `get_settings()`.
- **Database**: only `app/persistence/` builds queries or opens sessions. Routes and services use
  repositories.
- **Logging**: `logger = logging.getLogger(__name__)`. Never `print()`. Never configure handlers
  outside `logging_config.py`. Never log an API key or any credential.
- **Errors**: raise an `AdaptiveTrainerError` subclass from `app/errors.py` for expected failures
  so the handlers can render them properly. Do not swallow exceptions.
- **Secrets**: `SecretStr` for credentials; `.env` is git-ignored; `.env.example` documents the
  variables with empty values.
- **Tests** live in `tests/`, are named for the behaviour they check, and run against a temporary
  SQLite database — never the developer's `data/` directory.
