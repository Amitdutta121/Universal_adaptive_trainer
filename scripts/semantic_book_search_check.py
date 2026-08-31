"""Check whether topic/subtopic semantic search can find the right book chunk.

Two modes:
1. ``fixture`` builds a temporary database with the sample "Think Python" book
   and scores a small set of topic/subtopic queries against expected sections.
2. ``live`` queries one imported book from the configured application database
   and prints the top matching chunks for manual inspection.

This script does not modify the application's real schema beyond normal
read-only access in ``live`` mode. The fixture benchmark uses a throwaway SQLite
database under the system temp directory.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import tempfile
from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import openai
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.ingestion import BookImportService
from app.llm.client import OPENROUTER_BASE_URL
from app.persistence.database import create_db_engine, init_db, session_scope
from app.persistence.repositories import BookRepository, BookStructureRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = PROJECT_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import book_documents as docs


@dataclass(frozen=True)
class QueryCase:
    topic: str
    subtopic: str
    book_title: str | None = None
    topic_description: str | None = None
    subtopic_description: str | None = None
    candidate_labels: tuple[str, ...] = ()
    grouping_reason: str | None = None
    question_type: str | None = "coding"
    difficulty: str | None = "medium"
    expected_section_number: str | None = None
    expected_title: str | None = None

    def query_text(self) -> str:
        parts = [
            f"Topic: {self.topic}",
            f"Subtopic: {self.subtopic}",
        ]
        if self.topic_description:
            parts.append(f"Topic description: {self.topic_description}")
        if self.subtopic_description:
            parts.append(f"Subtopic description: {self.subtopic_description}")
        if self.candidate_labels:
            parts.append(f"Alternate labels: {', '.join(self.candidate_labels)}")
        if self.grouping_reason:
            parts.append(f"Grouping reason: {self.grouping_reason}")
        if self.question_type:
            parts.append(f"Question type: {self.question_type}")
        if self.difficulty:
            parts.append(f"Difficulty: {self.difficulty}")
        return "\n".join(parts)

    def label(self) -> str:
        if self.book_title:
            return f"{self.book_title} | {self.topic} -> {self.subtopic}"
        return f"{self.topic} -> {self.subtopic}"


@dataclass(frozen=True)
class ChunkCandidate:
    section_id: int
    book_id: int
    book_title: str
    chapter_title: str | None
    section_number: str | None
    section_title: str | None
    chunk_index: int
    text: str

    def display_label(self) -> str:
        number = self.section_number or "?"
        title = self.section_title or "Untitled section"
        return f"{self.book_title} | {number} {title} | chunk {self.chunk_index + 1}"


@dataclass(frozen=True)
class RankedChunk:
    candidate: ChunkCandidate
    score: float
    semantic_score: float
    lexical_score: float
    title_score: float
    book_score: float


@dataclass(frozen=True)
class FixtureBook:
    filename: str
    document: dict


@dataclass(frozen=True)
class EmbeddingClient:
    settings: Settings

    def __post_init__(self) -> None:
        if self.settings.llm_api_key is None:
            raise RuntimeError("LLM_API_KEY is required to run semantic retrieval checks.")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        client = openai.OpenAI(
            api_key=self.settings.llm_api_key.get_secret_value(),
            base_url=self.settings.llm_base_url or OPENROUTER_BASE_URL,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=1,
            default_headers={
                "HTTP-Referer": "https://localhost/adaptive-trainer",
                "X-Title": "Adaptive Trainer",
            },
        )
        response = client.embeddings.create(
            model=self.settings.embedding_model,
            input=list(texts),
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        return [cast(list[float], item.embedding) for item in ordered]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Embedding vectors must have the same dimension.")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def normalise_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 1}


def jaccard_score(left: str, right: str) -> float:
    a = normalise_tokens(left)
    b = normalise_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def sentence_chunks(text: str, *, max_chars: int = 320) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if len(sentences) <= 1 and len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        proposed = sentence if not current else f"{current} {sentence}"
        if current and len(proposed) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = proposed
    if current:
        chunks.append(current)
    return chunks or [cleaned]


def build_candidates(session: Session, *, book_ids: Sequence[int] | None = None) -> list[ChunkCandidate]:
    books = BookRepository(session)
    structure = BookStructureRepository(session)
    usable = books.list_usable()
    allowed = set(book_ids) if book_ids else {book.id for book in usable}
    candidates: list[ChunkCandidate] = []

    for book in usable:
        if book.id not in allowed:
            continue
        for section in structure.sections_in_book(book.id):
            chunks = sentence_chunks(section.text)
            for index, chunk_text in enumerate(chunks):
                chapter_title = section.chapter.title if section.chapter is not None else None
                candidates.append(
                    ChunkCandidate(
                        section_id=section.id,
                        book_id=book.id,
                        book_title=book.title,
                        chapter_title=chapter_title,
                        section_number=section.number,
                        section_title=section.title,
                        chunk_index=index,
                        text=chunk_text,
                    )
                )
    return candidates


def rank_chunks(
    client: EmbeddingClient,
    *,
    case: QueryCase,
    candidates: Sequence[ChunkCandidate],
    top_k: int = 5,
) -> list[RankedChunk]:
    if not candidates:
        return []
    query = case.query_text()
    texts = [
        "\n".join(
            part
            for part in (
                f"Book: {candidate.book_title}",
                f"Chapter: {candidate.chapter_title}" if candidate.chapter_title else None,
                f"Section: {candidate.section_number} {candidate.section_title}".strip(),
                candidate.text,
            )
            if part
        )
        for candidate in candidates
    ]
    query_vector = client.embed([query])[0]
    candidate_vectors = client.embed(texts)
    query_tokens = normalise_tokens(query)
    ranked = [
        RankedChunk(
            candidate=candidate,
            semantic_score=cosine_similarity(query_vector, vector),
            lexical_score=jaccard_score(
                query,
                " ".join(
                    part
                    for part in (
                        candidate.text,
                        candidate.section_title or "",
                        candidate.chapter_title or "",
                        candidate.book_title,
                    )
                    if part
                ),
            ),
            title_score=(
                0.65
                * jaccard_score(query, candidate.section_title or "")
                + 0.35 * jaccard_score(query, candidate.chapter_title or "")
            ),
            book_score=(
                1.0
                if case.book_title is not None
                and candidate.book_title.casefold() == case.book_title.casefold()
                else 0.0
            ),
            score=0.0,
        )
        for candidate, vector in zip(candidates, candidate_vectors, strict=True)
    ]
    enriched: list[RankedChunk] = []
    for item in ranked:
        candidate_tokens = normalise_tokens(
            " ".join(
                part
                for part in (
                    item.candidate.section_title or "",
                    item.candidate.chapter_title or "",
                    item.candidate.text,
                )
                if part
            )
        )
        overlap_boost = 0.03 if query_tokens & candidate_tokens else 0.0
        final_score = (
            0.58 * item.semantic_score
            + 0.14 * item.lexical_score
            + 0.08 * item.title_score
            + 0.20 * item.book_score
            + overlap_boost
        )
        enriched.append(
            RankedChunk(
                candidate=item.candidate,
                score=final_score,
                semantic_score=item.semantic_score,
                lexical_score=item.lexical_score,
                title_score=item.title_score,
                book_score=item.book_score,
            )
        )
    enriched.sort(key=lambda item: item.score, reverse=True)
    return enriched[:top_k]


def _matches_expected(result: RankedChunk, case: QueryCase) -> bool:
    if case.book_title and result.candidate.book_title != case.book_title:
        return False
    if (
        case.expected_section_number
        and result.candidate.section_number == case.expected_section_number
    ):
        return True
    if case.expected_title and result.candidate.section_title == case.expected_title:
        return True
    return False


def fixture_books() -> list[FixtureBook]:
    think_python = docs.think_python()

    python_workshop = {
        "schema_version": docs.SCHEMA_VERSION,
        "title": "Python Workshop Notes",
        "author": "Course Staff",
        "source_filename": "python_workshop.pdf",
        "producer": "example-converter 1.0",
        "page_count": 24,
        "chapters": [
            {
                "number": "1",
                "title": "Program Basics",
                "start_page": 1,
                "end_page": 8,
                "structure_source": "pdf_outline",
                "sections": [
                    {
                        "number": "1.1",
                        "title": "Programs and Steps",
                        "start_page": 1,
                        "end_page": 2,
                        "text": (
                            "A computer program is a list of steps that tells the machine what "
                            "to do."
                        ),
                        "structure_source": "pdf_outline",
                    },
                    {
                        "number": "1.2",
                        "title": "Using the REPL",
                        "start_page": 3,
                        "end_page": 4,
                        "text": (
                            "The Python REPL lets you type code into an interactive prompt and "
                            "see the result immediately."
                        ),
                        "structure_source": "pdf_outline",
                    },
                ],
            },
            {
                "number": "2",
                "title": "Names and Data",
                "start_page": 9,
                "end_page": 16,
                "structure_source": "pdf_outline",
                "sections": [
                    {
                        "number": "2.1",
                        "title": "Kinds of Values",
                        "start_page": 9,
                        "end_page": 11,
                        "text": "Values are pieces of data such as numbers, strings, and booleans.",
                        "structure_source": "pdf_outline",
                    },
                    {
                        "number": "2.2",
                        "title": "Naming Values",
                        "start_page": 12,
                        "end_page": 14,
                        "text": "A variable name points to stored data so the program can use it later.",
                        "structure_source": "pdf_outline",
                    },
                ],
            },
        ],
    }

    algorithm_reader = {
        "schema_version": docs.SCHEMA_VERSION,
        "title": "Algorithm Reader",
        "author": "Course Staff",
        "source_filename": "algorithm_reader.pdf",
        "producer": "example-converter 1.0",
        "page_count": 18,
        "chapters": [
            {
                "number": "1",
                "title": "Sequence and State",
                "start_page": 1,
                "end_page": 8,
                "structure_source": "pdf_outline",
                "sections": [
                    {
                        "number": "1.1",
                        "title": "Instructions and Order",
                        "start_page": 1,
                        "end_page": 3,
                        "text": (
                            "An algorithm is an ordered sequence of instructions carried out step "
                            "by step."
                        ),
                        "structure_source": "pdf_outline",
                    },
                    {
                        "number": "1.2",
                        "title": "Temporary Results",
                        "start_page": 4,
                        "end_page": 5,
                        "text": (
                            "Programs often keep intermediate values in named storage locations."
                        ),
                        "structure_source": "pdf_outline",
                    },
                ],
            },
            {
                "number": "2",
                "title": "Interactive Execution",
                "start_page": 9,
                "end_page": 14,
                "structure_source": "pdf_outline",
                "sections": [
                    {
                        "number": "2.1",
                        "title": "Prompt-Based Testing",
                        "start_page": 9,
                        "end_page": 11,
                        "text": (
                            "You can test small expressions by entering them at a prompt and "
                            "reading the immediate output."
                        ),
                        "structure_source": "pdf_outline",
                    }
                ],
            },
        ],
    }

    return [
        FixtureBook(filename="think_python.json", document=think_python),
        FixtureBook(filename="python_workshop.json", document=python_workshop),
        FixtureBook(filename="algorithm_reader.json", document=algorithm_reader),
    ]


def fixture_cases() -> list[QueryCase]:
    return [
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="What is a program",
            topic_description="How programs work as ordered instructions",
            subtopic_description="Definition of a computer program",
            candidate_labels=("program", "instructions", "computation"),
            grouping_reason="Sections that define what a program is and what instructions mean",
            expected_section_number="1.1",
            expected_title="What Is a Program?",
        ),
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="what does a program tell a computer to do",
            topic_description="How programs work as ordered instructions",
            subtopic_description="Program meaning in plain language",
            candidate_labels=("program", "computer instructions", "steps"),
            grouping_reason="Definitions of what a program tells a machine to do",
            expected_section_number="1.1",
            expected_title="What Is a Program?",
        ),
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="sequence of instructions in a program",
            topic_description="How programs work as ordered instructions",
            subtopic_description="Program definition phrased as a sequence of steps",
            candidate_labels=("program steps", "program instructions"),
            grouping_reason="Definitions of a program as an ordered set of instructions",
            expected_section_number="1.1",
            expected_title="What Is a Program?",
        ),
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="program as ordered computation steps",
            topic_description="How programs work as ordered instructions",
            subtopic_description="A program written as a sequence of steps",
            candidate_labels=("ordered steps", "computation", "instructions"),
            grouping_reason="Program definitions framed as ordered computation",
            expected_section_number="1.1",
            expected_title="What Is a Program?",
        ),
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="Running Python in the interpreter",
            topic_description="How to execute Python interactively",
            subtopic_description="Using the interpreter or prompt to run code",
            candidate_labels=("interpreter", "interactive Python", "prompt"),
            grouping_reason="Sections about executing Python interactively",
            expected_section_number="1.2",
            expected_title="Running Python",
        ),
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="run code in Python interpreter",
            topic_description="How to execute Python interactively",
            subtopic_description="Running code in the interpreter",
            candidate_labels=("interpreter", "run code", "interactive"),
            grouping_reason="Sections about using the interpreter to run code",
            expected_section_number="1.2",
            expected_title="Running Python",
        ),
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="interactive Python prompt",
            topic_description="How to execute Python interactively",
            subtopic_description="Working in a live prompt",
            candidate_labels=("REPL", "interpreter", "prompt"),
            grouping_reason="Interactive execution of Python code",
            expected_section_number="1.2",
            expected_title="Running Python",
        ),
        QueryCase(
            book_title="Think Python",
            topic="The Way of the Program",
            subtopic="python prompt for trying code",
            topic_description="How to execute Python interactively",
            subtopic_description="Trying code at a prompt",
            candidate_labels=("prompt", "interpreter", "try code"),
            grouping_reason="Prompt-based Python execution",
            expected_section_number="1.2",
            expected_title="Running Python",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="Values and types",
            topic_description="Core data concepts in Python",
            subtopic_description="Kinds of values a program works with",
            candidate_labels=("data types", "values", "types"),
            grouping_reason="Sections describing values and data categories",
            expected_section_number="2.1",
            expected_title="Values and Types",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="different kinds of values in a program",
            topic_description="Core data concepts in Python",
            subtopic_description="Categories of values programs work with",
            candidate_labels=("types", "values", "program data"),
            grouping_reason="Sections about classes of values",
            expected_section_number="2.1",
            expected_title="Values and Types",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="basic thing a program works with",
            topic_description="Core data concepts in Python",
            subtopic_description="Values as the primitive units programs manipulate",
            candidate_labels=("value", "program data"),
            grouping_reason="Definitions of value as basic program data",
            expected_section_number="2.1",
            expected_title="Values and Types",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="values are the data programs manipulate",
            topic_description="Core data concepts in Python",
            subtopic_description="Values as the data a program operates on",
            candidate_labels=("data", "value", "manipulate"),
            grouping_reason="Definitions of value as program data",
            expected_section_number="2.1",
            expected_title="Values and Types",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="Variables store names for values",
            topic_description="Names, values, and statements",
            subtopic_description="Variables connect names to stored values",
            candidate_labels=("variable", "name binding", "stored value"),
            grouping_reason="Sections about variables referring to values",
            expected_section_number="2.2",
            expected_title="Variables",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="variable as a name for stored value",
            topic_description="Names, values, and statements",
            subtopic_description="Variable definition in plain language",
            candidate_labels=("variable", "stored value", "name"),
            grouping_reason="Definitions of variables as names for values",
            expected_section_number="2.2",
            expected_title="Variables",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="name that refers to a value",
            topic_description="Names, values, and statements",
            subtopic_description="Definition of a variable as a name bound to a value",
            candidate_labels=("variable name", "refers to value"),
            grouping_reason="Variable definitions and value references",
            expected_section_number="2.2",
            expected_title="Variables",
        ),
        QueryCase(
            book_title="Think Python",
            topic="Variables, Expressions and Statements",
            subtopic="names bound to values",
            topic_description="Names, values, and statements",
            subtopic_description="Binding names to values",
            candidate_labels=("binding", "variable name", "value"),
            grouping_reason="Variable definitions through name binding",
            expected_section_number="2.2",
            expected_title="Variables",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Program Basics",
            subtopic="program is a list of steps",
            topic_description="Program execution basics",
            subtopic_description="A program tells the machine what to do step by step",
            candidate_labels=("program steps", "machine instructions"),
            grouping_reason="Program definitions framed as ordered steps",
            expected_section_number="1.1",
            expected_title="Programs and Steps",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Program Basics",
            subtopic="machine follows a list of steps",
            topic_description="Program execution basics",
            subtopic_description="A machine follows instructions in sequence",
            candidate_labels=("machine steps", "program instructions"),
            grouping_reason="Program definitions as machine-followed steps",
            expected_section_number="1.1",
            expected_title="Programs and Steps",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Program Basics",
            subtopic="interactive prompt with immediate result",
            topic_description="Using Python interactively",
            subtopic_description="Typing code in a live REPL and seeing output immediately",
            candidate_labels=("REPL", "interactive prompt", "immediate result"),
            grouping_reason="Interactive Python usage, not general prompt-based testing",
            expected_section_number="1.2",
            expected_title="Using the REPL",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Program Basics",
            subtopic="python repl gives immediate result",
            topic_description="Using Python interactively",
            subtopic_description="REPL usage with instant output",
            candidate_labels=("REPL", "instant output", "prompt"),
            grouping_reason="Interactive Python usage in a REPL",
            expected_section_number="1.2",
            expected_title="Using the REPL",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Program Basics",
            subtopic="type code and see output right away",
            topic_description="Using Python interactively",
            subtopic_description="Immediate output after typing code",
            candidate_labels=("interactive output", "prompt", "REPL"),
            grouping_reason="Sections about immediate REPL feedback",
            expected_section_number="1.2",
            expected_title="Using the REPL",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Names and Data",
            subtopic="numbers strings and booleans as values",
            topic_description="Common forms of data in Python",
            subtopic_description="Examples of values like numbers, strings, and booleans",
            candidate_labels=("data values", "booleans", "strings"),
            grouping_reason="Sections listing categories of values",
            expected_section_number="2.1",
            expected_title="Kinds of Values",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Names and Data",
            subtopic="examples of values like strings and booleans",
            topic_description="Common forms of data in Python",
            subtopic_description="Examples of data categories",
            candidate_labels=("strings", "booleans", "numbers"),
            grouping_reason="Sections listing concrete kinds of values",
            expected_section_number="2.1",
            expected_title="Kinds of Values",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Names and Data",
            subtopic="variable name points to stored data",
            topic_description="Naming and storing data",
            subtopic_description="Variables let code reuse stored data later",
            candidate_labels=("variable name", "stored data", "name points to value"),
            grouping_reason="Sections about names referring to stored data",
            expected_section_number="2.2",
            expected_title="Naming Values",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Names and Data",
            subtopic="names that point at stored data",
            topic_description="Naming and storing data",
            subtopic_description="Names refer to remembered data",
            candidate_labels=("stored data", "variable name", "points to"),
            grouping_reason="Sections about names referencing stored data",
            expected_section_number="2.2",
            expected_title="Naming Values",
        ),
        QueryCase(
            book_title="Python Workshop Notes",
            topic="Names and Data",
            subtopic="reuse data later with a variable name",
            topic_description="Naming and storing data",
            subtopic_description="Variables help reuse stored data",
            candidate_labels=("reuse data", "variable", "stored value"),
            grouping_reason="Sections about using variable names to reuse data",
            expected_section_number="2.2",
            expected_title="Naming Values",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Sequence and State",
            subtopic="ordered sequence of instructions",
            topic_description="Ordered procedures and state changes",
            subtopic_description="Algorithms as step-by-step instructions",
            candidate_labels=("algorithm", "ordered instructions", "sequence"),
            grouping_reason="Instruction-order definitions in algorithmic contexts",
            expected_section_number="1.1",
            expected_title="Instructions and Order",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Sequence and State",
            subtopic="algorithm as step by step ordered instructions",
            topic_description="Ordered procedures and state changes",
            subtopic_description="Algorithm definition using ordered steps",
            candidate_labels=("algorithm", "step by step", "ordered"),
            grouping_reason="Algorithm definitions focused on step order",
            expected_section_number="1.1",
            expected_title="Instructions and Order",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Sequence and State",
            subtopic="named storage for intermediate values",
            topic_description="State and temporary data in programs",
            subtopic_description="Intermediate results live in named storage",
            candidate_labels=("temporary values", "storage locations", "intermediate state"),
            grouping_reason="Sections about storing intermediate results",
            expected_section_number="1.2",
            expected_title="Temporary Results",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Sequence and State",
            subtopic="temporary storage for intermediate results",
            topic_description="State and temporary data in programs",
            subtopic_description="Storing partial results while working",
            candidate_labels=("temporary storage", "intermediate results", "state"),
            grouping_reason="Sections about storing intermediate program state",
            expected_section_number="1.2",
            expected_title="Temporary Results",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Sequence and State",
            subtopic="keep intermediate values in named locations",
            topic_description="State and temporary data in programs",
            subtopic_description="Named locations hold temporary values",
            candidate_labels=("named locations", "intermediate values", "storage"),
            grouping_reason="Sections about temporary named storage",
            expected_section_number="1.2",
            expected_title="Temporary Results",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Interactive Execution",
            subtopic="test small expressions at a prompt",
            topic_description="Prompt-driven testing of expressions",
            subtopic_description="Using a prompt to test snippets and inspect immediate output",
            candidate_labels=("prompt testing", "small expressions", "immediate output"),
            grouping_reason="Prompt-based testing rather than general REPL usage",
            expected_section_number="2.1",
            expected_title="Prompt-Based Testing",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Interactive Execution",
            subtopic="check small snippets in a prompt",
            topic_description="Prompt-driven testing of expressions",
            subtopic_description="Prompt used to test short snippets",
            candidate_labels=("snippets", "prompt", "testing"),
            grouping_reason="Prompt-based testing of small code pieces",
            expected_section_number="2.1",
            expected_title="Prompt-Based Testing",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Interactive Execution",
            subtopic="immediate output after entering expressions",
            topic_description="Prompt-driven testing of expressions",
            subtopic_description="Immediate feedback from entered expressions",
            candidate_labels=("prompt output", "interactive test"),
            grouping_reason="Testing expressions via prompt response",
            expected_section_number="2.1",
            expected_title="Prompt-Based Testing",
        ),
        QueryCase(
            book_title="Algorithm Reader",
            topic="Interactive Execution",
            subtopic="enter an expression and read the output",
            topic_description="Prompt-driven testing of expressions",
            subtopic_description="Expression testing via prompt output",
            candidate_labels=("expression output", "prompt response"),
            grouping_reason="Testing expressions by reading prompt output",
            expected_section_number="2.1",
            expected_title="Prompt-Based Testing",
        ),
    ]


def run_fixture_check(settings: Settings, *, top_k: int) -> int:
    client = EmbeddingClient(settings)
    temp_root = Path(tempfile.mkdtemp(prefix="semantic-book-search-"))
    eval_settings = Settings(
        **{
            **settings.model_dump(),
            "database_url": f"sqlite:///{(temp_root / 'fixture.db').as_posix()}",
            "book_upload_dir": temp_root / "books",
        }
    )
    engine = create_db_engine(eval_settings)
    init_db(engine)
    with Session(engine, expire_on_commit=False) as session:
        for fixture_book in fixture_books():
            BookImportService(session, eval_settings).import_upload(
                filename=fixture_book.filename,
                data=docs.to_bytes(deepcopy(fixture_book.document)),
            )
        session.commit()
        candidates = build_candidates(session)
        cases = fixture_cases()
        top1_passed = 0
        topk_passed = 0
        print(f"Fixture benchmark on {len(cases)} topic/subtopic queries across {len(fixture_books())} books")
        print(f"Embedding model: {settings.embedding_model}")
        print(f"Candidate chunks: {len(candidates)}")
        print("")
        for case in cases:
            results = rank_chunks(client, case=case, candidates=candidates, top_k=top_k)
            top = results[0] if results else None
            top1_ok = top is not None and _matches_expected(top, case)
            topk_ok = any(_matches_expected(result, case) for result in results)
            top1_passed += int(top1_ok)
            topk_passed += int(topk_ok)
            status = "PASS" if top1_ok else "FAIL"
            print(f"[{status}] {case.label()}")
            if top is None:
                print("  No results")
                continue
            print(
                f"  Top hit: {top.candidate.display_label()} | "
                f"score={top.score:.4f} sem={top.semantic_score:.4f} "
                f"lex={top.lexical_score:.4f} title={top.title_score:.4f} book={top.book_score:.4f}"
            )
            print(f"  Text: {top.candidate.text}")
            expected = f"{case.book_title} | {case.expected_section_number or case.expected_title or 'unknown'}"
            if not top1_ok:
                print(f"  Expected: {expected}")
            print(f"  In top-{top_k}: {'yes' if topk_ok else 'no'}")
            if len(results) > 1:
                print("  Top candidates:")
                for other in results[1:]:
                    print(
                        f"    - {other.candidate.display_label()} | "
                        f"score={other.score:.4f} sem={other.semantic_score:.4f} "
                        f"lex={other.lexical_score:.4f} title={other.title_score:.4f} book={other.book_score:.4f}"
                    )
            print("")
        print(f"Top-1 accuracy: {top1_passed}/{len(cases)}")
        print(f"Top-{top_k} accuracy: {topk_passed}/{len(cases)}")
        return 0 if top1_passed == len(cases) else 1


def parse_live_queries(raw_queries: Iterable[str]) -> list[QueryCase]:
    queries: list[QueryCase] = []
    for raw in raw_queries:
        if "::" in raw:
            topic, subtopic = [part.strip() for part in raw.split("::", 1)]
        else:
            topic = ""
            subtopic = raw.strip()
        if not subtopic:
            raise ValueError(f"Invalid query {raw!r}. Use 'Topic :: Subtopic' or just 'Subtopic'.")
        queries.append(QueryCase(topic=topic, subtopic=subtopic))
    return queries


def run_live_check(settings: Settings, *, book_id: int | None, queries: Sequence[str], top_k: int) -> int:
    client = EmbeddingClient(settings)
    with session_scope() as session:
        usable = BookRepository(session).list_usable()
        if not usable:
            print("No imported books found in the configured database.")
            return 1

        selected_ids = [book_id] if book_id is not None else [book.id for book in usable]
        candidates = build_candidates(session, book_ids=selected_ids)
        if not candidates:
            print("No section chunks found for the selected books.")
            return 1

        print(f"Live search across {len(candidates)} chunks")
        print(f"Embedding model: {settings.embedding_model}")
        print("")
        for book in usable:
            if book.id in selected_ids:
                print(f"Book {book.id}: {book.title}")
        print("")

        for case in parse_live_queries(queries):
            print(f"Query: {case.label()}")
            results = rank_chunks(client, case=case, candidates=candidates, top_k=top_k)
            if not results:
                print("  No results")
                print("")
                continue
            for result in results:
                print(
                    f"  - {result.candidate.display_label()} | score={result.score:.4f} "
                    f"sem={result.semantic_score:.4f} lex={result.lexical_score:.4f} "
                    f"title={result.title_score:.4f} book={result.book_score:.4f}"
                )
                print(f"    {result.candidate.text}")
            print("")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fixture", "live"), default="fixture")
    parser.add_argument("--book-id", type=int, default=None, help="Only for --mode live.")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Topic/subtopic query, for example 'Variables :: values and types'. Repeatable.",
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    settings = get_settings()
    if args.mode == "fixture":
        return run_fixture_check(settings, top_k=args.top_k)
    if not args.query:
        parser.error("--mode live requires at least one --query")
    return run_live_check(settings, book_id=args.book_id, queries=args.query, top_k=args.top_k)


if __name__ == "__main__":
    raise SystemExit(main())
