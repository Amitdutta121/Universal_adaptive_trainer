# Retrieval-First Personalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt generation to professor feedback via retrieval of reviewed examples plus conservatively inferred preferences, while leaving `base@1` unchanged and adding a separately identifiable `personalized-context@1` generator.

**Architecture:** Thin `app/personalization` package. Review history stays append-only evidence. Embeddings + metadata rank a small example set per `QuestionSpec`. Manual “Refresh preferences” runs structured LLM extraction into `preference_statements`. `GenerationService` chooses Base vs Personalized by an explicit UI flag. Same validators and pedagogical judge run after either path.

**Tech Stack:** Pydantic v2, SQLAlchemy 2.0, Instructor + OpenAI SDK (chat + embeddings via OpenRouter), FastAPI Form + Jinja2, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-11-retrieval-first-personalization-design.md`

## Global Constraints

- No GEPA / fine-tuning / LangChain / external vector DB.
- Do **not** change `BaseQuestionGenerator` behavior or `DESCRIPTOR` (`base@1`).
- Professor feedback only (ADR-006); never student scores.
- `app/personalization` must not import `app.adaptive` (ADR-001); update boundary tests to scan the package.
- Soft activation only — no hard “10 reviews” gate.
- Preferences never override global correctness; Base system rules stay first in the prompt.
- Book/taxonomy remain structured JSON; do not touch ingestion.
- No auth → treat all reviews as one professor pool (`professor_id` may stay `None`).
- Existing local DBs missing new columns fail `verify_schema` and must be deleted/recreated (ADR-008).
- Python 3.12, `from __future__ import annotations`, ruff line length 100.
- Tests use temp SQLite; fake LLM + fake embedder; never developer `data/`.
- Commands: `.\.venv\Scripts\python.exe -m pytest <target> -v` then full pytest + ruff before commit.
- Do not edit `.cursor/plans/` files.

## File structure

| Path | Responsibility |
| ---- | -------------- |
| `app/domain/enums.py` | `PreferenceCategory`, `PreferenceConfirmationState` |
| `app/domain/preferences.py` | Preference statement domain model + encode helpers |
| `app/domain/questions.py` | Optional `personalization_context_json` on `Question` |
| `app/config.py` | `embedding_model` setting |
| `app/persistence/models.py` | `PreferenceStatementRow`, `ReviewEmbeddingRow`, question JSON column |
| `app/persistence/repositories.py` | Preference + embedding + review listing helpers |
| `app/personalization/__init__.py` | Public exports; real learner wiring |
| `app/personalization/embeddings.py` | Embedder protocol, OpenRouter client, cosine, content hash |
| `app/personalization/retrieval.py` | Metadata + semantic ranking; example budgets |
| `app/personalization/learner.py` | Structured extraction + conservative merge |
| `app/personalization/context.py` | Build prompt blocks + transparency payload |
| `app/personalization/generator.py` | `PersonalizedContextGenerator` (`personalized-context@1`) |
| `app/personalization/service.py` | Refresh, confirm, correct, remove, list |
| `app/generation/service.py` | `generator` flag: base vs personalized |
| `app/generation/__init__.py` | `get_question_generator` may return personalized descriptor path |
| `app/web/navigation.py` | Preferences nav entry |
| `app/web/routes/pages.py` | Preferences routes; generate form flag; detail evidence |
| `app/web/templates/preferences.html` | Learned prefs UI |
| `app/web/templates/questions.html` | Base / Personalized choice |
| `app/web/templates/question_detail.html` | Personalization evidence panel |
| `docs/DECISIONS.md` | ADR for retrieval-first personalization |
| `tests/test_personalization_*.py` | Unit + page tests |

## Interfaces (locked)

```python
# Generator identity
# base@1 unchanged
DESCRIPTOR = GeneratorDescriptor(
    kind=GeneratorKind.PERSONALIZED,
    name="personalized-context",
    version="1",
)

# Ranking
META_WEIGHT = 0.6
SEM_WEIGHT = 0.4
MAX_APPROVED_EDITED = 4
MIN_APPROVED_EDITED = 0  # shrink with pool
MAX_REJECTED = 2
SOFT_PREF_FLOOR = 0.35
MAX_PREFS_IN_PROMPT = 5
MIN_SUPPORTING_REVIEWS = 2
PROFILE_VERSION = "1"

