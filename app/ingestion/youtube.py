"""A YouTube video as a source: its transcript becomes timestamped chunks (Phase 7, Task 30).

The video itself is never downloaded. Its transcript is fetched with ``youtube-transcript-api``;
when that fails (no captions, or YouTube blocking the server) the professor pastes the
transcript instead -- YouTube's "Show transcript" panel, WebVTT or SRT, as long as it carries
timestamps, because a clip needs them. Either way the text is cut into chunks at sentence
boundaries, each with start and end seconds, stored in ``chunks`` with ``source_kind=video``
beside a book's, so retrieval reads them the same way.

Everything is fetched and checked before the first row is written: a video that is gone, cannot
be embedded, or yields no transcript imports nothing. Whether a video can still be embedded is
asked of YouTube's oEmbed endpoint, at import and periodically after
(``app/jobs/video_availability.py``).
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import BookStatus, ChunkSourceKind, SourceFormat, VideoAvailability
from app.errors import DomainRuleError, InvalidBookDocumentError, TranscriptUnavailableError
from app.persistence.models import BookRow, ChunkRow
from app.persistence.repositories import BookRepository, ChunkRepository

logger = logging.getLogger(__name__)

#: A chunk closes at the first sentence end after this many words...
TARGET_WORDS = 160
#: ...or here, mid-sentence, for captions without punctuation.
MAX_WORDS = 320
#: Speaking rate assumed for the last caption when it states no duration.
_SECONDS_PER_WORD = 0.4

_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_OEMBED = "https://www.youtube.com/oembed"


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def parse_video_id(link: str) -> str:
    """The 11-character id of a YouTube link (watch, youtu.be, embed, shorts, live) or bare id.

    Raises:
        DomainRuleError: the text is not a YouTube video link.
    """
    text = link.strip()
    if _ID.match(text):
        return text
    parsed = urlparse(text if "//" in text else f"https://{text}")
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] in ("embed", "shorts", "live", "v"):
                candidate = parts[1]
    if not _ID.match(candidate):
        raise DomainRuleError(
            "That is not a YouTube video link.",
            detail="Use a link like https://www.youtube.com/watch?v=… or https://youtu.be/….",
        )
    return candidate


# ------------------------------------------------------------------ transcript


@dataclass(frozen=True)
class Segment:
    """One caption: its start, its duration when known, and its words."""

    start: float
    duration: float | None
    text: str


def fetch_transcript(video_id: str) -> list[Segment]:
    """The video's captions: English when there are any, else the first language listed.

    Raises:
        TranscriptUnavailableError: no captions, captions disabled, the video is unplayable,
            or YouTube refused the request (it often blocks cloud IPs).
    """
    from youtube_transcript_api import (
        NoTranscriptFound,
        YouTubeTranscriptApi,
        YouTubeTranscriptApiException,
    )

    api = YouTubeTranscriptApi()
    try:
        try:
            fetched = api.fetch(video_id, languages=("en", "en-US", "en-GB"))
        except NoTranscriptFound:
            fetched = next(iter(api.list(video_id))).fetch()
    except (YouTubeTranscriptApiException, StopIteration) as exc:
        logger.info("No transcript for %s: %s", video_id, type(exc).__name__)
        raise TranscriptUnavailableError(
            "YouTube did not give us this video's transcript. Paste it instead.",
            detail=type(exc).__name__,
        ) from exc
    except httpx.HTTPError as exc:  # pragma: no cover - the library uses requests today
        raise TranscriptUnavailableError(
            "YouTube could not be reached. Paste the transcript instead.", detail=str(exc)
        ) from exc
    return [Segment(s.start, s.duration, s.text) for s in fetched.snippets]


_TS = r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"
_CUE = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}")
_STAMPED = re.compile(rf"^\s*\[?{_TS}\]?(?:\s+(.*))?$")
_TAG = re.compile(r"<[^>]+>")


def _seconds(hours: str | None, minutes: str, seconds: str, fraction: str | None) -> float:
    value = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
    return value + (int(fraction.ljust(3, "0")) / 1000 if fraction else 0.0)


def parse_pasted_transcript(text: str) -> list[Segment]:
    """Captions from a pasted transcript with timestamps.

    Reads YouTube's "Show transcript" copy (a ``1:05`` line, or ``1:05 text``), WebVTT and SRT.

    Raises:
        DomainRuleError: no timestamped text was found.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[tuple[float, float | None, list[str]]] = []
    for n, raw in enumerate(lines):
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("NOTE", "Kind:", "Language:")):
            continue
        # An SRT cue number, just before its timing line.
        if line.isdigit() and n + 1 < len(lines) and "-->" in lines[n + 1]:
            continue
        if cue := _CUE.match(line):
            start = _seconds(*cue.groups()[:4])
            segments.append((start, _seconds(*cue.groups()[4:]) - start, []))
        elif stamped := _STAMPED.match(line):
            start = _seconds(*stamped.groups()[:4])
            segments.append((start, None, [stamped.group(5)] if stamped.group(5) else []))
        elif segments:
            segments[-1][2].append(_TAG.sub("", line))
    found = [
        Segment(start, duration, " ".join(words))
        for start, duration, words in segments
        if " ".join(words).strip()
    ]
    if not found:
        raise DomainRuleError(
            "No timestamped text was found in the pasted transcript.",
            detail="On YouTube open … > Show transcript and copy it with its timestamps, "
            "or paste a .vtt or .srt file's text.",
        )
    return sorted(found, key=lambda segment: segment.start)


