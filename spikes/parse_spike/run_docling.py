"""Docling: convert the PDF, chunk with HybridChunker, write normalised chunks as JSON.

Run with the spike venv, not the app's:  <venv-docling>/python run_docling.py <pdf> <out.json>
OCR is off: the Agah PDF is born-digital, and OCR only adds time.
"""

import json
import sys
import time
from pathlib import Path

from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
)

t0 = time.perf_counter()
doc = converter.convert(pdf).document
t_convert = time.perf_counter() - t0
chunker = HybridChunker()
chunks = []
for i, ch in enumerate(chunker.chunk(dl_doc=doc)):
    pages = sorted({p.page_no for item in ch.meta.doc_items for p in item.prov})
    chunks.append(
        {
            "i": i,
            "headings": list(ch.meta.headings or []),
            "pages": [pages[0], pages[-1]] if pages else None,
            "labels": sorted({str(item.label) for item in ch.meta.doc_items}),
            "text": ch.text,
        }
    )
t_total = time.perf_counter() - t0

headers = [
    {"text": it.text, "level": getattr(it, "level", None), "page": it.prov[0].page_no}
    for it, _ in doc.iterate_items()
    if str(it.label) in ("section_header", "title")
]
tables = [it.export_to_markdown(doc=doc) for it in doc.tables]
out.write_text(
    json.dumps(
        {
            "library": "docling",
            "seconds_convert": round(t_convert, 1),
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
print(f"docling: {len(chunks)} chunks, {len(tables)} tables, {t_total:.1f}s")
