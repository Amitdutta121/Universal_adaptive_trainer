# Taxonomy JSON upload (replace LLM curriculum generator)

**Status:** approved for planning  
**Date:** 2026-08-10

## Problem

Curriculum proposal today is an LLM two-stage generator (Stage A section analysis, Stage B
cross-book normalisation). That path is costly, brittle, and not what we want for the next
product step. The professor already supplies structured **book JSON**; they will also supply a
**fixed Topic → Subtopic taxonomy** as JSON. The app must stop generating curricula and instead
import that taxonomy.

## Goals

1. Remove the live LLM curriculum generator (UI + proposal service entry).
2. Let the professor upload a taxonomy `.json` file, validated totally before any write (same
   discipline as book import).
3. On success, persist an **APPROVED** curriculum version (upload is the declaration).
4. Auto-assign stable ids; the upload file does not carry ids.
5. Document the taxonomy format in the UI and project docs.

## Non-goals

- Professor in-app editing of topics/subtopics.
- Re-deriving a taxonomy from books.
- Embedding the taxonomy inside book documents.
- Changing the adaptive engine (BKT / weakness roulette) beyond consuming approved ids.
- Keeping Stage A/B as an alternate path.

## Approach

Thin taxonomy JSON + dedicated import service (mirror `BookImportService`), then hard-remove the
generator path so dead LLM curriculum code does not remain as a second way in.

## Taxonomy JSON contract

File: `.json` only. `schema_version` checked first. `extra="forbid"`. Invalid → reject in full,
write nothing.

```json
{
  "schema_version": "1",
  "label": "Intro Python — fixed taxonomy",
  "topics": [
    {
      "name": "Loops",
      "description": "Iteration constructs.",
      "subtopics": [
        {
          "name": "While loops",
          "description": "Repeat while a condition holds."
        },
        {
          "name": "For loops",
          "description": "Iterate over a sequence."
        }
      ]
    }
  ]
}
```

| Field | Required | Notes |
| ----- | -------- | ----- |
| `schema_version` | yes | Must be `"1"`. |
| `label` | yes | Version label shown in the UI. |
| `topics` | yes | Non-empty. |
| `topics[].name` | yes | Non-empty after trim. Unique among topics (case-insensitive). |
| `topics[].description` | no | Default `""` if omitted. |
| `topics[].subtopics` | yes | Non-empty. |
| `topics[].subtopics[].name` | yes | Non-empty after trim. Unique within the parent topic (case-insensitive). |
| `topics[].subtopics[].description` | no | Default `""` if omitted. |

Forbidden in the document (not part of this contract): `stable_id`, evidence, grouping reasons,
candidate labels, confidence. Those were LLM-proposal provenance; a fixed taxonomy does not need
them.

Order in the file is the display order (`position` = index).

## Identity

- On import, assign `TopicRow.stable_id` / `SubtopicRow.stable_id` automatically.
- Topic id: fingerprint of the normalised topic name (reuse `normalize_label` / `fingerprint`
  style from `app/curriculum/stable_ids.py`, with a clear `top-` prefix).
- Subtopic id: fingerprint of `(normalised topic name, normalised subtopic name)` with `sub-`
  prefix, so the same subtopic name under two topics stays distinct.
- Ids are **not** taken from display strings at read time later; they are stored on the rows at
  import. Renaming in a future editor is out of scope; a new upload with different names yields
  different ids (acceptable for a fixed-taxonomy workflow).

## Import behaviour

1. Validate upload size/extension (same limits spirit as books; taxonomy files are small).
2. Parse + validate against the Pydantic taxonomy document.
3. Run structural checks adapted for uploads: every topic has ≥1 subtopic; names non-empty;
   unique stable ids after assignment; **evidence is not required**.
4. Persist one `CurriculumVersionRow`:
   - `status = APPROVED`
   - `approved_at = now (UTC)`
   - `generated_by = "taxonomy-upload"`
   - `source_book_ids_json = null`
   - `extraction_metadata_json` / `warnings_json` = null
5. Write topics/subtopics with `review_status = APPROVED` (version and items agree: the upload
   is the professor’s declaration of the fixed taxonomy).

**Multiple approved versions:** each successful upload creates a **new** approved version.
`CurriculumRepository.get_approved()` (or equivalent) returns the **latest** approved version by
`approved_at` then `id`. Older approved versions remain readable in history.

Failure leaves no half-written version (assemble in memory / one transaction, same as books).

## UI

- `GET /curriculum`: replace “Generate a curriculum” with **Upload taxonomy JSON**.
- Show the format summary (schema_version, label, topics/subtopics names) and point at an example
  document under `docs/` (e.g. `docs/taxonomy_document_example.json`), kept valid by a test.
- `POST /curriculum/upload`: multipart file → import → 303 to the new version page.
- No LLM credential gate for upload.
- Version/subtopic browse pages stay; hide or soften empty evidence / grouping-reason panels when
  absent; drop “How this was produced” LLM stage copy for upload-sourced versions
  (`generated_by == "taxonomy-upload"`).

## Removals

- Route `POST /curriculum/generate` and `get_curriculum_proposer` / `CurriculumProposalService`
  as the live path.
- Stage A/B modules used only for proposal (`extraction.py`, `normalization.py`, `candidates.py`,
  LLM pieces of `schema.py` as applicable) — **delete** rather than leave unreferenced, unless a
  type is still needed by upload (prefer a new `app/curriculum/taxonomy_schema.py` for the upload
  contract).
- Proposal-only config: `CURRICULUM_MAX_SECTIONS`, `CURRICULUM_SECTION_CHAR_BUDGET` (and `.env`
  examples) if nothing else uses them.
- Tests that only cover LLM proposal; replace with taxonomy import + web upload tests.
- Update `CLAUDE.md`, `README.md`, and supersede **ADR-018** with an ADR that curriculum structure
  is **declared by taxonomy JSON upload**, not LLM-derived. Keep ADR-002 (generation needs
  approved curriculum ids) — upload now produces that approval.

LLM package (`app/llm/`) stays for later question generation; only curriculum proposal stops using
it.

## Testing

- Schema: valid example; reject unknown fields; empty topics; duplicate names; wrong
  `schema_version`.
- Import: APPROVED version; auto stable ids stable across re-import of identical document;
  different names → different ids; `get_approved` returns latest.
- Web: upload success redirect; invalid file shows error; generate button gone.
- Boundaries: proposal modules stay deleted / not reintroduced if `test_boundaries` style checks
  exist.

## Risks / decisions locked

| Decision | Choice |
| -------- | ------ |
| Status on upload | `APPROVED` immediately |
| Ids in file | No — auto-defined |
| Evidence | Not required |
| Generator | Removed |
| Format style | Declared JSON, like books |
| Which approved version | Latest by `approved_at`, then `id` |
