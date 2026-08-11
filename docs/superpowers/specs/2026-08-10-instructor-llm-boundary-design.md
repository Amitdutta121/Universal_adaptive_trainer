# Instructor LLM boundary — design

**Date:** 2026-08-10  
**Status:** approved for implementation planning  
**Goal:** Replace hand-rolled structured-output adapters with [Instructor](https://python.useinstructor.com/) over **OpenRouter only**, defaulting to DeepSeek models, so the app owns less wire-format code and changes models via config.

## Context

Today `app/llm/client.py` implements Anthropic, OpenAI, and OpenRouter clients. Docs (`CLAUDE.md`, ADR-017, `pyproject.toml`) still describe a custom `httpx` client and forbid provider SDKs, while runtime code already imports `openai` / `anthropic` and cites a non-existent ADR-020. Tests still mock `httpx.post`.

Local configuration already targets OpenRouter + DeepSeek (`.env`: `LLM_PROVIDER=openrouter`, `LLM_MODEL=deepseek/deepseek-chat`). Direct Anthropic/OpenAI paths add code without serving that use case.

Curriculum is the only live consumer. It calls `StructuredLLMClient.complete_structured(...)` with a JSON Schema dict, then re-validates via `parse_structured`.

## Decision

1. Use **Instructor** as the structured-output layer.
2. Support **OpenRouter only** as the live LLM transport (`LLMProvider.OPENROUTER | NONE`).
3. Choose models with `LLM_MODEL` (default `deepseek/deepseek-chat`; other OpenRouter routes such as `deepseek/deepseek-r1` remain config-only).
4. Keep a thin `app/llm` boundary so callers never import Instructor or the OpenAI SDK.

## Non-goals

- Free-text completion API
- Validation-repair loops (re-asking the model when Pydantic fails)
- Changing curriculum Stage A/B prompts, schemas, or deterministic assembly
- Implementing generation / validation / personalization LLM calls (stubs stay stubs)
- First-class direct Anthropic or OpenAI providers (removed; can return later if needed via OpenRouter routes or a new ADR)
- Setting OpenRouter `require_parameters` (still breaks DeepSeek routing)

## Architecture

```
curriculum (extraction / normalization)
    → app.llm.get_structured_client()
        → InstructorStructuredClient
            → instructor.from_openai(openai.OpenAI → OpenRouter)
```

One client class. Model identity is entirely `LLM_MODEL`.

## Public API

### Protocol

```python
class StructuredLLMClient(Protocol):
    @property
    def description(self) -> str: ...

    def complete_structured[T: BaseModel](
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[T],
    ) -> T: ...
```

Callers pass the Pydantic model class; the client returns a validated instance.

### Factory and package surface

Keep:

- `get_structured_client(settings?) -> StructuredLLMClient`
- `require_llm` / `describe_availability`
- `StructuredLLMClient` protocol

Remove from public `app.llm` exports (and delete implementations):

- `AnthropicStructuredClient`, `OpenAICompatibleClient`, `OpenAIStructuredClient`, `OpenRouterStructuredClient`
- `to_strict_schema`

### Curriculum call sites

`SectionConceptExtractor` and `CrossBookNormalizer` change from schema-dict + `parse_structured` to:

```python
analysis = self._client.complete_structured(
    system=...,
    prompt=...,
    response_model=SectionAnalysis,
)
```

`json_schema_for` may remain as a test/helper if useful; call sites stop using it for LLM calls. `parse_structured` remains available for non-LLM payload validation (tests, fixtures) but is not required on the happy path after an Instructor call.

`ScriptedLLMClient` in `tests/curriculum_fixtures.py` updates to the new signature (dispatch on `response_model`, return instances via `model_validate` on existing dict scripts).

## Instructor + OpenRouter usage

- Build `openai.OpenAI` with:
  - `base_url = settings.llm_base_url or https://openrouter.ai/api/v1`
  - API key from `LLM_API_KEY`
  - timeout / `max_retries=1` (transport only)
  - OpenRouter attribution headers (`HTTP-Referer`, `X-Title`)
- Wrap with `instructor.from_openai(...)`.
- Call structured create with `response_model=...`, `max_retries=0` (no validation repair).
- Pass `extra_body={"provider": {"data_collection": "deny"}}` on every call.
- Do **not** set `require_parameters`.
- Instructor `Mode`: pick the mode that works with DeepSeek via OpenRouter during implementation (likely tools or JSON mode rather than strict native `json_schema` if DeepSeek routes reject it). Confirm with a unit test that constructs the request shape, not a live billed call in CI.

Provenance: `openrouter/{llm_model}` (e.g. `openrouter/deepseek/deepseek-chat`).

## Retries and errors

| Failure | App error | Retry? |
|--------|-----------|--------|
| Provider is `none` or missing key | `ConfigurationError` | n/a |
| Transport / provider refuse (HTTP 408/409/429/5xx, network) | `LLMRequestError` | once via SDK `max_retries=1` |
| HTTP 4xx refuse | `LLMRequestError` | no |
| Unparseable or schema-invalid content | `MalformedModelOutputError` | **no** |

Map Instructor validation / parse failures to `MalformedModelOutputError`. Map OpenAI SDK errors to `LLMRequestError`. Never log the API key.

## Configuration

`LLMProvider` becomes:

- `openrouter`
- `none`

Remove `anthropic` and `openai` enum values. Settings that still set them must fail clearly at settings/client construction (invalid enum / validation error), not silently fall through.

Defaults in `app/config.py` (aligned with `.env.example` / README):

- `llm_provider = openrouter`
- `llm_model = deepseek/deepseek-chat`

Unchanged knobs:

- `LLM_API_KEY`, `LLM_BASE_URL` (optional override/proxy)
- `LLM_TIMEOUT_SECONDS`, `LLM_MAX_OUTPUT_TOKENS`

`llm_configured` remains: provider ≠ `none` **and** key present.

## Dependencies

Add to `pyproject.toml`:

- `instructor` (current stable)
- `openai`

Do **not** add `anthropic`.

Remove direct `httpx` **only if** nothing under `app/` still imports it after the migration (transitive via `openai` is fine).

Update the dependency comment to point at ADR-020.

## Documentation

1. Add **ADR-020** — Instructor + OpenRouter-only structured client; supersedes ADR-017’s httpx/no-SDK transport clause and narrows ADR-019’s multi-provider client surface to OpenRouter as the sole live provider. Preserve: structured-output-only, error taxonomy, no validation-repair, `data_collection: deny`, DeepSeek as default model via config.
2. Mark ADR-017 transport choice superseded; mark ADR-019’s “three live providers share one OpenAI-compatible client hierarchy” as superseded where it conflicts (OpenRouter remains first-class; direct Anthropic/OpenAI removed).
3. Update `CLAUDE.md` technology stack row for LLM access.
4. Update `.env.example`, `README.md` provider table: OpenRouter (+ `none`) only; DeepSeek model examples.
5. Align module docstrings / `pyproject.toml` comments.

## Testing

Rewrite `tests/test_llm_client.py` for the single OpenRouter+Instructor client:

- Do not mock `httpx.post`.
- Stub the Instructor/OpenAI create path as needed.
- Cover: happy path returns a Pydantic instance; invalid/unusable content → `MalformedModelOutputError`; SDK error → `LLMRequestError`; default OpenRouter base URL; `data_collection: deny`; base URL override; provenance `openrouter/deepseek/deepseek-chat`; `NONE` → `ConfigurationError`; description hides credentials.
- Drop Anthropic/OpenAI client tests and `to_strict_schema` tests.
- Update `tests/test_config.py` / `tests/test_boundaries.py` that construct `LLMProvider.ANTHROPIC` to use `OPENROUTER` (or `NONE`) instead.
- Update curriculum fixtures/fakes to the new protocol.

Verification after implementation (must actually run):

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

## File change map

| Path | Change |
|------|--------|
| `app/llm/client.py` | Single Instructor+OpenRouter client; delete Anthropic/OpenAI adapters |
| `app/llm/__init__.py` | Narrow exports; update package docstring |
| `app/config.py` | `LLMProvider` = `openrouter` \| `none`; defaults DeepSeek |
| `app/curriculum/extraction.py` | New `complete_structured` call shape |
| `app/curriculum/normalization.py` | Same |
| `pyproject.toml` | Declare `instructor`, `openai`; drop unused direct deps/comments |
| `docs/DECISIONS.md` | ADR-020; supersede conflicting ADR-017/019 transport clauses |
| `CLAUDE.md` | Stack table |
| `.env.example`, `README.md` | OpenRouter-only docs |
| `tests/test_llm_client.py` | Rewrite |
| `tests/test_config.py`, `tests/test_boundaries.py` | Provider enum updates |
| `tests/curriculum_fixtures.py` | `ScriptedLLMClient` signature |

## Success criteria

- No Anthropic SDK usage or Anthropic/OpenAI-specific request builders in `app/`.
- Live LLM path is OpenRouter + Instructor only; model changes are `LLM_MODEL` only.
- Default documented configuration is `openrouter` + `deepseek/deepseek-chat`.
- Curriculum Stage A soft-fail on `MalformedModelOutputError` still works; `LLMRequestError` still aborts.
- Docs, deps, and tests agree with the runtime code.
- Full pytest + ruff suite green.