# app/personalization/embeddings.py
class Embedder(Protocol):
    @property
    def model_id(self) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...

def cosine_similarity(a: list[float], b: list[float]) -> float: ...
def example_content_hash(text: str) -> str: ...

# app/personalization/retrieval.py
@dataclass(frozen=True)
class RetrievedExample:
    review_id: int
    decision: ReviewDecision
    prompt: str
    reasons: list[RejectionReason]
    comment: str | None
    score: float
    question_id: int

@dataclass(frozen=True)
class RetrievalResult:
    approved_or_edited: list[RetrievedExample]
    rejected: list[RetrievedExample]

def retrieve_examples(
    session: Session,
    *,
    spec: QuestionSpec,
    topic_id: int,
    topic_name: str,
    subtopic_names: list[str],
    citation: str,
    embedder: Embedder | None = None,
) -> RetrievalResult: ...

# app/personalization/learner.py
class PreferenceCandidate(BaseModel):
    rule_text: str
    category: PreferenceCategory
    supporting_review_ids: list[int]

class PreferenceExtractionResult(BaseModel):
    preferences: list[PreferenceCandidate]

def extract_preference_candidates(
    client: StructuredLLMClient,
    reviews_payload: str,
) -> PreferenceExtractionResult: ...

def merge_candidates(
    existing: list[PreferenceStatementRow],
    candidates: list[PreferenceCandidate],
) -> list[PreferenceStatementRow]:  # returns rows to add/update (mutates existing)

def confidence_from_evidence(evidence_count: int, *, confirmed: bool = False) -> float: ...

# app/personalization/service.py
def refresh_preferences(session: Session, *, client: StructuredLLMClient | None = None) -> int: ...
def list_active_preferences(session: Session) -> list[PreferenceStatementRow]: ...
def confirm_preference(session: Session, preference_id: int) -> PreferenceStatementRow: ...
def correct_preference(session: Session, preference_id: int, rule_text: str) -> PreferenceStatementRow: ...
def remove_preference(session: Session, preference_id: int) -> PreferenceStatementRow: ...

# app/personalization/context.py
def build_personalization_prompt_blocks(
    *,
    preferences: list[PreferenceStatementRow],
    retrieval: RetrievalResult,
) -> str: ...

def transparency_payload(
    *,
    preference_ids: list[int],
    review_ids: list[int],
) -> str: ...  # JSON string

# app/generation/service.py
def generate_for_sections(
    ...,
    generator: Literal["base", "personalized"] = "base",
) -> list[QuestionRow]: ...
```

---

### Task 1: Domain enums and preference model

**Files:**
- Create: `app/domain/preferences.py`
- Modify: `app/domain/enums.py`
- Modify: `app/domain/__init__.py` (export new types)
- Modify: `app/domain/questions.py` (add optional `personalization_context_json`)
- Test: `tests/test_preference_domain.py`

**Interfaces:**
- Consumes: existing `StrEnum` pattern
- Produces: `PreferenceCategory`, `PreferenceConfirmationState`, `PreferenceStatement`, encode helpers

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preference_domain.py
from app.domain.enums import PreferenceCategory, PreferenceConfirmationState
from app.domain.preferences import PreferenceStatement, confidence_from_evidence


def test_confidence_requires_repeated_evidence() -> None:
    assert confidence_from_evidence(1) < 0.35
    assert confidence_from_evidence(2) >= 0.35
    assert confidence_from_evidence(10) > confidence_from_evidence(2)


def test_preference_statement_defaults() -> None:
    stmt = PreferenceStatement(
        rule_text="Prefer concise prompts.",
        category=PreferenceCategory.WORDING,
        evidence_count=2,
        confidence=0.4,
        supporting_review_ids=[1, 2],
    )
    assert stmt.active is True
    assert stmt.confirmation_state is PreferenceConfirmationState.INFERRED
    assert stmt.profile_version == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_preference_domain.py -v`  
Expected: FAIL (imports missing)

- [ ] **Step 3: Write minimal implementation**

Add to `app/domain/enums.py`:

```python
class PreferenceCategory(StrEnum):
    WORDING = "wording"
    SCENARIO_STYLE = "scenario_style"
    EMPHASIS = "emphasis"
    DISLIKE = "dislike"
    EXAMPLE_PATTERN = "example_pattern"
    OTHER = "other"


class PreferenceConfirmationState(StrEnum):
    INFERRED = "inferred"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"
```

