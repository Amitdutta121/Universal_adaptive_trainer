"""The real login/protect/logout flow, over real HTTP.

Every other test file runs against the ``client`` fixture, which
pre-authenticates via a dependency override (``tests/conftest.py``) so tests
exercise business logic without each needing to log in first. This file is
the deliberate exception: it builds its own app with that override absent, to
prove the actual cookie-session wiring works end to end.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings

VALID_TAXONOMY = (
    b'{"schema_version":"1","label":"Uploaded","topics":['
    b'{"name":"Loops","subtopics":[{"name":"While loops"}]}]}'
)


@pytest.fixture
def dev_settings(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """The same throwaway database as ``settings``, but development-mode so
    the seeded developer account (``app/auth/seed.py``) actually gets created."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def real_app(dev_settings: Settings) -> FastAPI:
    from app.main import create_app

    return create_app(dev_settings)


@pytest.fixture
def real_client(real_app: FastAPI) -> Iterator[TestClient]:
    """A client with no auth override in force -- the actual login flow."""
    with TestClient(real_app) as client:
        yield client


def _login(client: TestClient, dev_settings: Settings) -> str:
    response = client.post(
        "/api/auth/login",
        data={
            "username": dev_settings.dev_user_email,
            "password": dev_settings.dev_user_password.get_secret_value(),
        },
    )
    assert response.status_code == 204, response.text
    cookie = response.cookies.get("atsession")
    assert cookie is not None
    return cookie


def test_protected_route_401s_with_no_session(real_client: TestClient) -> None:
    response = real_client.get("/api/students")
    assert response.status_code == 401


def test_seeded_dev_account_logs_in_and_reaches_a_protected_route(
    real_client: TestClient, dev_settings: Settings
) -> None:
    # The login response's Set-Cookie header is already in the client's own
    # cookie jar, so every request after this carries the session automatically.
    _login(real_client, dev_settings)

    me = real_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == dev_settings.dev_user_email

    students = real_client.get("/api/students")
    assert students.status_code == 200


def test_logout_revokes_the_session_immediately(
    real_client: TestClient, dev_settings: Settings
) -> None:
    """Proves the database strategy, not just a client-side cookie clear:
    the same cookie value stops working the instant logout runs."""
    cookie = _login(real_client, dev_settings)

    logout = real_client.post("/api/auth/logout")
    assert logout.status_code == 204

    # Re-inject the pre-logout value deliberately: the jar itself was cleared
    # by logout's own Set-Cookie, but a copied/stolen value must fail too.
    real_client.cookies.set("atsession", cookie)
    reused = real_client.get("/api/auth/me")
    assert reused.status_code == 401


def test_wrong_password_is_rejected(real_client: TestClient, dev_settings: Settings) -> None:
    response = real_client.post(
        "/api/auth/login",
        data={"username": dev_settings.dev_user_email, "password": "not-the-password"},
    )
    assert response.status_code == 400


def test_anonymous_student_flow_stays_public(real_client: TestClient) -> None:
    """The join-by-link flow (ADR-041) must never require a session."""
    real_client.cookies.set("atsession", "not-a-real-session")
    taxonomy = real_client.post(
        "/api/curriculum/versions",
        files={"file": ("taxonomy.json", VALID_TAXONOMY, "application/json")},
    )
    # Professor-only route: still refused with a garbage cookie.
    assert taxonomy.status_code == 401
    real_client.cookies.clear()

    enrolled = real_client.post(
        "/api/students", json={"display_name": "Anon Kid", "email": "anon.kid@example.edu"}
    )
    assert enrolled.status_code == 201
