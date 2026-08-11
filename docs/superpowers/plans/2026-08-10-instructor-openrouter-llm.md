# Instructor + OpenRouter LLM Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hand-rolled LLM adapters with Instructor over OpenRouter only (default DeepSeek), returning validated Pydantic models from `complete_structured`.

**Architecture:** One `InstructorStructuredClient` wraps `instructor.from_openai(OpenAI → OpenRouter)`. Curriculum passes `response_model=SectionAnalysis|NormalizationResult`. Config supports only `openrouter` | `none`. No Anthropic/OpenAI first-party clients.

**Tech Stack:** Python 3.12, Instructor, OpenAI SDK, Pydantic v2, FastAPI app boundary unchanged outside `app/llm` + curriculum call sites + config/docs/tests.

**Spec:** [`docs/superpowers/specs/2026-08-10-instructor-llm-boundary-design.md`](../specs/2026-08-10-instructor-llm-boundary-design.md)

## Global Constraints

- Structured-output only — no free-text completion API
- Instructor `max_retries=0` — never re-ask on validation failure
- OpenRouter only; models via `LLM_MODEL` (default `deepseek/deepseek-chat`)
- Always send `provider.data_collection: deny`; never set `require_parameters`
- Instructor mode: `instructor.Mode.JSON` (DeepSeek-friendly; avoids strict native json_schema routing issues)
- Error taxonomy: `ConfigurationError` / `LLMRequestError` / `MalformedModelOutputError`
- SDK transport `max_retries=1` only
- Never log or return the API key
- Callers import only `app.llm`, never `instructor` / `openai`
- After meaningful changes: pytest + `ruff check` + `ruff format --check` must pass

## File Structure

| Path | Responsibility |
|------|----------------|
| `app/config.py` | `LLMProvider` = openrouter \| none; DeepSeek defaults |
| `app/llm/client.py` | Single Instructor+OpenRouter client + factory |
| `app/llm/__init__.py` | Narrow public exports |
| `app/curriculum/extraction.py` | Stage A uses new protocol |
| `app/curriculum/normalization.py` | Stage B uses new protocol |
| `pyproject.toml` | `instructor`, `openai`; drop unused direct `httpx` if safe |
| `docs/DECISIONS.md` | ADR-020; supersede ADR-017/019 transport clauses |
| `CLAUDE.md`, `.env.example`, `README.md` | Docs aligned with OpenRouter-only |
| `tests/test_llm_client.py` | Rewrite for new client |
| `tests/test_config.py`, `tests/test_boundaries.py` | Provider enum updates |
| `tests/curriculum_fixtures.py` | `ScriptedClient` new signature |

---

### Task 1: Config — OpenRouter-only provider + DeepSeek defaults

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_boundaries.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: none
- Produces: `LLMProvider.OPENROUTER`, `LLMProvider.NONE` only; defaults `llm_provider=OPENROUTER`, `llm_model="deepseek/deepseek-chat"`

- [ ] **Step 1: Update failing expectations in config/boundary tests**

In `tests/test_config.py`, replace every `LLMProvider.ANTHROPIC` with `LLMProvider.OPENROUTER`, and add:

```python
def test_llm_defaults_are_openrouter_deepseek() -> None:
    settings = _settings()
    assert settings.llm_provider is LLMProvider.OPENROUTER
    assert settings.llm_model == "deepseek/deepseek-chat"


def test_anthropic_and_openai_providers_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(llm_provider="anthropic")
    with pytest.raises(ValidationError):
        _settings(llm_provider="openai")
```

In `tests/test_boundaries.py` `TestLLMBoundary`, change Anthropic settings to OpenRouter + key (same assertions about configured/unconfigured).

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_boundaries.py::TestLLMBoundary -v
```

Expected: FAIL on defaults and/or missing rejection of `anthropic`.

- [ ] **Step 3: Implement config changes**

In `app/config.py`:

```python
class LLMProvider(StrEnum):
    """Supported LLM providers.

    ``NONE`` keeps the UI runnable without credentials (ADR-010).
    ``OPENROUTER`` is the only live transport (ADR-020): DeepSeek and other
    routes are selected with ``LLM_MODEL``, not with extra provider values.
    """

    OPENROUTER = "openrouter"
    NONE = "none"
