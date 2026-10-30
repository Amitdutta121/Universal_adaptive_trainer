"""unstructured: partition_pdf + chunk_by_title, write normalised chunks as JSON.

Run with the spike venv:  <venv-unstructured>/python run_unstructured.py <pdf> <out.json> [fast|hi_res]
unstructured has no heading hierarchy for PDFs, so ``headings`` is the most recent Title
element before the chunk (what chunk_by_title splits on), a single level.
"""

import json
import sys
import time
from pathlib import Path

from unstructured.chunking.title import chunk_by_title
from unstructured.partition.pdf import partition_pdf

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
strategy = sys.argv[3] if len(sys.argv) > 3 else "fast"

t0 = time.perf_counter()
elements = partition_pdf(
    filename=str(pdf), strategy=strategy, infer_table_structure=(strategy == "hi_res")
)
t_partition = time.perf_counter() - t0
chunks_raw = chunk_by_title(elements, max_characters=1500, combine_text_under_n_chars=200)
t_total = time.perf_counter() - t0

chunks = []
title = None
for i, ch in enumerate(chunks_raw):
    origs = ch.metadata.orig_elements or [ch]
    first_title = next((e.text for e in origs if e.category == "Title"), None)
    if first_title:
        title = first_title
    pages = sorted({e.metadata.page_number for e in origs if e.metadata.page_number})
    chunks.append(
        {
            "i": i,
            "headings": [title] if title else [],
            "pages": [pages[0], pages[-1]] if pages else None,
            "labels": sorted({e.category for e in origs}),
            "text": ch.text,
        }
    )

headers = [
    {"text": e.text, "level": e.metadata.category_depth, "page": e.metadata.page_number}
    for e in elements
    if e.category == "Title"
]
tables = [e.metadata.text_as_html or e.text for e in elements if e.category == "Table"]
out.write_text(
    json.dumps(
        {
            "library": f"unstructured ({strategy})",
            "seconds_convert": round(t_partition, 1),
            "seconds_total": round(t_total, 1),
            "headers": headers,
            "tables": tables,
            "chunks": chunks,
        },
        indent=1,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
print(f"unstructured/{strategy}: {len(chunks)} chunks, {len(tables)} tables, {t_total:.1f}s")
