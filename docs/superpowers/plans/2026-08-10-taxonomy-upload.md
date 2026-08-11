# Taxonomy JSON Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the LLM curriculum generator and let professors upload a fixed Topic → Subtopic taxonomy JSON that becomes an APPROVED curriculum version.

**Architecture:** Mirror book ingestion: Pydantic taxonomy document (`extra="forbid"`) → `TaxonomyImportService` validates totally then persists one `CurriculumVersionRow` (`status=APPROVED`) with auto-assigned stable ids. Delete Stage A/B proposal modules and the generate route. Review pages keep working with empty evidence.

**Tech Stack:** FastAPI, Jinja2, Pydantic v2, SQLAlchemy 2.0, SQLite, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-10-taxonomy-upload-design.md`

## Global Constraints

- Taxonomy input is `.json` only; unknown fields rejected; invalid documents write nothing.
- Successful upload → curriculum version `status=APPROVED`, `approved_at=now(UTC)`, `generated_by="taxonomy-upload"`.
- Topic/subtopic item `review_status=ACCEPTED` (existing `CurriculumItemStatus` has no `APPROVED` value).
- Stable ids auto-assigned; never present in the upload file.
- Evidence / grouping_reason / candidate_labels not required.
- `get_approved()` already orders by `approved_at DESC, id DESC` — keep that as “latest wins”.
- LLM package stays for later question generation; curriculum must not call it.
- Do not implement professor in-app taxonomy editing.
- After meaningful changes: `pytest`, `ruff check .`, `ruff format --check .`.

## File structure

| Path | Responsibility |
| ---- | -------------- |
| `app/curriculum/taxonomy_schema.py` | Upload JSON contract + `parse_taxonomy_document` |
| `app/curriculum/taxonomy_ids.py` | Auto `top-` / `sub-` ids from normalised names |
| `app/curriculum/taxonomy_import.py` | Validate upload bytes → persist APPROVED version |
| `app/curriculum/__init__.py` | Export import API; drop proposer |
| `app/curriculum/checks.py` | Keep for shared structural name/id checks used by import (evidence optional path) |
| `app/errors.py` | `InvalidTaxonomyDocumentError` |
| `app/config.py` / `.env.example` | Remove proposal-only knobs |
| `app/web/routes/pages.py` | `POST /curriculum/upload`; delete generate |
| `app/web/templates/curriculum.html` | Upload panel + format blurb |
| `app/web/templates/curriculum_version.html` | Soften LLM “how produced” for uploads |
| `docs/taxonomy_document_example.json` | Valid example kept by a test |
| `docs/DECISIONS.md` / `CLAUDE.md` / `README.md` | Supersede ADR-018; update module map |
| Delete | `extraction.py`, `normalization.py`, `candidates.py`, `schema.py` (LLM), `draft.py` pieces only used by proposal, `service.py` proposer — replace with taxonomy modules; delete proposal-only tests |

Retain `stable_ids.normalize_label` / `fingerprint` (shared). Retain decode helpers needed by templates or move them next to web.

---

### Task 1: Taxonomy schema + example document

**Files:**
- Create: `app/curriculum/taxonomy_schema.py`
- Create: `docs/taxonomy_document_example.json`
- Create: `tests/test_taxonomy_schema.py`
- Modify: `app/errors.py` (add `InvalidTaxonomyDocumentError`)

**Interfaces:**
- Produces: `SCHEMA_VERSION = "1"`, `TaxonomyDocument`, `TaxonomyTopic`, `TaxonomySubtopic`, `parse_taxonomy_document(data: bytes) -> TaxonomyDocument`
- Produces: `InvalidTaxonomyDocumentError` (status 400, message + detail like book errors)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_taxonomy_schema.py
from pathlib import Path

import pytest

from app.curriculum.taxonomy_schema import SCHEMA_VERSION, parse_taxonomy_document
from app.errors import InvalidTaxonomyDocumentError

EXAMPLE = Path("docs/taxonomy_document_example.json")


def test_example_document_is_valid() -> None:
    doc = parse_taxonomy_document(EXAMPLE.read_bytes())
    assert doc.schema_version == SCHEMA_VERSION
    assert doc.topics
    assert all(topic.subtopics for topic in doc.topics)


def test_unknown_field_is_rejected() -> None:
    raw = b'{"schema_version":"1","label":"X","topics":[{"name":"T","subtopics":[{"name":"S"}]}],"extra":1}'
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)


def test_empty_topics_rejected() -> None:
    raw = b'{"schema_version":"1","label":"X","topics":[]}'
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)


def test_duplicate_topic_names_rejected() -> None:
    raw = (
        b'{"schema_version":"1","label":"X","topics":['
        b'{"name":"Loops","subtopics":[{"name":"A"}]},'
        b'{"name":"loops","subtopics":[{"name":"B"}]}]}'
    )
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)


def test_wrong_schema_version_rejected() -> None:
    raw = b'{"schema_version":"99","label":"X","topics":[{"name":"T","subtopics":[{"name":"S"}]}]}'
    with pytest.raises(InvalidTaxonomyDocumentError):
        parse_taxonomy_document(raw)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_taxonomy_schema.py -v`  
