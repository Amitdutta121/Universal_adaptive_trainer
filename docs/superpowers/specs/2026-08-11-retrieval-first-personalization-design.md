# Retrieval-first personalization — design

**Date:** 2026-08-11  
**Status:** approved for planning  
**Approach:** Thin `app/personalization` package (Approach 1) — structured LLM preference
inference, metadata + embeddings retrieval, manual preference refresh. No GEPA.

## Goal

Make question generation adapt to professor feedback **without fine-tuning**, while keeping the
Base generator separately identifiable and callable.

After reviews accumulate, a professor can generate a new question with **relevant reviewed
examples** and **conservatively inferred preferences**. Base generation remains available
unchanged (`base@1`).

Book and taxonomy stay structured JSON uploads (already in use). This work does not touch
ingestion.

## Non-goals

- GEPA or any prompt/optimizer loop
- Replacing or mutating `BaseQuestionGenerator` / `base@1`
- Compressing review history into a single preference blob and discarding evidence
- Student adaptive engine / BKT changes
- Real multi-professor auth (continue optional `professor_id`; default single-professor pool)
- External vector databases (Chroma, FAISS, etc.)
- LangChain or other RAG frameworks

## Decisions locked in brainstorming

1. **Preference learner:** structured LLM extraction via Instructor + existing OpenRouter client.
2. **Example retrieval:** metadata ranking **plus** embedding cosine similarity.
3. **Preference refresh:** **manual** “Refresh preferences” only (not eager after each review).
4. **Architecture:** thin personalization package; Base untouched; personalized generator is a
   separately named generator that reuses Base grounding/prompt structure and appends context.
5. **Soft activation:** no hard “N reviews” switch; evidence strength controls how much
   personalization appears in the prompt.

## Existing foundations (preserve)

| Piece | Location | Role |
| --- | --- | --- |
| Two loops | ADR-001 | Personalization must not import `adaptive` |
| Generator identity | ADR-005, `GeneratorDescriptor` | Base vs personalized stay distinguishable |
| Feedback authority | ADR-006, `ProfessorReviewRow` | Only professor reviews train preferences |
| Original retention | ADR-003 | Edits keep `original_*`; highest-value signal |
| Base generator | `app/generation/base.py` | `base@1`; do not overwrite |
| Feedback write path | `app/feedback/service.py` | Append-only reviews already implemented |
| Validation + judge | ADR-004 / ADR-023 / evaluation | Same pipeline after either generator |
| Personalization seam | `app/personalization/__init__.py` | Replace null learner with real modules |
| Inputs | book JSON + taxonomy JSON | Unchanged |

## Core principle

Past reviewed examples are the **primary** evidence. Preference statements are a **secondary**,
conservative compression that must keep links to supporting review IDs.

Maintain both:

1. **Professor Review History** (append-only; never discarded)
2. **Professor Preference Profile** (inferred statements + confirmation state)

## Hard separation

### Global validity (never personalized away)

- Python correctness
- Answer correctness
- Test correctness
- Source grounding
- Structural validity
- Avoiding genuine ambiguity that breaks scoring

These remain in Base system instructions and in deterministic validators / LLM judge.

### Professor preference (may personalize)

- Wording and clarity habits
- Preferred reasoning / scenario style
- Relative pedagogical emphasis
- Recurring dislikes (when repeatedly evidenced)
- Preferred example patterns

Preference **cannot** override global correctness.

---

## Architecture

```
Feedback history (SQLite) ──► Retriever (meta + embeddings) ──┐
                                                              ├──► personalized-context@1 prompt
Manual Refresh ──► Preference learner (structured LLM) ───────┘
                                                              │
QuestionSpec + section + curriculum ──► same as Base ─────────┘
                                                              │
BaseQuestionGenerator (base@1)  ◄── unchanged, still selectable
                                                              │
Either generator output ──► same validators + pedagogical judge
```

### Module layout