Create `app/domain/preferences.py`:

```python
"""Professor preference statements inferred from review history."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import PreferenceCategory, PreferenceConfirmationState

PROFILE_VERSION = "1"


def _now() -> datetime:
    return datetime.now(UTC)


def confidence_from_evidence(evidence_count: int, *, confirmed: bool = False) -> float:
    """Map repeated evidence to [0, 1]. One review stays below the soft floor."""
    if evidence_count <= 0:
        return 0.0
    # 1 → ~0.2; 2 → ~0.4; 5 → ~0.7; 10 → ~0.85
    raw = 1.0 - (1.0 / (1.0 + 0.5 * evidence_count))
    if confirmed:
        raw = min(1.0, raw + 0.1)
    return round(min(1.0, raw), 4)


def encode_review_ids(ids: list[int]) -> str:
    return json.dumps(ids)


def decode_review_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(x) for x in json.loads(raw)]


class PreferenceStatement(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    rule_text: str = Field(min_length=1)
    category: PreferenceCategory
    evidence_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_review_ids: list[int] = Field(default_factory=list)
    active: bool = True
    confirmation_state: PreferenceConfirmationState = PreferenceConfirmationState.INFERRED
    profile_version: str = PROFILE_VERSION
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime | None = None
```

Add to `Question` in `app/domain/questions.py`:

```python
personalization_context_json: str | None = None
```

Export new symbols from `app/domain/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_preference_domain.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/domain/enums.py app/domain/preferences.py app/domain/questions.py app/domain/__init__.py tests/test_preference_domain.py
git commit -m "feat(domain): add preference statement model and confidence helper"
```

---

### Task 2: Persistence tables and repositories

**Files:**
- Modify: `app/persistence/models.py`
- Modify: `app/persistence/repositories.py`
- Modify: `app/generation/service.py` (`_row_from_question` copy new field — can wait until Task 7 if preferred; do it here to keep ORM complete)
- Test: `tests/test_personalization_persistence.py`

**Interfaces:**
- Consumes: Task 1 enums/helpers
- Produces: `PreferenceStatementRow`, `ReviewEmbeddingRow`, repos

- [ ] **Step 1: Write the failing test**

```python
# tests/test_personalization_persistence.py
from sqlalchemy.orm import Session

from app.domain.enums import PreferenceCategory, PreferenceConfirmationState
from app.domain.preferences import encode_review_ids
from app.persistence.models import PreferenceStatementRow, ReviewEmbeddingRow
from app.persistence.repositories import PreferenceRepository, ReviewEmbeddingRepository


def test_preference_round_trip(session: Session) -> None:
    repo = PreferenceRepository(session)
    row = repo.add(
        PreferenceStatementRow(
            rule_text="Prefer application over recall.",
            category=PreferenceCategory.EMPHASIS,
            evidence_count=2,
            confidence=0.4,
            supporting_review_ids_json=encode_review_ids([1, 2]),
            active=True,
            confirmation_state=PreferenceConfirmationState.INFERRED,
            profile_version="1",
        )
    )
    session.commit()
    assert PreferenceRepository(session).get(row.id).rule_text.startswith("Prefer")


def test_embedding_upsert(session: Session) -> None:
    review = _seed_reviewed_question(session)  # helper: question + approve review
    repo = ReviewEmbeddingRepository(session)
    row = repo.upsert(
        ReviewEmbeddingRow(
            review_id=review.id,
            model_id="fake/embeddings",
            vector_json="[0.1, 0.2]",
            content_hash="abc",
        )
    )
    session.commit()
    assert ReviewEmbeddingRepository(session).get_for_review(review.id).id == row.id
```

Implement `_seed_reviewed_question` using the same patterns as `tests/test_feedback_service.py` (create question row + `submit_review`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_personalization_persistence.py -v`  
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

In `models.py`:

```python
class PreferenceStatementRow(TimestampMixin, Base):
    __tablename__ = "preference_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_text: Mapped[str] = mapped_column(Text)
    category: Mapped[PreferenceCategory] = mapped_column(String(32))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_review_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    active: Mapped[bool] = mapped_column(default=True)
    confirmation_state: Mapped[PreferenceConfirmationState] = mapped_column(
        String(16), default=PreferenceConfirmationState.INFERRED
    )
    profile_version: Mapped[str] = mapped_column(String(50), default="1")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ReviewEmbeddingRow(TimestampMixin, Base):
    __tablename__ = "review_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("professor_reviews.id", ondelete="CASCADE"), unique=True
    )
    model_id: Mapped[str] = mapped_column(String(200))
    vector_json: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