```

Change Settings defaults:

```python
llm_provider: LLMProvider = LLMProvider.OPENROUTER
llm_model: str = "deepseek/deepseek-chat"
```

Update the `LLMProvider` docstring that currently explains Anthropic/OpenAI/OpenRouter.

In `.env.example`, document only:

```dotenv
# openrouter | none
LLM_PROVIDER=openrouter
# OpenRouter route, e.g. deepseek/deepseek-chat or deepseek/deepseek-r1
LLM_MODEL=deepseek/deepseek-chat
```

- [ ] **Step 4: Re-run tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_boundaries.py::TestLLMBoundary -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py tests/test_boundaries.py .env.example
git commit -m "$(cat <<'EOF'
config: support OpenRouter only with DeepSeek defaults

EOF
)"
```

---

### Task 2: Dependencies — declare Instructor + OpenAI

**Files:**
- Modify: `pyproject.toml`
- Shell: install into `.venv`

**Interfaces:**
- Consumes: none
- Produces: importable `instructor` and `openai` packages for Task 3

- [ ] **Step 1: Update `pyproject.toml` dependencies**

Replace the `httpx` block with:

```toml
    # Structured LLM calls via Instructor over OpenRouter (app/llm/client.py).
    # See docs/DECISIONS.md ADR-020.
    "instructor>=1.7",
    "openai>=1.60",
```

- [ ] **Step 2: Install**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

- [ ] **Step 3: Sanity import**

```powershell
.\.venv\Scripts\python.exe -c "import instructor, openai; print(instructor.__version__, openai.__version__)"
```

Expected: versions print with no ImportError.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
deps: add instructor and openai for OpenRouter structured output

EOF
)"
```

---

### Task 3: Rewrite `app/llm/client.py` + package exports

**Files:**
- Modify: `app/llm/client.py` (replace contents)
- Modify: `app/llm/__init__.py`
- Test: `tests/test_llm_client.py` (replace contents)

**Interfaces:**
- Consumes: `Settings` with OpenRouter-only providers; `require_llm`
- Produces:
  - `StructuredLLMClient.complete_structured(*, system, prompt, response_model: type[T]) -> T`
  - `get_structured_client(settings?) -> StructuredLLMClient`
  - `InstructorStructuredClient` (concrete; not required in `__all__`)

- [ ] **Step 1: Write the new `tests/test_llm_client.py`**

Replace the file. Do **not** mock `httpx`. Patch `InstructorStructuredClient`’s create path by injecting a fake instructor client, or patch `openai.OpenAI` + the wrapped `.chat.completions.create`.

Use a tiny response model:

```python
from pydantic import BaseModel, ConfigDict

class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
```

Required cases:

1. Happy path: create returns `Answer(value="42")` → `complete_structured(..., response_model=Answer)` equals that instance.
2. Validation/parse failure from Instructor → `MalformedModelOutputError`.
3. `openai.OpenAIError` (or subclass with `status_code=503`) → `LLMRequestError`.
4. Client builds with default base URL `https://openrouter.ai/api/v1` when `llm_base_url` is None (assert on the `OpenAI(...)` kwargs or stored client).
5. `extra_body` includes `{"provider": {"data_collection": "deny"}}` and does **not** include `require_parameters`.
6. `description == "openrouter/deepseek/deepseek-chat"` for default openrouter settings.
7. `get_structured_client` with `LLMProvider.NONE` raises `ConfigurationError`.
8. Description never contains the API key string.

Helper settings:

```python
def openrouter_settings(**overrides: Any) -> Settings:
    data = dict(
        _env_file=None,
        llm_provider=LLMProvider.OPENROUTER,
        llm_model="deepseek/deepseek-chat",
        llm_api_key="sk-or-test",
        llm_timeout_seconds=5.0,
        llm_max_output_tokens=256,
    )
    data.update(overrides)
    return Settings(**data)  # type: ignore[call-arg]
```

- [ ] **Step 2: Run new LLM tests — expect fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_client.py -v
```

Expected: FAIL (old API / missing symbols).

- [ ] **Step 3: Implement `app/llm/client.py`**

Replace with a single-client module. Core shape:

```python
"""The structured-output LLM client (Instructor over OpenRouter)."""

from __future__ import annotations

import logging
from typing import TypeVar

import instructor
import openai
from pydantic import BaseModel

