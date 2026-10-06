"""Public professor registration, email verification and password reset (ADR-061, M3).

Runs the real app with no auth override, like ``tests/test_auth.py``. Email goes to the
``console`` backend, so each test reads the link out of the ``app.auth.email`` log exactly as a
developer would from the backend's output.
"""

from __future__ import annotations

import logging
import re
import smtplib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from fastapi_users.jwt import decode_jwt, generate_jwt
from fastapi_users.manager import RESET_PASSWORD_TOKEN_AUDIENCE, VERIFY_USER_TOKEN_AUDIENCE
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.email import ConsoleEmailSender, SmtpEmailSender, get_email_sender
from app.config import Environment, Settings, get_settings
from app.persistence.models import UserRow
from app.web.routes.api.coverage import get_generation_client
from app.web.routes.api.curriculum import get_draft_client
from app.web.routes.api.deps import COURSE_HEADER
from app.web.routes.api.retrieval import get_query_embedder
from app.web.routes.api.setup import get_setup_client

EMAIL = "new.professor@example.edu"
PASSWORD = "a-long-enough-passphrase"
NEW_PASSWORD = "an-even-longer-passphrase"

#: Every route that spends LLM or embedder credit, and so needs a verified email. Kept in sync
#: with the app by :func:`test_the_llm_route_list_matches_the_app`.
LLM_ROUTES: dict[tuple[str, str], str] = {
    ("POST", "/api/questions/generate"): "/api/questions/generate",
    ("POST", "/api/questions/{question_id}/regenerate"): "/api/questions/999999/regenerate",
    ("POST", "/api/questions/generate-batch"): "/api/questions/generate-batch",
    ("POST", "/api/questions/{question_id}/review"): "/api/questions/999999/review",
    ("POST", "/api/coverage/generation-runs"): "/api/coverage/generation-runs",
    ("GET", "/api/retrieval/sections"): "/api/retrieval/sections",
    ("POST", "/api/curriculum/drafts"): "/api/curriculum/drafts",
    ("POST", "/api/setup/suggest"): "/api/setup/suggest",
    ("POST", "/api/setup"): "/api/setup",
    ("POST", "/api/rounds"): "/api/rounds",
    ("POST", "/api/evaluation/batch-runs"): "/api/evaluation/batch-runs",
    ("POST", "/api/evaluation/batch-runs/{run_id}/poll"): "/api/evaluation/batch-runs/x/poll",
    ("POST", "/api/instructions/{question_type}/refresh"): "/api/instructions/true_false/refresh",
    ("POST", "/api/judge-prompts/{metric}/refresh"): "/api/judge-prompts/issues/refresh",
}

#: Read-only Studio calls an unverified account must still be able to make.
READ_ONLY = [
    "/api/courses/overview",
    "/api/books",
    "/api/curriculum/versions",
    "/api/questions",
    "/api/questions/review-queue",
    "/api/question-sets",
    "/api/students",
    "/api/coverage",
    "/api/judge-prompts",
    "/api/instructions",
    "/api/counts",
]


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    from app.main import create_app

    application = create_app(settings)
    # The suite has no LLM provider; a verified call may reach these, an unverified one never.
    application.dependency_overrides[get_generation_client] = lambda: None
    application.dependency_overrides[get_draft_client] = lambda: None
    application.dependency_overrides[get_setup_client] = lambda: None
    application.dependency_overrides[get_query_embedder] = object
    with TestClient(application):  # runs the lifespan: migrations, schema check
        yield application


