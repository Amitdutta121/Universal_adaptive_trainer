"""C6: the EXECUTOR setting decides where every code run goes."""

from __future__ import annotations

import pytest

from app.assessment.executor import configure_executor
from app.config import Settings
from graders import get_executor, set_executor
from graders.executors.local import LocalExecutor
from graders.executors.piston import PistonExecutor


@pytest.fixture(autouse=True)
def _reset_executor():
    yield
    set_executor(None)


def test_local_is_the_default() -> None:
    configure_executor(Settings(_env_file=None))
    assert isinstance(get_executor(), LocalExecutor)


def test_piston_is_used_when_chosen() -> None:
    configure_executor(
        Settings(_env_file=None, executor="piston", piston_url="http://sandbox:2000")
    )
    executor = get_executor()
    assert isinstance(executor, PistonExecutor)
    assert "sandbox:2000" in repr(vars(executor))


def test_an_unknown_executor_is_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, executor="docker")