Expected: FAIL (import / module missing)

- [ ] **Step 3: Implement error + schema + example**

Add to `app/errors.py` next to `InvalidBookDocumentError`:

```python
class InvalidTaxonomyDocumentError(AdaptiveTrainerError):
    """An uploaded taxonomy JSON document does not satisfy the schema."""

    status_code = 400
```

(Match the exact constructor pattern used by `InvalidBookDocumentError` in this file.)

Create `app/curriculum/taxonomy_schema.py`:

```python
"""The fixed Topic → Subtopic taxonomy document uploaded by the professor."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.curriculum.stable_ids import normalize_label
from app.errors import InvalidTaxonomyDocumentError

SCHEMA_VERSION = "1"


class TaxonomySubtopic(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)


class TaxonomyTopic(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    subtopics: list[TaxonomySubtopic] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_subtopic_names(self) -> TaxonomyTopic:
        seen: set[str] = set()
        for sub in self.subtopics:
            key = normalize_label(sub.name)
            if key in seen:
                raise ValueError(f"duplicate subtopic name {sub.name!r}")
            seen.add(key)
        return self


class TaxonomyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1"]
    label: str = Field(min_length=1, max_length=200)
    topics: list[TaxonomyTopic] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_topic_names(self) -> TaxonomyDocument:
        seen: set[str] = set()
        for topic in self.topics:
            key = normalize_label(topic.name)
            if key in seen:
                raise ValueError(f"duplicate topic name {topic.name!r}")
            seen.add(key)
        return self


def parse_taxonomy_document(data: bytes) -> TaxonomyDocument:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTaxonomyDocumentError(
            "The taxonomy file is not valid UTF-8 JSON.",
            detail=str(exc),
        ) from exc
    if not isinstance(payload, dict):
        raise InvalidTaxonomyDocumentError(
            "The taxonomy file must be a JSON object.",
            detail=f"Got {type(payload).__name__}.",
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise InvalidTaxonomyDocumentError(
            "Unsupported taxonomy schema_version.",
            detail=f"Expected {SCHEMA_VERSION!r}, got {payload.get('schema_version')!r}.",
        )
    try:
        return TaxonomyDocument.model_validate(payload)
    except ValidationError as exc:
        raise InvalidTaxonomyDocumentError(
            "The taxonomy document did not satisfy the schema.",
            detail="; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:8]
            ),
        ) from exc
```

Create `docs/taxonomy_document_example.json` with at least two topics (e.g. Loops + Variables) and multiple subtopics, matching the schema.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_taxonomy_schema.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/errors.py app/curriculum/taxonomy_schema.py docs/taxonomy_document_example.json tests/test_taxonomy_schema.py
git commit -m "$(cat <<'EOF'
Add taxonomy JSON schema and example document.

