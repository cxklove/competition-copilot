import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.ingestion.models import RawCompetitionData

OBSERVED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
SOURCE_URL = "https://example.org/notice"


def test_minimal_raw_data_has_missing_optional_fields_and_empty_tracks() -> None:
    raw = RawCompetitionData(source_url=SOURCE_URL, observed_at=OBSERVED_AT)

    assert raw.name is None
    assert raw.short_name is None
    assert raw.edition_name is None
    assert raw.edition_year is None
    assert raw.official_url is None
    assert raw.registration_start is None
    assert raw.registration_end is None
    assert raw.competition_start is None
    assert raw.competition_end is None
    assert raw.tracks == []
    assert raw.raw_payload is None
    assert raw.source_url == SOURCE_URL
    assert raw.observed_at == OBSERVED_AT
    assert not hasattr(raw, "id")


def test_complete_raw_data_preserves_unparsed_values_and_payload() -> None:
    payload = {
        "unknown_field": {"label": "keep this value"},
        "registration": ["pending", "announcement"],
    }
    raw = RawCompetitionData(
        name="Example Competition",
        short_name="EC",
        edition_name="2026 edition",
        edition_year="2026/27",
        official_url="official site to confirm",
        registration_start="early October 2026",
        registration_end="TBA",
        competition_start="2027-01-15",
        competition_end="2027-02-15",
        tracks=["Innovation", "Practice"],
        source_url=SOURCE_URL,
        observed_at=OBSERVED_AT,
        raw_payload=payload,
    )

    assert raw.name == "Example Competition"
    assert raw.short_name == "EC"
    assert raw.edition_name == "2026 edition"
    assert raw.edition_year == "2026/27"
    assert raw.official_url == "official site to confirm"
    assert raw.registration_start == "early October 2026"
    assert raw.registration_end == "TBA"
    assert raw.competition_start == "2027-01-15"
    assert raw.competition_end == "2027-02-15"
    assert raw.tracks == ["Innovation", "Practice"]
    assert raw.raw_payload == payload
    assert isinstance(raw.competition_start, str)


@pytest.mark.parametrize("year", ["2026", 2026])
def test_edition_year_keeps_source_type(year: str | int) -> None:
    raw = RawCompetitionData(
        edition_year=year, source_url=SOURCE_URL, observed_at=OBSERVED_AT
    )

    assert raw.edition_year == year
    assert type(raw.edition_year) is type(year)


def test_default_tracks_are_independent() -> None:
    first = RawCompetitionData(source_url=SOURCE_URL, observed_at=OBSERVED_AT)
    second = RawCompetitionData(source_url=SOURCE_URL, observed_at=OBSERVED_AT)

    first.tracks.append("Innovation")

    assert second.tracks == []


@pytest.mark.parametrize("source_url", [None, "", " \t "])
def test_missing_or_blank_source_url_is_rejected(source_url: str | None) -> None:
    data = {"observed_at": OBSERVED_AT}
    if source_url is not None:
        data["source_url"] = source_url

    with pytest.raises(ValidationError, match="source_url"):
        RawCompetitionData.model_validate(data)


def test_naive_observed_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="observed_at"):
        RawCompetitionData(
            source_url=SOURCE_URL, observed_at=datetime(2026, 10, 8, 12, 0)
        )


def test_timezone_aware_observed_at_is_accepted() -> None:
    observed_at = datetime(
        2026, 10, 8, 20, 0, tzinfo=timezone(timedelta(hours=8))
    )

    raw = RawCompetitionData(source_url=SOURCE_URL, observed_at=observed_at)

    assert raw.observed_at == observed_at
    assert raw.observed_at.utcoffset() == timedelta(hours=8)


def test_serialization_round_trip_preserves_raw_values() -> None:
    original = RawCompetitionData(
        name="Example Competition",
        edition_year="2026",
        registration_end="TBA",
        tracks=["Innovation"],
        source_url=SOURCE_URL,
        observed_at=OBSERVED_AT,
        raw_payload={"extra": {"unparsed": "April 2027"}},
    )

    payload = json.loads(original.model_dump_json())
    restored = RawCompetitionData.model_validate(payload)

    assert payload["edition_year"] == "2026"
    assert payload["registration_end"] == "TBA"
    assert payload["raw_payload"] == {"extra": {"unparsed": "April 2027"}}
    assert restored == original
