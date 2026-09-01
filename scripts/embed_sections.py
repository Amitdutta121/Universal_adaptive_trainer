"""Build (or refresh) the section embedding index.

Embeds every section of every usable book into ``section_embeddings`` using the
configured ``EMBEDDING_MODEL`` through the OpenRouter key in ``.env``. Idempotent:
a section whose text is unchanged since it was last embedded is skipped.

    python -m scripts.embed_sections              # embed new / changed sections
    python -m scripts.embed_sections --dry-run    # report counts, no API calls
    python -m scripts.embed_sections --rebuild    # re-embed everything
    python -m scripts.embed_sections --book-id 3  # one book (repeatable)

Cost is tiny: ~1,600 sections is ~400k tokens, well under one US cent with
text-embedding-3-small.
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.persistence.database import init_db, session_scope
from app.retrieval import SectionEmbeddingStore, get_embedder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--book-id",
        type=int,
        action="append",
        default=[],
        help="Limit to this book id. Repeatable.",
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="Re-embed sections even if their text is unchanged."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be embedded without calling the provider.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    init_db()

    book_ids = args.book_id or None
    try:
        embedder = get_embedder(settings)
    except Exception:
        if not args.dry_run:
            raise
        # A dry run only needs the model name for the hash comparison.
        embedder = _ModelOnlyEmbedder(settings.embedding_model)

    with session_scope() as session:
        store = SectionEmbeddingStore(session, embedder)
        result = store.backfill(book_ids=book_ids, rebuild=args.rebuild, dry_run=args.dry_run)
        if not args.dry_run:
            session.commit()

    prefix = "DRY RUN: would have " if args.dry_run else ""
    print(f"{prefix}{result.summary()}  [model={embedder.model}]")
    return 0


class _ModelOnlyEmbedder:
    """Stand-in for ``--dry-run`` when no API key is configured: carries the
    model name so the hash comparison still runs, and refuses to embed."""

    def __init__(self, model: str) -> None:
        self.model = model

    def embed(self, texts):  # pragma: no cover - dry run never calls this
        raise RuntimeError("dry-run embedder cannot embed")


if __name__ == "__main__":
    sys.exit(main())