# ------------------------------------------------------------------ chunking


@dataclass(frozen=True)
class TimedChunk:
    text: str
    start: float
    end: float


_SENTENCE_END = re.compile(r"[.?!][\"')\]]*$")


def _timed_words(segments: list[Segment]) -> tuple[list[tuple[str, float]], float]:
    """Every word with an interpolated start time, and the end of the last caption."""
    cleaned = [
        (s.start, s.duration, html.unescape(s.text).replace("\n", " ").split())
        for s in sorted(segments, key=lambda segment: segment.start)
    ]
    cleaned = [item for item in cleaned if item[2]]
    words: list[tuple[str, float]] = []
    end = 0.0
    for i, (start, duration, tokens) in enumerate(cleaned):
        start = max(start, end)
        # Captions overlap (each stays up until the next has shown), so a caption ends where
        # the next one starts.
        stop = start + duration if duration else start + len(tokens) * _SECONDS_PER_WORD
        if i + 1 < len(cleaned):
            stop = min(stop, cleaned[i + 1][0]) if duration else cleaned[i + 1][0]
        stop = max(stop, start)
        step = (stop - start) / len(tokens)
        words.extend((token, start + k * step) for k, token in enumerate(tokens))
        end = max(end, stop)
    return words, end


def chunk_segments(
    segments: list[Segment], *, target_words: int = TARGET_WORDS, max_words: int = MAX_WORDS
) -> list[TimedChunk]:
    """Captions cut into chunks that end on a sentence end, with monotonic, non-overlapping times.

    A chunk runs from its first word's time to the next chunk's first word (the last chunk, to
    the end of the last caption), so consecutive chunks meet exactly and a clip of one never
    starts mid-sentence.
    """
    words, last_end = _timed_words(segments)
    groups: list[list[tuple[str, float]]] = []
    current: list[tuple[str, float]] = []
    for word in words:
        current.append(word)
        sentence_end = _SENTENCE_END.search(word[0]) is not None
        if (len(current) >= target_words and sentence_end) or len(current) >= max_words:
            groups.append(current)
            current = []
    if current:
        # A short tail joins the chunk before it rather than standing alone.
        if groups and len(current) < target_words // 4:
            groups[-1].extend(current)
        else:
            groups.append(current)
    chunks: list[TimedChunk] = []
    for i, group in enumerate(groups):
        end = groups[i + 1][0][1] if i + 1 < len(groups) else max(last_end, group[-1][1])
        chunks.append(
            TimedChunk(
                text=" ".join(token for token, _ in group),
                start=round(group[0][1], 2),
                end=round(end, 2),
            )
        )
    return chunks


# ------------------------------------------------------------------ availability

AvailabilityCheck = Callable[[str], tuple[VideoAvailability, str | None]]