EOF
)"
```

---

### Task 2: Auto stable ids for taxonomy names

**Files:**
- Create: `app/curriculum/taxonomy_ids.py`
- Create: `tests/test_taxonomy_ids.py`
- Modify: reuse `app/curriculum/stable_ids.py` (`normalize_label`, `fingerprint`, prefixes)

**Interfaces:**
- Consumes: `normalize_label`, `fingerprint`, `TOPIC_PREFIX`, `SUBTOPIC_PREFIX`
- Produces: `topic_id_from_name(name: str) -> str`, `subtopic_id_from_names(topic_name: str, subtopic_name: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
from app.curriculum.taxonomy_ids import subtopic_id_from_names, topic_id_from_name


def test_topic_id_is_stable_across_spelling_noise() -> None:
    assert topic_id_from_name("Loops") == topic_id_from_name("  loops ")
    assert topic_id_from_name("Loops").startswith("top-")


def test_subtopic_id_includes_topic_path() -> None:
    a = subtopic_id_from_names("Loops", "While loops")
    b = subtopic_id_from_names("Control flow", "While loops")
    assert a != b
    assert a.startswith("sub-")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_taxonomy_ids.py -v`  
Expected: FAIL (module missing)

- [ ] **Step 3: Implement**

```python
"""Stable ids for uploaded taxonomies — derived from names at import time."""

from __future__ import annotations

from app.curriculum.stable_ids import (
    SUBTOPIC_PREFIX,
    TOPIC_PREFIX,
    fingerprint,
    normalize_label,
)


def topic_id_from_name(name: str) -> str:
    return f"{TOPIC_PREFIX}-{fingerprint([normalize_label(name)])}"


def subtopic_id_from_names(topic_name: str, subtopic_name: str) -> str:
    return f"{SUBTOPIC_PREFIX}-{fingerprint([normalize_label(topic_name), normalize_label(subtopic_name)])}"
```

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/curriculum/taxonomy_ids.py tests/test_taxonomy_ids.py
git commit -m "$(cat <<'EOF'
Add auto stable ids for uploaded taxonomy names.

EOF
)"
```

---

### Task 3: Taxonomy import service

**Files:**
- Create: `app/curriculum/taxonomy_import.py`
- Create: `tests/test_taxonomy_import.py`
- Modify: `app/curriculum/__init__.py` (export importer; remove proposer temporarily or in Task 5)
- Modify: `app/curriculum/checks.py` only if import reuses it — prefer inline uniqueness already in schema; import may skip `require_sound_draft` and write rows directly

**Interfaces:**
- Consumes: `parse_taxonomy_document`, `topic_id_from_name`, `subtopic_id_from_names`, `CurriculumRepository`
- Produces: `TaxonomyImportService.import_upload(*, filename: str, data: bytes) -> CurriculumVersionRow`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_taxonomy_import.py — use session/settings fixtures from conftest like book tests
from app.curriculum.taxonomy_import import TaxonomyImportService
from app.domain.enums import CurriculumItemStatus, CurriculumStatus
from app.errors import InvalidTaxonomyDocumentError, UnsupportedFileError
from app.persistence.repositories import CurriculumRepository

VALID = (
    b'{"schema_version":"1","label":"Demo","topics":['
    b'{"name":"Loops","description":"Iteration.","subtopics":['
    b'{"name":"While loops","description":"Condition-controlled."},'
    b'{"name":"For loops"}]}]}'
)


def test_import_writes_approved_version(session, settings) -> None:
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=VALID
    )
    session.commit()
    assert version.status is CurriculumStatus.APPROVED
    assert version.approved_at is not None
    assert version.generated_by == "taxonomy-upload"
    assert version.label == "Demo"
    assert len(version.topics) == 1
    topic = version.topics[0]
    assert topic.review_status is CurriculumItemStatus.ACCEPTED
    assert topic.stable_id and topic.stable_id.startswith("top-")
    assert {s.name for s in topic.subtopics} == {"While loops", "For loops"}
    assert all(s.review_status is CurriculumItemStatus.ACCEPTED for s in topic.subtopics)
    assert all(s.stable_id.startswith("sub-") for s in topic.subtopics)
    assert CurriculumRepository(session).get_approved().id == version.id


