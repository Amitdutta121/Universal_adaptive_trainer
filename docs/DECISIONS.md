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
`deterministic=True`, and an empty report does **not** pass. Deterministic execution checks need a
sandbox design before they can be implemented; until then validation raises rather than returning
a vacuously passing report.

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
- Automatic validation, professor review writes, personalization, and database migrations remain
  deferred. Existing local SQLite databases that predate question-generation columns must be
  recreated until migrations are introduced (ADR-008 and ADR-014).