```

Add to `QuestionRow`:

```python
personalization_context_json: Mapped[str | None] = mapped_column(Text, default=None)
```

Repositories:

```python
class PreferenceRepository:
    def add(...) -> PreferenceStatementRow: ...
    def get(self, preference_id: int) -> PreferenceStatementRow: ...
    def list_all(self, *, active_only: bool = False) -> list[PreferenceStatementRow]: ...
    def list_for_generation(self, *, soft_floor: float) -> list[PreferenceStatementRow]: ...

class ReviewEmbeddingRepository:
    def get_for_review(self, review_id: int) -> ReviewEmbeddingRow | None: ...
    def upsert(self, row: ReviewEmbeddingRow) -> ReviewEmbeddingRow: ...
```

Extend `ProfessorReviewRepository` with `list_with_questions(limit: int = 50)` joining questions for retrieval/learner (or add query in retrieval module using session).

Update `_row_from_question` to copy `personalization_context_json`.

- [ ] **Step 4: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_personalization_persistence.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/persistence/models.py app/persistence/repositories.py app/generation/service.py tests/test_personalization_persistence.py
git commit -m "feat(persistence): add preference statements and review embeddings"
```

---

### Task 3: Embeddings client and cosine helper

**Files:**
- Create: `app/personalization/embeddings.py`
- Modify: `app/config.py` (`embedding_model: str = "openai/text-embedding-3-small"`)
- Modify: `.env.example` (document `EMBEDDING_MODEL=`)
- Test: `tests/test_personalization_embeddings.py`

**Interfaces:**
- Consumes: `get_settings`, OpenAI SDK pattern from `app/llm/client.py`
- Produces: `Embedder`, `FakeEmbedder` (test), `OpenRouterEmbedder`, `cosine_similarity`, `example_content_hash`

- [ ] **Step 1: Write the failing test**

```python
from app.personalization.embeddings import FakeEmbedder, cosine_similarity, example_content_hash


def test_cosine_identical_vectors() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_fake_embedder_is_deterministic() -> None:
    emb = FakeEmbedder(dim=8)
    a = emb.embed(["hello"])[0]
    b = emb.embed(["hello"])[0]
    assert a == b
    assert emb.embed(["hello"])[0] != emb.embed(["world"])[0]


def test_content_hash_stable() -> None:
    assert example_content_hash("x") == example_content_hash("x")
```

- [ ] **Step 2: Run test — expect FAIL**

- [ ] **Step 3: Implement**

```python
"""Embedding helpers for review-example retrieval."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import openai

from app.config import Settings, get_settings
from app.errors import ConfigurationError, LLMRequestError
from app.llm.availability import require_llm
from app.llm.client import OPENROUTER_BASE_URL


class Embedder(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def example_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FakeEmbedder:
    def __init__(self, dim: int = 8) -> None:
        self._dim = dim

    @property
    def model_id(self) -> str:
        return "fake/embeddings"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(self._dim)]
            out.append(vec)
        return out


class OpenRouterEmbedder:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = require_llm(settings or get_settings())
        key = self._settings.llm_api_key
        if key is None:
            raise ConfigurationError("LLM API key is required for embeddings.")
        self._client = openai.OpenAI(
            api_key=key.get_secret_value(),
            base_url=self._settings.llm_base_url or OPENROUTER_BASE_URL,
            timeout=self._settings.llm_timeout_seconds,
        )
        self._model = self._settings.embedding_model

    @property
    def model_id(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
        except openai.OpenAIError as exc:
            raise LLMRequestError("Embedding request failed.", detail=str(exc)[:400]) from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


def get_embedder(settings: Settings | None = None) -> Embedder:
    return OpenRouterEmbedder(settings)
```

