"""Upload validation and file retention.

The uploaded book document is always kept. It is the exact input that produced
the stored rows, so keeping it makes an import reproducible and lets a corrected
document be diffed against the one it replaces.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import uuid
from pathlib import Path

from app.config import Settings
from app.domain.enums import SourceFormat
from app.errors import FileTooLargeError, UnsupportedFileError

logger = logging.getLogger(__name__)

#: Accepted extensions. Structured JSON declares its own structure directly; a
#: PDF is turned into that same declared shape by ``app.ingestion.pdf`` before
#: validation (ADR-048) -- it is not extracted here, only routed.
FORMAT_BY_EXTENSION: dict[str, SourceFormat] = {
    ".json": SourceFormat.BOOK_JSON,
    ".pdf": SourceFormat.BOOK_PDF,
}

SUPPORTED_EXTENSIONS = tuple(sorted(FORMAT_BY_EXTENSION))

#: Raw book formats this application still does not convert. They get an
#: explanation of what to supply instead, rather than a bare refusal.
_RAW_BOOK_EXTENSIONS = {".epub", ".md", ".markdown", ".txt", ".html", ".htm"}

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def format_for_filename(filename: str) -> SourceFormat:
    """Map a filename to its source format.

    Raises:
        UnsupportedFileError: if the extension is not one this system reads. A raw
            book file gets an explanation of what to supply instead.
    """
    extension = Path(filename).suffix.lower()
    source_format = FORMAT_BY_EXTENSION.get(extension)
    if source_format is not None:
        return source_format

    if extension in _RAW_BOOK_EXTENSIONS:
        raise UnsupportedFileError(
            f"{extension} files cannot be imported directly.",
            detail=(
                "This application imports structured book JSON only, so a book's structure is "
                "always declared rather than guessed. Supply a book JSON document that lists "
                "the chapters, sections and section text -- see the document shape on this page."
            ),
        )
    raise UnsupportedFileError(
        f"{extension or 'This file type'} is not a supported textbook format.",
        detail=f"Supported formats: {', '.join(SUPPORTED_EXTENSIONS)}.",
    )


def validate_upload(filename: str, data: bytes, settings: Settings) -> SourceFormat:
    """Check an upload's name and size before anything is stored.

    Structural validation is separate and happens in
    :func:`app.ingestion.schema.parse_book_document`; this is only the cheap
    front gate.

    Raises:
        UnsupportedFileError: unknown extension, or an empty file.
        FileTooLargeError: file exceeds the configured limit.
    """
    source_format = format_for_filename(filename)

    if not data:
        raise UnsupportedFileError(
            "The uploaded file is empty.",
            detail="Choose a file with content and try again.",
        )

    limit_bytes = settings.max_book_upload_mb * 1024 * 1024
    if len(data) > limit_bytes:
        raise FileTooLargeError(
            f"This file is larger than the {settings.max_book_upload_mb} MB limit.",
            detail=f"The upload was {len(data) / (1024 * 1024):.1f} MB.",
        )

    return source_format


def safe_filename(original: str) -> str:
    """Build a collision-free, filesystem-safe name that keeps the original visible.

    A random prefix guarantees uniqueness, so two uploads of ``book.json`` never
    overwrite one another.
    """
    name = unicodedata.normalize("NFKD", Path(original).name)
    cleaned = _UNSAFE_CHARS.sub("_", name).strip("._") or "upload"
    return f"{uuid.uuid4().hex[:12]}_{cleaned[:120]}"


def checksum(data: bytes) -> str:
    """SHA-256 of the uploaded bytes, for de-duplication and integrity checks."""
    return hashlib.sha256(data).hexdigest()


def store_upload(data: bytes, original_filename: str, settings: Settings) -> tuple[str, Path]:
    """Write an upload into the configured directory.

    Returns:
        The stored filename and its absolute path.
    """
    directory = Path(settings.book_upload_dir)
    directory.mkdir(parents=True, exist_ok=True)

    stored_name = safe_filename(original_filename)
    destination = directory / stored_name
    destination.write_bytes(data)
    logger.info("Stored upload %r as %s (%d bytes)", original_filename, stored_name, len(data))
    return stored_name, destination


def resolve_stored_path(stored_filename: str, settings: Settings) -> Path:
    """Absolute path of a retained upload."""
    return Path(settings.book_upload_dir) / stored_filename
