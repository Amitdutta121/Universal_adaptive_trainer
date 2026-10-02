"""Question types, one module each (phase 2, T0a). See :mod:`app.question_types.base`.

A type is *implemented* when its module is listed in :data:`_MODULES` and importable; a listed
module that does not exist yet (its work package has not landed) contributes nothing, exactly
like the graders registry. Each module exposes ``TYPE``, an instance of
:class:`~app.question_types.base.QuestionTypeModule`.
"""

from __future__ import annotations

import importlib

from app.domain.enums import QuestionType
from app.question_types.base import DraftColumns, QuestionTypeModule, StudentView

_MODULES: tuple[str, ...] = (
    "app.question_types.multiple_choice",
    "app.question_types.true_false",
    "app.question_types.output_prediction",
    "app.question_types.code_completion",
    "app.question_types.debugging",
    "app.question_types.parsons",
    "app.question_types.coding",
    "app.question_types.numeric_response",  # T1
    "app.question_types.equation_response",  # T2
)

_cache: dict[QuestionType, QuestionTypeModule] | None = None


def _types() -> dict[QuestionType, QuestionTypeModule]:
    global _cache
    if _cache is None:
        built: dict[QuestionType, QuestionTypeModule] = {}
        for module_name in _MODULES:
            try:
                module = importlib.import_module(module_name)
            except ModuleNotFoundError as error:
                if error.name == module_name:
                    continue  # that work package has not landed yet
                raise
            question_type = module.TYPE.question_type
            if question_type in built:
                raise RuntimeError(f"Two modules claim question type {question_type!r}.")
            built[question_type] = module.TYPE
        _cache = built
    return _cache


def get_type(question_type: QuestionType) -> QuestionTypeModule:
    """The module for ``question_type``. ``KeyError`` when that type is not built."""
    types = _types()
    if question_type not in types:
        raise KeyError(f"Question type {question_type.value!r} is not built.")
    return types[question_type]


def implemented_types() -> list[QuestionType]:
    """Built types, in :class:`~app.domain.enums.QuestionType` order."""
    types = _types()
    return [question_type for question_type in QuestionType if question_type in types]


def type_for_draft(draft: object) -> QuestionTypeModule:
    """The module whose ``draft_model`` produced ``draft``. ``TypeError`` if none."""
    for module in _types().values():
        if type(draft) is module.draft_model:
            return module
    raise TypeError(f"Unsupported draft type: {type(draft).__name__}")


__all__ = [
    "DraftColumns",
    "QuestionTypeModule",
    "StudentView",
    "get_type",
    "implemented_types",
    "type_for_draft",
]
