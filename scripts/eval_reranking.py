"""Mixed-source retrieval gold set and reranker comparison (book PDF + video transcript).

The page-overlap gold set (``scripts/build_retrieval_gold.py``) covers one PDF; a transcript
chunk has no pages. This set grades chunks directly, so it scores any mix of sources.

    python -m scripts.eval_reranking label --version 14      # build the gold set (spends LLM)
    python -m scripts.eval_reranking score --version 14      # dense / hybrid / reranked

**label** spends API: one judge call per subtopic (about 30). For each subtopic it pools the
top ``POOL_K`` chunks of the dense, BM25 and hybrid rankings (TREC-style pooling, so every
chunk a reranker of the first ``CANDIDATES`` could promote is judged), and the ``judges``
model grades each one:

* 2 -- teaches the subtopic's skill with concrete detail a question could be built from
  (code, pseudocode, a worked example, a precise definition);
* 1 -- on topic but only mentions or summarises it, or covers a neighbouring skill;
* 0 -- unrelated, front matter, a table of contents, or course logistics.

The grades are written to ``tests/fixtures/retrieval_gold_<name>.json`` with the books'
checksums, so the set is only scored against the same imports.

**score** spends one embedding call per query and runs the rerankers locally (CPU). It reports
P@1, MRR@10 and recall@5 with grade 2 as relevant, and graded nDCG@5, per configuration.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: Chunks taken from each first-stage ranking into the judged pool.
POOL_K = 20
#: First-stage candidates a reranker reorders.
CANDIDATES = 20
#: Characters of a chunk the judge sees.
JUDGE_CHARS = 1200

RERANKERS = {
    "minilm": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "bge-base": "BAAI/bge-reranker-base",
    "bge-v2-m3": "BAAI/bge-reranker-v2-m3",
}
#: Where the rerankers are downloaded; ``RERANKER_DIR`` moves them off a full system drive.
RERANKER_DIR = Path(os.environ.get("RERANKER_DIR", ROOT / "models" / "rerankers"))
#: Only the PyTorch weights and tokenizer: repos also ship ONNX, OpenVINO and Flax copies.
RERANKER_FILES = ["*.json", "*.txt", "*.model", "model.safetensors"]

JUDGE_SYSTEM = (
    "You grade passages from a course's materials for one subtopic of its curriculum. "
    "Grade each passage: 2 if it teaches the subtopic's skill with concrete detail a quiz "
    "question could be built from (code, pseudocode, a worked example, a precise definition); "
    "1 if it is on topic but only mentions or summarises it, or covers a neighbouring skill; "
    "0 if it is unrelated, front matter, a table of contents, or course logistics. "
    "Judge only by what the passage itself says. Return one grade per passage number."
)


def _gold_path(name: str) -> Path:
    return ROOT / "tests" / "fixtures" / f"retrieval_gold_{name}.json"


def _session():
    from app.persistence.database import get_session_factory

    return get_session_factory()()


def _context(session, version_id: int):
    """The version, its subtopics, the course's book ids, and the chunk rows by id."""
    from sqlalchemy import select

    from app.persistence.models import BookRow, ChunkRow, CurriculumVersionRow
    from app.persistence.repositories import ChunkRepository

    version = session.get(CurriculumVersionRow, version_id)
    books = list(session.scalars(select(BookRow).where(BookRow.course_id == version.course_id)))
    book_ids = [book.id for book in books]
    current = ChunkRepository(session).current_ids(book_ids)
    chunks = {
        row.id: row for row in session.scalars(select(ChunkRow).where(ChunkRow.id.in_(current)))
    }
    subtopics = [s for topic in version.topics for s in topic.subtopics]
    return version, books, book_ids, chunks, subtopics


def _bm25_rank(query: str, chunks: dict, k: int) -> list[str]:
    from llama_index.core.schema import QueryBundle, TextNode
    from llama_index.retrievers.bm25 import BM25Retriever

    from app.retrieval.chunks import embedding_text

    nodes = [TextNode(id_=cid, text=embedding_text(row)) for cid, row in chunks.items()]
    retriever = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=k)
    return [hit.node.node_id for hit in retriever.retrieve(QueryBundle(query))]


def _first_stage(session, query: str, book_ids: list[int], *, hybrid: bool, k: int) -> list[str]:
    from app.generation.rounds import default_embedder
    from app.retrieval.chunks import ChunkEmbeddingStore, ChunkRetriever

    retriever = ChunkRetriever(
        session, ChunkEmbeddingStore(session, default_embedder()), hybrid=hybrid
    )
    return [hit.chunk_id for hit in retriever.search(query, book_ids=book_ids, top_k=k)]