Add `embedding_model: str = "openai/text-embedding-3-small"` to `Settings`.

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add app/personalization/embeddings.py app/config.py .env.example tests/test_personalization_embeddings.py
git commit -m "feat(personalization): add embeddings client and cosine helper"
```

---

### Task 4: Example retrieval (metadata + semantic)

**Files:**
- Create: `app/personalization/retrieval.py`
- Test: `tests/test_personalization_retrieval.py`

**Interfaces:**
- Consumes: Embedder, review+question rows, `QuestionSpec`
- Produces: `retrieve_examples`, `RetrievalResult`

- [ ] **Step 1: Write failing tests**

Cover:

1. Prefer same subtopic over other subtopic
2. Prefer edit over approve over reject in metadata
3. Combined score uses fake embeddings
4. Empty history → empty lists
5. Partial history shrinks budgets (1 approve → at most 1 positive example)
6. Never exceed 4 positive / 2 rejected

```python
def test_retrieval_prefers_same_subtopic(session, seeded_reviews, fake_embedder):
    result = retrieve_examples(session, spec=..., topic_id=..., ..., embedder=fake_embedder)
    assert result.approved_or_edited[0].review_id == same_subtopic_review_id

def test_retrieval_empty_history(session, empty_db, fake_embedder):
    result = retrieve_examples(...)
    assert result.approved_or_edited == []
    assert result.rejected == []
```

Seed helper: create several questions with different `subtopic_id` / `question_type` / `difficulty` and reviews (approve/edit/reject).

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement ranking**

```python
# Weights (fixed)
SUBTOPIC = 5.0
TOPIC = 2.0
TYPE = 2.0
DIFFICULTY_EXACT = 1.0
DIFFICULTY_ADJACENT = 0.5
DECISION_EDIT = 3.0
DECISION_APPROVE = 2.0
DECISION_REJECT = 1.0
RECENCY_MAX = 1.0  # scale by rank among candidates
META_WEIGHT = 0.6
SEM_WEIGHT = 0.4
MIN_SCORE_FLOOR = 0.05  # drop near-zero weak pads
```

Algorithm:

1. Load recent reviews joined to questions (e.g. last 200).
2. Build example text = prompt (edited_prompt if edit else question.prompt) + reasons + comment.
3. Ensure embeddings via `ReviewEmbeddingRepository` + embedder (skip semantic if embedder is None → sem=0).
4. Compute meta raw scores; normalize by max meta in pool (or 1).
5. `final = META_WEIGHT * meta_norm + SEM_WEIGHT * cosine`.
6. Split pools: decisions in `{APPROVE, EDIT}` vs `REJECT`.
7. Sort each by final desc; take up to budgets; apply floor.

For query text:

```python
f"{topic_name}\n{', '.join(subtopic_names)}\n{spec.question_type.value}\n{spec.difficulty.value}\n{citation}"
```

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/personalization/retrieval.py tests/test_personalization_retrieval.py
git commit -m "feat(personalization): retrieve relevant professor-reviewed examples"
```

---

### Task 5: Preference learner (structured LLM + conservative merge)

**Files:**
- Create: `app/personalization/learner.py`
- Test: `tests/test_personalization_learner.py`

**Interfaces:**
- Consumes: `StructuredLLMClient`, reviews payload, existing preference rows
- Produces: extract + merge; rejects single-evidence candidates

- [ ] **Step 1: Write failing tests**

```python
def test_merge_drops_single_supporting_review():
    candidates = [PreferenceCandidate(
        rule_text="Prefer easy questions",
        category=PreferenceCategory.DISLIKE,
        supporting_review_ids=[1],  # only one
    )]
    merged = merge_candidates([], candidates)
    assert merged == []

def test_merge_accepts_two_supporting_reviews():
    candidates = [PreferenceCandidate(
        rule_text="Prefer concise prompts.",
        category=PreferenceCategory.WORDING,
        supporting_review_ids=[1, 2],
    )]
    rows = merge_candidates([], candidates)
    assert len(rows) == 1
    assert rows[0].evidence_count == 2
    assert rows[0].confidence >= 0.35

def test_extract_uses_structured_client():
    client = FakePreferenceClient(...)  # returns PreferenceExtractionResult
    result = extract_preference_candidates(client, reviews_payload="...")
    assert result.preferences
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

```python
SYSTEM = (
    "Infer stable pedagogical preference rules from professor reviews. "
    "Only propose rules supported by repeated evidence across multiple reviews. "
    "Never propose difficulty preference from a single too_easy/too_difficult reject. "
    "Do not invent correctness rules; those are global. "
    "Return structured preferences only."
)