| Module | Responsibility |
| --- | --- |
| `app/feedback/` | Unchanged review history |
| `app/personalization/embeddings.py` | OpenRouter embeddings client + cosine helper |
| `app/personalization/retrieval.py` | Rank and select few relevant review examples |
| `app/personalization/learner.py` | Manual refresh: extract/merge preference statements |
| `app/personalization/generator.py` | `PersonalizedContextGenerator` (`personalized-context@1`) |
| `app/personalization/service.py` | Orchestrate refresh, list prefs, confirm/edit/remove |
| `app/generation/base.py` | **No behavior change** |
| `app/generation/service.py` | Select Base vs personalized by explicit request flag |
| `app/persistence/` | New tables + repositories |

Dependency rules stay: `personalization` may use `feedback`, `generation` (descriptor/spec/prompts),
`llm`, `domain`, `persistence`. Must not import `adaptive`. Prefer `personalization` building on
generation helpers rather than `generation` importing personalization internals (service may
construct either generator).

---

## A. Relevant-example retrieval

### Output budget

For one `QuestionSpec`, retrieve up to:

- **2–4** approved or edited examples (prefer edits)
- **1–2** rejected examples with reasons/comments
- Hard cap ≈ **6** total examples
- Never send the full review history

### Ranking

**Metadata score** (deterministic):

| Signal | Effect |
| --- | --- |
| Same subtopic | Strong boost |
| Same topic (other subtopic) | Medium boost |
| Same question type | Medium boost |
| Same / adjacent difficulty | Small boost |
| Decision | **edit > approve > reject** |
| Recency | Small boost |

**Semantic score:** cosine similarity between:

- **Query text:** topic name, subtopic name(s), question type, difficulty, short source citation
  (and optionally a section title if available)
- **Example text:** current question prompt (post-edit if edited), plus rejection reasons labels
  and comment when present

**Combined:**  
`final = 0.6 * meta_normalized + 0.4 * cosine`  
(weights fixed as constants in v1)

Within each outcome bucket (approved/edited vs rejected), take top-N by `final`.

### Embeddings

- Provider: OpenRouter embeddings API (same API key as chat)
- Config: `embedding_model` in `app/config.py` (default e.g. `openai/text-embedding-3-small`)
- Persist one vector per review example key in `review_embeddings` (JSON float list + model id)
- Compute on first need; reuse thereafter; recompute if model id changes
- Tests use a fake embedder (deterministic vectors); no network

### Fallbacks

| Situation | Behavior |
| --- | --- |
| No reviews | Personalized generator runs with **empty** example/preference blocks; Base instructions dominate. Descriptor still `personalized-context@1`. |
| Few reviews | Shrink budgets; do not pad with weak matches below a minimum score floor |
| Missing embedding | Rank by metadata only for that item; backfill embedding when API available |

---

## B. Preference learner

### Trigger

**Manual only:** professor clicks **Refresh preferences** on the Preferences UI.

Not run automatically after each review.

### Extraction

Structured LLM call (Instructor) over a batch of reviews (cap if large, e.g. most recent 50 +
all edits). Response model lists candidate preference rules with:

- `rule_text`
- `category` (enum: wording, scenario_style, emphasis, dislike, example_pattern, other)
- `supporting_review_ids`

### Conservative merge

- Do **not** invent preferences from a single weak signal (e.g. one `too_difficult` reject →
  “prefers easy”).
- Create or strengthen a statement only when evidence is **repeated/consistent**
  (default: ≥2 distinct supporting reviews, **or** ≥2 edits that agree on the same rule theme).
- Each stored preference:

| Field | Meaning |
| --- | --- |
| `id` | Stable preference ID |
| `rule_text` | Human-readable preference |
| `category` | Category enum |
| `evidence_count` | Number of supporting reviews |
| `confidence` | 0–1 from evidence strength / agreement |
| `supporting_review_ids` | Links back to history |
| `active` | Included in generation when true |
| `confirmation_state` | `inferred` / `confirmed` / `corrected` |
| `profile_version` | Learner procedure version (e.g. `"1"`) |

### Soft activation in generation

No exact “10 reviews” gate.

- Include only preferences with `active` and `confidence ≥ soft_floor` (e.g. 0.35)
- Order by confidence descending; cap count (e.g. ≤5)
- When evidence is weak, omit preferences and/or use fewer examples → Base behavior dominates
- Around **10–15** meaningful consistent reviews, visible personalization should normally emerge

