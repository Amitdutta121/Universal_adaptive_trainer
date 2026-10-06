"""Create a professor account from the command line.

This is how the first account comes to exist in production, where nothing is
seeded (``app/auth/seed.py`` runs in development only)::

    python -m app.auth.create_user --email admin@example.edu --superuser

The password is prompted for (twice, never echoed). For a non-interactive
deploy step, pipe it in with ``--password-stdin`` instead.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from fastapi_users import InvalidPasswordException, schemas
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.password import PasswordHelper
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from pydantic import ValidationError

from app.auth.users import UserManager
from app.persistence.async_database import get_async_engine, get_async_session_factory
from app.persistence.database import init_db
from app.persistence.models import UserRow


class CreateUserError(Exception):
    """A reason the account could not be created, worded for the operator."""


async def create_user(email: str, password: str, *, superuser: bool = False) -> UserRow:
    """Create an active, verified account; raise :class:`CreateUserError` if refused."""
    try:
        user_create = schemas.BaseUserCreate(
            email=email, password=password, is_superuser=superuser, is_verified=True
        )
    except ValidationError as exc:
        raise CreateUserError(f"Invalid email address: {email}") from exc

    init_db()
    async with get_async_session_factory()() as session:
        manager = UserManager(SQLAlchemyUserDatabase(session, UserRow), PasswordHelper())
        try:
            # safe=False: the operator may set is_superuser/is_verified, which
            # a public request must never be able to.
            return await manager.create(user_create, safe=False)
        except UserAlreadyExists as exc:
            raise CreateUserError(f"An account for {email} already exists.") from exc
        except InvalidPasswordException as exc:
            raise CreateUserError(str(exc.reason)) from exc


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise CreateUserError("Passwords do not match.")
    return password


async def _run(args: argparse.Namespace) -> None:
    try:
        user = await create_user(
            args.email, _read_password(args.password_stdin), superuser=args.superuser
        )
    finally:
        await get_async_engine().dispose()
    kind = "superuser" if user.is_superuser else "professor"
    print(f"Created {kind} account {user.email} ({user.id}).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.auth.create_user", description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--superuser", action="store_true", help="grant admin rights")
    parser.add_argument(
        "--password-stdin", action="store_true", help="read the password from stdin"
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except CreateUserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