def merge_candidates(existing, candidates):
    # For each candidate with len(ids) >= MIN_SUPPORTING_REVIEWS:
    #   if similar rule_text (normalize case/strip) exists: union ids, bump evidence/confidence
    #   else create new PreferenceStatementRow with confirmation_state=INFERRED
    # Skip candidates below threshold
```

Similarity for merge: exact normalized `rule_text` match in v1 (keep simple). Professor corrections use explicit edit UI, not fuzzy merge.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/personalization/learner.py tests/test_personalization_learner.py
git commit -m "feat(personalization): add conservative structured preference learner"
```

---

### Task 6: Preference service (refresh / confirm / correct / remove)

**Files:**
- Create: `app/personalization/service.py`
- Modify: `app/personalization/__init__.py` (wire real API; replace null `build_profile`)
- Modify: `tests/test_boundaries.py` (preference learner no longer raises; package scan)
- Test: `tests/test_personalization_service.py`

**Interfaces:**
- Consumes: learner, PreferenceRepository, review listing
- Produces: service functions listed in Interfaces

- [ ] **Step 1: Write failing tests**

```python
def test_refresh_persists_merged_preferences(session, reviews, fake_client):
    n = refresh_preferences(session, client=fake_client)
    assert n >= 1
    assert PreferenceRepository(session).list_all()

def test_confirm_correct_remove(session, preference_row):
    confirm_preference(session, preference_row.id)
    correct_preference(session, preference_row.id, "Prefer short realistic programs.")
    remove_preference(session, preference_row.id)
    row = PreferenceRepository(session).get(preference_row.id)
    assert row.active is False
    assert row.confirmation_state is PreferenceConfirmationState.CORRECTED
```

Update `test_preference_learning_fails_loudly` → `test_preference_learning_builds_profile`:

```python
def test_preference_learning_builds_profile(session):
    profile = get_preference_learner().build_profile(1)
    assert profile.profile_version == "1"
    assert profile.review_count >= 0
```

Expand `test_the_two_loops_do_not_import_each_other` to scan all `*.py` under both packages.

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement service + package exports**

```python
def refresh_preferences(session, *, client=None) -> int:
    # Load up to 50 recent reviews (+ prioritize edits)
    # Serialize compact payload (decision, reasons, comment, prompt snippet, changed_fields)
    # extract_preference_candidates
    # merge into existing rows; commit
    # return number of active preferences

def build_profile(professor_id: int) -> ProfessorPreferenceProfile:
    # review_count from ProfessorReviewRepository.count()
    # profile_version = PROFILE_VERSION
```

Replace `NullPreferenceLearner` with `ReviewPreferenceLearner` that uses a session factory **or** keep `build_profile` session-free by counting via injected session in service only, and make `get_preference_learner().build_profile` use `session_scope()`. Prefer:

```python
class ReviewPreferenceLearner:
    def build_profile(self, professor_id: int) -> ProfessorPreferenceProfile:
        with session_scope() as session:
            count = ProfessorReviewRepository(session).count()
        return ProfessorPreferenceProfile(
            professor_id=professor_id,
            review_count=count,
            profile_version=PROFILE_VERSION,
        )
```

Keep thin `ProfessorPreferenceProfile` in `__init__.py` as today; extend later if UI needs statement list (UI uses repository directly).

- [ ] **Step 4: Run personalization + boundary tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/personalization/service.py app/personalization/__init__.py tests/test_personalization_service.py tests/test_boundaries.py
git commit -m "feat(personalization): wire refresh and preference professor actions"
```

---

### Task 7: Personalized context builder + generator

**Files:**
- Create: `app/personalization/context.py`
- Create: `app/personalization/generator.py`
- Test: `tests/test_personalization_generator.py`
- Test: `tests/test_generation_base.py` (assert Base descriptor still `base@1` — already true; add regression assert if missing)

**Interfaces:**
- Consumes: retrieval, preferences, `build_prompt` from generation
- Produces: `PersonalizedContextGenerator`

- [ ] **Step 1: Write failing tests**

```python
def test_personalized_descriptor():
    gen = PersonalizedContextGenerator(session=session, client=fake, embedder=fake_emb)
    assert gen.descriptor.label() == "personalized:personalized-context@1"