def check_availability(video_id: str) -> tuple[VideoAvailability, str | None]:
    """Whether the video can be embedded, and its title, from YouTube's oEmbed endpoint.

    oEmbed answers 200 for a public embeddable video, 401/403 when it is private or its owner
    turned embedding off (a clip cannot play in either case), and 400/404 when it is deleted
    or never existed. Anything else, network errors included, is ``UNKNOWN``.
    """
    try:
        response = httpx.get(
            _OEMBED, params={"url": watch_url(video_id), "format": "json"}, timeout=10.0
        )
    except httpx.HTTPError:
        return VideoAvailability.UNKNOWN, None
    if response.status_code == 200:
        try:
            title = response.json().get("title")
        except ValueError:
            title = None
        return VideoAvailability.AVAILABLE, title if isinstance(title, str) else None
    if response.status_code in (401, 403):
        return VideoAvailability.NOT_EMBEDDABLE, None
    if response.status_code in (400, 404):
        return VideoAvailability.UNAVAILABLE, None
    return VideoAvailability.UNKNOWN, None


# ------------------------------------------------------------------ import


TranscriptFetch = Callable[[str], list[Segment]]


class YouTubeImportService:
    """Imports a YouTube video's transcript as a chunked, timestamped source."""

    def __init__(
        self,
        session: Session,
        *,
        fetch: TranscriptFetch = fetch_transcript,
        check: AvailabilityCheck = check_availability,
    ) -> None:
        self._session = session
        self._fetch = fetch
        self._check = check

    def import_video(
        self,
        link: str,
        *,
        title: str | None = None,
        transcript: str | None = None,
        course_id: int | None = None,
    ) -> BookRow:
        """Check, fetch (or read the pasted transcript), chunk and store one video.

        The same video and transcript again returns the existing source; a different
        transcript for a video already in the course becomes its next chunk version.

        Raises:
            DomainRuleError: not a YouTube link, the video is gone or cannot be embedded, or the
                pasted transcript has no timestamps.
            TranscriptUnavailableError: no transcript was pasted and none could be fetched.
            InvalidBookDocumentError: the transcript holds no words.
        """
        video_id = parse_video_id(link)
        availability, found_title = self._check(video_id)
        if availability is VideoAvailability.UNAVAILABLE:
            raise DomainRuleError("This video is private, deleted or does not exist.")
        if availability is VideoAvailability.NOT_EMBEDDABLE:
            raise DomainRuleError(
                "This video cannot be played inside the app: it is private or its owner "
                "turned off embedding."
            )
        pasted = bool(transcript and transcript.strip())
        segments = parse_pasted_transcript(transcript or "") if pasted else self._fetch(video_id)
        chunks = chunk_segments(segments)
        if not chunks:
            raise InvalidBookDocumentError("The transcript has no words to import.")
        digest = hashlib.sha256("\n".join(c.text for c in chunks).encode("utf-8")).hexdigest()
        now = datetime.now(UTC)

        book = self._existing(video_id, course_id)
        if book is not None and book.checksum_sha256 == digest:
            logger.info("Video %s is already book %s with this transcript", video_id, book.id)
            return book
        if book is None:
            book = BookRepository(self._session).add(
                BookRow(
                    course_id=course_id,
                    title=(title or "").strip() or found_title or f"YouTube video {video_id}",
                    original_filename=watch_url(video_id),
                    source_format=SourceFormat.YOUTUBE,
                    status=BookStatus.IMPORTED,
                    video_id=video_id,
                )
            )
            self._session.flush()
        book.checksum_sha256 = digest
        book.producer = "pasted transcript" if pasted else "YouTube transcript"
        book.video_availability = availability
        book.availability_checked_at = now
        book.imported_at = now
        version = ChunkRepository(self._session).add_version(
            book,
            [
                ChunkRow(
                    text=chunk.text,
                    source_kind=ChunkSourceKind.VIDEO,
                    start_seconds=chunk.start,
                    end_seconds=chunk.end,
                    heading_path=[],
                )
                for chunk in chunks
            ],
        )
        logger.info(
            "Video %s: book %s version %d, %d chunk(s)", video_id, book.id, version, len(chunks)
        )
        return book

    def _existing(self, video_id: str, course_id: int | None) -> BookRow | None:
        return self._session.scalars(
            select(BookRow)
            .where(BookRow.video_id == video_id, BookRow.course_id == course_id)
            .order_by(BookRow.id)
        ).first()
