"""Capability id -> grader. The one place the app asks for a grader (C0).

Each grader module registers itself by being listed in :data:`_MODULES`; a module that is not
there yet (its work package is unfinished) simply contributes nothing. Graders that run code are
built with the one shared executor (:func:`get_executor`); :func:`set_executor` chooses which
(local by default, the sandbox in production -- C6). A module whose third-party dependency is
not installed is skipped with a warning.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable

from graders.core import Grader
from graders.executors.base import Executor

#: Module path -> name of a ``build(executor)`` function returning its graders.
_MODULES: tuple[str, ...] = (
    "graders.structured",
    "graders.text",
    "graders.python",
    "graders.quantity",
    "graders.symbolic",
)

logger = logging.getLogger(__name__)

_executor_factory: Callable[[], Executor] | None = None
_executor: Executor | None = None
_cache: dict[str, Grader] | None = None


def set_executor(factory: Callable[[], Executor] | None) -> None:
    """Choose the executor (``None``: local); drops the shared one and any built graders."""
    global _executor_factory, _executor, _cache
    close = getattr(_executor, "close", None)
    if callable(close):
        close()
    _executor_factory = factory
    _executor = None
    _cache = None


def _default_executor() -> Executor:
    from graders.executors.local import LocalExecutor

    return LocalExecutor()


def get_executor() -> Executor:
    """The one shared executor, as configured by :func:`set_executor` (local by default).

    Graders and the app's authoring checks all run code through it, so a sandbox client (and
    its connection pool) is created once, not per run.
    """
    global _executor
    if _executor is None:
        _executor = (_executor_factory or _default_executor)()
    return _executor


def _graders() -> dict[str, Grader]:
    global _cache
    if _cache is None:
        built: dict[str, Grader] = {}
        for module_name in _MODULES:
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError as error:
                if error.name == module_name:
                    continue  # that work package has not landed yet
                if error.name and not error.name.startswith("graders"):
                    # A third-party dependency (pint, sympy) is not installed: only this
                    # module's capabilities are unavailable; the rest still grade.
                    logger.warning(
                        "%s is unavailable: %s is not installed.", module_name, error.name
                    )
                    continue
                raise
            for grader in module.build(get_executor):
                if grader.capability in built:
                    raise RuntimeError(f"Two graders claim {grader.capability!r}.")
                built[grader.capability] = grader
        _cache = built
    return _cache


def get_grader(capability: str) -> Grader:
    """The grader for ``capability``. ``KeyError`` when none is built."""
    graders = _graders()
    if capability not in graders:
        raise KeyError(f"No grader is built for capability {capability!r}.")
    return graders[capability]


def available_capabilities() -> list[str]:
    return sorted(_graders())