from app.config import LLMProvider, Settings, get_settings
from app.errors import ConfigurationError, LLMRequestError, MalformedModelOutputError
from app.llm.availability import require_llm

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 1
ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredLLMClient(Protocol):
    @property
    def description(self) -> str: ...

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[ModelT],
    ) -> ModelT: ...


class InstructorStructuredClient:
    provider_label = "openrouter"

    def __init__(self, settings: Settings) -> None:
        ...
        raw = openai.OpenAI(
            api_key=key.get_secret_value(),
            base_url=settings.llm_base_url or OPENROUTER_BASE_URL,
            timeout=settings.llm_timeout_seconds,
            max_retries=MAX_RETRIES,
            default_headers={
                "HTTP-Referer": "https://localhost/adaptive-trainer",
                "X-Title": "Adaptive Trainer",
            },
        )
        self._client = instructor.from_openai(raw, mode=instructor.Mode.JSON)

    @property
    def description(self) -> str:
        return f"{self.provider_label}/{self._settings.llm_model}"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[ModelT],
    ) -> ModelT:
        try:
            return self._client.chat.completions.create(
                model=self._settings.llm_model,
                max_tokens=self._settings.llm_max_output_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_model=response_model,
                max_retries=0,
                extra_body={"provider": {"data_collection": "deny"}},
            )
        except openai.OpenAIError as exc:
            raise _as_request_error(exc) from exc
        except Exception as exc:
            # Instructor validation / parse failures — never retry-repair here.
            if isinstance(exc, (LLMRequestError, MalformedModelOutputError, ConfigurationError)):
                raise
            raise MalformedModelOutputError(
                "The model did not return a usable structured answer.",
                detail=f"{type(exc).__name__}: {str(exc)[:400]}",
            ) from exc


def get_structured_client(settings: Settings | None = None) -> StructuredLLMClient:
    settings = require_llm(settings or get_settings())
    if settings.llm_provider is LLMProvider.OPENROUTER:
        return InstructorStructuredClient(settings)
    raise ConfigurationError(
        f"No structured client exists for provider {settings.llm_provider.value!r}."
    )
```

Keep `_as_request_error` (OpenRouter/OpenAI errors only). Import `Protocol` from `typing`. Prefer catching Instructor’s documented exception types (`InstructorRetryException`, `ValidationError`, response parsing errors) if imports are stable; map those explicitly to `MalformedModelOutputError` before the broad `Exception` fallback.

Delete `to_strict_schema`, Anthropic client, and OpenAI/OpenRouter subclass hierarchy.

- [ ] **Step 4: Narrow `app/llm/__init__.py`**

```python
from app.llm.availability import describe_availability, require_llm
from app.llm.client import StructuredLLMClient, get_structured_client

__all__ = [
    "StructuredLLMClient",
    "describe_availability",
    "get_structured_client",
    "require_llm",
]
```

Update the package docstring: Instructor + OpenRouter, Pydantic model in / instance out.

- [ ] **Step 5: Run LLM tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_client.py -v
```

Expected: PASS. If Instructor’s create API differs slightly (`client.create` vs `chat.completions.create`), adjust the client to the installed Instructor version and keep tests green.

- [ ] **Step 6: Commit**

```bash
git add app/llm/client.py app/llm/__init__.py tests/test_llm_client.py
git commit -m "$(cat <<'EOF'
llm: use Instructor over OpenRouter for structured output

EOF
)"
```

---

### Task 4: Curriculum callers + ScriptedClient

**Files:**
- Modify: `app/curriculum/extraction.py`
- Modify: `app/curriculum/normalization.py`
- Modify: `tests/curriculum_fixtures.py`

**Interfaces:**
- Consumes: `StructuredLLMClient.complete_structured(*, system, prompt, response_model) -> T`
- Produces: Stage A/B still return `SectionAnalysis` / `NormalizationResult`; fixtures return model instances

- [ ] **Step 1: Update `ScriptedClient.complete_structured`**

```python
def complete_structured(
    self,
    *,
    system: str,
    prompt: str,
    response_model: type[BaseModel],
) -> BaseModel:
    self.prompts.append((response_model.__name__, prompt))
    if response_model is SectionAnalysis or response_model.__name__ == "SectionAnalysis":
        payload = self._analyse(prompt)
    else:
        payload = self._normalize(prompt)
    try:
        return response_model.model_validate(payload)
    except ValidationError as exc:
        raise MalformedModelOutputError(
            "The model did not return a usable structured answer.",
            detail=str(exc)[:400],
        ) from exc
```

