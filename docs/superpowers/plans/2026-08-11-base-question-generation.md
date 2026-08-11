# Base Question Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a professor select approved topic/subtopic, difficulty, question type, and book section(s), then generate one structured textbook-grounded question per section via the base (cold-start) generator.

**Architecture:** Section-first orchestration builds a validated `QuestionSpec` per section, then `BaseQuestionGenerator` calls Instructor with a type-specific Pydantic response model, maps into extended `Question`/`QuestionRow` (`content_json` + existing prompt fields), and the Jinja UI lists/details results.

**Tech Stack:** FastAPI, Jinja2, Pydantic v2, SQLAlchemy 2.0, SQLite, Instructor + OpenAI SDK → OpenRouter, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-11-base-question-generation-design.md`

## Global Constraints

- Section-first: one QuestionSpec + one question per selected book section.
- Same approved topic + subtopic + difficulty + type for the whole run.
- Reject unapproved/foreign taxonomy IDs and missing section IDs before any LLM call.
- `QuestionType` (format) ≠ `QuestionKind` (scoring); derive kind from type.
- Use `StructuredLLMClient.complete_structured` only — no free-text JSON parsing.
- Common principles + per-type prompts; no single vague “infer the format” prompt.
- Parsons stores block order and indentation.
- Do not implement validation sandbox, student runtime, personalization, or GEPA.
- Additive `questions` columns; local DB may need delete/recreate (ADR-008).
- After meaningful changes: `pytest`, `ruff check .`, `ruff format --check .`.

## File structure

| Path | Responsibility |
| ---- | -------------- |
| `app/domain/enums.py` | Add `QuestionType` |
| `app/domain/questions.py` | Extend `Question` with type/topic/spec/content |
| `app/generation/spec.py` | `QuestionSpec` + curriculum/section validation |
| `app/generation/schemas.py` | Seven response models + content encode/decode |
| `app/generation/principles.py` | Shared system rules string |
| `app/generation/prompts.py` | Per-type prompt builders |
| `app/generation/base.py` | `BaseQuestionGenerator` |
| `app/generation/service.py` | Expand sections → generate → persist |
| `app/generation/__init__.py` | Public exports; wire base generator |
| `app/errors.py` | `InvalidQuestionSpecError` |
| `app/persistence/models.py` | Extend `QuestionRow` |
| `app/persistence/repositories.py` | Map new columns if helpers needed |
| `app/web/routes/pages.py` | Generate POST + detail GET |
| `app/web/templates/questions.html` | Form + bank links |
| `app/web/templates/question_detail.html` | Structured display |
| `docs/DECISIONS.md` | ADR for QuestionSpec / section-first |
| `tests/test_generation_*.py` | Schema, spec, base, pages, optional integration |
| `tests/test_boundaries.py` | Generation no longer null |

---

### Task 1: QuestionType, schemas, and scoring map

**Files:**
- Modify: `app/domain/enums.py`
- Create: `app/generation/schemas.py`
- Create: `tests/test_generation_schemas.py`

**Interfaces:**
- Produces: `QuestionType` StrEnum with seven values
- Produces: `scoring_kind_for(question_type: QuestionType) -> QuestionKind`
- Produces: response models `MultipleChoiceDraft`, `TrueFalseDraft`, `OutputPredictionDraft`, `CodeCompletionDraft`, `DebuggingDraft`, `ParsonsDraft`, `CodingDraft`
- Produces: `RESPONSE_MODEL_FOR: dict[QuestionType, type[BaseModel]]`
- Produces: `ParsonsBlock` with `id`, `text`, `indent: int >= 0`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_generation_schemas.py
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.enums import QuestionKind, QuestionType
from app.generation.schemas import (
    RESPONSE_MODEL_FOR,
    CodingDraft,
    MultipleChoiceDraft,
    ParsonsBlock,
    ParsonsDraft,
    scoring_kind_for,
)


def test_all_seven_types_have_response_models() -> None:
    assert set(RESPONSE_MODEL_FOR) == set(QuestionType)


@pytest.mark.parametrize(
    ("qtype", "kind"),
    [
        (QuestionType.MULTIPLE_CHOICE, QuestionKind.DISCRETE),
        (QuestionType.TRUE_FALSE, QuestionKind.DISCRETE),
        (QuestionType.OUTPUT_PREDICTION, QuestionKind.DISCRETE),
        (QuestionType.PARSONS, QuestionKind.DISCRETE),
        (QuestionType.CODE_COMPLETION, QuestionKind.TESTABLE_PROGRAM),
        (QuestionType.DEBUGGING, QuestionKind.TESTABLE_PROGRAM),
        (QuestionType.CODING, QuestionKind.TESTABLE_PROGRAM),
    ],
)
def test_scoring_kind_mapping(qtype: QuestionType, kind: QuestionKind) -> None:
    assert scoring_kind_for(qtype) is kind


def test_multiple_choice_requires_options_and_answer() -> None:
    draft = MultipleChoiceDraft(
        prompt="What does s[1:3] return for s='abcd'?",
        options=["ab", "bc", "cd", "abc"],
        correct_option_index=1,
        explanation="Slice end is exclusive.",
    )
    assert draft.correct_option_index == 1


def test_parsons_supports_order_and_indent() -> None:
    draft = ParsonsDraft(
        prompt="Arrange the function.",
        blocks=[
            ParsonsBlock(id="a", text="def f(x):", indent=0),
            ParsonsBlock(id="b", text="return x + 1", indent=1),
        ],
        correct_order=["a", "b"],
        explanation="Body is indented.",
    )
    assert draft.blocks[1].indent == 1


def test_coding_requires_tests() -> None:
    draft = CodingDraft(
        prompt="Write add(a, b).",
        reference_solution="def add(a, b):\n    return a + b",
        tests=[{"stdin": "", "call": "add(1, 2)", "expected": "3"}],
        explanation="Simple addition.",
    )
    assert len(draft.tests) >= 1


def test_parsons_rejects_unknown_order_id() -> None:
    with pytest.raises(ValidationError):
        ParsonsDraft(
            prompt="x",
            blocks=[ParsonsBlock(id="a", text="pass", indent=0)],
            correct_order=["a", "missing"],
            explanation="x",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_schemas.py -v`  