def test_prompt_includes_examples_and_style_disclaimer(session, ...):
    gen.generate_one(spec, topic_name=..., subtopic_names=...)
    system, user = fake.calls[0]["system"], fake.calls[0]["prompt"]
    assert "style and pedagogy only" in system.lower() or "style and pedagogy only" in user.lower()
    assert "Professor preferences" in user or "Approved" in user

def test_no_feedback_still_personalized_descriptor(session, empty):
    q = gen.generate_one(...)
    assert q.generator_name == "personalized-context"
    assert q.personalization_context_json is not None
    payload = json.loads(q.personalization_context_json)
    assert payload["retrieved_review_ids"] == []

def test_base_generator_unchanged():
    from app.generation.base import DESCRIPTOR
    assert DESCRIPTOR.name == "base" and DESCRIPTOR.version == "1"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

`context.py`: format preference bullets + example blocks (approved/edited vs rejected). Soft-filter prefs: `active and confidence >= SOFT_PREF_FLOOR`, sort by confidence, cap `MAX_PREFS_IN_PROMPT`.

`generator.py`: mirror `BaseQuestionGenerator.generate_one` flow:

1. Load section + citation
2. `build_prompt(...)` for Base blocks
3. `retrieve_examples(...)`
4. Load soft-activated preferences
5. Append `build_personalization_prompt_blocks(...)`
6. Prepend/append system reminder that prefs cannot override correctness
7. `complete_structured` same response models
8. Stamp personalized descriptor + `personalization_context_json`

Do **not** modify `app/generation/base.py`.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/personalization/context.py app/personalization/generator.py tests/test_personalization_generator.py
git commit -m "feat(personalization): add personalized-context@1 generator"
```

---

### Task 8: Wire GenerationService and generator selection

**Files:**
- Modify: `app/generation/service.py`
- Modify: `app/generation/__init__.py` (`get_question_generator`)
- Test: `tests/test_generation_service_personalization.py` (or extend `test_generation_base.py`)

**Interfaces:**
- Consumes: `PersonalizedContextGenerator`
- Produces: `generator: Literal["base","personalized"]` on `generate_for_sections`

- [ ] **Step 1: Write failing test**

```python
def test_generation_service_selects_personalized(session, fake_client, fake_embedder, monkeypatch):
    # patch get_embedder / inject via GenerationService(..., embedder=)
    rows = GenerationService(session, client=fake_client, embedder=fake_embedder).generate_for_sections(
        ...,
        generator="personalized",
    )
    assert rows[0].generator_name == "personalized-context"
    assert rows[0].personalization_context_json

def test_generation_service_default_is_base(...):
    rows = GenerationService(...).generate_for_sections(..., generator="base")
    assert rows[0].generator_name == "base"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

```python
class GenerationService:
    def __init__(self, session, *, client=None, embedder=None):
        self._base = BaseQuestionGenerator(...)
        self._personalized = PersonalizedContextGenerator(
            session=session, client=client, retrieval=..., embedder=embedder
        )

    def generate_for_sections(..., generator: Literal["base", "personalized"] = "base"):
        active = self._personalized if generator == "personalized" else self._base
        ...
        question = active.generate_one(...)
```

Update `get_question_generator(professor_id=None)`:
- still return Base when `professor_id is None` for descriptor checks
- if `professor_id is not None`, return unconfigured `PersonalizedContextGenerator()` for descriptor — **or** ignore professor_id and keep Base-only for this helper; selection is explicit via service flag (preferred for v1). Document that UI flag drives selection, not `professor_id`.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/generation/service.py app/generation/__init__.py tests/test_generation_service_personalization.py
git commit -m "feat(generation): select base or personalized-context explicitly"
```

---

### Task 9: Preferences UI + generate form + evidence panel

**Files:**
- Modify: `app/web/navigation.py`
- Modify: `app/web/routes/pages.py`
- Create: `app/web/templates/preferences.html`
- Modify: `app/web/templates/questions.html`
- Modify: `app/web/templates/question_detail.html`
- Modify: `tests/test_navigation.py` (if exists)
- Test: `tests/test_personalization_pages.py`

**Interfaces:**
- Routes:
  - `GET /preferences`
  - `POST /preferences/refresh`
  - `POST /preferences/{id}/confirm`
  - `POST /preferences/{id}/correct` (form: `rule_text`)
  - `POST /preferences/{id}/remove`
  - `POST /questions/generate` gains `generator: str = "base"`

- [ ] **Step 1: Write failing page tests**

```python
def test_preferences_page_ok(client):
    assert client.get("/preferences").status_code == 200