Import `SectionAnalysis`, `ValidationError`, `MalformedModelOutputError`, `BaseModel` as needed. Keep `_analyse` / `_normalize` returning dicts.

- [ ] **Step 2: Update extraction + normalization call sites**

`extraction.py`:

```python
analysis = self._client.complete_structured(
    system=SYSTEM_PROMPT.format(max_concepts=MAX_CONCEPTS_PER_SECTION),
    prompt=_build_prompt(section, source, text, truncated),
    response_model=SectionAnalysis,
)
```

Remove unused `json_schema_for` / `parse_structured` imports if unused. `SCHEMA_NAME` / `SCHEMA_DESCRIPTION` can be deleted if nothing else references them.

`normalization.py`: same pattern with `response_model=NormalizationResult`.

- [ ] **Step 3: Run curriculum + LLM tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_client.py tests/test_curriculum_service.py tests/test_curriculum_normalization.py tests/test_web_curriculum.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app/curriculum/extraction.py app/curriculum/normalization.py tests/curriculum_fixtures.py
git commit -m "$(cat <<'EOF'
curriculum: pass Pydantic response models to the LLM client

EOF
)"
```

---

### Task 5: Docs — ADR-020, CLAUDE, README

**Files:**
- Modify: `docs/DECISIONS.md`
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: decisions from the approved spec
- Produces: ADR-020; ADR-017 and ADR-019 marked superseded where they conflict

- [ ] **Step 1: Mark ADR-017 and ADR-019 superseded**

ADR-017 status → `superseded by ADR-020` (structured-output-only intent still historically true; transport clause replaced).

ADR-019 status → `superseded by ADR-020` (OpenRouter+DeepSeek intent kept; multi-provider client hierarchy and `require_parameters` clause replaced).

- [ ] **Step 2: Append ADR-020**

```markdown
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
```

- [ ] **Step 3: Update CLAUDE.md stack row**

```markdown
| LLM access | Instructor + OpenAI SDK → OpenRouter. Structured output only — Pydantic model in, validated instance out. |
```

Also update the module-map blurb for `llm/` if it still says httpx / schema-dict.

- [ ] **Step 4: Update README provider section**

Keep OpenRouter + None only. Remove Anthropic/OpenAI table rows. Soften/remove the claim that requests are pinned with `require_parameters`; point at ADR-020 + `data_collection: deny`.

- [ ] **Step 5: Commit**

```bash
git add docs/DECISIONS.md CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
docs: record ADR-020 Instructor over OpenRouter

EOF
)"
```

---

### Task 6: Full verification

**Files:** none new — verify whole tree

- [ ] **Step 1: Grep for leftovers**

```powershell
.\.venv\Scripts\rg -n "AnthropicStructuredClient|to_strict_schema|LLMProvider\.ANTHROPIC|LLMProvider\.OPENAI|import anthropic|from anthropic|httpx\.post|require_parameters" app tests CLAUDE.md README.md docs/DECISIONS.md pyproject.toml
```

Expected: only historical mentions inside superseded ADR text (if any). No live code references.

- [ ] **Step 2: Full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

Expected: all green. If ruff wants formatting, run `ruff format` on touched files and re-check.

- [ ] **Step 3: Commit any format-only fixes if needed**

```bash
git add -u
git commit -m "$(cat <<'EOF'
chore: format after Instructor LLM migration

EOF
)"
```

Only create this commit if there are changes.

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Instructor structured layer | Task 3 |
| OpenRouter only / DeepSeek default | Tasks 1, 3 |
| Protocol: `response_model` → instance | Tasks 3–4 |
| `max_retries=0`, no repair | Task 3 |
| `data_collection: deny`, no `require_parameters` | Task 3 tests |
| Remove concrete provider exports / `to_strict_schema` | Task 3 |
| Curriculum call sites | Task 4 |
| Deps: instructor + openai, no anthropic | Task 2 |
| ADR-020 + CLAUDE/README/.env.example | Tasks 1, 5 |
| Tests rewritten; fixtures updated | Tasks 1, 3, 4, 6 |

No TBDs. Instructor create method locked to `chat.completions.create` with note to adjust to installed API if needed while keeping the public `StructuredLLMClient` contract fixed.
