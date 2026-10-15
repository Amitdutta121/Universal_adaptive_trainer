"""Score chunk retrieval against the gold set (tasks/todo.md, Tasks 2 and 6).

**Spends API: one embedding call per gold query (66 short strings, well under a cent), plus
embedding any of the book's current chunks not yet embedded in the configured model (about
200 short texts, once).** Reads the database and needs the Agah book imported with chunks;
it writes only ``chunk_embeddings``. (The Task 2 section baseline was scored with the
section retriever, retired in Task 10; its numbers are in ``docs/RETRIEVAL_BASELINE.md``.)

    python -m scripts.eval_retrieval                        # the configured DATABASE_URL
    python -m scripts.eval_retrieval --db data/adaptive_trainer.db
    python -m scripts.eval_retrieval --mode hybrid           # dense + BM25, fused by RRF

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
from app.persistence.models import BookRow
from app.persistence.repositories import ChunkRepository
from app.retrieval import ChunkEmbeddingStore, ChunkRetriever, get_embedder
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
    parser.add_argument("--mode", choices=("dense", "hybrid"), default="dense")
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
            c.id: unit_pages(c.page_start, c.page_end)
            for c in ChunkRepository(session).list_for_book(book.id)
        }
        if not index:
            raise SystemExit("The gold set's book has no chunks: re-import it.")
        retriever = ChunkRetriever(
            session,
            ChunkEmbeddingStore(session, get_embedder(settings)),
            hybrid=args.mode == "hybrid",
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
                        ranked=[index[h.chunk_id] for h in hits],
                        n_relevant_units=sum(is_hit(p, relevant) for p in index.values()),
                    ),
                )
            )

    all_runs = [r for _, r in runs]
    overall = mean_metrics(all_runs, KS)
    unanswerable = sum(r.n_relevant_units == 0 for r in all_runs)
    print(
        f"book {book.id} ({book.title}), {len(index)} chunks, {len(all_runs)} queries "
        f"({unanswerable} with no overlapping unit), embedder {settings.embedding_model}, "
        f"mode {args.mode}\n"
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