def test_refresh_preferences_post(client, session_with_reviews, monkeypatch):
    # monkeypatch extract to fake
    r = client.post("/preferences/refresh", follow_redirects=False)
    assert r.status_code in (302, 303)

def test_generate_form_accepts_personalized(client, ...):
    r = client.post("/questions/generate", data={..., "generator": "personalized"}, ...)
    # with fakes injected via dependency or by setting LLM_PROVIDER and patching service

def test_question_detail_shows_personalization_evidence(client, personalized_question):
    html = client.get(f"/questions/{id}").text
    assert "Personalization evidence" in html
```

Use the same FakeClient patterns as generation page tests; patch `GenerationService` or LLM + embedder at the boundary used by routes.

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement templates/routes**

Nav:

```python
NavSection(
    key="preferences",
    label="Preferences",
    path="/preferences",
    summary="Learned professor preferences from review history (manual refresh).",
)
```

Questions form: radio Base / Personalized.

Preferences table columns: Rule, Category, Evidence, Confidence, State, Actions.

Question detail: if `generator_name == "personalized-context"`, parse `personalization_context_json` and list preference ids + review links.

- [ ] **Step 4: Run page + navigation tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add app/web/navigation.py app/web/routes/pages.py app/web/templates/preferences.html app/web/templates/questions.html app/web/templates/question_detail.html tests/test_personalization_pages.py
git commit -m "feat(web): preferences UI and personalized generation choice"
```

---

### Task 10: ADR + package docstring + final verification

**Files:**
- Modify: `docs/DECISIONS.md` (new ADR)
- Modify: `app/personalization/__init__.py` docstring (status: implemented retrieval-first)
- Modify: `app/generation/__init__.py` docstring (personalized available)
- Test: full suite

- [ ] **Step 1: Add ADR** summarizing retrieval-first personalization, dual stores (history + statements), generator IDs, soft activation, no GEPA.

- [ ] **Step 2: Run full verification**

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Expected: all pass.

- [ ] **Step 3: Manual UI checklist (document in completion report)**

1. Ensure book JSON + taxonomy JSON already imported; curriculum approved.
2. `/questions` → generate with **Base** → confirm `base@1` on detail.
3. Approve / edit / reject several questions on related subtopics.
4. `/preferences` → **Refresh preferences** → see inferred rows; Confirm one; Correct one; Remove one.
5. `/questions` → generate with **Personalized** → detail shows Personalization evidence (review ids ± prefs).
6. Generate again with **Base** → still `base@1`.

- [ ] **Step 4: Commit**

```bash
git add docs/DECISIONS.md app/personalization/__init__.py app/generation/__init__.py
git commit -m "docs: record retrieval-first personalization ADR"
```

- [ ] **Step 5: Completion report** (for the human)

Return:

- Retrieval approach (meta 0.6 + cosine 0.4; budgets)
- Preference learner (Instructor extract; ≥2 evidence; manual refresh)
- Activation (soft floor 0.35; empty context falls back to Base-like prompt)
- Generator IDs: `base@1`, `personalized-context@1`
- Files changed
- pytest/ruff results
- Exact UI test steps above

---

## Self-review (plan vs spec)

| Spec requirement | Task |
| --- | --- |
| Relevant-example retrieval | Task 4 |
| Metadata + embeddings | Tasks 3–4 |
| Preference learner + conservative confidence | Tasks 1, 5–6 |
| Manual refresh + confirm/correct/remove | Tasks 6, 9 |
| Soft activation | Tasks 5, 7 |
| `personalized-context@1` without changing Base | Tasks 7–8 |
| Same validators/judge | Task 8 (reuse service pipeline) |
| Transparency JSON + UI | Tasks 7, 9 |
| Preserve review history | No feedback mutation |
| Tests listed in spec | Tasks 1–9 |
| No GEPA / no ingestion changes | Global constraints |

No TBD placeholders. Types aligned across tasks (`personalized-context`, `PreferenceConfirmationState`, soft floor 0.35).