def test_identical_document_reimport_keeps_same_stable_ids(session, settings) -> None:
    first = TaxonomyImportService(session, settings).import_upload(
        filename="a.json", data=VALID
    )
    session.commit()
    second = TaxonomyImportService(session, settings).import_upload(
        filename="b.json", data=VALID
    )
    session.commit()
    assert first.id != second.id
    assert first.topics[0].stable_id == second.topics[0].stable_id
    assert {s.stable_id for s in first.topics[0].subtopics} == {
        s.stable_id for s in second.topics[0].subtopics
    }
    assert CurriculumRepository(session).get_approved().id == second.id


def test_non_json_extension_rejected(session, settings) -> None:
    with pytest.raises(UnsupportedFileError):
        TaxonomyImportService(session, settings).import_upload(
            filename="taxonomy.txt", data=VALID
        )
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement `TaxonomyImportService`**

```python
"""Import a professor-uploaded fixed taxonomy as an APPROVED curriculum version."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.curriculum.taxonomy_ids import subtopic_id_from_names, topic_id_from_name
from app.curriculum.taxonomy_schema import TaxonomyDocument, parse_taxonomy_document
from app.domain.enums import CurriculumItemStatus, CurriculumStatus
from app.errors import UnsupportedFileError
from app.persistence.models import CurriculumVersionRow, SubtopicRow, TopicRow
from app.persistence.repositories import CurriculumRepository

logger = logging.getLogger(__name__)

GENERATED_BY = "taxonomy-upload"


class TaxonomyImportService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._curriculum = CurriculumRepository(session)

    def import_upload(self, *, filename: str, data: bytes) -> CurriculumVersionRow:
        if not filename.lower().endswith(".json"):
            raise UnsupportedFileError(
                "Only .json taxonomy documents are accepted.",
                detail=f"Got {filename!r}.",
            )
        # Reuse book size limit — taxonomies are tiny; keeps one knob.
        max_bytes = self._settings.max_book_upload_mb * 1024 * 1024
        if len(data) > max_bytes:
            from app.errors import FileTooLargeError

            raise FileTooLargeError(
                "The taxonomy file is too large.",
                detail=f"{len(data)} bytes exceeds the configured limit.",
            )

        document = parse_taxonomy_document(data)
        version = self._persist(document)
        logger.info(
            "Imported taxonomy version %s (%d topic(s))",
            version.id,
            len(version.topics),
        )
        return version

    def _persist(self, document: TaxonomyDocument) -> CurriculumVersionRow:
        now = datetime.now(UTC)
        version = self._curriculum.add(
            CurriculumVersionRow(
                label=document.label,
                status=CurriculumStatus.APPROVED,
                approved_at=now,
                generated_by=GENERATED_BY,
                source_book_ids_json=None,
                extraction_metadata_json=None,
                warnings_json=None,
            )
        )
        for position, topic in enumerate(document.topics):
            topic_row = TopicRow(
                name=topic.name,
                description=topic.description or None,
                position=position,
                stable_id=topic_id_from_name(topic.name),
                review_status=CurriculumItemStatus.ACCEPTED,
            )
            for sub_position, subtopic in enumerate(topic.subtopics):
                topic_row.subtopics.append(
                    SubtopicRow(
                        name=subtopic.name,
                        description=subtopic.description or None,
                        position=sub_position,
                        stable_id=subtopic_id_from_names(topic.name, subtopic.name),
                        review_status=CurriculumItemStatus.ACCEPTED,
                        candidate_labels_json=None,
                        grouping_reason=None,
                        confidence=None,
                    )
                )
            version.topics.append(topic_row)
        self._session.flush()
        return version
```