@pytest.fixture
def browser(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def email_log(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """The console email backend's output. ``app`` loggers do not propagate to the root."""
    logger = logging.getLogger("app.auth.email")
    logger.addHandler(caplog.handler)
    previous = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(previous)


def _link_token(log: pytest.LogCaptureFixture, page: str) -> str:
    tokens = re.findall(rf"http://localhost:3000/{page}\?token=([\w.\-]+)", log.text)
    assert tokens, f"no /{page} link was logged: {log.text!r}"
    return tokens[-1]


def _register(client: TestClient, email: str = EMAIL, **extra: Any) -> Any:
    return client.post("/api/auth/register", json={"email": email, "password": PASSWORD, **extra})


def _login(client: TestClient, password: str = PASSWORD) -> int:
    response = client.post("/api/auth/login", data={"username": EMAIL, "password": password})
    return response.status_code


def _expired(token: str, secret: str, audience: str) -> str:
    claims = decode_jwt(token, secret, [audience])
    claims.pop("exp")
    return generate_jwt(claims, secret, lifetime_seconds=-60)


# ------------------------------------------------------------------ 1. registration


def test_register_creates_an_unverified_account_and_logs_a_verify_link(
    browser: TestClient, email_log: pytest.LogCaptureFixture
) -> None:
    response = _register(browser)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == EMAIL
    assert (body["is_active"], body["is_verified"], body["is_superuser"]) == (True, False, False)
    assert "EMAIL_BACKEND=console" in email_log.text
    assert EMAIL in email_log.text
    assert _link_token(email_log, "verify")


def test_a_duplicate_email_is_a_400(browser: TestClient) -> None:
    assert _register(browser).status_code == 201

    again = _register(browser)

    assert again.status_code == 400
    assert again.json()["error"] == {
        "code": "register_user_already_exists",
        "message": "An account with this email already exists.",
    }


def test_a_short_password_is_a_400_with_the_reason(browser: TestClient) -> None:
    response = browser.post("/api/auth/register", json={"email": EMAIL, "password": "short"})

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "register_invalid_password",
        "message": "Password must be at least 12 characters.",
    }


def test_privilege_flags_in_the_body_have_no_effect(browser: TestClient, session: Session) -> None:
    response = _register(browser, is_superuser=True, is_verified=True, is_active=False)

    assert response.status_code == 201, response.text
    row = session.scalars(select(UserRow).where(UserRow.email == EMAIL)).one()
    assert (row.is_active, row.is_verified, row.is_superuser) == (True, False, False)
    assert _login(browser) == 204


# ------------------------------------------------------------------ 2. verify and reset


def test_a_good_verify_token_verifies_the_account(
    browser: TestClient, email_log: pytest.LogCaptureFixture
) -> None:
    _register(browser)
    assert _login(browser) == 204  # an unverified account can log in
    assert browser.get("/api/auth/me").json()["is_verified"] is False

    verified = browser.post("/api/auth/verify", json={"token": _link_token(email_log, "verify")})

    assert verified.status_code == 200, verified.text
    assert verified.json()["is_verified"] is True
    assert browser.get("/api/auth/me").json()["is_verified"] is True


def test_a_bad_or_expired_verify_token_is_a_400(
    browser: TestClient, settings: Settings, email_log: pytest.LogCaptureFixture
) -> None:
    _register(browser)
    good = _link_token(email_log, "verify")
    secret = settings.auth_secret_key.get_secret_value()

    for token in ["not-a-token", _expired(good, secret, VERIFY_USER_TOKEN_AUDIENCE)]:
        response = browser.post("/api/auth/verify", json={"token": token})
        assert response.status_code == 400
        assert response.json()["error"] == {
            "code": "verify_user_bad_token",
            "message": "This verification link is invalid or has expired.",
        }


def test_resend_sends_a_new_verify_link(
    browser: TestClient, email_log: pytest.LogCaptureFixture
) -> None:
    _register(browser)
    email_log.clear()

    response = browser.post("/api/auth/request-verify-token", json={"email": EMAIL})

    assert response.status_code == 202
    assert _link_token(email_log, "verify")


def test_forgot_password_is_202_for_known_and_unknown_emails_alike(
    browser: TestClient, email_log: pytest.LogCaptureFixture
) -> None:
    _register(browser)
    email_log.clear()

    unknown = browser.post("/api/auth/forgot-password", json={"email": "nobody@example.edu"})
    assert unknown.status_code == 202
    assert "reset-password" not in email_log.text

    known = browser.post("/api/auth/forgot-password", json={"email": EMAIL})
    assert known.status_code == 202
    assert known.json() == unknown.json()
    assert _link_token(email_log, "reset-password")


def test_reset_changes_the_password(
    browser: TestClient, email_log: pytest.LogCaptureFixture
) -> None:
    _register(browser)
    assert _login(browser) == 204  # a session that must not outlive the old password
    browser.post("/api/auth/forgot-password", json={"email": EMAIL})
    token = _link_token(email_log, "reset-password")

    reset = browser.post(
        "/api/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
    )

    assert reset.status_code == 200, reset.text
    assert browser.get("/api/auth/me").status_code == 401
    assert _login(browser, PASSWORD) == 400
    assert _login(browser, NEW_PASSWORD) == 204
    # The token is tied to the old password, so it cannot be used twice.
    again = browser.post("/api/auth/reset-password", json={"token": token, "password": PASSWORD})
    assert again.status_code == 400


def test_reset_refuses_bad_tokens_and_short_passwords(
    browser: TestClient, settings: Settings, email_log: pytest.LogCaptureFixture
) -> None:
    _register(browser)
    browser.post("/api/auth/forgot-password", json={"email": EMAIL})
    good = _link_token(email_log, "reset-password")
    secret = settings.auth_secret_key.get_secret_value()

    for token in ["not-a-token", _expired(good, secret, RESET_PASSWORD_TOKEN_AUDIENCE)]:
        response = browser.post(
            "/api/auth/reset-password", json={"token": token, "password": NEW_PASSWORD}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "reset_password_bad_token"

    short = browser.post("/api/auth/reset-password", json={"token": good, "password": "short"})
    assert short.status_code == 400
    assert short.json()["error"] == {
        "code": "reset_password_invalid_password",
        "message": "Password must be at least 12 characters.",
    }
    assert _login(browser, PASSWORD) == 204


# ------------------------------------------------------------------ 3. the verified-email gate


def _verified_only_routes(app: FastAPI) -> set[tuple[str, str]]:
    found = set()
    for context in iter_route_contexts(app.routes):
        if not isinstance(context.original_route, APIRoute):
            continue
        stack = list(context.dependant.dependencies)
        while stack:
            dependency = stack.pop()
            if getattr(dependency.call, "__name__", "") == "current_verified_user":
                found.update((method, context.path) for method in context.methods)
                break
            stack.extend(dependency.dependencies)
    return found


def test_the_llm_route_list_matches_the_app(app: FastAPI) -> None:
    """A route that starts requiring a verified email, or stops, must update the list."""
    assert _verified_only_routes(app) == set(LLM_ROUTES)


def test_an_unverified_account_is_refused_llm_routes_until_it_verifies(
    browser: TestClient, email_log: pytest.LogCaptureFixture
) -> None:
    _register(browser)
    assert _login(browser) == 204
    course = browser.post("/api/courses", json={"name": "Physics 101"})
    assert course.status_code == 201, course.text
    headers = {COURSE_HEADER: str(course.json()["id"])}

    for (method, _), url in LLM_ROUTES.items():
        response = browser.request(method, url, headers=headers)
        assert response.status_code == 403, (url, response.text)
        error = response.json()["error"]
        assert error["code"] == "email_not_verified"
        assert error["message"] == "Verify your email address to use AI features."
        assert EMAIL in error["detail"]

    assert browser.get("/api/courses").status_code == 200
    for url in READ_ONLY:
        response = browser.get(url, headers=headers)
        assert response.status_code == 200, (url, response.text)

    browser.post("/api/auth/verify", json={"token": _link_token(email_log, "verify")})

    for (method, _), url in LLM_ROUTES.items():
        response = browser.request(method, url, headers=headers)
        # Past the auth check: what remains is the request itself (no body, no such row).
        assert response.status_code not in {401, 403}, (url, response.text)


# ------------------------------------------------------------------ 5. verification off


@pytest.fixture
def verification_off(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The shipped default: ``REQUIRE_EMAIL_VERIFICATION`` unset."""
    monkeypatch.delenv("REQUIRE_EMAIL_VERIFICATION")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_verification_is_off_by_default() -> None:
    assert Settings.model_fields["require_email_verification"].default is False


def test_with_verification_off_a_new_account_is_verified_and_sent_no_link(
    verification_off: None, browser: TestClient, email_log: pytest.LogCaptureFixture
) -> None:
    response = _register(browser)

    assert response.status_code == 201, response.text
    assert response.json()["is_verified"] is True
    assert "/verify?token=" not in email_log.text
    assert _login(browser) == 204
    assert browser.get("/api/auth/me").json()["is_verified"] is True


def test_with_verification_off_an_unverified_account_may_use_llm_routes(
    browser: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(browser)  # verification is on here, so the account stays unverified
    assert _login(browser) == 204
    course = browser.post("/api/courses", json={"name": "Physics 101"})
    headers = {COURSE_HEADER: str(course.json()["id"])}

    monkeypatch.setenv("REQUIRE_EMAIL_VERIFICATION", "false")
    get_settings.cache_clear()
    assert browser.get("/api/auth/me").json()["is_verified"] is False
    for (method, _), url in LLM_ROUTES.items():
        response = browser.request(method, url, headers=headers)
        assert response.status_code not in {401, 403}, (url, response.text)


# ------------------------------------------------------------------ 6. production config

PRODUCTION = {"environment": Environment.PRODUCTION, "auth_secret_key": "x" * 32}
SMTP = {
    "smtp_host": "smtp.example.edu",
    "smtp_user": "mailer",
    "smtp_password": "mail-password",
    "smtp_from": "Adaptive Trainer <no-reply@example.edu>",
}


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_refuses_a_missing_public_app_url() -> None:
    with pytest.raises(ValidationError, match="PUBLIC_APP_URL"):
        _settings(**PRODUCTION, **SMTP)


@pytest.mark.parametrize("missing", sorted(SMTP))
def test_production_refuses_smtp_without_its_settings(missing: str) -> None:
    values = {name: value for name, value in SMTP.items() if name != missing}
    with pytest.raises(ValidationError, match=missing.upper()):
        _settings(**PRODUCTION, public_app_url="https://trainer.example.edu", **values)
    # The explicit choice of smtp is held to the same rule as the production default.
    with pytest.raises(ValidationError, match=missing.upper()):
        _settings(**PRODUCTION, public_app_url="https://x.edu", email_backend="smtp", **values)


def test_production_defaults_to_smtp_and_accepts_complete_settings() -> None:
    settings = _settings(**PRODUCTION, public_app_url="https://trainer.example.edu/", **SMTP)

    assert settings.effective_email_backend == "smtp"
    assert settings.app_url == "https://trainer.example.edu"
    assert isinstance(get_email_sender(settings), SmtpEmailSender)


def test_development_logs_email_and_links_to_localhost() -> None:
    settings = _settings()

    assert settings.effective_email_backend == "console"
    assert settings.app_url == "http://localhost:3000"
    assert isinstance(get_email_sender(settings), ConsoleEmailSender)


def test_smtp_sender_upgrades_to_tls_before_logging_in(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            calls.append(f"connect {host}:{port}")

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *args: object) -> None:
            calls.append("quit")

        def starttls(self, context: object) -> None:
            calls.append("starttls")

        def login(self, user: str, password: str) -> None:
            calls.append(f"login {user} {password}")

        def send_message(self, message: Any) -> None:
            calls.append(f"send {message['To']} {message['From']}")

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    sender = SmtpEmailSender(_settings(**SMTP))

    sender.send_now(to=EMAIL, subject="Hello", body="A link")

    assert calls == [
        "connect smtp.example.edu:587",
        "starttls",
        "login mailer mail-password",
        f"send {EMAIL} Adaptive Trainer <no-reply@example.edu>",
        "quit",
    ]


def test_a_failed_smtp_send_is_logged_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise ConnectionRefusedError("no mail server")

    monkeypatch.setattr(smtplib, "SMTP", refuse)

    SmtpEmailSender(_settings(**SMTP)).send_now(to=EMAIL, subject="Hello", body="A link")
