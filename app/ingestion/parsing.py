"""Turning an uploaded book file into chunks (Task 5, ``docs/PARSE_SPIKE.md``).

Two parsers, chosen by ``Settings.book_parser``:

``docling``
    The parser chosen at Checkpoint A: layout-aware chunks (``HybridChunker``) that keep
    tables and code with their explanation, and one API for PDF, DOCX and PPTX. Heavy
    (CPU torch plus ~500 MB of models on first run), so it is the optional ``parse`` extra.
``pages``
    Page text packed into chunks of up to :data:`MAX_FALLBACK_CHARS`. PDF only. Already a
    dependency, so it is what runs when Docling is not installed, and in the test suite.

For a PDF the heading path comes from the PDF's own outline (``get_toc``), which matched
all 66 table-of-contents entries in the spike; Docling's own heading levels are flat. A
DOCX or PPTX takes Docling's headings as they are. A PDF with no outline gets Docling's
leaf heading, or no heading path at all from the fallback parser.

Nothing here writes rows: :class:`~app.ingestion.service.BookImportService` does, and
only once a file has parsed into at least one chunk with text.
"""

from __future__ import annotations

import functools
import importlib.util
import io
import logging
import re
import zipfile
from dataclasses import dataclass
from typing import Any

import pymupdf

from app.domain.enums import SourceFormat
from app.errors import InvalidBookDocumentError, UnsupportedFileError

logger = logging.getLogger(__name__)

PARSER_DOCLING = "docling"
PARSER_PAGES = "pages"

#: The fallback parser's chunk size; close to the ~700-char chunks the spike measured.
MAX_FALLBACK_CHARS = 1200

#: The formats each parser reads.
FORMATS_BY_PARSER: dict[str, frozenset[SourceFormat]] = {
    PARSER_DOCLING: frozenset(
        {SourceFormat.BOOK_PDF, SourceFormat.BOOK_DOCX, SourceFormat.BOOK_PPTX}
    ),
    PARSER_PAGES: frozenset({SourceFormat.BOOK_PDF}),
}

#: The part an Office file must contain to be the format its extension claims.
_OFFICE_MAIN_PART = {
    SourceFormat.BOOK_DOCX: "word/document.xml",
    SourceFormat.BOOK_PPTX: "ppt/presentation.xml",
}


@dataclass(frozen=True)
class ParsedChunk:
    text: str
    page_start: int | None
    page_end: int | None
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class ParsedBook:
    #: From the file's own metadata; ``None`` when it states none (never guessed here).
    title: str | None
    author: str | None
    page_count: int | None
    parser: str
    chunks: list[ParsedChunk]


def docling_available() -> bool:
    return importlib.util.find_spec("docling") is not None


def resolve_parser(setting: str) -> str:
    """The parser to run for ``Settings.book_parser`` (``auto``, ``docling`` or ``pages``)."""
    if setting == PARSER_PAGES:
        return PARSER_PAGES
    if docling_available():
        return PARSER_DOCLING
    if setting == PARSER_DOCLING:
        logger.warning("BOOK_PARSER=docling but Docling is not installed; using page chunks")
    return PARSER_PAGES


def check_readable(data: bytes, source_format: SourceFormat, parser: str) -> None:
    """The quick checks, before anything is stored: the parser reads it, and it opens.

    Raises:
        UnsupportedFileError: the active parser does not read this format.
        InvalidBookDocumentError: the file is not what its extension says.
    """
    if source_format not in FORMATS_BY_PARSER[parser]:
        raise UnsupportedFileError(
            f"{source_format.value.removeprefix('book_').upper()} import needs Docling.",
            detail="Install the 'parse' extra (pip install -e .[parse]), or upload a PDF.",
        )
    if source_format is SourceFormat.BOOK_PDF:
        _open_pdf(data).close()
        return
    part = _OFFICE_MAIN_PART.get(source_format)
    if part is not None:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if part not in archive.namelist():
                    raise zipfile.BadZipFile(f"missing {part}")
        except zipfile.BadZipFile as exc:
            raise InvalidBookDocumentError(
                f"This file could not be read as a {source_format.value[5:].upper()} file.",
                detail=str(exc),
            ) from exc


def parse_book(
    data: bytes, *, filename: str, source_format: SourceFormat, parser: str
) -> ParsedBook:
    """Parse a book file into chunks, in reading order.

    Raises:
        UnsupportedFileError, InvalidBookDocumentError: as :func:`check_readable`, or no
            chunk with text came out (e.g. a scanned PDF with no text layer).
    """
    check_readable(data, source_format, parser)
    title = author = None
    page_count: int | None = None
    toc: list[tuple[int, int, str]] = []
    if source_format is SourceFormat.BOOK_PDF:
        doc = _open_pdf(data)
        try:
            title = str(doc.metadata.get("title") or "").strip() or None
            author = str(doc.metadata.get("author") or "").strip() or None
            page_count = doc.page_count
            toc = [
                (int(level), int(page), str(text).strip())
                for level, text, page in doc.get_toc(simple=True)
            ]
            chunks = _page_chunks(doc, toc) if parser == PARSER_PAGES else None
        finally:
            doc.close()
    else:
        chunks = None
    if chunks is None:
        chunks, docling_pages = _docling_chunks(data, filename, toc)
        page_count = page_count or docling_pages

    chunks = [chunk for chunk in chunks if chunk.text.strip()]
    if not chunks:
        raise InvalidBookDocumentError(
            "No text could be read from this file.",
            detail="It may be a scanned document without a text layer.",
        )
    return ParsedBook(
        title=title, author=author, page_count=page_count, parser=parser, chunks=chunks
    )