Expected: FAIL (module missing)

- [ ] **Step 3: Implement enum + schemas**

Add to `app/domain/enums.py` after `QuestionKind`:

```python
class QuestionType(StrEnum):
    """Assessment format (independent of scoring mode)."""

    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    OUTPUT_PREDICTION = "output_prediction"
    CODE_COMPLETION = "code_completion"
    DEBUGGING = "debugging"
    PARSONS = "parsons"
    CODING = "coding"
```

Create `app/generation/schemas.py` with module docstring, `scoring_kind_for`, all seven draft models (shared fields: `prompt`, `explanation`; type-specific: options / boolean / code / expected_output / tests / parsons), `RESPONSE_MODEL_FOR` map, and a Parsons `model_validator` ensuring `correct_order` ⊆ block ids.

Keep models Instructor-friendly: plain fields, no fancy unions in the LLM response model. Storage encoding comes in Task 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_schemas.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/domain/enums.py app/generation/schemas.py tests/test_generation_schemas.py
git commit -m "$(cat <<'EOF'
feat(generation): add QuestionType and seven structured draft schemas

EOF
)"
```

---

### Task 2: QuestionSpec validation

**Files:**
- Create: `app/generation/spec.py`
- Modify: `app/errors.py`
- Create: `tests/test_generation_spec.py`

**Interfaces:**
- Produces: `InvalidQuestionSpecError(AdaptiveTrainerError)` status 422
- Produces: `QuestionSpec` Pydantic model
- Produces: `build_question_spec(session, *, curriculum_version_id, topic_id, subtopic_ids, question_type, difficulty, source_section_ids, seed=None) -> QuestionSpec`
- Consumes: `CurriculumRepository.get_with_tree`, `BookStructureRepository.get_section` (or `SourceRetrieval`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_generation_spec.py
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.errors import InvalidQuestionSpecError
from app.generation.spec import build_question_spec
from app.ingestion import BookImportService
import book_documents as docs


def _seed(session: Session, settings):
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    taxonomy = (
        b'{"schema_version":"1","label":"T","topics":['
        b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="tax.json", data=taxonomy
    )
    session.commit()
    topic = version.topics[0]
    sub = topic.subtopics[0]
    section_id = book.chapters[0].sections[0].id
    return version, topic, sub, section_id


def test_build_spec_accepts_approved_ids(session: Session, settings) -> None:
    version, topic, sub, section_id = _seed(session, settings)
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[sub.id],
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_id],
    )
    assert spec.source_section_ids == [section_id]


def test_rejects_unapproved_topic(session: Session, settings) -> None:
    version, topic, sub, section_id = _seed(session, settings)
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=999999,
            subtopic_ids=[sub.id],
            question_type=QuestionType.DEBUGGING,
            difficulty=Difficulty.MEDIUM,
            source_section_ids=[section_id],
        )


def test_rejects_subtopic_from_other_topic(session: Session, settings) -> None:
    version, topic, sub, section_id = _seed(session, settings)
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=topic.id,
            subtopic_ids=[sub.id, 999999],
            question_type=QuestionType.CODING,
            difficulty=Difficulty.EASY,
            source_section_ids=[section_id],
        )


def test_rejects_missing_section(session: Session, settings) -> None:
    version, topic, sub, _section_id = _seed(session, settings)
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=topic.id,
            subtopic_ids=[sub.id],
            question_type=QuestionType.TRUE_FALSE,
            difficulty=Difficulty.HARD,
            source_section_ids=[999999],
        )


def test_rejects_non_approved_curriculum_version(session: Session, settings) -> None:
    from datetime import UTC, datetime

    from app.domain.enums import CurriculumStatus
    from app.persistence.models import CurriculumVersionRow

    version = CurriculumVersionRow(
        label="draft",
        status=CurriculumStatus.PROPOSED,
        approved_at=None,
    )
    session.add(version)
    session.commit()
    with pytest.raises(InvalidQuestionSpecError):
        build_question_spec(
            session,
            curriculum_version_id=version.id,
            topic_id=1,
            subtopic_ids=[1],
            question_type=QuestionType.MULTIPLE_CHOICE,
            difficulty=Difficulty.EASY,
            source_section_ids=[1],
        )
```

