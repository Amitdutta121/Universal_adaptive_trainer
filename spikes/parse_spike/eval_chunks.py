"""Score each parser's chunks on the retrieval gold set, same embedder and metrics as the baseline.

**Spends API: embeds every chunk and the 66 queries (~1,000 short texts, well under a cent).**
Vectors are cached in out/emb_cache.npz by text hash, so re-runs are free.
Run with the app venv from the repo root:  python spikes/parse_spike/eval_chunks.py
"""

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pymupdf

from app.config import get_settings
from app.retrieval import get_embedder
from app.retrieval.eval import QueryRun, is_hit, mean_metrics

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "out"
PDF = ROOT / "books" / "Introduction_to_Data_Science_Using_Python_Agah.pdf"
GOLD = json.loads((ROOT / "tests/fixtures/retrieval_gold.json").read_text(encoding="utf-8"))
KS = (1, 3, 5, 10)
CACHE = OUT / "emb_cache.npz"


def toc_heading(toc: list, page: int) -> list[str]:
    """Heading path in force at the top of ``page``, from the PDF outline."""
    path: list[str] = []
    for level, title, start in toc:
        if start > page:
            break
        path = path[: level - 1] + [title]
    return path


def pymupdf_chunks(max_chars: int | None) -> list[dict]:
    doc = pymupdf.open(PDF)
    toc = doc.get_toc()
    chunks = []
    for i, page in enumerate(doc, start=1):
        text = re.sub(r"[ \t]+", " ", page.get_text()).strip()
        if not text:
            continue
        parts = [text]
        if max_chars:
            parts, buf = [], ""
            for para in re.split(r"\n(?=[A-Z0-9•])", text):
                if buf and len(buf) + len(para) > max_chars:
                    parts.append(buf)
                    buf = ""
                buf = f"{buf}\n{para}" if buf else para
            parts.append(buf)
        for part in parts:
            chunks.append({"headings": toc_heading(toc, i), "pages": [i, i], "text": part})
    return chunks


def corpora() -> dict[str, list[dict]]:
    out = {
        "pymupdf, 1 chunk per page": pymupdf_chunks(None),
        "pymupdf, ~700-char chunks": pymupdf_chunks(700),
    }
    for name, label in [
        ("docling", "docling HybridChunker"),
        ("unstructured_fast", "unstructured fast"),
        ("unstructured_hires", "unstructured hi_res"),
    ]:
        data = json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))
        out[label] = [c for c in data["chunks"] if c["pages"] and c["text"].strip()]
    return out


class CachedEmbedder:
    def __init__(self) -> None:
        self._inner = get_embedder(get_settings())
        self._cache: dict[str, np.ndarray] = dict(np.load(CACHE)) if CACHE.exists() else {}
        self.calls = 0

    def embed(self, texts: list[str]) -> np.ndarray:
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        missing = sorted({k: t for k, t in zip(keys, texts, strict=True) if k not in self._cache}.items())
        if missing:
            vectors = self._inner.embed([t for _, t in missing])
            self.calls += len(missing)
            for (k, _), v in zip(missing, vectors, strict=True):
                self._cache[k] = np.asarray(v, dtype=np.float32)
            np.savez(CACHE, **self._cache)
        m = np.vstack([self._cache[k] for k in keys])
        return m / np.linalg.norm(m, axis=1, keepdims=True)


def main() -> None:
    embedder = CachedEmbedder()
    entries = GOLD["entries"]
    q = embedder.embed([e["query"] for e in entries])
    rows = []
    for label, chunks in corpora().items():
        pages = [frozenset(range(c["pages"][0], c["pages"][1] + 1)) for c in chunks]
        for variant in ("text", "heading + text"):
            texts = [
                ("\n".join(c["headings"]) + "\n" + c["text"]) if variant != "text" else c["text"]
                for c in chunks
            ]
            sims = q @ embedder.embed(texts).T
            runs = []
            for e, row in zip(entries, sims, strict=True):
                rel = frozenset(e["relevant_pages"])
                top = np.argsort(-row)[: max(KS)]
                runs.append(
                    QueryRun(e["query"], rel, [pages[i] for i in top], sum(is_hit(p, rel) for p in pages))
                )
            m = mean_metrics(runs, KS)
            stu = mean_metrics([r for r, e in zip(runs, entries, strict=True) if e["kind"] == "student"], [5])[5]
            span = sum(len(p) for p in pages) / len(pages)
            rows.append((label, variant, len(chunks), span, m, stu))

    print(f"embedded {embedder.calls} new texts\n")
    print("| chunks from | embedded as | n | pages/chunk | R@5 | R@10 | nDCG@5 | nDCG@10 | MRR@10 | student MRR@5 |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for label, variant, n, span, m, stu in rows:
        print(
            f"| {label} | {variant} | {n} | {span:.2f} | {m[5]['recall']:.3f} | {m[10]['recall']:.3f} "
            f"| {m[5]['ndcg']:.3f} | {m[10]['ndcg']:.3f} | {m[10]['mrr']:.3f} | {stu['mrr']:.3f} |"
        )


if __name__ == "__main__":
    main()