def label(version_id: int, name: str) -> None:
    from pydantic import BaseModel

    from app.llm.client import get_structured_client
    from app.retrieval.chunks import embedding_text, subtopic_query_text
    from app.settings_store import ModelRole

    class _Grade(BaseModel):
        passage: int
        grade: int

    class _Grades(BaseModel):
        grades: list[_Grade]

    session = _session()
    version, books, book_ids, chunks, subtopics = _context(session, version_id)
    client = get_structured_client(role=ModelRole.JUDGES, temperature=0)
    out = {
        "course_id": version.course_id,
        "curriculum_version_id": version.id,
        "judge": client.description,
        "books": {
            str(book.id): {"title": book.title, "checksum": book.checksum_sha256} for book in books
        },
        "entries": [],
    }
    path = _gold_path(name)
    # Resumable: a subtopic already judged on the same imports is kept, not paid for twice.
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("books") == out["books"]:
            out["entries"] = previous["entries"]
    done = {entry["subtopic_id"] for entry in out["entries"]}
    for subtopic in subtopics:
        if subtopic.id in done:
            continue
        query = subtopic_query_text(subtopic)
        pool: list[str] = []
        for ranked in (
            _first_stage(session, query, book_ids, hybrid=False, k=POOL_K),
            _first_stage(session, query, book_ids, hybrid=True, k=POOL_K),
            _bm25_rank(query, chunks, POOL_K),
        ):
            pool += [cid for cid in ranked if cid not in pool]
        passages = "\n\n".join(
            f"[{i}] ({chunks[cid].book_id}) {embedding_text(chunks[cid])[:JUDGE_CHARS]}"
            for i, cid in enumerate(pool)
        )
        answer = client.complete_structured(
            system=JUDGE_SYSTEM,
            prompt=f"Subtopic: {query}\n\nPassages:\n{passages}",
            response_model=_Grades,
        )
        grades = {g.passage: max(0, min(2, g.grade)) for g in answer.grades}
        judged = {cid: grades.get(i, 0) for i, cid in enumerate(pool)}
        out["entries"].append({"subtopic_id": subtopic.id, "query": query, "judged": judged})
        path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
        top = sum(v == 2 for v in judged.values())
        print(f"{subtopic.name[:48]:48} pool {len(pool):3}  grade2 {top:3}")
    print(f"Wrote {path}")


class _Reranker:
    """A cross-encoder run locally with transformers; higher logit = more relevant."""

    def __init__(self, repo_id: str) -> None:
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        local = RERANKER_DIR / repo_id.replace("/", "--")
        if not local.is_dir():
            snapshot_download(
                repo_id=repo_id, local_dir=local, allow_patterns=RERANKER_FILES, token=False
            )
        self.tokenizer = AutoTokenizer.from_pretrained(local)
        self.model = AutoModelForSequenceClassification.from_pretrained(local).eval()
        self.torch = torch

    def scores(self, query: str, texts: list[str]) -> list[float]:
        with self.torch.no_grad():
            batch = self.tokenizer(
                [query] * len(texts),
                texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            return self.model(**batch).logits[:, 0].tolist()


def _metrics(ranked: list[str], judged: dict[str, int]) -> dict[str, float]:
    relevant = {cid for cid, grade in judged.items() if grade == 2}
    first = next((i for i, cid in enumerate(ranked[:10], 1) if cid in relevant), None)
    gains = [judged.get(cid, 0) for cid in ranked[:5]]
    ideal = sorted(judged.values(), reverse=True)[:5]
    dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gains))
    idcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return {
        "P@1": float(bool(ranked) and ranked[0] in relevant),
        "MRR@10": 1 / first if first else 0.0,
        "R@5": len(relevant & set(ranked[:5])) / len(relevant) if relevant else 0.0,
        "nDCG@5": dcg / idcg if idcg else 0.0,
    }


def score(version_id: int, name: str, rerankers: list[str]) -> None:
    from app.retrieval.chunks import embedding_text

    gold = json.loads(_gold_path(name).read_text(encoding="utf-8"))
    session = _session()
    _, books, book_ids, chunks, _ = _context(session, version_id)
    for book in books:
        expected = gold["books"].get(str(book.id), {}).get("checksum")
        if expected != book.checksum_sha256:
            sys.exit(f"Book {book.id} is not the import the gold set was judged on.")
    entries = [e for e in gold["entries"] if any(v == 2 for v in e["judged"].values())]
    print(
        f"{len(entries)} of {len(gold['entries'])} subtopics have a grade-2 chunk; scoring those.\n"
    )
    stages = {
        e["subtopic_id"]: {
            "dense": _first_stage(session, e["query"], book_ids, hybrid=False, k=CANDIDATES),
            "hybrid": _first_stage(session, e["query"], book_ids, hybrid=True, k=CANDIDATES),
        }
        for e in entries
    }
    rows: list[tuple[str, dict[str, float], float]] = []

    def run(label_: str, ranking) -> None:
        start = time.perf_counter()
        per = [_metrics(ranking(e), e["judged"]) for e in entries]
        seconds = (time.perf_counter() - start) / len(entries)
        rows.append((label_, {m: sum(p[m] for p in per) / len(per) for m in per[0]}, seconds))

    for stage in ("dense", "hybrid"):
        run(stage, lambda e, s=stage: stages[e["subtopic_id"]][s])
    for key in rerankers:
        model = _Reranker(RERANKERS[key])
        for stage in ("dense", "hybrid"):

            def reranked(e, s=stage, m=model):
                ids = stages[e["subtopic_id"]][s]
                texts = [embedding_text(chunks[cid]) for cid in ids]
                scored = m.scores(e["query"], texts)
                order = sorted(zip(scored, range(len(ids)), strict=True), reverse=True)
                return [ids[i] for _, i in order]

            run(f"{stage} + {key}", reranked)
    print(f"{'configuration':22} {'P@1':>6} {'MRR@10':>7} {'R@5':>6} {'nDCG@5':>7} {'s/query':>8}")
    for label_, m, seconds in rows:
        cells = " ".join(f"{m[k]:{w}.2f}" for k, w in (("P@1", 6), ("MRR@10", 7), ("R@5", 6)))
        print(f"{label_:22} {cells} {m['nDCG@5']:7.2f} {seconds:8.2f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["label", "score"])
    parser.add_argument("--version", type=int, required=True, help="curriculum version id")
    parser.add_argument("--name", default="cs220", help="gold set name")
    parser.add_argument("--rerankers", default="minilm,bge-base,bge-v2-m3")
    args = parser.parse_args(argv)
    if args.command == "label":
        label(args.version, args.name)
    else:
        score(args.version, args.name, [r for r in args.rerankers.split(",") if r])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