Wire exports in `app/curriculum/__init__.py` for the importer (proposer removal is Task 5 if imports still break — update `__init__` here to export `TaxonomyImportService`, `parse_taxonomy_document`, `SCHEMA_VERSION`, and keep decode helpers used by pages until Task 5 moves them).

- [ ] **Step 4: Run `tests/test_taxonomy_import.py` — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/curriculum/taxonomy_import.py app/curriculum/__init__.py tests/test_taxonomy_import.py
git commit -m "$(cat <<'EOF'
Import uploaded taxonomy JSON as an approved curriculum version.

EOF
)"
```

---

### Task 4: Web upload UI (replace generate)

**Files:**
- Modify: `app/web/routes/pages.py`
- Modify: `app/web/templates/curriculum.html`
- Modify: `app/web/templates/curriculum_version.html`
- Modify: `tests/test_web_curriculum.py` (rewrite generate tests → upload tests)

**Interfaces:**
- Consumes: `TaxonomyImportService.import_upload`
- Produces: `POST /curriculum/upload` → 303 `/curriculum/versions/{id}`

- [ ] **Step 1: Rewrite failing web tests**

Replace generate-button / `POST /curriculum/generate` tests with:

```python
def test_curriculum_page_offers_taxonomy_upload(client) -> None:
    response = client.get("/curriculum")
    assert response.status_code == 200
    assert b"Upload taxonomy" in response.content
    assert b"/curriculum/upload" in response.content
    assert b"/curriculum/generate" not in response.content


def test_taxonomy_upload_creates_approved_version(client, session) -> None:
    data = (
        b'{"schema_version":"1","label":"Uploaded","topics":['
        b'{"name":"Loops","subtopics":[{"name":"While loops"}]}]}'
    )
    response = client.post(
        "/curriculum/upload",
        files={"file": ("taxonomy.json", data, "application/json")},
    )
    assert response.status_code == 303
    assert "/curriculum/versions/" in response.headers["location"]
    # follow or query DB: status approved
```

Also test invalid JSON returns 400 page with error message (no redirect).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Update route + templates**

In `pages.py`:
- Remove `generate_curriculum` and LLM imports used only for it.
- Change `curriculum()` to not require `LLMClient` for the page (or ignore it).
- Add:

```python
@router.post("/curriculum/upload", name="upload_taxonomy")
def upload_taxonomy(
    request: Request,
    session: DbSession,
    file: Annotated[UploadFile, File()],
) -> Response:
    data = file.file.read()
    filename = file.filename or "taxonomy.json"
    try:
        version = TaxonomyImportService(session).import_upload(filename=filename, data=data)
    except (UnsupportedFileError, FileTooLargeError, InvalidTaxonomyDocumentError) as exc:
        session.rollback()
        return _curriculum_page(
            request, session, error=exc.message, error_detail=exc.detail, status_code=exc.status_code
        )
    session.commit()
    return RedirectResponse(
        url=f"/curriculum/versions/{version.id}", status_code=status.HTTP_303_SEE_OTHER
    )
```

Pass `schema_version` and a short format hint into the curriculum template context.

In `curriculum.html`: replace the Generate panel with an upload form (`enctype="multipart/form-data"`, `action` = upload route) and a compact format note listing required keys + link to `/` docs path text for `docs/taxonomy_document_example.json`.

In `curriculum_version.html`: if `version.generated_by == "taxonomy-upload"`, show “Uploaded fixed taxonomy” instead of Stage A/B metadata.

- [ ] **Step 4: Run `tests/test_web_curriculum.py` — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/web/routes/pages.py app/web/templates/curriculum.html app/web/templates/curriculum_version.html tests/test_web_curriculum.py
git commit -m "$(cat <<'EOF'
Replace curriculum generate UI with taxonomy JSON upload.

EOF
)"
```

---

### Task 5: Delete LLM curriculum proposal path

