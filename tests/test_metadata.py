"""S1b metadata extraction. `extract_metadata` (real regex heuristic) is
tested for real, no mocking. `extract_metadata_llm`/backfill tests use a
fake client — explicitly PLUMBING ONLY (see tests/stubs.py's docstring
and the `feedback_dont_overclaim_selfauthored_test_validity` project
memory): they prove the request/response wiring, not real extraction
quality against real messy scans, which only a real Gemini call can show."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, DisciplineORM, PageORM
from practice_forge.ingest.metadata import BookMetadata, extract_metadata, extract_metadata_llm
from practice_forge.ingest.pipeline import _extract_metadata_with_fallback, backfill_metadata
from practice_forge.llm.client import LLMResponse


def test_extract_metadata_parses_well_formatted_title_page() -> None:
    text = "Title: Strength of Materials\nAuthor: R.S. Khurmi, N. Khurmi\nEdition: 3rd Edition"
    result = extract_metadata(text)
    assert result.title == "Strength of Materials"
    assert result.authors == ["R.S. Khurmi", "N. Khurmi"]
    assert result.edition == "3rd Edition"


def test_extract_metadata_falls_back_to_unknown_title_on_messy_real_scan() -> None:
    # Real, representative of an actual scanned textbook cover: no
    # "Title:"/"Author:" literal labels at all.
    text = "ENGINEERING\nTHERMODYNAMICS\nP.K. NAG\nTata McGraw-Hill\nISBN 0-07-047338-2"
    result = extract_metadata(text)
    assert result.title == "Unknown Title"
    assert result.authors == []


class _FakeMetadataClient:
    def __init__(self, response_json: dict[str, object]) -> None:
        self.response_json = response_json
        self.calls: list[str] = []

    def complete(self, *, stage: str, prompt: str, job_id: str, **kwargs: object) -> LLMResponse:
        self.calls.append(stage)
        return LLMResponse(
            text=json.dumps(self.response_json),
            stop_reason="stop",
            provider="fake",
            model="fake",
            input_tokens=0,
            output_tokens=0,
            extra_tokens=0,
            cost_usd=0.0,
        )


def test_extract_metadata_llm_returns_real_fields_from_response() -> None:
    client = _FakeMetadataClient(
        {"title": "Engineering Thermodynamics", "authors": ["P.K. Nag"], "edition": "5th Edition"}
    )
    result = extract_metadata_llm(client, "job-1", "ENGINEERING THERMODYNAMICS P.K. NAG")  # type: ignore[arg-type]
    assert result == BookMetadata(
        title="Engineering Thermodynamics", authors=["P.K. Nag"], edition="5th Edition"
    )
    assert client.calls == ["s1_metadata"]


def test_extract_metadata_llm_never_fabricates_a_missing_field() -> None:
    client = _FakeMetadataClient({"title": None, "authors": [], "edition": None})
    result = extract_metadata_llm(client, "job-1", "some ambiguous text")  # type: ignore[arg-type]
    assert result == BookMetadata(title="Unknown Title", authors=[], edition=None)


def test_metadata_fallback_skips_llm_when_regex_already_succeeded() -> None:
    client = _FakeMetadataClient({"title": "Wrong Title", "authors": [], "edition": None})
    result = _extract_metadata_with_fallback(
        "Title: Real Title\nAuthor: Real Author", client, "job-1"  # type: ignore[arg-type]
    )
    assert result.title == "Real Title"
    assert client.calls == []  # never spent the call — the free heuristic already won


def test_metadata_fallback_calls_llm_when_regex_fails_and_client_given() -> None:
    client = _FakeMetadataClient({"title": "Real Title From LLM", "authors": [], "edition": None})
    result = _extract_metadata_with_fallback("no labeled fields here", client, "job-1")  # type: ignore[arg-type]
    assert result.title == "Real Title From LLM"
    assert client.calls == ["s1_metadata"]


def test_metadata_fallback_stays_unknown_without_a_client() -> None:
    result = _extract_metadata_with_fallback("no labeled fields here", None, "job-1")
    assert result.title == "Unknown Title"


def test_backfill_metadata_updates_the_real_book_row(db_session: Session) -> None:
    discipline = db_session.execute(
        select(DisciplineORM).where(DisciplineORM.key == "mechanical")
    ).scalar_one()
    book = BookORM(
        id=uuid.uuid4(),
        title="Unknown Title",
        authors=[],
        discipline_id=discipline.id,
        page_count=1,
        file_sha256=uuid.uuid4().hex,
        uploaded_by="test",
    )
    db_session.add(book)
    db_session.flush()
    db_session.add(
        PageORM(
            id=uuid.uuid4(),
            book_id=book.id,
            page_no=1,
            markdown="ENGINEERING THERMODYNAMICS P.K. NAG",
            has_math=False,
            has_figure=False,
            unit_system_detected=None,
            extraction_confidence=0.9,
        )
    )
    db_session.commit()

    client = _FakeMetadataClient(
        {"title": "Engineering Thermodynamics", "authors": ["P.K. Nag"], "edition": None}
    )
    result = backfill_metadata(db_session, book.id, client)  # type: ignore[arg-type]
    assert result.title == "Engineering Thermodynamics"

    refreshed = db_session.get(BookORM, book.id)
    assert refreshed is not None
    assert refreshed.title == "Engineering Thermodynamics"
    assert refreshed.authors == ["P.K. Nag"]


def test_backfill_metadata_404s_on_unknown_book(db_session: Session) -> None:
    with pytest.raises(ValueError, match="No such book"):
        backfill_metadata(db_session, uuid.uuid4(), _FakeMetadataClient({}))  # type: ignore[arg-type]
