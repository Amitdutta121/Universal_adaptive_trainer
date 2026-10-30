"""DOCX/PPTX: make a tiny file of each, then parse it with whichever library is importable.

make:   <venv-unstructured>/python office_check.py make <dir>
parse:  <venv>/python office_check.py parse <dir>
"""

import sys
from pathlib import Path

mode, d = sys.argv[1], Path(sys.argv[2])

if mode == "make":
    import docx
    from pptx import Presentation

    doc = docx.Document()
    doc.add_heading("5. Functions", level=1)
    doc.add_paragraph("A function is a block of code that only runs when called.")
    doc.add_heading("5.1. Void and Value Returning Functions", level=2)
    doc.add_paragraph("A void function does not return any value.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Operation", "Meaning"
    table.cell(1, 0).text, table.cell(1, 1).text = "<", "Less than"
    doc.save(d / "sample.docx")

    prs = Presentation()
    for title, body in [
        ("Recursion", "A function that calls itself."),
        ("Base case", "Stops the recursion."),
    ]:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    prs.save(d / "sample.pptx")
    print("made", d / "sample.docx", d / "sample.pptx")
else:
    for name in ("sample.docx", "sample.pptx"):
        path = d / name
        try:
            from docling.chunking import HybridChunker
            from docling.document_converter import DocumentConverter

            doc = DocumentConverter().convert(path).document
            for ch in HybridChunker().chunk(dl_doc=doc):
                pages = sorted({p.page_no for it in ch.meta.doc_items for p in it.prov})
                print(
                    f"docling {name}: headings={ch.meta.headings} pages={pages} text={ch.text[:80]!r}"
                )
        except ImportError:
            from unstructured.chunking.title import chunk_by_title
            from unstructured.partition.auto import partition

            els = partition(filename=str(path))
            print(
                f"unstructured {name}: elements={[(e.category, e.metadata.page_number) for e in els]}"
            )
            for ch in chunk_by_title(els):
                print(f"   chunk page={ch.metadata.page_number} text={ch.text[:80]!r}")
