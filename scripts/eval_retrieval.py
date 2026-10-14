"""Score section retrieval against the gold set (tasks/todo.md, Task 2).

**Spends API: one embedding call per gold query (66 short strings, well under a cent).**
Reads the database (read-only) and needs the Agah book's sections embedded already
(``python -m scripts.embed_sections``):

    python -m scripts.eval_retrieval                        # the configured DATABASE_URL
    python -m scripts.eval_retrieval --db data/adaptive_trainer.db

Prints recall, precision, nDCG and MRR at k = 1, 3, 5, 10, scored by page overlap
(see :mod:`app.retrieval.eval`), then the same at k = 5 split by query kind.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.persistence.models import BookRow, BookSectionRow
from app.retrieval import SectionEmbeddingStore, SectionRetriever, get_embedder
from app.retrieval.eval import QueryRun, is_hit, mean_metrics, unit_pages

GOLD = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "retrieval_gold.json"
KS = (1, 3, 5, 10)


def table(rows: dict[str, dict[str, float]], first: str) -> str:
    lines = [
        f"| {first} | recall | precision | nDCG | MRR |",
        "|---|---|---|---|---|",
    ]
    for label, m in rows.items():
        lines.append(
            f"| {label} | {m['recall']:.3f} | {m['precision']:.3f} | {m['ndcg']:.3f} "
            f"| {m['mrr']:.3f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", help="SQLite file to read (default: DATABASE_URL)")
    parser.add_argument("--gold", type=Path, default=GOLD)
    args = parser.parse_args()

    settings = get_settings()
    url = f"sqlite:///{Path(args.db).as_posix()}" if args.db else settings.database_url
    gold = json.loads(args.gold.read_text(encoding="utf-8"))

    with Session(create_engine(url)) as session:
        book = session.scalars(
            select(BookRow)
            .where(BookRow.checksum_sha256 == gold["book"]["checksum_sha256"])
            .order_by(BookRow.id)
        ).first()
        if book is None:
            raise SystemExit("The gold set's book is not imported in this database.")
        index = {
            s.id: unit_pages(s.start_page, s.end_page)
            for s in session.scalars(
                select(BookSectionRow).where(BookSectionRow.book_id == book.id)
            )
        }
        retriever = SectionRetriever(
            session, SectionEmbeddingStore(session, get_embedder(settings))
        )

        runs: list[tuple[str, QueryRun]] = []
        for entry in gold["entries"]:
            relevant = frozenset(entry["relevant_pages"])
            hits = retriever.search(entry["query"], book_ids=[book.id], top_k=max(KS))
            runs.append(
                (
                    entry["kind"],
                    QueryRun(
                        query=entry["query"],
                        relevant=relevant,
                        ranked=[index[h.section_id] for h in hits],
                        n_relevant_units=sum(is_hit(p, relevant) for p in index.values()),
                    ),
                )
            )

    all_runs = [r for _, r in runs]
    overall = mean_metrics(all_runs, KS)
    unanswerable = sum(r.n_relevant_units == 0 for r in all_runs)
    print(
        f"book {book.id} ({book.title}), {len(index)} sections, {len(all_runs)} queries "
        f"({unanswerable} with no overlapping section), embedder {settings.embedding_model}\n"
    )
    print(table({str(k): overall[k] for k in KS}, "k"))
    kinds = sorted({kind for kind, _ in runs})
    by_kind = {
        f"{kind} (n={sum(k == kind for k, _ in runs)})": mean_metrics(
            [r for k, r in runs if k == kind], [5]
        )[5]
        for kind in kinds
    }
    print("\nk = 5, by query kind\n")
    print(table(by_kind, "kind"))


if __name__ == "__main__":
    main()
