"""Application configuration.

All runtime configuration is read from environment variables (optionally via a
local ``.env`` file). Nothing else in the codebase should read ``os.environ``
directly -- import :func:`get_settings` instead so that tests can override
configuration in one place.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: The ``AUTH_SECRET_KEY`` default. Safe on one developer's machine only, so a
#: production run refuses to start with it (``Settings._require_real_auth_secret``).
DEV_AUTH_SECRET_KEY = "dev-only-insecure-secret-change-me"
#: Shortest ``AUTH_SECRET_KEY`` a production run accepts -- 32 characters is
#: what ``secrets.token_urlsafe(24)`` produces.
MIN_PRODUCTION_SECRET_LENGTH = 32


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LLMProvider(StrEnum):
    """Supported LLM providers.

    ``NONE`` keeps the UI runnable without credentials (ADR-010).
    ``OPENROUTER`` is the only live transport (ADR-020): DeepSeek and other
    routes are selected with ``LLM_MODEL``, not with extra provider values.
    """

    OPENROUTER = "openrouter"
    NONE = "none"


class Settings(BaseSettings):
    """Typed application settings.

    Values come from (in order of precedence) constructor arguments, process
    environment variables, then a ``.env`` file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application / development settings ---------------------------------
    app_name: str = "Adaptive Trainer"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"

    # -- Persistence --------------------------------------------------------
    database_url: str = "sqlite:///./data/adaptive_trainer.db"
    database_echo: bool = False

    # -- LLM provider -------------------------------------------------------
    llm_provider: LLMProvider = LLMProvider.OPENROUTER
    llm_model: str = "deepseek/deepseek-chat"
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_output_tokens: int = Field(default=4096, gt=0)
    #: Sent only to reasoning models (gpt-5 family, o-series), which spend part of their
    #: output budget thinking. ``low`` keeps generation and judging fast and cheap.
    llm_reasoning_effort: Literal["minimal", "low", "medium", "high"] = "low"
    embedding_model: str = "openai/text-embedding-3-small"
    validation_timeout_seconds: float = Field(default=2.0, gt=0)
    # Where student and generated code runs (C6, ADR-055). ``local`` is a plain subprocess and
    # NOT a sandbox -- fine for one researcher's machine, not for real students. ``piston`` sends
    # every run to the Piston sandbox at ``piston_url`` (see docker/piston/README.md).
    executor: Literal["local", "piston"] = "local"
    piston_url: str = "http://127.0.0.1:2000"

    # -- Bulk judge re-run (ADR-030) ----------------------------------------
    # OpenRouter's batch jobs are asynchronous and live under /api/beta, not
    # under the /api/v1 path the synchronous client uses. Off by default: a run
    # costs real money and completes over hours, so it is opted into.
    judge_batch_enabled: bool = False
    judge_batch_base_url: str = "https://openrouter.ai/api/beta"
    #: Falls back to ``llm_model`` so the re-run judges with the same route that
    #: generation used unless a cheaper one is named deliberately.
    judge_batch_model: str | None = None
    #: Falls back to ``llm_api_key``. Separate so a batch-scoped key can be used.
    judge_batch_api_key: SecretStr | None = None
    #: Requests per provider job. A larger bank is split across several jobs
    #: under one run id rather than submitted as one oversized body.
    judge_batch_max_requests_per_job: int = Field(default=200, gt=0)
    judge_batch_timeout_seconds: float = Field(default=120.0, gt=0)

    #: Sampling temperature for judge calls. Zero by default: a judge is a
    #: measuring instrument, and the OpenAI default of 1.0 was measured here to
    #: flip 20% of verdicts between runs of the *same* prompt on the *same*
    #: question -- enough to manufacture the disagreements that trigger a repair.
    judge_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # Trust is learned only from explicit professor observations, never approvals
    # performed by the router. A rolling window makes recent errors visible.
    judge_trust_min_observations: int = Field(default=20, ge=20)
    judge_trust_min_agreement: float = Field(default=0.9, ge=0.9, le=1.0)
    #: Share of the window's questions the professor approved unedited. Judges can agree on
    #: difficulty and topic while the questions are still not worth keeping.
    judge_trust_min_acceptance: float = Field(default=0.9, ge=0.9, le=1.0)
    judge_trust_window: int = Field(default=20, ge=20)

    #: Which of the four metric judges run on newly generated questions
    #: (docs/QUESTION_SETUP_PLAN.md). ``JudgeMetricId`` itself is not shrunk -- stored rows and
    #: calibration depend on it -- and calibration already skips a metric a judge did not
    #: answer. Values are ``JudgeMetricId`` values; ``JUDGE_METRICS_ENABLED=difficulty,subtopic``
    #: in a ``.env`` file. Not yet read by the judge service (Phase 1, agent C).
    judge_metrics_enabled: Annotated[list[str], NoDecode] = ["difficulty", "subtopic"]
    #: Models that answer each round multiple-choice / true-false question without its key
    #: (app/generation/solve.py). Any disagreement is retried, then flagged. Empty turns it
    #: off: ``BLIND_SOLVE_MODELS=`` in a ``.env`` file.
    blind_solve_models: Annotated[list[str], NoDecode] = [
        "anthropic/claude-haiku-4.5",
        "deepseek/deepseek-chat",
    ]

    # -- Learning loops (ADR-042) -------------------------------------------
    # Both loops can be frozen independently. A judge cannot be measured while
    # the generator is also adapting: the question population moves under the
    # measurement, and no agreement change can be attributed to either.
    judge_learning_enabled: bool = True
    generator_learning_enabled: bool = True

    #: Disagreements naming one judge before its prompt may be rewritten.
    #: Rewriting on a single case was measured to produce a rule about that one
    #: question ("do not report technically_incorrect if swapping logic in an
    #: operation is correct"), which is overfitting, not learning.
    judge_repair_min_disagreements: int = Field(default=5, gt=0)

    #: Score a rewritten judge before adopting it, and keep it only if it does
    #: not lose. Every published prompt optimiser does this -- GEPA's minibatch
    #: acceptance, MIPRO's validation search, OPRO's scored meta-prompt. Applying
    #: an unscored candidate is mutation without selection, which is drift.
    judge_repair_gate_enabled: bool = True
    #: Held-out pairs a candidate is scored on. Each costs one judge call per
    #: prompt, so this is the cost dial for the gate.
    judge_repair_scoring_pairs: int = Field(default=8, gt=0)
    #: Below this many held-out pairs the gate cannot tell a real improvement
    #: from judge noise, so the repair is refused rather than applied blind.
    judge_repair_min_scoring_pairs: int = Field(default=5, gt=0)

    # -- Book ingestion -----------------------------------------------------
    book_upload_dir: Path = PROJECT_ROOT / "data" / "books"
    max_book_upload_mb: int = Field(default=100, gt=0)

    # -- Auth (app/auth/) -----------------------------------------------------
    #: Signs the email-verification and password-reset links (ADR-061).
    #: Generate a real value for anything beyond a single developer's machine;
    #: ENVIRONMENT=production refuses to start without one.
    auth_secret_key: SecretStr = SecretStr(DEV_AUTH_SECRET_KEY)
    #: The one seeded professor account (app/auth/seed.py). Only created when
    #: ENVIRONMENT=development -- a production run never seeds a credential.
    dev_user_email: str = "dev@local.test"
    dev_user_password: SecretStr = SecretStr("devpassword123")

    # -- Account email (app/auth/email.py, ADR-061) ---------------------------
    #: Off for now: a registered account is verified on creation and no verification link is
    #: sent, and routes that spend LLM credit do not check verification. Set it true to make a
    #: new account confirm its email first (ADR-061's original behaviour).
    require_email_verification: bool = False
    #: Where the Studio is served; verification and reset links point here. Required in
    #: production, where a localhost link in a real inbox would be useless.
    public_app_url: str | None = None
    #: ``console`` logs each email (with its link) instead of sending it; ``smtp`` sends it.
    #: Unset means ``console`` in development and test and ``smtp`` in production, so a
    #: deployment never writes password-reset links into its logs by default.
    email_backend: Literal["console", "smtp"] | None = None
    smtp_host: str | None = None
    #: 587 is the submission port; the connection is upgraded with STARTTLS before login.
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    #: The From address, e.g. ``Adaptive Trainer <no-reply@example.edu>``.
    smtp_from: str | None = None

    # -- Browser clients ----------------------------------------------------
    # Origins allowed to call /api from a browser. Defaults cover the Vite and
    # create-react-app development servers; set explicitly in production.
    # ``NoDecode`` keeps pydantic-settings from JSON-decoding the raw value so
    # that a plain comma-separated list works in a ``.env`` file.
    cors_allow_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator(
        "llm_api_key",
        "llm_base_url",
        "judge_batch_api_key",
        "judge_batch_model",
        "public_app_url",
        "email_backend",
        "smtp_host",
        "smtp_user",
        "smtp_password",
        "smtp_from",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        """Treat ``KEY=`` in a ``.env`` file as "not configured"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("judge_metrics_enabled", mode="before")
    @classmethod
    def _split_metrics(cls, value: object) -> object:
        """Accept ``JUDGE_METRICS_ENABLED=difficulty,subtopic``; reject unknown metric ids."""
        from app.domain.enums import JudgeMetricId

        if isinstance(value, str):
            value = [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            known = {metric.value for metric in JudgeMetricId}
            unknown = [item for item in value if str(item) not in known]
            if unknown:
                raise ValueError(f"unknown judge metric(s): {', '.join(map(str, unknown))}")
        return value

    @field_validator("blind_solve_models", mode="before")
    @classmethod
    def _split_models(cls, value: object) -> object:
        """Accept ``BLIND_SOLVE_MODELS=a/b,c/d``; an empty value turns blind solve off."""
        if isinstance(value, str):
            return [model.strip() for model in value.split(",") if model.strip()]
        return value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept ``CORS_ALLOW_ORIGINS=http://a,http://b`` from the environment."""
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_real_auth_secret(self) -> Self:
        """Fail at startup rather than sign tokens with a public, known secret."""
        if self.environment is not Environment.PRODUCTION:
            return self
        secret = self.auth_secret_key.get_secret_value()
        if secret == DEV_AUTH_SECRET_KEY or len(secret) < MIN_PRODUCTION_SECRET_LENGTH:
            raise ValueError(
                "ENVIRONMENT=production needs AUTH_SECRET_KEY set to a random value of at "
                f"least {MIN_PRODUCTION_SECRET_LENGTH} characters, e.g. "
                '`python -c "import secrets; print(secrets.token_urlsafe(32))"`.'
            )
        return self

    @model_validator(mode="after")
    def _require_production_email(self) -> Self:
        """Fail at startup rather than send links nobody can open, or no email at all."""
        if self.environment is not Environment.PRODUCTION:
            return self
        if self.public_app_url is None:
            raise ValueError(
                "ENVIRONMENT=production needs PUBLIC_APP_URL, the address the Studio is served "
                "at (e.g. https://trainer.example.edu); email links are built from it."
            )
        if self.effective_email_backend == "smtp":
            missing = [
                name.upper()
                for name in ("smtp_host", "smtp_user", "smtp_password", "smtp_from")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    f"ENVIRONMENT=production sends email over SMTP and needs {', '.join(missing)}"
                    " (or EMAIL_BACKEND=console to only log each email)."
                )
        return self

    @property
    def effective_email_backend(self) -> Literal["console", "smtp"]:
        """The configured email backend, defaulting by environment."""
        if self.email_backend is not None:
            return self.email_backend
        return "smtp" if self.environment is Environment.PRODUCTION else "console"

    @property
    def app_url(self) -> str:
        """Base URL for links in emails, without a trailing slash."""
        return (self.public_app_url or "http://localhost:3000").rstrip("/")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def llm_configured(self) -> bool:
        """True when an LLM provider *and* credentials are both available.

        LLM-backed features (question generation and later LLM features) must
        check this and degrade gracefully instead of raising at import time.
        """
        return self.llm_provider is not LLMProvider.NONE and self.llm_api_key is not None

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    @property
    def judge_batch_route(self) -> str:
        """The model the bulk judge re-run submits under."""
        return self.judge_batch_model or self.llm_model

    @property
    def judge_batch_credential(self) -> SecretStr | None:
        """The key the bulk judge re-run authenticates with, or ``None``."""
        return self.judge_batch_api_key or self.llm_api_key

    def describe_judge_batch(self) -> str:
        """Human-readable batch re-run status. Never leaks the credential."""
        if not self.judge_batch_enabled:
            return "disabled (JUDGE_BATCH_ENABLED=false)"
        if self.judge_batch_credential is None:
            return f"{self.judge_batch_route} (no API key configured)"
        return self.judge_batch_route

    def describe_llm(self) -> str:
        """Human-readable LLM status for the UI. Never leaks the credential."""
        if self.llm_provider is LLMProvider.NONE:
            return "disabled (LLM_PROVIDER=none)"
        if self.llm_api_key is None:
            return f"{self.llm_provider.value}/{self.llm_model} (no API key configured)"
        return f"{self.llm_provider.value}/{self.llm_model}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that configuration is parsed once. Tests that need different
    values should call ``get_settings.cache_clear()`` or construct ``Settings``
    directly.
    """
    return Settings()
