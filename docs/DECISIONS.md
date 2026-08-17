# Architectural decision log

Stable, append-only record of decisions that shape this codebase. Each entry states the decision,
why it was taken, and what it implies for future work. **Do not delete entries.** When a decision
is replaced, add a new entry and mark the old one superseded, naming the entry that replaces it.

Status values: `accepted` · `superseded by ADR-nnn`

---

## ADR-001 — Two separate adaptation loops

**Status:** accepted

Student adaptation and professor content optimization are separate loops that share only the
question bank.

- The **student loop** reacts to student scores: BKT topic mastery and subtopic weakness decide
  what to ask next.
- The **professor loop** reacts to professor reviews: approve / reject / edit history decides what
  kind of questions to generate.

**Why:** the loops optimize different objectives on different timescales. Mixing them would let
student performance silently redefine what the professor is deemed to prefer, which is both wrong
and untraceable. Keeping them apart also means either can be changed without regression risk to
the other.

**Implications:** `app/adaptive/` must not import `app/personalization/`, and vice versa; a test
in `tests/test_boundaries.py` enforces this. Student scores must never be an input to preference
learning, and preference data must never influence student selection beyond the questions it
produced.

---

## ADR-002 — Question generation is grounded in approved curriculum IDs

**Status:** accepted

Every generation request names a **curriculum version id** and a **subtopic id** from that
version, and the version must be approved. Generation without an approved curriculum is an error,
not a fallback to some default.

**Why:** questions must be traceable to the structure the professor signed off on. Free-form
generation against a topic *name* would drift from the approved curriculum and make later
curriculum edits impossible to reason about.

**Implications:** `GenerationRequest` (in `app/generation/`) requires both ids — they are not
optional fields. The curriculum is **versioned**, and editing an approved curriculum creates a new
version rather than mutating the approved one, so questions keep pointing at what they were
actually written against. `QuestionRow` stores `curriculum_version_id` and `subtopic_id`.

---

## ADR-003 — Generated originals are retained after professor edits

**Status:** accepted

When a professor edits a generated question, the generated text is preserved alongside the edit.
The `original_prompt`, `original_reference_solution` and `original_tests` fields are written once,
at generation time, and are never overwritten.

**Why:** the difference between *what was generated* and *what was accepted* is the highest-value
training signal available for improving the generator. Overwriting the original destroys it
permanently and irrecoverably.

**Implications:** `Question` seeds the `original_*` fields on construction, and
`apply_professor_edit()` is the only sanctioned edit path. Professor reviews are **append-only**
for the same reason: a later review is a new row, never an update. Tests in `tests/test_domain.py`
pin this behaviour.

---

## ADR-004 — Deterministic correctness checks take precedence over LLM judgment

**Status:** accepted

A question is valid only if every **deterministic** check passes. LLM judgment is advisory: it may
add non-deterministic checks and flag concerns, but it can neither rescue a question that failed a
deterministic check nor validate one that had no deterministic checks at all.

**Why:** deterministic checks (does the code parse, does the reference solution pass its own
tests, does it terminate) are reproducible and cheap to trust. LLM judgment is neither, and it
fails in correlated ways with the generator that produced the question — the same model that
wrote a subtly wrong question will happily approve it.

**Implications:** `QuestionValidationReport.passed` considers only checks marked
`deterministic=True`, and an empty report does **not** pass. Deterministic execution checks run via
a local isolated subprocess runner (ADR-023); validation stores a report and never returns a
vacuously empty passing report.

---

## ADR-005 — Base and personalized generators stay distinguishable and versioned

**Status:** accepted

Every generator carries a `GeneratorDescriptor` of `kind` (base | personalized), `name` and
`version`, and that identity is stamped onto every question it produces and copied onto every
review of that question.

**Why:** personalization is only worth having if its effect can be measured. That requires
attributing each question — and each professor verdict — to the exact generator that produced it.
A silent in-place swap from base to personalized would make any later quality comparison
impossible.

**Implications:** `QuestionRow` stores `generator_kind`, `generator_name`, `generator_version`.
`ProfessorReviewRow` copies the generator name and version at review time, so the signal survives
later changes to the question row. Personalized generators are versioned alongside the procedure
that built their preference profile.

---

## ADR-006 — Professor feedback is the authority for professor preference

**Status:** accepted

A professor's preferences are derived from their explicit approve / reject / edit decisions and
comments, and from nothing else.

**Why:** preference is a statement about pedagogical intent, and only the professor can make it.
Inferring it from proxies — student pass rates, engagement, question popularity — would answer a
different question and would quietly overrule the person responsible for the course.

**Implications:** `app/personalization/` reads professor feedback only. Comments are stored
verbatim rather than reduced to tags at write time, because the useful structure is not yet known.
`ProfessorPreferenceProfile.review_count` exposes how much signal a profile rests on, so a profile
built from two reviews is not mistaken for a confident one.

---

## ADR-007 — Server-rendered FastAPI + Jinja2, no frontend framework

**Status:** accepted

The professor UI is server-rendered Jinja2 with a single hand-written CSS file. No SPA framework,
no bundler, no npm dependency.

**Why:** the repository was empty at the start of this work, so there was no existing stack to
preserve, and the professor workflow is forms, tables and review screens — it does not need
client-side state management. Avoiding a JS toolchain keeps the number of ways to run and break
the project to one.

**Implications:** interactive review screens must be built with forms and full-page requests, or
with small amounts of inline JavaScript. If a genuinely interactive surface (e.g. an in-browser
code editor) later justifies a frontend framework, that needs a new ADR — not an ad-hoc
introduction.

---

## ADR-008 — SQLite via SQLAlchemy, schema created with `create_all`, no migration tool yet

**Status:** accepted

Persistence is SQLite through the SQLAlchemy 2.0 ORM. Tables are created with
`Base.metadata.create_all()` on startup. Only the tables the professor pipeline needs now exist:
`books`, `curriculum_versions`, `topics`, `subtopics`, `questions`, `professor_reviews`.

**Why:** SQLite needs no server and suits a single-professor workload. Adding Alembic now would
mean maintaining migrations for a schema that is still being discovered; `create_all` is honest
about that stage. Designing the remaining tables up front would mean guessing at shapes the
features have not yet constrained.

**Implications:** deliberately absent for now — extracted book structure, generator artefacts, and
all student progress tables (BKT state, subtopic weakness, attempt history). Because there are no
migrations, changing an existing column currently means recreating the local database. **A
migration tool must be introduced before the first deployment that holds data worth keeping.**

---

## ADR-009 — Deferred features fail loudly

**Status:** accepted

Each not-yet-implemented subsystem ships a `Null*` implementation behind its `Protocol` that
raises `FeatureNotAvailableError`. Placeholder pages show real (empty) database state and state
plainly what is not implemented.

**Why:** a stub that returns an empty list or a vacuously passing report is indistinguishable from
a working feature with no data. That ambiguity causes exactly the sort of false "it works" claim
this project forbids.

**Implications:** the boundary exists and is typed, so the real implementation is a drop-in
replacement, but nothing can accidentally depend on placeholder output. `tests/test_boundaries.py`
asserts each placeholder raises.

---

## ADR-010 — Configuration only through `app/config.py`

**Status:** accepted

All configuration is read from environment variables (optionally via `.env`) into a typed
`Settings` object. No other module reads `os.environ`. Credentials are `SecretStr`, and the app
must start and serve the whole UI with no LLM credentials configured.

**Why:** one place to look, one place to validate, one place to keep secrets out of logs. Being
runnable without credentials means the UI can be developed and reviewed without a paid API key,
and it makes "LLM not configured" a displayed state rather than a crash.

**Implications:** `Settings.llm_configured` gates LLM-backed features; `require_llm()` raises a
`ConfigurationError` with actionable text when they are called unconfigured. `describe_llm()` is
the only sanctioned way to show LLM status and never reveals the key. `.env` is git-ignored;
`.env.example` documents every variable.

---

## ADR-011 — The instructional section is the unit of the source model

**Status:** superseded by ADR-015 — the "section is the unit" rule carries forward unchanged;
the heuristic extraction described below was removed.

Book extraction preserves **semantic textbook sections**. It never splits text on a token,
character or page budget. One section row is one instructional unit, however long that is.

Structural signals are used in a fixed order of trustworthiness, and each unit records which one
produced it (`StructureSource`) and how much that is worth trusting (`StructureConfidence`):

1. the PDF outline / bookmarks — the publisher's own table of contents (HIGH);
2. Markdown ATX headings (HIGH);
3. a numbered heading corroborated by larger type (MEDIUM);
4. a numbered heading with no typographic corroboration (LOW);
5. the page, preserved as-is, when no heading could be found (LOW).

**Why:** a question grounded in "characters 4000-6000 of chapter 3" cannot be cited, reviewed or
trusted, and an arbitrary boundary routinely cuts an explanation in half. The section is the unit
the textbook's author chose as self-contained, which is exactly what a question needs to be
grounded in and what a professor needs to review.

**Implications:** downstream consumers may chunk a long section internally to fit a model context
window, but that chunking is theirs and is never persisted here. `book_sections.text` always holds
the whole section. Extraction is implemented with `pypdf` — pure Python, no native binaries — for
page text, the outline, and the per-fragment font sizes that typography detection needs. Optical
character recognition is out of scope: a scan with no text layer is rejected outright rather than
stored as a book with empty sections.

---

## ADR-012 — Uncertain structure is marked, never smoothed over

**Status:** accepted — the rule stands. Since ADR-015 the uncertainty is *declared by the book
document* rather than measured by this application, and `FAILED` is gone because an invalid
document is now rejected before any row exists.

Extraction never fabricates a heading. When no heading is found, the unit's `title` is `NULL`, its
confidence is LOW, and the UI labels it by *location* ("Untitled section (Pages 12-13)") rather
than by an invented name. Heading detection is deliberately biased towards missing a heading
rather than inventing one: a candidate is rejected unless its title starts like a title, and
table-of-contents leader lines are excluded.