# -- outline --------------------------------------------------------------------


@dataclass(frozen=True)
class _OutlinePath:
    page: int
    title: str
    path: tuple[str, ...]


def _outline_paths(toc: list[tuple[int, int, str]]) -> list[_OutlinePath]:
    """Every outline entry with the full path of titles above and including it."""
    stack: list[str] = []
    paths: list[_OutlinePath] = []
    for level, page, title in toc:
        if not title or level < 1:
            continue
        del stack[level - 1 :]
        stack.append(title)
        paths.append(_OutlinePath(page=page, title=title, path=tuple(stack)))
    return paths


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".:").casefold()


def _path_at_page(paths: list[_OutlinePath], page: int | None) -> tuple[str, ...]:
    """The path of the last outline entry that starts on or before ``page``."""
    if page is None:
        return ()
    found: tuple[str, ...] = ()
    for entry in paths:
        if 0 < entry.page <= page:
            found = entry.path
    return found


def _heading_path(
    paths: list[_OutlinePath], headings: list[str], page: int | None
) -> tuple[str, ...]:
    """A chunk's path: its leaf heading matched to the outline, else where its page sits."""
    if not paths:
        return tuple(headings)
    if headings:
        leaf = _normalise(headings[-1])
        matches = [entry for entry in paths if _normalise(entry.title) == leaf]
        if matches:
            return min(matches, key=lambda entry: abs(entry.page - (page or entry.page))).path
    return _path_at_page(paths, page)


# -- parsers --------------------------------------------------------------------


def _open_pdf(data: bytes) -> pymupdf.Document:
    try:
        return pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:  # pymupdf raises its own, undocumented exception types
        raise InvalidBookDocumentError(
            "This file could not be read as a PDF.", detail=str(exc)
        ) from exc


def _page_chunks(doc: pymupdf.Document, toc: list[tuple[int, int, str]]) -> list[ParsedChunk]:
    """Each page's paragraphs, packed into chunks of up to :data:`MAX_FALLBACK_CHARS`.

    A single paragraph longer than that stays whole; the embedder truncates it.
    """
    paths = _outline_paths(toc)
    chunks: list[ParsedChunk] = []
    for index in range(doc.page_count):
        page = index + 1
        heading_path = _path_at_page(paths, page)
        # PyMuPDF's text blocks are its paragraphs; block type 1 is an image.
        paragraphs = [
            " ".join(str(block[4]).split())
            for block in doc[index].get_text("blocks", sort=True)
            if block[6] == 0
        ]
        buffer = ""
        for paragraph in filter(None, paragraphs):
            if buffer and len(buffer) + len(paragraph) + 2 > MAX_FALLBACK_CHARS:
                chunks.append(ParsedChunk(buffer, page, page, heading_path))
                buffer = ""
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if buffer:
            chunks.append(ParsedChunk(buffer, page, page, heading_path))
    return chunks


@functools.cache
def _docling_converter() -> Any:
    """One converter per process: building it loads the layout models."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    # OCR off: textbooks are born-digital, and OCR only adds time (PARSE_SPIKE.md).
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


#: ``HybridChunker``'s own default tokenizer, named so it can be loaded from the local cache.
_CHUNKER_TOKENIZER = "sentence-transformers/all-MiniLM-L6-v2"


@functools.cache
def _docling_chunker() -> Any:
    """The chunker, with its tokenizer from the local cache when it is there.

    The default ``HybridChunker()`` asks the Hugging Face Hub about the tokenizer every time it
    is built, so an import failed whenever the Hub was unreachable or the stored HF token was
    invalid, even with the tokenizer cached. Only a missing tokenizer is downloaded.
    """
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

    try:
        tokenizer = HuggingFaceTokenizer.from_pretrained(
            model_name=_CHUNKER_TOKENIZER, local_files_only=True
        )
    except OSError:
        tokenizer = HuggingFaceTokenizer.from_pretrained(model_name=_CHUNKER_TOKENIZER)
    return HybridChunker(tokenizer=tokenizer)


def _docling_chunks(
    data: bytes, filename: str, toc: list[tuple[int, int, str]]
) -> tuple[list[ParsedChunk], int | None]:
    from docling.datamodel.base_models import DocumentStream

    try:
        result = _docling_converter().convert(
            DocumentStream(name=filename, stream=io.BytesIO(data))
        )
    except Exception as exc:  # Docling wraps parser failures in several exception types
        raise InvalidBookDocumentError("This file could not be parsed.", detail=str(exc)) from exc
    document = result.document
    paths = _outline_paths(toc)
    chunks: list[ParsedChunk] = []
    for chunk in _docling_chunker().chunk(dl_doc=document):
        pages = sorted({prov.page_no for item in chunk.meta.doc_items for prov in item.prov})
        start, end = (pages[0], pages[-1]) if pages else (None, None)
        headings = list(chunk.meta.headings or [])
        chunks.append(ParsedChunk(chunk.text, start, end, _heading_path(paths, headings, start)))
    page_count = len(document.pages) or None
    return chunks, page_count
