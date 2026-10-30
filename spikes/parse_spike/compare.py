"""Compare the parse outputs in out/*.json against the book's own outline and the gold set.

Run with the app venv (needs pymupdf):  python spikes/parse_spike/compare.py <pdf> out/*.json
"""

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
GOLD = json.loads((ROOT / "tests/fixtures/retrieval_gold.json").read_text(encoding="utf-8"))
#: Pages the current importer puts in no section (docs/RETRIEVAL_BASELINE.md).
LOST = [10, 22, 37, 45, 50, 51, 52, 53, 54, 56, 65, 71, 77, 84, 85]
#: Three known sections: a phrase from their body, and the path the book's TOC gives them.
KNOWN = [
    ("nested inside another loop", ["4. Repetitions", "4.4. Nested Loops"]),
    ("Inheritance allows one class", ["11. Object Oriented Programming", "11.2 Inheritance"]),
    ("significant difference between two groups", ["15. Python and Statistics", "15.2 T-Test"]),
]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def main() -> None:
    pdf = pymupdf.open(sys.argv[1])
    toc = [norm(t) for _, t, _ in pdf.get_toc()]
    for path in sys.argv[2:]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        chunks = [c for c in data["chunks"] if c["pages"]]
        covered = {p for c in chunks for p in range(c["pages"][0], c["pages"][1] + 1)}
        sizes = sorted(len(c["text"]) for c in chunks)
        header_texts = {norm(h["text"]) for h in data["headers"]}
        levels = sorted({h["level"] for h in data["headers"]}, key=str)
        answerable = sum(bool(covered & set(e["relevant_pages"])) for e in GOLD["entries"])
        code_like = [c for c in chunks if re.search(r"\n\s+(print|return|Action)", c["text"])]
        print(f"\n=== {data['library']} ===")
        print(f"time: {data['seconds_total']}s (convert {data['seconds_convert']}s)")
        print(f"chunks: {len(chunks)}, chars median {sizes[len(sizes) // 2]} max {sizes[-1]}")
        print(
            f"pages covered: {len(covered)}/{pdf.page_count}; lost-intro pages covered: "
            f"{sum(p in covered for p in LOST)}/{len(LOST)}"
        )
        print(f"gold queries with an overlapping chunk: {answerable}/{len(GOLD['entries'])}")
        print(
            f"headers: {len(data['headers'])}, levels {levels}; TOC entries matched: "
            f"{sum(t in header_texts for t in toc)}/{len(toc)}"
        )
        print(f"tables: {len(data['tables'])}; chunks with indented code kept: {len(code_like)}")
        labels = sorted({lab for c in chunks for lab in c["labels"]})
        print(f"element labels: {labels}")
        for phrase, expected in KNOWN:
            hit = next((c for c in chunks if norm(phrase) in norm(c["text"])), None)
            got = hit["headings"] if hit else None
            print(f"  heading path for {expected[-1]!r}: {got} (TOC: {expected})")
            if hit:
                print("    pages", hit["pages"], "| text:", norm(hit["text"])[:300])


if __name__ == "__main__":
    main()