**Files:**
- Delete: `app/curriculum/extraction.py`, `normalization.py`, `candidates.py`, `schema.py` (LLM Stage A/B), `service.py` (proposer), and proposal-only helpers in `draft.py` if unused
- Delete or rewrite: `tests/test_curriculum_service.py`, `test_curriculum_normalization.py`, `test_curriculum_schema.py`, `curriculum_fixtures.py`
- Keep: `checks.py` only if still imported; otherwise delete and rely on taxonomy schema validators
- Modify: `app/curriculum/__init__.py`, `tests/test_boundaries.py`, `app/config.py`, `.env.example`
- Move `decode_json_list` / `decode_metadata` / `decode_proposal_warnings` to a small `app/curriculum/display.py` (or into `taxonomy_import.py` / pages helpers) so version pages still work with null metadata

**Interfaces:**
- Produces: package exports only taxonomy import + display decoders + schema version
- Removes: `get_curriculum_proposer`, `CurriculumProposalService`

- [ ] **Step 1: Identify remaining imports**

Run: `.\.venv\Scripts\rg -n "CurriculumProposalService|get_curriculum_proposer|section-analysis|CrossBookNormalizer|SectionConceptExtractor|curriculum_max_sections" app tests`  
Expected: list of call sites to clear

- [ ] **Step 2: Delete modules + fix imports + drop config fields**

Remove from `Settings`:
- `curriculum_max_sections`
- `curriculum_section_char_budget`

Remove matching `.env.example` lines.

Update `tests/test_boundaries.py` expectation: curriculum proposal is **not** implemented; taxonomy upload **is**.

Update `tests/test_config.py` if it asserted those settings.

- [ ] **Step 3: Run full suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add -A app/curriculum app/config.py .env.example tests docs
git commit -m "$(cat <<'EOF'
Remove LLM curriculum proposal in favour of taxonomy upload.

EOF
)"
```

---

### Task 6: Docs + ADR

**Files:**
- Modify: `docs/DECISIONS.md` (supersede ADR-018)
- Modify: `CLAUDE.md` (fixed curriculum decisions + module map)
- Modify: `README.md` (curriculum upload, format pointer, remove generate wording)

- [ ] **Step 1: Write ADR-021 (or supersede ADR-018 in place)**

Content locked by spec:
- Curriculum structure is declared by uploaded taxonomy JSON.
- Not LLM-derived; Stage A/B removed.
- Upload → APPROVED; latest approved wins.
- Auto stable ids from names at import.
- Evidence not required for uploaded taxonomies.

- [ ] **Step 2: Update CLAUDE.md module map**

Replace curriculum Stage A/B/C bullets with taxonomy schema + import. Professor step 3 becomes “upload a fixed Topic → Subtopic taxonomy JSON”.

- [ ] **Step 3: Update README**

Document upload on `/curriculum`, show example JSON snippet, link `docs/taxonomy_document_example.json`.

- [ ] **Step 4: Commit**

```bash
git add docs/DECISIONS.md CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
Document taxonomy upload and supersede LLM curriculum ADR.

EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| ---------------- | ---- |
| Remove LLM generator | 5 |
| Upload taxonomy JSON | 3, 4 |
| Validate totally / forbid extras | 1 |
| APPROVED on success | 3 |
| Auto stable ids | 2, 3 |
| Evidence not required | 3 |
| Format in UI + example doc | 1, 4, 6 |
| Latest approved wins | already in repo; covered by Task 3 reimport test |
| Update CLAUDE/README/ADR | 6 |
| Item review_status accepted | 3 (`ACCEPTED`) |

## Plan self-review notes

- No TBD placeholders left; item status explicitly `ACCEPTED` to match `CurriculumItemStatus`.
- `CurriculumProposalError` may remain in `errors.py` unused — Task 5 should remove it if nothing references it.
- Taxonomy files reuse `max_book_upload_mb` rather than adding a new setting (YAGNI).