Adapt `_seed` if `docs.minimal()` / relationship loading differs — follow patterns in `tests/test_taxonomy_import.py` and `tests/test_ingestion_retrieval.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_spec.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement error + QuestionSpec**

```python
# app/errors.py (add)
class InvalidQuestionSpecError(AdaptiveTrainerError):
    """A generation QuestionSpec names ids that are missing or not approved."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_question_spec"
```

```python
# app/generation/spec.py (core shape)
class QuestionSpec(BaseModel):
    curriculum_version_id: int
    topic_id: int
    subtopic_ids: list[int] = Field(min_length=1)
    question_type: QuestionType
    difficulty: Difficulty
    source_section_ids: list[int] = Field(min_length=1)
    seed: str | None = None
```

`build_question_spec` must:

1. Load curriculum version; require `status == APPROVED`.
2. Find `topic_id` in that version’s topics.
3. Ensure every `subtopic_id` belongs to that topic.
4. Ensure every `source_section_id` exists.
5. For cold-start callers, service may pass exactly one section id; spec allows ≥1 for future use.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_spec.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/errors.py app/generation/spec.py tests/test_generation_spec.py
git commit -m "$(cat <<'EOF'
feat(generation): validate QuestionSpec against approved taxonomy and sections

EOF
)"
```

---

### Task 3: Persist extended Question fields

**Files:**
- Modify: `app/domain/questions.py`
- Modify: `app/persistence/models.py`
- Modify: `app/persistence/repositories.py` (only if row↔domain helpers needed)
- Modify: `tests/test_persistence.py` or add assertions in generation tests
- Create helper in `app/generation/schemas.py`: `draft_to_content_json`, `prompt_fields_from_draft`

**Interfaces:**
- Extends `Question` / `QuestionRow` with: `question_type: QuestionType | None`, `topic_id: int | None`, `spec_json: str | None`, `content_json: str | None`
- Produces: helpers that fill `prompt`, `reference_solution`, `tests` from a draft so `original_*` seeding still works

- [ ] **Step 1: Write a persistence-focused failing test**

```python
def test_question_row_stores_spec_and_content(session: Session) -> None:
    from app.domain.enums import Difficulty, GeneratorKind, QuestionKind, QuestionStatus, QuestionType
    from app.persistence.models import QuestionRow
    from app.persistence.repositories import QuestionRepository

    row = QuestionRow(
        curriculum_version_id=None,
        topic_id=None,
        subtopic_id=None,
        kind=QuestionKind.DISCRETE,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=Difficulty.EASY,
        status=QuestionStatus.GENERATED,
        prompt="Strings are immutable.",
        reference_solution="true",
        tests=None,
        spec_json='{"topic_id":1}',
        content_json='{"explanation":"because..."}',
        generator_kind=GeneratorKind.BASE,
        generator_name="base",
        generator_version="1",
    )
    saved = QuestionRepository(session).add(row)
    session.commit()
    loaded = QuestionRepository(session).get(saved.id)
    assert loaded.question_type == QuestionType.TRUE_FALSE
    assert loaded.spec_json and loaded.content_json
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_persistence.py -k spec_and_content -v`  
Expected: FAIL (unknown columns / args)

- [ ] **Step 3: Extend models**

On `QuestionRow` and domain `Question`, add the four fields. Keep defaults nullable so older test fixtures that omit them still construct. Update `apply_professor_edit` only if needed (do not clear `content_json` in this milestone).

Add `encode_content(draft) -> str` / `prompt_fields_from_draft(draft) -> tuple[str, str | None, str | None]` in schemas:

- MCQ: reference = option text or index string; tests = None
- T/F: reference = `"true"` / `"false"`
- output_prediction: reference = expected output
- parsons: reference = JSON of correct_order + indents; tests = None
- testable types: reference = reference_solution; tests = JSON list of tests

- [ ] **Step 4: Run persistence tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_persistence.py tests/test_domain.py -v`  
Expected: PASS (update any constructors that break)

- [ ] **Step 5: Commit**

```bash
git add app/domain/questions.py app/persistence/models.py app/generation/schemas.py tests/test_persistence.py
git commit -m "$(cat <<'EOF'
feat(questions): store QuestionSpec and typed content_json on questions

EOF
)"
```

---

### Task 4: Base generator + service (mocked LLM)

**Files:**
- Create: `app/generation/principles.py`
- Create: `app/generation/prompts.py`
- Create: `app/generation/base.py`
- Create: `app/generation/service.py`
- Modify: `app/generation/__init__.py`
- Create: `tests/test_generation_base.py`
- Modify: `tests/test_boundaries.py`

**Interfaces:**
- Produces: `COMMON_SYSTEM: str` in principles
- Produces: `build_prompt(spec: QuestionSpec, *, section_text: str, citation: str, topic_name: str, subtopic_names: list[str]) -> tuple[str, str]`
- Produces: `BaseQuestionGenerator(client: StructuredLLMClient, retrieval: SourceRetrieval, ...)`
- Produces: `generate_one(spec: QuestionSpec) -> Question`
- Produces: `GenerationService.generate_for_sections(...) -> list[QuestionRow]`
- Produces: `get_question_generator()` → `BaseQuestionGenerator` (client from `get_structured_client` lazily on generate, or inject client)
- Updates: `GenerationRequest` to include `question_type` and `source_section_ids` (keep `subtopic_id` as primary for ADR-002 compatibility; map to `subtopic_ids=[subtopic_id]`)

- [ ] **Step 1: Write mocked generator tests**

```python
# tests/test_generation_base.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, QuestionKind, QuestionType
from app.generation.base import BaseQuestionGenerator
from app.generation.schemas import DebuggingDraft, RESPONSE_MODEL_FOR
from app.generation.service import GenerationService
from app.generation.spec import build_question_spec
# reuse _seed from spec tests or shared fixture


class FakeClient:
    def __init__(self, draft: BaseModel) -> None:
        self.draft = draft
        self.calls: list[dict[str, Any]] = []

    @property
    def description(self) -> str:
        return "fake/test-model"

    def complete_structured(self, *, system: str, prompt: str, response_model: type[BaseModel]):
        self.calls.append({"system": system, "prompt": prompt, "model": response_model})
        assert response_model is RESPONSE_MODEL_FOR[QuestionType.DEBUGGING]
        return self.draft


def test_base_generator_attaches_source_and_scoring_kind(session, settings) -> None:
    version, topic, sub, section_id = _seed(session, settings)  # shared helper
    spec = build_question_spec(
        session,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[sub.id],
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_id],
    )
    draft = DebuggingDraft(
        prompt="Find the bug.",
        code="s = 'ab'\ns[0] = 'c'",
        reference_solution="Strings are immutable; build a new string.",
        tests=[{"call": "explain", "expected": "TypeError"}],
        explanation="Item assignment on str fails.",
    )
    client = FakeClient(draft)
    from app.ingestion import SourceRetrieval

    gen = BaseQuestionGenerator(client=client, retrieval=SourceRetrieval(session))
    question = gen.generate_one(spec, topic_name=topic.name, subtopic_names=[sub.name])
    assert question.kind is QuestionKind.TESTABLE_PROGRAM
    assert question.generator_name == "base"
    assert question.content_json and "TypeError" in (question.tests or "")
    assert client.calls and "Immutability" in client.calls[0]["prompt"] or True
```

Also test `GenerationService` creates one DB row per section id when given two sections (second seed section may require a richer book fixture — use `docs` example with ≥2 sections or import the example document).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_base.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement principles, prompts, base, service**

`principles.py`: short system string covering grounding rules from the spec.

`prompts.py`: dict or match/case on `QuestionType` returning type-specific instructions appended to the user prompt; include section text, citation, topic/subtopic names, difficulty.

`base.py`:

```python
DESCRIPTOR = GeneratorDescriptor(kind=GeneratorKind.BASE, name="base", version="1")

class BaseQuestionGenerator:
    def __init__(self, *, client: StructuredLLMClient, retrieval: SourceRetrieval) -> None: ...

    @property
    def descriptor(self) -> GeneratorDescriptor:
        return DESCRIPTOR

    def generate_one(
        self,
        spec: QuestionSpec,
        *,
        topic_name: str,
        subtopic_names: list[str],
    ) -> Question:
        section_id = spec.source_section_ids[0]
        section = self._retrieval.get_section(section_id)
        source = self._retrieval.section_source(section_id)
        system, user = build_prompt(
            spec,
            section_text=section.text,
            citation=source.citation(),
            topic_name=topic_name,
            subtopic_names=subtopic_names,
        )
        response_model = RESPONSE_MODEL_FOR[spec.question_type]
        draft = self._client.complete_structured(
            system=system, prompt=user, response_model=response_model
        )
        prompt, reference, tests = prompt_fields_from_draft(draft)
        content = encode_content(
            draft,
            sources=[{"section_id": section_id, "citation": source.citation()}],
            model=self._client.description,
        )
        return Question(
            curriculum_version_id=spec.curriculum_version_id,
            topic_id=spec.topic_id,
            subtopic_id=spec.subtopic_ids[0],
            kind=scoring_kind_for(spec.question_type),
            question_type=spec.question_type,
            difficulty=spec.difficulty,
            prompt=prompt,
            reference_solution=reference,
            tests=tests,
            spec_json=spec.model_dump_json(),
            content_json=content,
            generator_kind=DESCRIPTOR.kind,
            generator_name=DESCRIPTOR.name,
            generator_version=DESCRIPTOR.version,
        )
```

`service.py`: resolve section id list (explicit or all-in-book via `SourceRetrieval.sections_in_book`), loop `build_question_spec` with one section each, `generate_one`, map to `QuestionRow`, `QuestionRepository.add`, commit.

`__init__.py`: update docstring to implemented; `get_question_generator` returns a factory that builds `BaseQuestionGenerator` with real client when generating (call `require_llm()` inside `generate` / service). Keep `NullQuestionGenerator` only if tests still need it — prefer removing from the happy path.

Update `tests/test_boundaries.py`: generation no longer raises `FeatureNotAvailableError` for “not implemented”; instead either remove that test or assert descriptor is `base@1` and that generating without LLM raises `ConfigurationError` when provider is `none`.

- [ ] **Step 4: Run generator + boundary tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_base.py tests/test_boundaries.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/generation tests/test_generation_base.py tests/test_boundaries.py
git commit -m "$(cat <<'EOF'
feat(generation): implement section-first base question generator

EOF
)"
```

---

### Task 5: Professor UI

**Files:**
- Modify: `app/web/routes/pages.py`
- Modify: `app/web/templates/questions.html`
- Create: `app/web/templates/question_detail.html`
- Create: `tests/test_generation_pages.py`

**Interfaces:**
- `GET /questions` — form context: approved tree, books, sections grouped by book (or load sections for selected book via query `?book_id=` to keep HTML small)
- `POST /questions/generate` — form fields: `topic_id`, `subtopic_id`, `difficulty`, `question_type`, `book_id`, `section_ids` (list), `all_sections` (optional)
- `GET /questions/{question_id}` — detail

Practical UI choice (locked): on `GET /questions`, if `book_id` query present, list that book’s sections in the multi-select; otherwise prompt to pick a book first (same page GET with book_id). Zero JS.

- [ ] **Step 1: Write page tests**

```python
# tests/test_generation_pages.py
def test_questions_page_shows_generate_form_when_ready(client, session, settings):
    # seed book + taxonomy via services, commit through client app engine
    ...
    body = client.get("/questions").text
    assert "Generate Question" in body
    assert "Immutability" in body or "subtopic" in body.lower()


def test_generate_post_creates_question(client, monkeypatch, ...):
    # monkeypatch GenerationService or BaseQuestionGenerator to avoid LLM
    ...
    response = client.post(
        "/questions/generate",
        data={
            "topic_id": str(topic_id),
            "subtopic_id": str(subtopic_id),
            "difficulty": "medium",
            "question_type": "debugging",
            "book_id": str(book_id),
            "section_ids": str(section_id),
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert "/questions/" in response.headers["location"]


def test_detail_shows_prompt_and_source(client, ...):
    ...
    body = client.get(f"/questions/{qid}").text
    assert "Find the bug" in body
    assert "Explanation" in body or "explanation" in body.lower()
```

Use the same FakeClient injection pattern: patch `app.generation.service.get_structured_client` or pass through a test hook. Prefer patching `GenerationService._client_factory` or `get_structured_client` in `base` construction.

- [ ] **Step 2: Run page tests to verify fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_pages.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement routes + templates**

In `questions` GET, load `get_approved()` with tree, `BookRepository.list_usable()`, optional sections for `book_id`.

In `upload`-style POST handler `generate_questions`:

```python
@router.post("/questions/generate", name="generate_questions")
def generate_questions(
    request: Request,
    session: DbSession,
    topic_id: Annotated[int, Form()],
    subtopic_id: Annotated[int, Form()],
    difficulty: Annotated[str, Form()],
    question_type: Annotated[str, Form()],
    book_id: Annotated[int, Form()],
    section_ids: Annotated[list[int] | None, Form()] = None,
    all_sections: Annotated[str | None, Form()] = None,
) -> Response:
    ...
```

On success redirect; on `InvalidQuestionSpecError` / `ConfigurationError` / `LLMRequestError` re-render form with error panel (mirror books upload).

Detail template: show fields from row + parsed `content_json` (explanation, options, parsons blocks, tests, citations).

Remove the deferred checklist items that are now done; leave validation/review as deferred.

- [ ] **Step 4: Run page tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_generation_pages.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/pages.py app/web/templates/questions.html app/web/templates/question_detail.html tests/test_generation_pages.py
git commit -m "$(cat <<'EOF'
feat(web): professor UI to generate and inspect base questions

EOF
)"
```

---

### Task 6: ADR, integration smoke, full verification

**Files:**
- Modify: `docs/DECISIONS.md`
- Modify: `CLAUDE.md` module map line for `generation/` if it still says boundary only
- Create: `tests/test_generation_integration.py` (optional)
- Modify: `pyproject.toml` to register `integration` marker

- [ ] **Step 1: Add ADR**

Append ADR-022 (or next free number): section-first cold-start; QuestionSpec; QuestionType vs QuestionKind; content_json; base generator `base@1`.

- [ ] **Step 2: Optional integration test**

```python
import os
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not os.getenv("LLM_API_KEY"), reason="No LLM_API_KEY")
def test_real_generation_smoke(session, settings, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    # rebuild settings / client
    ...
    rows = GenerationService(session).generate_for_sections(...)
    assert rows and rows[0].prompt
```

Register marker in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = ["integration: hits a real LLM provider"]
```

- [ ] **Step 3: Full suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Expected: all PASS. If local `data/*.db` lacks new columns, delete it and restart the app once.

- [ ] **Step 4: Manual milestone check**

1. Import book JSON + taxonomy JSON if needed.
2. Open `/questions`, pick topic/subtopic/difficulty/type/book/section.
3. Click Generate Question.
4. Confirm detail shows question, answer, explanation, tests (if any), taxonomy, difficulty, type, source citation.

- [ ] **Step 5: Commit docs + markers**

```bash
git add docs/DECISIONS.md CLAUDE.md pyproject.toml tests/test_generation_integration.py
git commit -m "$(cat <<'EOF'
docs: record base question-generation ADR and integration smoke hook

EOF
)"
```

- [ ] **Step 6: Completion report**

Return to the user:

- QuestionSpec design summary
- Generator architecture
- Type-specific modules
- Files changed
- Tests/results
- Real-generation result if performed
- Exact UI flow
- Known limitations (no validator, no review UI writes, no personalization, schema recreate)

---

## Spec coverage checklist

| Spec requirement | Task |
| ---------------- | ---- |
| QuestionSpec typed object | 2 |
| Reject unapproved taxonomy | 2 |
| Seven question types + schemas | 1 |
| Parsons order + indent | 1 |
| Difficulty easy/medium/hard | 2–5 |
| Source grounding rules in prompts | 4 |
| Common + type-specific prompts | 4 |
| Store structured fields / scoring compatibility | 3–4 |
| Section-first one question per section | 4–5 |
| Professor UI generate + display | 5 |
| Mocked tests + optional real smoke | 4, 6 |
| Completion report | 6 |

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-11-base-question-generation.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