### Professor actions (are themselves feedback)

| Action | Effect |
| --- | --- |
| Confirm | `confirmation_state=confirmed`; keep active |
| Edit/Correct | Update `rule_text`; `confirmation_state=corrected`; treat as strong signal |
| Remove | `active=false` (soft delete; retain row for audit) |

---

## C. Personalized generation

### Generator identity

| Kind | Name | Version | Label |
| --- | --- | --- | --- |
| `base` | `base` | `1` | `base:base@1` (unchanged) |
| `personalized` | `personalized-context` | `1` | `personalized:personalized-context@1` |

### Same inputs as Base

- Base generation instructions (correctness/grounding first)
- Source section
- Approved curriculum definition
- `QuestionSpec`

### Added personalized context

- Relevant active preferences (soft-activated)
- Retrieved approved/edited examples
- Retrieved rejected examples with reasons

Prompt must state that preference/example blocks affect **style and pedagogy only** and must not
override correctness, tests, or grounding.

### Post-generation

Identical deterministic validators and pedagogical judge as Base.

### Transparency (no chain-of-thought)

Persist on the question row (new nullable JSON column), e.g. `personalization_context_json`:

```json
{
  "preference_ids": [1, 2],
  "retrieved_review_ids": [10, 11, 12],
  "profile_version": "1",
  "generator": "personalized-context@1"
}
```

UI on question detail shows which preferences and which reviews influenced generation.
Do not expose raw model chain-of-thought.

---

## Persistence

### `preference_statements`

Stores inferred/confirmed preferences (fields above + timestamps).

### `review_embeddings`

| Field | Role |
| --- | --- |
| `review_id` | FK to `professor_reviews` |
| `model_id` | Embedding model used |
| `vector_json` | Float list |
| `content_hash` | Detect when prompt/comment changed and re-embed |

### `questions.personalization_context_json`

Nullable; set only by personalized generator.

`create_all` remains acceptable (ADR-008); no Alembic yet.

---

## UI

### Questions generate form

Explicit choice: **Base** vs **Personalized** (both always available).

### Preferences page (new nav section or Feedback subsection)

- **Refresh preferences** button
- Table: rule, category, evidence count, confidence, confirmation state
- Actions: Confirm, Edit/Correct, Remove
- Link out to supporting reviews where practical

### Question detail

When `generator_name == personalized-context`, show **Personalization evidence** panel
(preferences + retrieved examples). Avoid CoT.

---

## Libraries (reuse, don’t reinvent)

| Concern | Library / existing code |
| --- | --- |
| Preference extraction | Instructor + `StructuredLLMClient` |
| Question generation | Same structured chat path as Base |
| Embeddings | OpenAI SDK embeddings via OpenRouter |
| Persistence | SQLAlchemy 2.0 + SQLite |
| Schemas | Pydantic v2 |
| UI | Jinja2 + existing CSS |

No GEPA. No vector DB. No new frontend framework.

---

## Testing

Offline fakes for LLM and embedder. Cover:

1. Retrieval ranking (metadata + combined score)
2. Fallback with no feedback
3. Partial feedback (budget shrink)
4. Preference inference merge + conservative confidence
5. Professor confirm / correct / remove
6. Personalized generation context assembly
7. Base generator path and descriptor unchanged
8. Boundary: personalization ↛ adaptive

## Required visible milestone

After accumulating professor reviews (on existing book JSON + taxonomy JSON data):

1. Generate with **Base** → `base@1`
2. Submit sample reviews
3. Refresh preferences (optional for examples-only path; needed for preference rules)
4. Generate with **Personalized** → retrieved examples (and prefs if refreshed) visible on detail
5. Base still separately available

## Verification / completion report (implementation phase)

Return: retrieval approach; preference learner; activation behavior; generator IDs/versions;
files changed; tests/results; exact UI test steps.

## Out of scope for follow-ups (explicit)

- GEPA / automatic prompt optimization
- Multi-professor accounts
- Embedding index beyond SQLite
- Changing book/taxonomy ingestion
