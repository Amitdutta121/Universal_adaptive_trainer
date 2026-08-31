"""Module boundaries.

These tests protect the *shape* of the architecture rather than any behaviour:
the deferred subsystems must exist, must fail loudly instead of pretending to
work, and the two adaptation loops must stay independent.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.adaptive import AdaptiveTrainingEngine, get_adaptive_engine
from app.domain.enums import Difficulty, GeneratorKind, QuestionType
from app.domain.questions import QuestionValidationReport
from app.errors import ConfigurationError, NotFoundError
from app.generation import GenerationRequest, GeneratorDescriptor, get_question_generator
from app.llm import describe_availability, require_llm
from app.validation import get_question_validator

BOUNDARY_MODULES = [
    "app.ingestion",
    "app.curriculum",
    "app.generation",
    "app.validation",
    "app.evaluation",
    "app.feedback",
    "app.personalization",
    "app.adaptive",
    "app.persistence",
    "app.llm",
    "app.web",
]


def test_validation_package_imports_in_a_clean_process() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-c", "from app.validation import get_question_validator"],
        cwd=root,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(root)},
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("module_name", BOUNDARY_MODULES)
def test_boundary_module_exists_and_is_documented(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__doc__, f"{module_name} must document its responsibility"


def test_book_ingestion_is_implemented() -> None:
    """Ingestion is no longer a placeholder: it validates and stores for real.

    Replaces the previous "fails loudly" assertion, which held while ingestion was
    deferred. The remaining subsystems below are still placeholders.
    """
    import book_documents as docs

    from app.domain.enums import SourceFormat
    from app.ingestion import SUPPORTED_EXTENSIONS, format_for_filename, parse_book_document

    assert SUPPORTED_EXTENSIONS == (".json", ".pdf")
    assert format_for_filename("book.json") is SourceFormat.BOOK_JSON
    assert format_for_filename("book.pdf") is SourceFormat.BOOK_PDF
    assert parse_book_document(docs.to_bytes(docs.minimal())).section_count == 1


def test_unsupported_uploads_are_rejected() -> None:
    from app.errors import UnsupportedFileError
    from app.ingestion import format_for_filename

    with pytest.raises(UnsupportedFileError):
        format_for_filename("book.docx")


def test_the_application_does_no_heuristic_extraction() -> None:
    """Structure must be declared by the input, not inferred by this code.

    Guards ADR-015/ADR-016 as narrowed by ADR-048: the removed heuristic modules
    must not reappear, and nothing under ``app/`` may reach for a PDF parser
    except ``app/ingestion/pdf/`` -- the one place ADR-048 grants an exception,
    to read a PDF's own outline and page text.
    """
    import importlib.util
    from pathlib import Path

    app_root = Path(importlib.util.find_spec("app").origin).parent  # type: ignore[arg-type]
    for removed in (
        "ingestion/headings.py",
        # The removed heuristic converter *file*; distinct from the
        # `ingestion/pdf/` *package* ADR-048 introduces.
        "ingestion/pdf.py",
        "ingestion/text.py",
        "ingestion/assembly.py",
    ):
        assert not (app_root / removed).exists(), f"{removed} must stay removed"

    sources = [
        path
        for path in app_root.rglob("*.py")
        if path.relative_to(app_root).parts[:2] != ("ingestion", "pdf")
    ]
    assert sources
    for forbidden in ("pypdf", "PdfReader", "fitz", "pdfplumber", "pdfminer", "pymupdf"):
        offenders = [
            path.relative_to(app_root).as_posix()
            for path in sources
            if forbidden in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], (
            f"the application must not use {forbidden} outside ingestion/pdf/: {offenders}"
        )


def test_pymupdf_is_the_only_pdf_dependency_and_it_is_declared() -> None:
    """ADR-048 grants exactly one exception to ADR-016's "no PDF parser" rule.

    ``pymupdf``/``pymupdf4llm`` are now a deliberate, declared dependency; every
    other PDF library stays absent, exactly as before. Absence of the import is
    easy to reintroduce by accident; absence (or presence) of the dependency
    makes it impossible without a deliberate change to pyproject.toml.
    """
    import importlib.util
    import tomllib
    from pathlib import Path

    for library in ("pypdf", "pdfplumber", "pdfminer"):
        assert importlib.util.find_spec(library) is None, f"{library} must not be installed"

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    declared = " ".join(config["project"]["dependencies"]).lower()
    for library in ("pypdf", "pdfplumber", "pdfminer"):
        assert library not in declared, f"{library} must not be a dependency"
    assert "pymupdf" in declared, "pymupdf must be a declared dependency (ADR-048)"


def test_curriculum_boundary_only_exports_taxonomy_import_and_display_helpers() -> None:
    """The boundary imports, authors, edits and deletes -- it never proposes.

    An exact list rather than a subset check: every addition to this boundary has
    to be looked at, because the one thing that must never come back is a way to
    derive curriculum instead of receiving it (ADR-021). Authoring and library
    (ADR-046) act on documents a professor wrote and rows an import already made.
    """
    import app.curriculum as curriculum

    assert curriculum.__all__ == [
        "ALL_FIELDS",
        "DESCRIPTION_MAX_LENGTH",
        "DOCUMENT_FIELDS",
        "EXAMPLE_DOCUMENT",
        "LABEL_MAX_LENGTH",
        "NAME_MAX_LENGTH",
        "SCHEMA_VERSION",
        "SUBTOPIC_FIELDS",
        "SUPPORTED_EXTENSIONS",
        "TOPIC_FIELDS",
        "CurriculumLibraryService",
        "CurriculumUsage",
        "FieldLimit",
        "TaxonomyImportService",
        "example_json",
        "extraction_metadata",
        "parse_taxonomy_document",
        "proposal_warnings",
        "taxonomy_authoring_prompt",
    ]
    assert not hasattr(curriculum, "CurriculumProposalService")
    assert not hasattr(curriculum, "get_curriculum_proposer")


def test_llm_curriculum_proposal_modules_stay_removed() -> None:
    curriculum_root = Path(importlib.import_module("app.curriculum").__file__).parent
    for removed in (
        "candidates.py",
        "checks.py",
        "draft.py",
        "extraction.py",
        "normalization.py",
        "schema.py",
        "service.py",
    ):
        assert not (curriculum_root / removed).exists(), f"{removed} must stay removed"


def test_question_generator_is_base_and_requires_llm_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    request = GenerationRequest(
        curriculum_version_id=1,
        subtopic_id=2,
        question_type=QuestionType.DEBUGGING,
        source_section_ids=[3],
        difficulty=Difficulty.EASY,
        count=3,
    )
    generator = get_question_generator()
    assert generator.descriptor == GeneratorDescriptor(
        kind=GeneratorKind.BASE, name="base", version="1"
    )
    with pytest.raises(ConfigurationError):
        generator.generate(request)
    get_settings.cache_clear()


def test_generation_request_requires_curriculum_grounding() -> None:
    """Generation must always name an approved curriculum version and a source."""
    with pytest.raises(ValueError):
        GenerationRequest(  # type: ignore[call-arg]
            question_type=QuestionType.DEBUGGING,
            source_section_ids=[3],
            difficulty=Difficulty.EASY,
        )
    with pytest.raises(ValueError):
        GenerationRequest(  # type: ignore[call-arg]
            curriculum_version_id=1,
            question_type=QuestionType.DEBUGGING,
            source_section_ids=[],
            difficulty=Difficulty.EASY,
        )


def test_generation_request_names_no_topic_or_subtopic() -> None:
    """The generator classifies its own question, so the request cannot pre-empt it."""
    fields = set(GenerationRequest.model_fields)
    assert "subtopic_id" not in fields
    assert "topic_id" not in fields


def test_generator_provenance_is_still_labelled() -> None:
    """One generator now (ADR-033), but questions still record which made them.

    ``GeneratorKind.PERSONALIZED`` is kept because rows written before ADR-033
    carry it; nothing new is stamped with it.
    """
    base = GeneratorDescriptor(kind=GeneratorKind.BASE, name="grounded", version="1")
    assert base.label() == "base:grounded@1"
    historical = GeneratorDescriptor(kind=GeneratorKind.PERSONALIZED, name="grounded", version="1")
    assert base.label() != historical.label()


def test_question_validation_returns_a_report() -> None:
    from app.domain.questions import Question

    report = get_question_validator().validate(Question(prompt="Anything"))

    assert isinstance(report, QuestionValidationReport)
    assert report.passed is False


def test_personalization_is_the_type_instruction(session) -> None:
    """ADR-033: nothing is appended to the prompt; the type slot is replaced.

    The deleted modules stay deleted. A retrieval or preference module coming
    back would mean the appended-block design had returned with it.
    """
    for module in (
        "app.personalization.retrieval",
        "app.personalization.context",
        "app.personalization.embeddings",
        "app.personalization.learner",
        "app.personalization.service",
        "app.personalization.generator",
        "app.domain.preferences",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)

    from app.personalization import refresh_type_instruction

    assert callable(refresh_type_instruction)


def test_adaptive_engine_is_implemented(session) -> None:
    """The engine is real (ADR-041); an unknown session is not found, not stubbed."""
    engine = get_adaptive_engine(session)
    assert isinstance(engine, AdaptiveTrainingEngine)
    with pytest.raises(NotFoundError):
        engine.serve_next(404)
    with pytest.raises(NotFoundError):
        engine.submit_answer(404, "answer")


class TestLLMBoundary:
    def test_require_llm_raises_when_unconfigured(self) -> None:
        from app.config import LLMProvider, Settings

        settings = Settings(_env_file=None, llm_provider=LLMProvider.NONE)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError):
            require_llm(settings)

    def test_require_llm_passes_when_configured(self) -> None:
        from app.config import LLMProvider, Settings

        settings = Settings(  # type: ignore[call-arg]
            _env_file=None, llm_provider=LLMProvider.OPENROUTER, llm_api_key="sk-test"
        )
        assert require_llm(settings) is settings

    def test_availability_description_hides_the_key(self) -> None:
        from app.config import LLMProvider, Settings

        settings = Settings(  # type: ignore[call-arg]
            _env_file=None, llm_provider=LLMProvider.OPENROUTER, llm_api_key="sk-hidden"
        )
        configured, description = describe_availability(settings)
        assert configured is True
        assert "sk-hidden" not in description


def test_the_two_loops_do_not_import_each_other() -> None:
    """Student adaptation and professor content optimization stay separate."""
    adaptive_root = Path(importlib.import_module("app.adaptive").__file__).parent
    personalization_root = Path(importlib.import_module("app.personalization").__file__).parent

    for path in adaptive_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import app.personalization" not in text
        assert "from app.personalization" not in text

    for path in personalization_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import app.adaptive" not in text
        assert "from app.adaptive" not in text


def test_the_adaptive_engine_keeps_its_declared_dependencies() -> None:
    """``app/adaptive`` names its allowed imports in its docstring; enforce them.

    ``app.generation`` is the tempting one: scoring a submitted program needs the
    question's stored test cases, whose schema lives there. The engine reaches
    them through :func:`app.validation.runner.parse_test_cases` instead, so the
    student loop stays clear of the generator entirely.
    """
    adaptive_root = Path(importlib.import_module("app.adaptive").__file__).parent
    forbidden = ("app.generation", "app.web")

    for path in adaptive_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for package in forbidden:
            assert f"import {package}" not in text, f"{path.name} imports {package}"
            assert f"from {package}" not in text, f"{path.name} imports {package}"
