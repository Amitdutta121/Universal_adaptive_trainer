"""Opt-in smoke coverage against the configured real structured LLM."""

from __future__ import annotations

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionType
from app.generation.service import GenerationService
from app.llm import get_structured_client
from app.persistence.database import create_db_engine, init_db

pytestmark = pytest.mark.integration


@pytest.mark.skipif(not Settings().llm_configured, reason="No configured LLM provider and API key")
def test_real_generation_smoke(tmp_path) -> None:
    """Generate and persist one multiple-choice question through OpenRouter."""
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'integration.db').as_posix()}",
        book_upload_dir=tmp_path / "books",
    )
    engine = create_db_engine(settings)
    init_db(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            book = docs.chunked_book(session, docs.minimal())
            version = TaxonomyImportService(session, settings).import_upload(
                filename="taxonomy.json",
                data=(
                    b'{"schema_version":"1","label":"Python","topics":['
                    b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
                ),
            )
            session.commit()

            row = GenerationService(
                session, client=get_structured_client(settings)
            ).generate_for_chunks(
                curriculum_version_id=version.id,
                topic_id=version.topics[0].id,
                subtopic_id=version.topics[0].subtopics[0].id,
                question_type=QuestionType.MULTIPLE_CHOICE,
                difficulty=Difficulty.EASY,
                source_chunk_ids=[book.chunks[0].id],
            )[0]

            assert row.prompt
            assert row.content
    finally:
        engine.dispose()
