"""YouTube sources: transcript fetch, paste fallback, availability check (Phase 7, Task 30).

No test reaches YouTube: the fetcher and the oEmbed check are replaced, or the libraries they
call are.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import SourceFormat, VideoAvailability
from app.errors import DomainRuleError, TranscriptUnavailableError
from app.ingestion import youtube
from app.ingestion.youtube import (
    Segment,
    check_availability,
    fetch_transcript,
    parse_pasted_transcript,
    parse_video_id,
)
from app.jobs.video_availability import check_video_sources
from app.persistence.models import BookRow, ChunkRow
from app.web.routes.api.books import get_youtube_check, get_youtube_fetch

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "lecture_transcript.json").read_text(encoding="utf-8")
)
SEGMENTS = [Segment(s["start"], s["duration"], s["text"]) for s in FIXTURE["segments"]]
VIDEO_ID = "AbCdEfGhIjK"
URL = f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42s"

PANEL_COPY = """0:00
Welcome back. Today we look at loops.
0:04
A for loop repeats a block of code.
1:02:05
That is all for today.
"""


# ------------------------------------------------------------------ links and pasted text


@pytest.mark.parametrize(
    "link",
    [
        VIDEO_ID,
        URL,
        f"youtube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=abc",
        f"https://m.youtube.com/watch?feature=share&v={VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}?start=3",
    ],
)
def test_every_youtube_link_shape_gives_the_video_id(link: str) -> None:
    assert parse_video_id(link) == VIDEO_ID


@pytest.mark.parametrize(
    "link", ["https://vimeo.com/12345", "https://www.youtube.com/watch?v=short", "hello"]
)
def test_a_link_that_is_not_a_youtube_video_is_refused(link: str) -> None:
    with pytest.raises(DomainRuleError):
        parse_video_id(link)


def test_the_youtube_transcript_panel_copy_is_read() -> None:
    segments = parse_pasted_transcript(PANEL_COPY)

    assert [(s.start, s.text) for s in segments] == [
        (0.0, "Welcome back. Today we look at loops."),
        (4.0, "A for loop repeats a block of code."),
        (3725.0, "That is all for today."),
    ]


def test_timestamps_on_the_same_line_are_read() -> None:
    segments = parse_pasted_transcript("0:01 Hello there.\n[0:05] Second line.\n")

    assert [(s.start, s.text) for s in segments] == [(1.0, "Hello there."), (5.0, "Second line.")]


def test_webvtt_and_srt_are_read_with_their_cue_durations() -> None:
    vtt = (
        "WEBVTT\n\n00:00:01.500 --> 00:00:04.000\nHello <c>there</c>.\n\n"
        "00:00:04.000 --> 00:00:06.250\nNext.\n"
    )
    srt = (
        "1\n00:00:01,500 --> 00:00:04,000\nHello there.\n\n"
        "2\n00:00:04,000 --> 00:00:06,250\nNext.\n"
    )

    for text in (vtt, srt):
        segments = parse_pasted_transcript(text)
        assert [(s.start, s.duration, s.text) for s in segments] == [
            (1.5, 2.5, "Hello there."),
            (4.0, 2.25, "Next."),
        ]


def test_a_paste_without_timestamps_is_refused() -> None:
    with pytest.raises(DomainRuleError, match="timestamped"):
        parse_pasted_transcript("Just the words, with no times at all.")


# ------------------------------------------------------------------ fetching (library mocked)


def test_a_fetch_the_library_refuses_becomes_transcript_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from youtube_transcript_api import TranscriptsDisabled, YouTubeTranscriptApi

    def refuse(self, video_id, languages=("en",)):
        raise TranscriptsDisabled(video_id)

    monkeypatch.setattr(YouTubeTranscriptApi, "fetch", refuse)

    with pytest.raises(TranscriptUnavailableError):
        fetch_transcript(VIDEO_ID)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, VideoAvailability.AVAILABLE),
        (401, VideoAvailability.NOT_EMBEDDABLE),
        (403, VideoAvailability.NOT_EMBEDDABLE),
        (404, VideoAvailability.UNAVAILABLE),
        (400, VideoAvailability.UNAVAILABLE),
        (503, VideoAvailability.UNKNOWN),
    ],
)
def test_oembed_answers_map_to_availability(
    monkeypatch: pytest.MonkeyPatch, status: int, expected: VideoAvailability
) -> None:
    def get(url, params=None, timeout=None):
        assert params["url"].endswith(VIDEO_ID)
        body = {"title": "Loops in Python"} if status == 200 else None
        return httpx.Response(status, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(youtube.httpx, "get", get)

    availability, title = check_availability(VIDEO_ID)
    assert availability is expected
    assert title == ("Loops in Python" if status == 200 else None)


def test_youtube_unreachable_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(url, params=None, timeout=None):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(youtube.httpx, "get", get)
    assert check_availability(VIDEO_ID) == (VideoAvailability.UNKNOWN, None)


# ------------------------------------------------------------------ the endpoint


class Fakes:
    def __init__(self) -> None:
        self.availability = VideoAvailability.AVAILABLE
        self.fetched: list[str] = []
        self.fail_fetch = False

    def fetch(self, video_id: str) -> list[Segment]:
        self.fetched.append(video_id)
        if self.fail_fetch:
            raise TranscriptUnavailableError("YouTube did not give us this video's transcript.")
        return SEGMENTS

    def check(self, video_id: str) -> tuple[VideoAvailability, str | None]:
        return self.availability, "Loops in Python"


@pytest.fixture
def fakes(configured_app: FastAPI) -> Iterator[Fakes]:
    fake = Fakes()
    configured_app.dependency_overrides[get_youtube_fetch] = lambda: fake.fetch
    configured_app.dependency_overrides[get_youtube_check] = lambda: fake.check
    yield fake


def _counts(client: TestClient) -> tuple[int, int]:
    from app.persistence.database import get_session_factory

    with get_session_factory()() as session:
        return (
            len(session.scalars(select(BookRow.id)).all()),
            len(session.scalars(select(ChunkRow.id)).all()),
        )


def test_a_youtube_link_imports_its_transcript_as_video_chunks(
    client: TestClient, fakes: Fakes
) -> None:
    response = client.post("/api/books/youtube", json={"url": URL})

    assert response.status_code == 201, response.text
    book = response.json()["book"]
    assert book["source_format"] == SourceFormat.YOUTUBE.value
    assert book["video_id"] == VIDEO_ID
    assert book["video_availability"] == "available"
    assert book["title"] == "Loops in Python"
    assert fakes.fetched == [VIDEO_ID]
    chunks = client.get("/api/chunks", params={"book_id": book["id"]}).json()["chunks"]
    assert len(chunks) >= 2
    assert all("\u2013" in chunk["citation"] for chunk in chunks)


def test_a_failed_fetch_offers_the_paste_and_imports_nothing(
    client: TestClient, fakes: Fakes
) -> None:
    fakes.fail_fetch = True

    response = client.post("/api/books/youtube", json={"url": URL})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "transcript_unavailable"
    assert _counts(client) == (0, 0)

    pasted = client.post("/api/books/youtube", json={"url": URL, "transcript": PANEL_COPY})
    assert pasted.status_code == 201, pasted.text
    assert pasted.json()["book"]["producer"] == "pasted transcript"
    assert _counts(client) == (1, 1)


def test_a_bad_paste_imports_nothing(client: TestClient, fakes: Fakes) -> None:
    response = client.post(
        "/api/books/youtube", json={"url": URL, "transcript": "no times in here"}
    )

    assert response.status_code == 422
    assert _counts(client) == (0, 0)
    assert fakes.fetched == []


@pytest.mark.parametrize(
    "availability", [VideoAvailability.UNAVAILABLE, VideoAvailability.NOT_EMBEDDABLE]
)
def test_a_video_that_cannot_play_is_refused_before_anything_is_fetched(
    client: TestClient, fakes: Fakes, availability: VideoAvailability
) -> None:
    fakes.availability = availability

    response = client.post("/api/books/youtube", json={"url": URL})

    assert response.status_code == 422
    assert fakes.fetched == []
    assert _counts(client) == (0, 0)


def test_the_same_video_twice_is_one_source_and_a_new_paste_is_a_new_version(
    client: TestClient, fakes: Fakes
) -> None:
    first = client.post("/api/books/youtube", json={"url": URL}).json()["book"]
    again = client.post("/api/books/youtube", json={"url": f"https://youtu.be/{VIDEO_ID}"})
    pasted = client.post("/api/books/youtube", json={"url": URL, "transcript": PANEL_COPY})

    assert again.json()["book"]["id"] == first["id"]
    assert pasted.json()["book"]["id"] == first["id"]
    detail = client.get(f"/api/books/{first['id']}").json()
    assert detail["current_version"] == 2
    assert detail["chunk_count"] == 1


# ------------------------------------------------------------------ the periodic check


def _video(session: Session, video_id: str, availability: VideoAvailability) -> BookRow:
    book = BookRow(
        title=video_id,
        original_filename=youtube.watch_url(video_id),
        source_format=SourceFormat.YOUTUBE,
        video_id=video_id,
        video_availability=availability,
    )
    session.add(book)
    session.commit()
    return book


def test_the_periodic_check_flags_videos_that_went_away(session: Session, engine) -> None:
    gone = _video(session, "gonegonegon", VideoAvailability.AVAILABLE)
    locked = _video(session, "lockedlocke", VideoAvailability.AVAILABLE)
    blip = _video(session, "blipblipbli", VideoAvailability.AVAILABLE)
    fine = _video(session, "finefinefin", VideoAvailability.AVAILABLE)
    answers = {
        "gonegonegon": VideoAvailability.UNAVAILABLE,
        "lockedlocke": VideoAvailability.NOT_EMBEDDABLE,
        "blipblipbli": VideoAvailability.UNKNOWN,
        "finefinefin": VideoAvailability.AVAILABLE,
    }

    result = check_video_sources(
        lambda: Session(engine, expire_on_commit=False),
        check=lambda video_id: (answers[video_id], None),
    )

    assert result == {
        gone.id: VideoAvailability.UNAVAILABLE,
        locked.id: VideoAvailability.NOT_EMBEDDABLE,
        # YouTube unreachable: the earlier answer stands.
        blip.id: VideoAvailability.AVAILABLE,
        fine.id: VideoAvailability.AVAILABLE,
    }
    session.expire_all()
    assert all(
        session.get(BookRow, book.id).availability_checked_at is not None
        for book in (gone, locked, blip, fine)
    )
