"""``python -m app.auth.create_user`` and the production auth-secret guard (M1).

Production seeds no account (``app/auth/seed.py``), so the CLI is the only way
the first one comes to exist; these tests prove an account it creates can
actually log in through the real cookie flow.
"""

from __future__ import annotations

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.create_user import main
from app.config import DEV_AUTH_SECRET_KEY, Environment, Settings

EMAIL = "admin@example.edu"
PASSWORD = "a-long-enough-passphrase"


def _run(monkeypatch: pytest.MonkeyPatch, password: str, *extra: str) -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
    return main(["--email", EMAIL, "--password-stdin", *extra])


@pytest.fixture
def real_client(settings: Settings) -> Iterator[TestClient]:
    """The real app with no auth override, so login is actually exercised."""
    from app.main import create_app

    with TestClient(create_app(settings)) as client:
        yield client


def test_created_superuser_can_log_in(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, real_client: TestClient
) -> None:
    assert _run(monkeypatch, PASSWORD, "--superuser") == 0

    response = real_client.post("/api/auth/login", data={"username": EMAIL, "password": PASSWORD})
    assert response.status_code == 204, response.text
    me = real_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


def test_duplicate_email_is_refused(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, PASSWORD) == 0
    assert _run(monkeypatch, PASSWORD) == 1
    assert "already exists" in capsys.readouterr().err


def test_short_password_is_refused(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(monkeypatch, "short-pass") == 1
    assert "at least 12" in capsys.readouterr().err


def test_invalid_email_is_refused(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert main(["--email", "not-an-email", "--password-stdin"]) == 1
    assert "Invalid email" in capsys.readouterr().err


@pytest.mark.parametrize("secret", [DEV_AUTH_SECRET_KEY, "too-short"])
def test_production_refuses_a_weak_auth_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="AUTH_SECRET_KEY"):
        Settings(environment=Environment.PRODUCTION, auth_secret_key=secret)  # type: ignore[arg-type]


def test_production_accepts_a_real_auth_secret_and_dev_keeps_the_default() -> None:
    Settings(
        environment=Environment.PRODUCTION,
        auth_secret_key="x" * 32,  # type: ignore[arg-type]
        # Also required in production (ADR-061), not under test here.
        public_app_url="https://trainer.example.edu",
        email_backend="console",
    )
    assert Settings(environment=Environment.DEVELOPMENT).auth_secret_key.get_secret_value() == (
        DEV_AUTH_SECRET_KEY
    )