A book whose extraction lost or could not determine something is `PARTIAL`, never `EXTRACTED`. A
book that yielded no text at all is `FAILED` with the reason attached — not an empty success.

Warnings carry a severity. Only `DEFECT` warnings make a book `PARTIAL`; `INFO` warnings state a
fact without implying a fault (for example, "this PDF has no table of contents", or "this format
carries no page numbers").

**Why:** a fabricated section heading corrupts every citation made against it, and unlike missing
structure it cannot be detected later. Distinguishing severity matters for the same reason a
warning light that is always on is useless: if a perfectly good extraction were flagged partial
merely because the PDF lacked bookmarks, the professor would learn to ignore the flag and miss the
extractions that genuinely went wrong.

**Implications:** `title` is nullable on both `book_chapters` and `book_sections`, and
`has_detected_heading` is how callers ask whether a heading was real. `BookStructure.is_partial`
drives the status. The professor-facing pages show status, per-section confidence, the detection
method in words, and every warning.

---

## ADR-013 — Uploaded originals are retained, and validated before storage

**Status:** accepted — the rule stands. Since ADR-015 the retained file is the book JSON document
rather than a PDF, and "validated" now means the full schema check, so a rejected upload leaves
behind neither a file nor a row.

The uploaded file is written to `BOOK_UPLOAD_DIR` under a collision-free name and kept, with its
size and SHA-256 recorded. Validation — extension, size limit, and the `%PDF-` signature for PDFs
— happens **before** anything is stored or any book row is created.

**Why:** extraction quality will improve, and re-running it against the retained original is the
only way to benefit without asking the professor to upload a textbook again. Validating first
means a rejected upload leaves nothing behind: no orphan file, and no book row that looks like it
might work later.

**Implications:** `books` stores `stored_filename`, `file_size_bytes` and `checksum_sha256`.
Rejected uploads raise before `BookRepository.add`, and the route re-renders the Books page with
an inline error so the professor can correct and retry. Extraction *failures*, by contrast, do
create a book row: the file was valid enough to accept, so the failure belongs on that book's page
where it can be seen and explained.

---

## ADR-014 — Schema drift is reported at startup

**Status:** accepted

`init_db()` calls `verify_schema()`, which compares every mapped column against the live database
and raises `SchemaOutOfDateError` — naming the missing columns and the remedy — when they differ.

**Why:** `create_all` adds missing tables but never alters existing ones, so a database file
created before a model gained a column survives startup and then fails mid-request with a bare
"no such column". While there is no migration tool (ADR-008), the honest response is to detect the
drift immediately and say what to do about it.

**Implications:** this stage added columns to `books`, so any pre-existing local database must be
deleted and recreated; the error says so explicitly. This makes the absence of migrations visible
and self-correcting rather than a lurking failure, and it does not reduce the need for a real
migration tool before any deployment holds data worth keeping.

---

## ADR-015 — Book structure is declared by the input, never extracted by the application

**Status:** accepted (supersedes ADR-011)

The application imports **structured book JSON documents** and nothing else. A document states its
own chapters, sections, section text and page ranges; the application validates that document and
stores it. It performs no heading detection, no font-size comparison, no text segmentation and no
guessing of any kind. `.json` is the only accepted upload extension.

**Why:** heuristic extraction is not deterministic across books. Rules tuned on one textbook —
numbered-heading patterns, "larger than body text" thresholds, table-of-contents leader detection —
silently mis-segment the next book, and the failure is invisible because the output still looks
like a valid structure. Every downstream citation then points at a boundary the textbook does not
have. Making structure an input turns import into a total, reproducible function: the same JSON
always produces the same rows, and the fallible book-specific work moves to a producer whose
output can be inspected and corrected before it reaches the database.

**Implications:**

- `app/ingestion/schema.py` is the contract, and validation is strict: `extra="forbid"` so a
  misspelled key is an error rather than an ignored field; non-empty `text` required on every
  section; at least one section per chapter and one chapter per book; page ranges must not run
  backwards; `schema_version` is checked first so an old document reports a version problem rather
  than a pile of field errors.
- Removed: `app/ingestion/headings.py`, `pdf.py`, `text.py`, `assembly.py`, and `pypdf` as a
  dependency of any kind. `tests/test_boundaries.py` asserts they stay removed and that no PDF
  parser is imported, installed or declared (see ADR-016).
- `StructureSource` values now describe what the *producer* relied on (`pdf_outline`,
  `markdown_heading`, `manual`, `structured_json`, `producer_inferred`). A document may also state
  a unit's `confidence` explicitly, which is stored rather than re-derived.
- Section text is stored verbatim, including leading whitespace, because a section may open with an
  indented code listing. Only label fields are trimmed.
- `BookStatus` is `IMPORTED` or `PARTIAL`. There is no `FAILED`: validation precedes storage, so
  every book row in the database is one whose structure validated.

---

## ADR-016 — Producing a book document is out of scope for this repository

**Status:** accepted

This repository contains **no book conversion code at all** — no PDF parser, no EPUB or HTML
reader, no offline converter script. The professor supplies a valid book JSON document; the
application's entire responsibility is to validate it uncompromisingly and store it. `pypdf` is not
a dependency of any kind, and is not installed.

An earlier revision shipped `tools/pdf_to_book_json.py`, an outline-only PDF converter. It was
removed.

**Why:** any converter is book-specific in practice. A PDF-outline reader works on textbooks whose
publisher wrote bookmarks and fails on the rest; an EPUB reader needs different code again; a
scanned book needs OCR. Shipping one converter inside this repository would make it look like the
supported path, invite the next book to be forced through it, and pull book-specific maintenance
into the codebase that is supposed to be book-agnostic. Keeping the boundary at "a valid document
arrives" means this codebase has exactly one behaviour to get right, and it is testable without any
book at all.

**Implications:**

- The Books page documents the document shape and points at
  `docs/book_document_example.json`; it does not offer to convert anything.
- Uploading a `.pdf`, `.epub`, `.md`, `.txt` or `.html` is rejected with an explanation of what to
  supply instead — informative, but never a conversion attempt.
- `tests/test_boundaries.py` asserts that the deleted heuristic modules stay deleted, that nothing
  under `app/` mentions `pypdf`, `PdfReader`, `fitz`, `pdfplumber` or `pdfminer`, that no PDF parser
  is installed, and that none is declared in `pyproject.toml`. Reintroducing one now requires a
  deliberate, visible change.
- The `producer` field remains in the schema so a document can record what made it, for provenance
  only. The application never interprets it.
- Whoever writes a converter is responsible for declaring its own uncertainty: a guessed boundary
  must be `structure_source: "producer_inferred"`, which the application stores as LOW confidence
  and which makes the book `PARTIAL`.

---

## ADR-017 — The LLM boundary offers structured output only, over `httpx`

**Status:** superseded by ADR-020

`app/llm/` exposes exactly one operation: give it a JSON Schema, get back a dictionary that
satisfied it, or an error. There is no free-text completion API. Both providers are called with
plain HTTP through `httpx`, which is now a runtime dependency, rather than through a provider SDK.
Anthropic is called with a forced tool call whose `input_schema` is the caller's schema; OpenAI is
called with a strict `json_schema` response format.

**Why:** a text endpoint would invite exactly the thing this codebase already rejected for book
structure (ADR-015) — recovering structure by pattern-matching prose. Making the only available
call a schema-shaped one means every consumer parses into a strict Pydantic model or fails.
Choosing raw HTTP over an SDK keeps the second provider from becoming a second large dependency
tree, for perhaps thirty lines of saved code; `httpx` was already installed and is the client this
stack already uses.

**Implications:** `LLMRequestError` (provider unreachable or refusing) and
`MalformedModelOutputError` (call succeeded, content unusable) are separate types, because the
first is worth retrying and the second is not. Transport failures and 408/409/429/5xx are retried
once; a 4xx is not, since a rejected schema will be rejected again. Credentials travel in headers
only and never appear in a request body, a log line or an error page. `get_structured_client()`
raises `ConfigurationError` before any work starts, so an unconfigured run costs nothing.

---

## ADR-018 — Curriculum is derived in two LLM stages, then checked deterministically

**Status:** superseded by ADR-021

A proposed Topic → Subtopic curriculum is derived from the imported books by two separate LLM
stages, followed by deterministic assembly and validation that never consults a model:

1. **Stage A** (`app/curriculum/extraction.py`), once per instructional section: what the section
   teaches, and which assessable concepts it introduces, each with a definition and verbatim
   supporting excerpts.
2. **Stage B** (`app/curriculum/normalization.py`), once over every candidate from every book:
   which candidates are the same skill, under one normalised name, with a one-sentence auditable
   reason.

Everything after Stage B — checking that the ids returned are ids that were sent, merging groups
that normalised to the same name, assigning identifiers, ordering, attaching evidence, and the
structural checks in `app/curriculum/checks.py` — is deterministic.

**Why:** the professor should not have to hand-author a complete knowledge-component model, but
they must be able to audit the one they are given. Splitting judgement from bookkeeping is what
makes that possible: the model's judgement is unrepeatable, so the surrounding accounting must not
be. Two stages rather than one because equivalence across books cannot be judged from inside a
single section — the section does not know how other books word the same skill.

**Implications:**

- **Granularity is a first-class constraint, not a prompt suggestion.** A proposed subtopic must be
  something a student can practise, a professor can assess with several different questions, and
  the adaptive engine can track a weakness against. Term extraction is explicitly not the task: a
  glossary makes a useless weakness model, because weakness spread over hundreds of micro-concepts
  never accumulates enough evidence to steer selection. `MAX_CONCEPTS_PER_SECTION` enforces a
  ceiling in the schema, so a model that ignores the instruction fails validation.
- **Every subtopic is traceable.** `subtopic_evidence` records the book, section, the label that
  book used, and representative excerpts. A subtopic with no supporting section fails the checks.
- **Stable ids are derived from source material, never from display names**
  (`app/curriculum/stable_ids.py`): the candidate labels the books used, the candidate topic
  labels, and a fingerprint of each supporting section's position in its book. A professor renaming
  a subtopic must not detach its evidence or, later, reset a student's measured weakness for that
  skill. Known limitation: moving a subtopic between topics, or re-running over a different set of
  books, does change its id — identity is defined by the source material it was derived from.
- **The proposal is assembled and checked in full before a row is written**, as ingestion does with
  book documents. A failed run leaves no half-built curriculum.
- **Nothing is dropped in silence.** Sections skipped by `CURRICULUM_MAX_SECTIONS`, sections
  truncated to the analysis context budget, a section whose analysis failed, and candidates Stage B
  did not place are all recorded as warnings on the version and shown to the professor. By
  contrast, an id the model invented or assigned twice fails the run: that is the answer failing to
  refer to the question, not a judgement call.
- **Proposing is not approving.** The version is written `PROPOSED`, every topic and subtopic is
  `PROPOSED`, and question generation still requires an approved version (ADR-002). Review, editing
  and approval are not implemented yet.
- Stage A is one call per section, so a whole-textbook run is slow and costs real money;
  `CURRICULUM_MAX_SECTIONS` bounds it. Stage B is a single call over every candidate, so a very
  large book set will eventually strain its context window — the point at which that becomes a
  problem needs a batching design, not a silent truncation.

---

## ADR-019 — OpenRouter is a first-class provider, used to reach DeepSeek

**Status:** superseded by ADR-020

`LLM_PROVIDER` accepts `openrouter` alongside `anthropic`, `openai` and `none`, and the default
local configuration is OpenRouter routed to `deepseek/deepseek-chat`. OpenRouter speaks OpenAI's
chat-completions wire format, so `OpenAIStructuredClient` and `OpenRouterStructuredClient` are now
two thin subclasses of a shared `OpenAICompatibleClient`; only the default endpoint, the provenance
label and a few provider-specific fields differ.

**Why not just set `LLM_PROVIDER=openai` with `LLM_BASE_URL=https://openrouter.ai/api/v1`:** that
works on the wire but hides three differences the application has to get right. OpenRouter's model
names are namespaced (`deepseek/deepseek-chat`), so provenance recorded as `openai/...` would name
the wrong service on every curriculum version. OpenRouter routes one model name to whichever
upstream provider is available, and they do not all enforce a JSON Schema — so the request must
carry `provider.require_parameters: true`, or a reply can come back as prose from a route that
treated `response_format` as a suggestion. And because the input here is a professor's textbook
content, the request also asks for `provider.data_collection: deny` so routing avoids upstreams
that retain it for training. None of that is expressible as a base-URL override.

**Implications:**

- Structured output stays a routing constraint rather than a hope; a route that cannot honour the
  schema is not used, instead of being paid for and then rejected as malformed output.
- `to_strict_schema()` is applied to every OpenAI-compatible request. Strict mode refuses an object
  schema whose `required` array omits any property, and Pydantic omits fields that have defaults —
  `SectionAnalysis.concepts` is the one that matters, so Stage A was being refused with an HTTP 400
  before the model ever saw it. Listing every property as required only means the model must answer
  `"concepts": []` explicitly; `parse_structured` remains the authority on every other constraint,
  and nothing is relaxed.
- Model choice is a configuration concern, not a code one. `deepseek/deepseek-chat` is the default
  because it is inexpensive and non-reasoning, so the whole of `LLM_MAX_OUTPUT_TOKENS` goes to the
  answer. A reasoning route such as `deepseek/deepseek-r1` spends part of that budget on hidden
  reasoning tokens and needs the budget raised before a full Stage B reply will fit.
- Attribution headers (`HTTP-Referer`, `X-Title`) are sent because OpenRouter asks for them. They
  carry no credential, and the API key still travels in the `authorization` header only.

---

## ADR-020 — Instructor over OpenRouter owns structured LLM calls

**Status:** accepted

`app/llm/` exposes one operation: pass a Pydantic model type, receive a validated
instance (or an error). Transport is OpenRouter via the OpenAI SDK, wrapped by
Instructor (`Mode.JSON`). Direct Anthropic/OpenAI providers and hand-rolled
`httpx` request builders are removed. Model choice is `LLM_MODEL`
(default `deepseek/deepseek-chat`).

**Why:** maintaining provider wire formats (tools vs strict json_schema,
`to_strict_schema`) cost more than it saved. Instructor provides structured
output; OpenRouter provides one endpoint for DeepSeek and future routes.
Validation-repair retries stay off (`max_retries=0`) so bad answers surface as
`MalformedModelOutputError` rather than being silently re-prompted.

**Implications:**

- `LLM_PROVIDER` is `openrouter` or `none` only.
- Every request sends `provider.data_collection: deny`. Do not set
  `require_parameters` — DeepSeek routes would disappear.
- `LLMRequestError` vs `MalformedModelOutputError` remain distinct.
- Callers depend on `StructuredLLMClient`, never on Instructor or OpenAI types.

**Amended by ADR-030** for asynchronous work only. A batch job is submitted now
and collected up to 24 hours later, so there is no call for Instructor to wrap:
`app/llm/batch.py` builds those request bodies by hand. The provider is
unchanged — still OpenRouter, still one credential, still
`provider.data_collection: deny` — and every synchronous call still goes through
Instructor. Batch jobs live under `/api/beta/batches`, not `/api/v1`.

---

## ADR-021 — Curriculum comes from fixed taxonomy uploads

**Status:** accepted

Professors provide a strict JSON Topic → Subtopic taxonomy. A valid upload is persisted as an
approved curriculum version; an invalid upload writes nothing. The application does not propose
curriculum from books or through an LLM.

**Why:** the fixed taxonomy is the intended adaptive knowledge-component model. Keeping a second,
LLM-derived route creates competing definitions of curriculum and leaves an expensive proposal
path available even though its output is no longer part of the product workflow.

**Implications:**

- The former Stage A/B extraction, normalization, draft assembly and structural-check modules are
  deleted, along with their configuration limits and proposal-specific error.
- `app/curriculum/` exports taxonomy import, schema version and display decoders only.
- A valid upload is written as **APPROVED** immediately; question generation and the UI treat the
  latest approved version as authoritative (ADR-002).
- Stable ids are assigned from topic and subtopic names at import (`app/curriculum/taxonomy_ids.py`)
  and survive later display-name edits.
- Uploaded taxonomies do not require textbook evidence, candidate labels, grouping rationales or
  model metadata.
- Existing LLM-generated database rows remain renderable; the display decoders tolerate null or
  malformed legacy metadata without restoring any generation capability.
- Taxonomy pages do not imply that uploaded subtopics contain textbook evidence, grouping
  rationales or model metadata.
- `app/llm/` remains because structured LLM access will be used by question generation.

---

## ADR-022 — Base questions are generated section-first as typed specifications

**Status:** accepted

Cold-start question generation resolves a `QuestionSpec` before making an LLM request. The spec
must name an approved curriculum version, one topic, one or more subtopics belonging to that
topic, a difficulty, a question type, and exactly one source section. A base-generation request
with several selected sections is therefore expanded into one independently validated spec and one
generated question per section.

**Why:** generation needs a stable, auditable contract shared by the base generator and future
personalized generators. Grounding a question in one instructional section keeps its source
citation meaningful and prevents a later invalid selection from producing a partially grounded
batch. It also makes the cold-start path deterministic around the LLM boundary: all database
relationships are checked before the first model call.

**Implications:**

- `QuestionType` describes the assessment format (multiple choice, true/false, output prediction,
  code completion, debugging, Parsons, or coding). `QuestionKind` remains a separate scoring
  classification: naturally discrete formats score `0` or `100`, while programming formats are
  testable programs. The type-to-kind mapping is fixed in `app/generation/schemas.py`.
- Each type has its own strict Pydantic response model. The model output is retained in
  `questions.content_json` with its source citation and model provenance, while the stable
  `prompt`, `reference_solution`, and `tests` columns remain available to existing review and
  adaptive paths.
- The section-first base generator is identified as `base@1` on every persisted question. A
  future personalized generator must use the same `QuestionSpec` contract and a distinct,
  versioned descriptor (ADR-005).
- `GenerationService` validates all selected sections before it calls the LLM, persists each
  generated question, and commits only after the batch succeeds. A model or provider failure does
  not claim that generation succeeded.
- The professor workflow is: import a book JSON document and taxonomy JSON, open `/questions`,
  choose a book, then select topic, subtopic, difficulty, type, and one or more sections. The
  generated question detail shows its prompt, typed content, answer/tests when applicable,
  curriculum, difficulty, type, generator, and source citation.
- Automatic validation is implemented (ADR-023). Professor review writes, personalization, and
  database migrations remain deferred. Existing local SQLite databases that predate
  question-generation columns must be recreated until migrations are introduced (ADR-008 and
  ADR-014).

---

## ADR-023 — Local deterministic validation uses an isolated subprocess runner

**Status:** accepted

Executable question checks use a hybrid test shape: each case may provide standard input, expected
standard output, an assertion, or both output and an assertion. The local runner writes generated
Python to a temporary directory and invokes the current interpreter with `-I`, a minimal
environment, captured output, and a configured timeout.

**Why:** syntax checks alone cannot establish that expected output is correct or that a reference
solution passes its own tests. A bounded subprocess makes those deterministic behaviors
reproducible while keeping execution failure and timeout separate from the web process. Validation
does not use an LLM: deterministic runtime and structural evidence remains the authority required
by ADR-004.

**Implications:** every generated question is validated before its generation transaction commits.
The complete `QuestionValidationReport` is stored on the question, and its deterministic result
sets the question's validation status. The question detail page renders the stored report in a
**Deterministic checks** panel, including failure evidence when available.

This runner is local research-prototype isolation, not multi-tenant security isolation. `-I`, a
temporary working directory, and a timeout reduce accidental interference, but generated code can
still reach the filesystem and other same-user process capabilities in theory. Untrusted
multi-tenant execution requires a stronger sandbox outside this design.

---

## ADR-024 — Advisory structured LLM pedagogical evaluation supplements deterministic validation

**Status:** accepted

After deterministic validation completes, every generated question receives a structured LLM
pedagogical evaluation stored in `pedagogical_eval_json`. The evaluation records the judge model,
rubric version, and timestamp alongside per-dimension scores and rationales. When deterministic
validation fails, `GenerationService` skips the judge and stores a `skipped` evaluation; the judge
never overrides a failed deterministic check (ADR-004).

**Why:** deterministic checks catch invalid Python, broken tests, and incorrect expected output,
but they cannot assess pedagogical quality — clarity, alignment with source material, difficulty
appropriateness, or whether a question teaches the intended concept. A separate advisory judge
gives professors structured feedback without conflating runtime correctness with instructional
value.

**Implications:** `app/evaluation/` owns the rubric, schema, and `PedagogicalJudge` service.
`app/validation/` remains LLM-free (ADR-023). Individual dimension results are the primary
evaluation output; the overall advisory score is an unweighted arithmetic mean of applicable
dimension scores, provided as a summary only. A completed or glowing pedagogical evaluation
cannot change a failed deterministic result to passed; an `error` evaluation cannot fail a question
that passed deterministic checks. The question detail page renders deterministic checks and LLM
pedagogical evaluation in separate panels.

---

## ADR-025 — Retrieval-first personalization with dual stores and soft activation

**Status:** superseded by ADR-033

Professor personalization is **retrieval-first**: at generation time the personalized generator
(`personalized-context@1`) augments the same section-first base prompt with (a) ranked
professor-reviewed examples and (b) active preference statements. It does **not** replace the
base generator (`base@1`), rewrite the base prompt contract, or run a separate optimization loop.

**Dual stores**

- **Review history** — append-only `ProfessorReviewRow` records (approve / reject / edit) are the
  authoritative source of examples. Reviews are never mutated when preferences are refreshed.
- **Preference statements** — `PreferenceStatementRow` holds inferred rules extracted from that
  history. Professors refresh manually, then confirm, correct, or remove individual statements.

**Retrieval**

- Up to 200 recent reviews are scored per request. Final rank combines normalized metadata
  (subtopic/topic match, question type, difficulty adjacency, decision weight, recency) at weight
  **0.6** with cosine similarity of review embeddings to the current generation query at weight
  **0.4**.
- Budgets: up to **4** approved/edited examples and **2** rejected examples; minimum score floor
  **0.05**. Embeddings are cached in `ReviewEmbeddingRow` keyed by review and content hash.
- Up to **5** preference statements with confidence ≥ **0.35** (soft floor) are included in the
  prompt. If retrieval and preferences both yield nothing, the prompt stays base-like — only the
  style/pedagogy disclaimer is added.

**Preference learning**

- On manual **Refresh preferences**, recent reviews are serialized and sent through Instructor
  structured extraction. A candidate rule requires **≥ 2** supporting review ids; single-evidence
  rules are dropped. Confidence is derived from evidence count; professor **confirm** boosts it.
- No automatic refresh on every review; no student data; no GEPA or other offline generator
  optimization in this repository.

**Generator identity and pipeline**

- Base: `base@1` via `BaseQuestionGenerator`. Personalized:
  `personalized-context@1` via `PersonalizedContextGenerator`.
- Selection is explicit (`generator="base"` | `"personalized"`) on
  `GenerationService.generate_for_sections`; the UI drives the flag.
- Personalized questions reuse the same deterministic validation and advisory pedagogical judge
  as base questions. `personalization_context_json` on each question records
  `preference_ids`, `retrieved_review_ids`, `profile_version`, and `generator` for transparency.

**Why:** retrieval over concrete reviewed examples is traceable and conservative — the professor
can see which reviews and preferences influenced a question. Separating history from inferred
statements lets the system learn without overwriting feedback. Soft activation avoids blocking
personalized generation when signal is thin while keeping weak rules out of the prompt. Keeping
`base@1` unchanged preserves A/B comparison and avoids silent generator swaps (ADR-005).

**Implications:** `app/personalization/` owns retrieval, embeddings, preference extraction,
refresh/confirm/correct/remove, and `PersonalizedContextGenerator`. `app/generation/` owns
`GenerationService` selection and the base generator. `app/personalization/` must not import
`app/adaptive/` (ADR-001). Future generator optimization (including any GEPA-style procedure) is
out of scope until explicitly requested; it would be a new ADR and a new generator version, not an
in-place change to `personalized-context@1`.

---

## ADR-026 — JSON and enum columns decode themselves

**Status:** accepted

Sixteen columns hold JSON, and eighteen hold an enum. Both were plain
`Text`/`String` columns that every reader decoded for itself, so `json.loads`
plus `isinstance` guards were repeated at each call site and the copies were
free to disagree. `app/persistence/types.py` moves that work into the column:

- `JsonObject` / `JsonList` — a `dict | None` / `list`;
- `PydanticObject(Model)` / `PydanticList(Model)` — validated model instances;
- `EnumList(Enum)` — a list of members;
- `StrEnumType(Enum)` — one member.

The Python attribute is named for what it holds (`question.content`,
`review.reasons`) while `mapped_column`'s first positional argument pins the
original database column name (`content_json`, `reasons_json`).

**Why:** decoding belongs to the thing that encoded it. The duplicated version
had already drifted — `MultipleChoiceDraft` accepts duplicate options while
`_multiple_choice` rejects them — and `Mapped[SomeEnum]` backed by `String`
returned the member on a constructed row but a bare `str` on a loaded one, so
callers had grown `hasattr(value, "value")` guards to survive both.

`TypeDecorator` over `Text`/`String` rather than `sqlalchemy.JSON` keeps the
stored text and the emitted DDL byte-identical, so an existing database file
keeps working. That matters while there is still no migration tool (ADR-008):
altering column types would mean "delete your database", and professor reviews
are append-only history that must not be deleted.

**Implications:**

- Tolerance policy lives in one place: an unreadable *display* value yields
  `None`/`[]` and logs a warning, because a bad stored value must not break a
  page the professor came to read. An unrecognised **scalar enum** value raises
  instead — that is a schema/code mismatch, and naming it beats rendering
  around it (same spirit as `verify_schema`).
- Mutation is not tracked. Assign a new value; mutating a returned `list`,
  `dict` or model in place will not persist.
- `app/persistence/` still must not import a subsystem, so columns whose shape
  is owned by one (`pedagogical_eval`, curriculum `extraction_metadata` and
  `warnings`) stay `JsonObject`/`JsonList` and the subsystem validates them.
- Removed as redundant: `encode_reasons`/`decode_reasons`,
  `encode_changed_fields`/`decode_changed_fields`, `encode_review_ids`/
  `decode_review_ids`, `encode_warnings`/`decode_warnings`, `decode_json_list`,
  `load_content`, and the local `_decode_json`/`_decode_object` helpers in
  `app/validation/shared.py` and `app/evaluation/service.py`.

---

## ADR-027 — The JSON API is the single implementation; pages call it

**Status:** accepted

Every professor capability is exposed as JSON under `/api`, and
`app/web/routes/pages.py` calls those same handler functions rather than
repeating their work. A page's remaining job is to pick a template, hand it
display objects, and turn a raised `AdaptiveTrainerError` into an inline banner
instead of a whole error page.

**Why:** before this change `/api` held one endpoint (`/api/health`) and every
professor action lived only in an HTML form-post route. A JSON client — the
planned React UI, a script, a test — could not upload a book, generate a
question, or record a review at all. Adding a parallel set of API routes would
have created two implementations of each capability that were free to drift; a
validation rule fixed in one would silently not apply to the other.

**How the delegation works**

- Handlers are plain functions. FastAPI resolves `DbSession` when it serves a
  request; the page routes pass a session in directly. There is no internal HTTP
  call, no second transaction and no extra serialisation hop.
- Errors are raised, not returned. The handlers in `app/errors.py` already
  render an `AdaptiveTrainerError` as JSON for `/api` paths and as an HTML error
  page elsewhere, so one raise serves both surfaces.
- Writes commit inside the API handler (or inside the service it calls, for
  preferences) and roll back before re-raising, so a rejected upload leaves no
  partial state on either surface.

**What is deliberately not shared**

Read paths still pass ORM rows and domain objects to Jinja. The templates call
`display_title()` and `citation()`, which the response models do not carry —
mirroring those methods into the JSON contract would put presentation logic in
the API, and rewriting twelve templates to consume response models would be a
large change with no benefit to a JSON client. The duplication left behind is a
single repository call per page.

**Response models are a contract, not a mirror.** `app/web/routes/api/schemas.py`
builds every response through an explicit `from_row` constructor rather than
`from_attributes` over a mapped class, so renaming a column cannot silently
change a shape a client depends on.

**Implications:**

- `app/web/routes/api/` is a package: `schemas.py` plus one module per resource
  (`system`, `books`, `curriculum`, `questions`, `feedback`, `preferences`).
- Tests that need to intercept generation or preference refresh must patch the
  API module that imports the symbol (`app.web.routes.api.questions`,
  `app.web.routes.api.preferences`), not `pages`.
- `POST /api/questions/generate` resolves the approved curriculum id *before*
  constructing `GenerationService`, so a missing curriculum reports that fixable
  problem rather than the LLM-configuration error the constructor would raise
  first.
- `GET /api/config` publishes the enum vocabularies (difficulties, question
  types, rejection reasons with their labels, generators) so a client never
  hard-codes them.
- The API mirrors current capability only. Filtering, batch generation and a
  review queue are not part of it yet.

---

## ADR-028 — CORS is configuration, with an explicit origin allow-list

**Status:** accepted

The application enables `CORSMiddleware` when `CORS_ALLOW_ORIGINS` names at least one origin, so a
React front end served from its own host can call `/api`. The default is the two React development
server origins (`http://localhost:5173`, `http://localhost:3000`); an empty value disables CORS
entirely.

**Why:** the JSON API is meant to serve a browser client (ADR-027), and a browser refuses a
cross-origin call without these headers. The allow-list is configuration rather than a hard-coded
constant because the production origin is not known here, and it is an explicit list rather than
`*` because credentials are allowed — a wildcard origin plus credentials is exactly the
combination that makes any site able to act as a logged-in user.

**Implications:**

- The middleware is added *after* `RequestLoggingMiddleware`, which makes it the outermost layer,
  so an error response still carries the CORS headers. Without that the browser reports a CORS
  failure and the client never sees the status or the JSON error body the API actually returned.
- `CORS_ALLOW_ORIGINS` is read as a comma-separated list, not JSON, so the field is annotated with
  pydantic-settings' `NoDecode` and split by a validator. Trailing slashes are stripped: an origin
  header never carries one and `http://localhost:3000/` would silently never match.
- Methods and request headers are allowed wholesale. Narrowing them buys nothing while every
  professor capability is unauthenticated; when authentication arrives, that is the point to
  revisit both this and `allow_credentials`.

---

## ADR-029 — Judge calibration is measured against the first professor review

**Status:** accepted

`GET /api/calibration/results` reports how often the advisory pedagogical judge (ADR-024) agreed
with the professor, over questions that already carry both a stored evaluation and at least one
review. Both verdicts are projected onto one two-valued label in `app/calibration/`: the judge's
`strong` band means ACCEPT and `adequate` / `weak` / `uncertain` mean NEEDS_REVIEW, while the
professor's `approve` means ACCEPT and `edit` / `reject` mean NEEDS_REVIEW. The endpoint returns
`n`, `judge_accept_count`, `agreement`, `auto_accept_precision` and `unsafe_auto_accept_rate`.

**Why:** the judge is advisory precisely because nobody has measured it. Deciding whether it could
ever pre-screen questions needs a number drawn from data the professor already produced, not a new
labelling exercise — so calibration reads existing rows only, and stores nothing.

**Implications:**

- **The *first* review of a question is the one compared, never the latest.** The judge scored the
  question *as generated*; an edit-then-approve pair means the generated question was not usable,
  so counting the later approval would credit the judge for an outcome the professor's own edit
  produced. Reviews are append-only (ADR-006), which is what makes the first one recoverable.
- **Only `strong` counts as a judge ACCEPT.** Auto-acceptance is the decision being measured, so
  the accept bucket must hold exactly the questions that would have skipped review, not every
  question the judge tolerated.
- **`skipped` and `error` evaluations, and any evaluation not `COMPLETED`, are excluded** rather
  than counted as a wrong answer: the judge made no prediction there. `uncertain` *is* a
  prediction — the judge ran and declined to vouch — so it counts as NEEDS_REVIEW.
- **A stored evaluation that no longer validates is skipped, with a warning logged.** Rubric and
  schema versions change; an old blob is missing data, not evidence of inaccuracy, and failing the
  whole endpoint over one stale row would hide the figure the professor asked for.
- **Every rate is `null` when its denominator is zero.** A fresh database reported as `0.0` reads
  as a judge that agrees with nobody rather than as an absent measurement.
- No new table or column: the query joins `questions.pedagogical_eval_json` to
  `professor_reviews`, eager-loading reviews so the report costs two queries regardless of size.
- Deliberately out of scope for now: breakdowns (by difficulty, question type, generator, rubric
  version), a review queue ordered by judge confidence, and any automation mode that would act on
  these figures. Acting on a rate before it is stable is how an unvalidated judge quietly becomes
  the approver.

---

## ADR-030 — Judge re-runs are bulk, asynchronous and manually collected; every evaluation is kept

**Status:** accepted

The pedagogical judge (ADR-024) ran in exactly one place: once per question, inside
`GenerationService.generate_*`, writing its answer to `questions.pedagogical_eval_json`. There was
no way to re-judge an existing question, and no way to have re-judged one without destroying what
the judge said the first time.

Two things change. **Every evaluation is now retained** in `question_evaluations`, an append-only
history keyed by question and run. And **the whole eligible bank can be re-judged in one go**, as
an asynchronous provider batch job recorded in `judge_batch_runs`.

`questions.pedagogical_eval_json` still holds the *current* evaluation and is still what the
question detail page, the API response and calibration read. History is added beside that column,
not in place of it, so no existing reader changes.

**Why a batch job rather than a loop of synchronous calls:** OpenRouter prices batch requests at
roughly half the synchronous rate and this is the one operation that is inherently bulk. The
trade-off is real and worth naming: on today's seven-question bank the saving is cents and a
synchronous loop would finish in under a minute, so this machinery does not pay for itself yet. It
pays at hundreds of questions per run, which is the scale a re-run exists for — re-judging after a
rubric change, or measuring a new model against the bank.

**Transport (amends ADR-020, does not overturn it).** ADR-020 says Instructor over OpenRouter owns
structured LLM calls. That still holds for every synchronous call. It cannot hold here: a batch job
is submitted now and collected up to 24 hours later, so there is no call for Instructor to wrap.
`app/llm/batch.py` therefore builds request bodies and parses responses by hand.

What does *not* change is the provider: this is still OpenRouter, still the same credential,
still `provider.data_collection: deny` on every request. No direct-provider path was added and
`LLM_PROVIDER` is still `openrouter` or `none`. The batch API simply lives at a different path —
`/api/beta/batches`, not `/api/v1` — and takes its requests inline rather than as an uploaded
JSONL file.

The rubric is **not** forked. `build_judge_prompts` in `app/evaluation/service.py` is the one place
both transports get their system and user prompts, and the response schema is
`JudgeModelResponse.model_json_schema()`. Two copies of the rubric would be free to drift, and a
re-run would then be answering a different question from the one the stored evaluation answered.

**Structured output is requested as `json_object`, not as a strict `json_schema`.** The first real
submission (`batch-1786508645`, six requests) was rejected upstream on every request with
*"'additionalProperties' is required to be supplied and to be false"*: OpenAI's strict mode demands
`additionalProperties: false` on every object and every property listed as required, and a Pydantic
`model_json_schema()` provides neither. Rewriting the schema into one provider's strict dialect is
precisely the wire-format maintenance ADR-020 deleted, so the batch path instead asks for
`{"type": "json_object"}` and states the schema in the system message — byte for byte what
Instructor's `Mode.JSON` does on the synchronous path, which has worked against this model since
ADR-024. An answer that still does not fit the schema costs one question an `error` evaluation at
ingest, not the batch.

**Implications:**

- **`app/llm/batch.py` knows nothing about evaluation.** `app.llm` sits below the subsystems, so it
  takes prompts and a JSON schema as arguments rather than importing `app.evaluation`. It is a
  transport, not a judge.
- **Eligibility is ADR-024's rule, not a new one.** A re-run excludes any question whose
  `validation_report` is absent or not `passed`, because the judge never ran on those. Bulk
  re-running must not quietly extend the judge's reach past deterministic validation.
- **The backfill runs once, before the first submission.** Evaluations recorded before this table
  existed are real judge output; each gets a history row under trigger `generation` with its
  *stored* `created_at` preserved, so history stays ordered by when the judge actually spoke. The
  set is defined as "current evaluation with no history row", which is what makes a second pass a
  no-op without a marker.
- **Collection is manual and idempotent.** There is no scheduler in this repository and this does
  not add one: `POST /api/evaluation/batch-runs/{run_id}/poll` is how results arrive. Re-polling a
  finished run writes nothing and reports `already_recorded`, so the professor need not remember
  whether they already pressed the button. The unique constraint on `(run_id, question_id)` is what
  guarantees that rather than a convention.
- **One malformed line costs one evaluation, not the run.** A result that cannot be parsed becomes
  an `error` evaluation for that question and ingest continues; the transaction commits per result.
- **A failed evaluation is retained in history but does not become the current one.** When an
  `error` or `skipped` evaluation arrives for a question that already carries a `completed` one,
  the history row is written and `pedagogical_eval_json` is left alone. ADR-024 already holds that
  an `error` evaluation cannot fail a question that passed deterministic checks; the same reasoning
  applies to the current pointer, because a re-run that never reached the model says nothing about
  the question. Without this rule the rejected batch above blanked all six stored judgements at
  once — recoverable from history, but every question read as unjudged until it was. The next
  successful re-run still takes over, and a question with nothing better still shows the failure.
- **A run may be several provider jobs.** A bank over the per-job cap is split at submission, and
  the jobs share one run id, so the professor sees one re-run. A run is `completed` only when every
  one of its jobs is — reporting completion while part of the bank went unjudged would be a false
  statement about coverage. A job the provider `cancelled` is recorded as `failed` with the
  cancellation in `error_detail`; there is no separate cancelled state to show.
- **Re-ingesting changes past calibration figures retroactively.** ADR-029 reads
  `questions.pedagogical_eval_json`, so a question whose current evaluation a re-run replaced is
  measured against the *new* one. The reported agreement rate can therefore move without a single
  professor review changing. What is untouched is the review side: reviews are append-only
  (ADR-006) and the first-review rule of ADR-029 still selects the same review it always did. A
  future breakdown by rubric version is the honest fix; pinning calibration to a particular run is
  deliberately not attempted here.
- **The denormalised columns on `question_evaluations` are plain strings.** `eval_status`,
  `advisory_status`, `judge_model` and `rubric_version` are copies of values inside `evaluation`,
  kept so a run can be summarised without decoding every blob. They are not mapped enums because
  their vocabularies belong to `app.evaluation`, which persistence must not import (ADR-026).
- **Stored blobs that no longer validate are still returned.** The history endpoint publishes the
  raw `evaluation` object plus the summary columns rather than a parsed `PedagogicalEvaluation`,
  because a row written under an older rubric is the record this table exists to keep — the same
  policy ADR-029 applies when it skips such a row for measurement.
- **Off by default.** `JUDGE_BATCH_ENABLED` is `false`: a run costs real money and completes over
  hours, so it is opted into rather than discovered.
- **Deliberately out of scope:** scheduling, automatic retry of failed lines, cancelling a
  submitted run, and any use of re-run output to change a question's status. The judge stays
  advisory (ADR-024).

## ADR-031 — The generator classifies its own question, and four judges check it

**Status:** accepted. Supersedes the scoring parts of ADR-024 and the label mapping of ADR-029.

**Context.** The advisory judge produced ten rubric dimensions, each scored 1–5 with a confidence
and a rationale, averaged into one number and bucketed into strong / adequate / weak / uncertain.
Two problems. The scores were not actionable: a professor reading "difficulty_alignment: 3/5"
still had to decide what to do about it, and the number could not be compared with anything the
professor themselves recorded. And the judge and the professor spoke different languages — an
advisory band on one side, approve / edit / reject with structured reasons on the other — so
calibration could only compare them by projecting both onto a two-valued label.

Separately, generation required the professor to pick the topic and subtopic before the model ran.
That put the classification decision on the person with the least information about what the chunk
could actually support, and it made the "is this tagged right?" question unanswerable, because the
tag was the professor's own.

**Decision.**

- **The generator classifies its own question.** The professor selects a chunk, a difficulty and a
  question type. The whole approved taxonomy goes into the prompt and the model returns `topic_id`
  and `subtopic_ids` alongside the question. `QuestionSpec` no longer carries a taxonomy;
  `resolve_claimed_taxonomy` validates the model's claim *after* the call, against the same
  approved tree the professor's ids used to be checked against.
- **A question claims one topic and up to `MAX_CLAIMED_SUBTOPICS` of its subtopics.** Stored in a
  `question_subtopics` join table, replacing the single `questions.subtopic_id` column. A question
  spread across two topics is refused: it would have no single home in the taxonomy, and the
  adaptive engine could not decide whose weakness its score updates. An invalid claim fails the
  generation rather than being repaired — guessing which subtopic the model meant would put an
  invented tag on a question and hide the miss from the very judge that exists to catch it.
  *Superseded by ADR-032: the claim is still never silently repaired, but it is now retried with the
  violation stated, and the question is kept either way rather than the run being discarded.*
- **Four judges, one model call each**, replacing the ten-dimension rubric: `issues` (which known
  problems the question has, drawn from the professor's own `RejectionReason` vocabulary, plus a
  free-text `custom_issue`), `subtopic` (the topic and subtopics it would assign), `difficulty`
  (the level it would assign), and `generatability` (whether the chunk could support the request at
  all). Separate calls because a single reviewer asked four unrelated questions at once lets a
  strong opinion on one bleed into the others, and one malformed answer costs all four.
- **Judges return values, not verdicts.** `passed` is derived by comparing the judge's answer with
  what the generator claimed. Three of the four therefore give the professor something to act on —
  the subtopic to use instead, the difficulty it really is — rather than a score to interpret.
- **The generatability judge never sees the question.** Its subject is the source material, and
  knowing that a question already exists is exactly the bias that would stop it saying "this chunk
  could not support one."
- **The gate is a count.** Four passes → `approved`, none → `reject`, anything between →
  `needs_review`. No fifth model call: a derived gate cannot contradict its own inputs. It is
  `None` unless all four judges answered, because a gate derived from three would read as a verdict
  on four. It remains advisory — the professor's `ReviewDecision` is the authority.
- **A failed judge never withholds a question.** It is recorded as an absent measurement, the
  evaluation lands as `partial`, and the question reaches the review queue with whatever came back.
  This extends ADR-024's rule that an advisory failure is not a verdict.
- **Calibration compares like with like.** `judge_label` reads `gate == approved`; the auto-accept
  figures of ADR-029 are unchanged in meaning. Added beside them: per-metric agreement, and
  confusion tables for subtopic and difficulty. These are possible only because both sides now draw
  from one vocabulary. A professor who did not cite a metric's reason is read as not objecting to
  it — they had the code available and chose not to use it. `generatability` has no professor
  counterpart and is deliberately not given a proxy one.
- **Personalization retrieval re-keys on the chunk.** `retrieve_examples` scored candidates by
  shared subtopic and topic; neither exists before generation now. It scores by source proximity
  instead — same section, then same chapter — and builds its embedding query from the section text,
  citation, type and difficulty.

**Consequences.**

- Evaluation costs four model calls per question instead of one, and four times the latency at
  generation time, since the structured client is synchronous. The batch path submits one job per
  metric (a provider job carries a single response schema) and regroups the four result lines per
  question at ingest; a question is recorded only once all four arrive, or once the run has ended.
- `RUBRIC_VERSION` becomes `question-metrics@1`. Existing evaluations were discarded rather than
  migrated: they were unannotated development data, and the annotation pass that gives the
  calibration figures meaning starts from this rubric.
- `reject` requires all four metrics to fail, so it will be rare in practice. This is intended:
  the professor sees everything and rejects manually; the gate is a hint, not a filter.

---

## ADR-032 — A rejected taxonomy claim is retried and kept, never discarded

**Status:** accepted. Supersedes the invalid-claim bullet of ADR-031.

**Context.** ADR-031 made an invalid taxonomy claim fail the generation. In practice that decision
destroyed work that had already been paid for. `resolve_claimed_taxonomy` raised, the exception
propagated through `GenerationService` to the API route, and the route's `session.rollback()`
discarded the **whole batch** — so one misclassified question threw away every question generated
before it in the same run. Measured on a three-section run: three model calls spent, zero questions
kept.

It also made the generator's accuracy unobservable. The defective question was never stored, so
nothing recorded how often the model tags across two topics, which subtopic pairs it confuses, or
whether a restatement would have fixed it. The one artefact that could answer those questions was
the one artefact being thrown away.

**Decision.**

- **Every generated question is stored, valid claim or not.** A question whose claim was rejected is
  persisted, marked `validation_failed`, and carries the violation and the claim verbatim.
- **A defective question is retried with the defect stated**, up to `MAX_GENERATION_ATTEMPTS` = 3
  generation calls per section: the first attempt plus two corrections. There is a cap because a
  model that has failed the same check twice is not converging, and an uncapped loop would spend a
  professor's budget on one section.
- **Three kinds of defect trigger the retry, and they are treated alike**: a refused taxonomy claim,
  a failed deterministic check from `app.validation`, and a reply that could not be read as a
  question at all. They cost the same thing — a call spent for a question that cannot be used — so
  they earn the same response. Validation therefore runs *inside* the generation loop; the validator
  is injected into the generator rather than imported, so `app.generation` still does not depend on
  `app.validation`.
- **A malformed reply is retried, and recorded.** Observed in production: the provider returned the
  JSON *schema* of the draft instead of an instance, and because `max_retries=0` (ADR-020) that one
  reply ended the whole generation. ADR-020's objection is to bad answers being **silently**
  re-prompted, so the attempt is written onto the question with `malformed` set and no claim, where
  it can be counted. If every attempt is malformed there is no question to store and the provider's
  own error is raised.
- **The correction carries every defect raised so far**, not only the latest attempt's. Showing one
  attempt at a time let the model fix the current fault and reintroduce the previous one: observed
  as verbose options → unbalanced options → verbose options again, three calls ending where they
  started.
- **This is not repair.** ADR-031's reasoning stands: the application never guesses which subtopic
  the model meant. It states what was wrong and asks the model to classify again. The distinction
  matters — a repaired claim would be an invented tag, whereas a retried claim is still the
  generator's own.
- **Attempts are history on one row, not rows of their own.** `questions.generation_attempts_json`
  records each attempt's claim, violations, failed checks and outcome. Separate rows per attempt
  would fill the bank with drafts that every later query — selection, calibration, counts — would
  have to learn to exclude, and the adaptive engine has no use for a question that was never valid.
  `failed_checks` reuses `QuestionCheck` and rides in the existing column, so widening the retry
  needed no migration.
- **An unresolvable id is stored as `NULL` with the claim as evidence.** `questions.topic_id` and
  `question_subtopics.subtopic_id` are foreign keys, so a claim naming an id that does not exist
  cannot be stored as-is. What is storable is decided by existence, not by correctness: a cross-topic
  claim stores verbatim (both rows exist; only the relationship is wrong), an over-long list stores
  verbatim, and a non-existent id is dropped with the raw claim readable in `content_json`.
- **The review queue offers only questions that passed deterministic validation.** A rejected claim
  is not a matter of opinion — the check names the fault exactly — so there is no verdict for a
  professor to add, and professor attention is the scarcest resource in this system. The failed
  questions remain in the bank behind a status filter, which is where the generator's failure modes
  are meant to be read.
- **The judge still never sees them**, by ADR-024's existing rule rather than a new one: a report
  that did not pass yields `skipped_evaluation()`, so a claim-failed question spends no judge calls.
- **Sections commit individually.** An LLM transport error partway through a batch now keeps the
  questions generated before it, for the same reason the claim failure does.

**Consequences.**

- A pathological section can cost three generation calls instead of one. `generation-plan` prices the
  optimistic case; it is not a ceiling, and it does not claim to be.
- Widening the retry to deterministic checks was measured before it was adopted. Of six questions
  that had failed validation in the bank, five failed a deterministic check and had used a single
  generation call, because validation ran after the loop had returned; only the one claim failure
  had been retried. Feeding the failures back took hard `debugging` questions from 2/6 to 6/6
  passing, with the mechanism visible in the drafts: declared `stdout` cases fell from 14 to 1.
- `questions` gains `generation_attempts_json`, so an existing local database must be deleted and
  recreated — ADR-014's `verify_schema()` names the column and the remedy at startup.
- The `validation_failed` count becomes a real signal rather than always zero, and the question bank
  needs a status filter to stay readable. The count stays visible so the filter hides nothing
  silently.
- `claimed_taxonomy_accepted` is a new deterministic check, derived from the stored attempts. It is
  emitted only for questions that have recorded attempts, so every question stored before this
  decision validates exactly as it did. It exists because the pre-existing `approved_taxonomy_ids`
  check structurally cannot see two of the violations: a claim of too many subtopics, and a dropped
  non-existent subtopic id that leaves a valid-looking remainder.

---

## ADR-033 — Personalization is the per-type instruction, not a block appended to the prompt

**Status:** accepted. Supersedes ADR-025.

**Context.** ADR-025 personalized generation by *adding* to the prompt: the shipped one-line type
instruction stayed, and after it came a block of inferred preference statements plus five or six
retrieved review examples. Measured against alternatives, that design never won.

- Its preference rules were not actionable. Of eight learned from 31 reviews, four could not change
  any output — "Avoid poor wording in prompts", "Poor wording is frequently associated with
  incorrect difficulty assessments". The extractor's `MIN_SUPPORTING_REVIEWS = 2` forced every rule
  to generalise across two reviews, and the only thing nine different wording complaints share is
  that wording was bad.
- Duplicates accumulated. `merge_candidates` matched on exact text while the extractor reworded the
  same rule each refresh, so 17 stored preferences were really 8 distinct ones. Three pairs cited
  *identical* evidence. The five injected rules covered two concepts; deduplicated they covered five.
- A fixed, published item-writing checklist in the type slot beat the whole appended block on every
  objective measure, across 10 runs of 4 arms: correct-option-is-longest 0.37 → 0.17, mean option
  length 61 → 48. The learned preferences did not separate from the shipped instruction.
- Retrieved examples were not the problem either, but they were not the solution: an arm with them
  and an arm without were indistinguishable at n=8, and both lost to the checklist.

What did work was replacing the type instruction with one rewritten from the reviews *of that type*.
It captured requirements no generic source could know — "not book-specific", "not trivial recall" —
both traceable to specific review comments, and it produced the best-reviewed arm in a blind hand
review (3 approvals, 0 rejections of 6).

**Decision.**

- **The learned instruction occupies the type-specific slot.** `build_prompt` takes a
  `type_instruction` override; personalization replaces the shipped one-liner rather than arriving
  after the prompt. One row per `QuestionType` on `type_instructions`.
- **The shipped text is kept and the rules are appended to it.** It carries the format contract —
  which fields to fill, how the test harness runs — which is a fact about this application, not a
  preference anyone reviewed.
- **Rules accumulate and are edited; the instruction is never rewritten from scratch.** Measured over
  six rounds of a closed loop: a wholesale rewrite each round drifted from "test a single concept,
  not a collection of unrelated facts" to "avoid broad, unrelated content", and dropped specific
  rules about annotating defects and verifying a single correct option entirely. The rewriter is
  shown the rules it already has and returns them edited.
- **A type with no reviews learns nothing** and keeps the shipped instruction. Rules invented from
  no evidence are not personalization.
- **There is one generator.** With personalization in the type slot, `base` and
  `personalized-context` differ in nothing, so the split, the `generator` request field and the UI
  selector are removed. `GeneratorKind.PERSONALIZED` stays for rows already stamped with it.
- **Retrieval and preference statements are removed**, with them `app.personalization.retrieval`,
  `context`, `embeddings`, `learner`, `service`, `app.domain.preferences`, `preference_statements`,
  `review_embeddings`, and the preferences page and API.

**Consequences.**

- The whole `MAX_PREFS_IN_PROMPT` / `SOFT_PREF_FLOOR` / `merge_candidates` apparatus disappears: with
  one instruction per type there is nothing to rank, threshold or deduplicate.
- Personalization now needs feedback *per type*. Reviews spread across seven types learn more slowly
  than one global profile did — but a global profile that could not change an output was not
  learning at all.
- What the generator is told is now readable in one place, per type, on `/instructions`. The previous
  design could only be reconstructed by tracing which preferences cleared a confidence floor and
  which examples retrieval happened to return.
- Questions generated before this decision keep their `personalization_context`, and the question
  detail page still renders it. Deleting the display would drop evidence attached to real questions.

---

## ADR-034 — Calibration is reported as four cells per question type, and never blames an unaskable judge

**Status:** accepted

ADR-029 put breakdowns "by difficulty, question type, generator, rubric version" out of scope. That
was right while the question was *"can this judge be measured at all?"*. The question is now *"which
judge, for which question type, could be trusted to approve without me?"*, and a pooled two-valued
agreement figure cannot answer it. This decision reverses the question-type and rubric-version half
of that exclusion. Difficulty and generator breakdowns stay out of scope.

Three things are added to `app/calibration/`, all read-only and all derived from pairs that already
existed:

- **`QuadrantCell`** — the judge label crossed with the professor label, as four named values rather
  than `agrees: bool`.
- **`TypeCalibration`** — one `CalibrationReport` per `QuestionType`, over the same arithmetic.
- **`CalibrationPair.missed_metrics` / `.false_alarm_metrics`** — the same comparison
  `MetricAgreement` aggregates, kept per question so the output is a work list and not a rate.

**Why four cells rather than agreement:** the two agreeing cells are not interchangeable and neither
are the two disagreeing ones. `auto_accept_precision` is `confirmed_good / (confirmed_good +
missed)` — the two cells where the judge did not accept are *absent from it entirely*, because
auto-acceptance would never have released those questions. A professor reading one agreement figure
cannot see that, and so cannot tell a judge that is dangerous from one that is merely strict.

**Why per question type:** ADR-033 made the generation instruction per type. There are therefore
seven generators, and a figure pooled across them describes a mixture and authorises none of it.
The type is the unit a professor would ever switch on.

**Implications:**

- **`MISSED` is the only cell that blocks auto-acceptance.** `FALSE_ALARM` costs coverage and
  nothing else — the gate is advisory (ADR-031), so a strict judge delays no question today and
  loses none. The page says so, because a professor who treats the two as equally bad will spend
  their effort on the harmless one.
- **A fault is attributed to a named judge only where the professor's vocabulary can contradict it.**
  `GENERATABILITY` has no entry in `PROFESSOR_OBJECTIONS`, so it never appears in either list, and
  the response publishes `unattributable_metrics` rather than staying silent. A miss no judge can be
  blamed for is reported as unattributed; blaming the nearest judge would send the professor to
  repair a prompt that was not at fault.
- **A type with no measured pair is omitted, not reported as zeroes.** Seven empty rows would bury
  the one or two carrying evidence. Questions predating `question_type` group under `null`, last.
- **Pairs carry `rubric_version`, and a report names every version it drew on.** Repairing a judge
  prompt raises `RUBRIC_VERSION`, after which older pairs measure a judge that no longer runs.
  `build_calibration_pairs(rubric_version=...)` narrows to one; the default stays unfiltered so a
  figure the professor has already read does not silently change, and the mixture is disclosed
  instead.
- **Still no new table, no new column, and no write.** The four cells are a projection of pairs the
  previous report already built. Calibration remains an observation about history (ADR-029).
- **Still no automation.** This decision reports where to work. It does not approve a question, does
  not change a status, and does not turn anything on. Auto-acceptance, audit sampling and any
  revocation mechanism remain undecided and unbuilt.

---

## ADR-035 — One question in three is held back from judge repair

**Status:** accepted

ADR-034 turned calibration into work lists: the questions a named judge got wrong, so its prompt can
be rewritten. That creates a failure mode the report did not have while it was only a rate. If the
professor rewrites a judge prompt against *every* pair, re-runs the judges and reads the agreement
figure, the figure rises whether or not the judge improved — the prompt has been fitted to the
questions it is then scored on.

`app/calibration/` therefore splits the pairs. `is_held_out(question_id)` is
`question_id % HELD_OUT_DIVISOR == 0`, with `HELD_OUT_DIVISOR = 3`. Held-out pairs are excluded from
every repair list on the page and from `TypeCalibration.to_repair()`. They are the only pairs behind
`TypeCalibration.check_report`, which is what a repaired judge is scored on.

**Why keyed on the question id:** the split must not move. A random draw would re-draw itself on
every request, and a recency split would migrate: a judge repaired against one draw would be scored
on a set that had since absorbed the very questions it was tuned on. The id is assigned once and
never changes, so a question is in the same half before and after any repair.

**Why one in three rather than one in two:** the repair list is what the professor reads to find a
pattern, and a pattern is what justifies a prompt change. Halving that list costs more than the
check set gains.

**Implications:**

- **The split governs judge repair only.** `refresh_type_instruction` (ADR-033) is untouched: it
  learns the *generator's* instruction from reviews, and the generator is measured by the
  professor's approval rate, not by the judge. Applying one split to both would hold questions back
  from a learner that has no leakage problem.
- **`report` still covers every pair and is unchanged.** The check figure is published beside it,
  not instead of it. Narrowing the number the professor has already been reading would be a silent
  restatement of the thing they use to decide.
- **The split divides evidence, it does not create it.** Below roughly
  `MIN_INFORMATIVE_SAMPLE * HELD_OUT_DIVISOR` measured questions of one type, there is not enough
  for both a repair list and an honest score, and the page says so rather than printing a rate over
  four questions. This is a real limitation of doing this at current bank sizes, not a detail.
- **The rule is published, not implied.** `held_out_divisor` is in the API response and each pair
  carries `held_out`, so a client states the rule rather than inferring it from which ids happen to
  be flagged.
- **Nothing enforces the discipline.** A professor can open a held-out question from any other page.
  The split removes it from the list they work from and names why; it is not access control, and
  claiming otherwise would overstate what a read-only report can do.

---

## ADR-036 — A training run points at a frozen question set, and coverage is a property of the set

**Status:** accepted

Two things are added, both read-only except for one deliberate write.

**Coverage** (`app/coverage/`) reports a grid of **subtopic × difficulty** over approved questions,
with three states per cell: `EMPTY` (no question), `THIN` (fewer than `MIN_QUESTIONS_PER_CELL`) and
`READY`. **Question sets** (`question_set_versions`, `question_set_members`) freeze the approved
bank under a name, and are never edited afterwards.

**Why coverage is not derivable from the questions:** the adaptive engine selects a **subtopic**
first and a **difficulty** second (`CLAUDE.md`, fixed decisions). A bank in which every question is
excellent is still unusable if one subtopic has no hard question, because that is a request the
engine can make and cannot satisfy. Quality is a property of a question; coverage is a property of
a set, and nothing in the review pipeline measures it.

**Why the grid is walked from the taxonomy:** grouping questions by subtopic produces a report in
which a subtopic nobody has written for simply does not appear — the one row the professor most
needs. So the report iterates the approved curriculum and looks each cell up, defaulting to zero.

**Why a cell needs three questions rather than one:** a served question drops to
`LOWEST_PRIORITY`, so the engine prefers a different question next time. With one question in a
cell there is no different question to prefer and the student meets it again immediately. Three is
the smallest number that avoids that; the professor may demand more.

**Implications:**

- **`EMPTY` and `THIN` are never merged.** `is_servable` is false only while a cell is empty —
  that is the blocking condition. `is_ready` additionally requires no thin cell. Collapsing them
  would make a bank needing one more question look like a bank needing a hundred.
- **Only `APPROVED` questions count.** A question that passed deterministic validation carries no
  professor verdict and must not reach a student.
- **A set is immutable.** There is no update method on `QuestionSetRepository` and no edit route.
  A snapshot that could change answers nothing about what a cohort was served. `question_count` is
  frozen at creation and published beside the live `member_count`, so a set that lost a row to a
  deleted question reads as damaged rather than as a set that was always smaller.
- **An empty set is refused.** Creating one would leave a named, dated, permanently useless row
  that later reads as a real snapshot of an empty moment.
- **The grid cannot be turned into a work queue automatically.** ADR-031 gives the *generator* the
  choice of topic and subtopics; the professor selects a chunk, a difficulty and a type. So a gap
  is filled by generating from a chunk that teaches that subtopic and then checking what the
  generator claimed. The page says this rather than offering a button that cannot exist. Adding a
  requested-subtopic field to the generation request would change ADR-031 and needs its own
  decision — deferred until the gap counts show it is worth it.
- **No training link is built.** `app/adaptive/` is still a boundary with no engine, so there is
  nothing to link to. The page lists that as deferred rather than rendering a link that would not
  work. *Superseded in fact by ADR-041:* the engine exists, and the set list now links to
  `/students#start`, where a run is begun against a chosen set. Nothing else in this entry changes.

---

## ADR-041 — The adaptive engine: partial-credit BKT, a floored weakness, and a per-student reuse filter

**Status:** accepted

`CLAUDE.md` fixes the adaptive mechanism — BKT per topic, weakness per subtopic, weakness-weighted
roulette, mastery-banded difficulty, priority-ordered selection, 0-100 scores. It leaves four rules
undefined that no engine can run without. This entry decides them. Nothing here redesigns the fixed
mechanism; each item fills a hole inside it.

**1. A partial score is a partial observation.**

BKT updates on a binary observation, but a testable question scores `passed_tests / total_tests`.
The engine computes both posteriors — the one for a correct answer and the one for a wrong one —
blends them by `score / 100`, then applies the single learning transition:

```
posterior = f·P(L|correct) + (1 − f)·P(L|wrong)      where f = score / 100
p_known'  = posterior + (1 − posterior)·p_learn
```

**Why not binarize at a threshold:** 10/10 and 6/10 are different evidence about whether a student
knows a skill, and a threshold discards the difference. It also puts a cliff at the pass mark,
where one test case flips the update to its opposite. The blend is continuous, reduces exactly to
standard BKT at 0 and at 100, and needs no threshold constant that nobody can justify.

**Why blend before the transition:** the transition is affine in the posterior, so blending on
either side of it yields the same number. Before it reads as what it is — one blended observation,
followed by one opportunity to learn.

**2. Weakness moves by a fixed rate and never reaches zero.**

`weakness' = weakness + α·((1 − score/100) − weakness)`, with `α = 0.3`, clamped to
`[MIN_SUBTOPIC_WEAKNESS, INITIAL_SUBTOPIC_WEAKNESS]` = `[0.05, 1.0]`.

**Why a floor:** weakness *is* the roulette weight. A subtopic that reached zero would have zero
draw probability and could never be asked again — the exploration half of "exploitation of weak
areas while retaining exploration" would be gone precisely where mastery was demonstrated once and
may have decayed since. At 0.05 against nine untouched subtopics that cell is still drawn about one
time in 180: rare, not impossible.

**Why a moving average rather than a running counter:** it needs one stored float per
(student, subtopic) and weights recent evidence more heavily, which is what "current weakness"
should mean.

**3. A student is not re-served a question they have already answered while an unseen one remains.**

The fixed rule is kept exactly: a served question's priority drops to `LOWEST_PRIORITY`, and
`priority` and `times_used` remain properties of the question, global to the bank. The engine adds
one ordering key *above* them — within a cell, questions this student has not answered sort before
questions they have.

**Why:** the fixed rule was written for one learner. With two, student A answering a question
demotes it for student B, who has never seen it; and B could be handed the same question twice
while an unseen one sat in the same cell at lower priority. Ordering on the student's own history
first fixes both without touching the global column and without disabling reuse: once the cell's
unseen questions are exhausted, seen ones are offered again, which is the reuse the design asks
for.

**4. An empty cell relaxes difficulty before it redraws.**

Roulette can name a subtopic whose (subtopic, difficulty) cell holds no question. The engine tries,
in order: the same subtopic at the nearest other difficulty; then a fresh roulette draw excluding
the exhausted subtopic; then it raises. Every fallback is logged.

**Why difficulty first:** the subtopic is the measured weakness and the thing worth practising.
Difficulty is derived from a coarse three-band mapping and is the cheaper of the two to compromise.
From `medium` the engine steps to `easy` before `hard` — serving a struggling student something too
hard is the worse error.

**Why it is logged and not absorbed:** a bank with gaps will fall back constantly, and an engine
that silently serves the wrong difficulty still looks like an engine that is adapting. The coverage
grid (ADR-036) already names those gaps; the log is what ties one served question to one of them.

**Implications:**

- Per-student state rows are created on first touch, with `p_init` and
  `INITIAL_SUBTOPIC_WEAKNESS`, never seeded in bulk. A subtopic added to the curriculum after a
  student began is therefore ordinary rather than a special case.
- `MIN_SUBTOPIC_WEAKNESS` and the learning rate live in `app/adaptive/state.py`, not
  `app/domain/mastery.py`. The domain module owns the values both loops share and states that the
  updates themselves belong to this package.
- The roulette takes an injected `random.Random` and iterates its weights in sorted id order.
  Selection that depended on dict ordering could not be reproduced from a recorded seed, and the
  tests would be flaky.
- **Student-submitted code is executed by `LocalCodeRunner`, which is a bounded subprocess and not
  a sandbox.** It was built for model-generated code (ADR-023). Arbitrary submitted code is a
  larger threat, and this is acceptable only while the application runs locally for one professor.
  Exposing training to real students over a network requires a real sandbox first; that is a
  separate decision, not an implementation detail of this one.
- **`app/adaptive` depends on `app/validation`, and on nothing else new.** Scoring a submitted
  program means running it, and duplicating a runner would be worse than the dependency. Reading a
  question's stored test cases moved to `app.validation.runner.parse_test_cases` for this reason:
  the parser used to live in `type_checks.py` and would have dragged `app.generation.schemas` into
  the student loop. The engine therefore imports **no** part of `app.generation`, which
  `tests/test_boundaries.py` now enforces alongside the existing ban on `app.web` and the ADR-001
  separation from `app.personalization`.
- **A served question is recorded before it is answered, and re-asking returns it.** `serve_next`
  is idempotent while an attempt is open. Otherwise reloading the page would abandon the open
  attempt and let a student skip any question they disliked — a selection bias the mastery estimate
  cannot see, because the skipped question leaves no trace.
- **Parsons puzzles are scored on block order only.** The stored `indents` are not assessed:
  nothing collects indentation from a student yet, and marking against a field the answer cannot
  express would fail every submission. This becomes a partial score when the ordering UI grows
  indentation.
- **A malformed answer is a wrong answer, not an error.** Typing `banana` where an option index was
  expected scores zero. Only a question that cannot be marked at all — no options, no test cases —
  raises, because that is a defect in an approved question rather than in the answer.
- ADR-036 records that no training link is built because there was no engine to link to. When the
  engine ships the coverage page gains that link; nothing else in ADR-036 changes.

**A served question never carries its own answer.** `ServedQuestionOut` lists every presentable
field explicitly instead of publishing the stored `content`, which holds `correct_option_index`,
`correct_answer`, `expected_output`, `correct_order` and `reference_solution`. A whitelist per type
is the only shape in which adding a question format cannot leak its answer by default. Parsons
blocks are additionally shuffled, seeded on the attempt id — stored order *is* the correct order,
and a reload must not re-pose the puzzle differently.

**Implementation status:** complete and reachable. `app/adaptive/state.py`, `selection.py`,
`scoring.py` and `service.py` over the five student tables in `app/persistence/models.py`;
`app/web/routes/api/students.py` exposes the nine endpoints; `/students`, `/students/{id}` and
`/training/{id}` are the pages. `get_adaptive_engine(session)` returns the real
`AdaptiveTrainingEngine`; `NullAdaptiveEngine` is gone.

Not built, and not pretended to be: item analysis per frozen set, any notion of a cohort, and
indentation in Parsons answers.

One branch is defensive rather than reachable: because the roulette is weighted only over
subtopics the set can answer, and the difficulty fallback tries all three bands, "subtopic
exhausted at every difficulty" cannot occur through the empty-cell route. It survives as insurance
against the two queries drifting apart. What *is* reachable, and tested, is a question whose
subtopic tag outlived the subtopic: there is no topic behind it, so no difficulty can be derived
and the engine drops it.
