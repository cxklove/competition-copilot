from datetime import datetime, timedelta, timezone

import pytest

from competition_copilot.domain.source_metadata import (
    SourceType,
    VerificationStatus,
)
from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import (
    CompetitionNormalizer,
    NormalizationError,
)

OBSERVED_AT = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def raw_data(**overrides: object) -> RawCompetitionData:
    data: dict[str, object] = {
        "competition_id": "example",
        "name": "Example Competition",
        "edition_id": "example-2026",
        "edition_name": "2026 Edition",
        "edition_year": 2026,
        "source_url": "https://example.org/notice",
        "source_type": "organizer",
        "observed_at": OBSERVED_AT,
    }
    data.update(overrides)
    return RawCompetitionData.model_validate(data)


def test_clean_raw_produces_provisional_models_without_mutation() -> None:
    raw = raw_data()
    before = raw.model_dump()

    competition, edition, tracks = CompetitionNormalizer().normalize(raw)

    assert competition.id == "example"
    assert competition.name == "Example Competition"
    assert edition.id == "example-2026"
    assert edition.competition_id == competition.id
    assert edition.name == "2026 Edition"
    assert edition.year == 2026
    assert edition.registration_window is None
    assert edition.competition_window is None
    assert tracks == []
    assert raw.model_dump() == before
    assert CompetitionNormalizer().normalize(raw) == (competition, edition, tracks)


def test_whitespace_is_trimmed_without_inventing_other_fields() -> None:
    raw = raw_data(
        competition_id="  example  ",
        name="  Example Competition  ",
        short_name="  EC  ",
        edition_id="  example-2026  ",
        edition_name="  2026 Edition  ",
        edition_year=" 2026 ",
        official_url="  https://example.org/competition  ",
        source_type=" organizer ",
        tracks=["  Innovation  "],
        track_ids=["  innovation  "],
    )

    competition, edition, tracks = CompetitionNormalizer().normalize(raw)

    assert competition.id == "example"
    assert competition.name == "Example Competition"
    assert competition.short_name == "EC"
    assert str(competition.official_url) == "https://example.org/competition"
    assert edition.id == "example-2026"
    assert edition.name == "2026 Edition"
    assert edition.year == 2026
    assert edition.official_url is None
    assert tracks[0].id == "innovation"
    assert tracks[0].name == "Innovation"
    assert tracks[0].official_url is None


def test_explicit_string_year_is_parsed() -> None:
    _, edition, _ = CompetitionNormalizer().normalize(raw_data(edition_year="2026"))

    assert edition.year == 2026


@pytest.mark.parametrize("year", [None, "2026/27", "about 2026", "2026.0"])
def test_missing_or_ambiguous_year_is_rejected(year: str | None) -> None:
    with pytest.raises(NormalizationError) as error:
        CompetitionNormalizer().normalize(raw_data(edition_year=year))

    assert error.value.code == "INVALID_YEAR"
    assert error.value.field == "edition_year"


def test_aware_iso_datetime_builds_time_windows() -> None:
    raw = raw_data(
        registration_start="2026-10-01T09:00:00+08:00",
        registration_end="2026-10-31T23:59:00+08:00",
        competition_start="2026-11-15T09:00:00Z",
    )

    _, edition, _ = CompetitionNormalizer().normalize(raw)

    assert edition.registration_window is not None
    assert edition.registration_window.start_at == datetime(
        2026, 10, 1, 9, 0, tzinfo=timezone(timedelta(hours=8))
    )
    assert edition.registration_window.end_at == datetime(
        2026, 10, 31, 23, 59, tzinfo=timezone(timedelta(hours=8))
    )
    assert edition.competition_window is not None
    assert edition.competition_window.start_at == datetime(
        2026, 11, 15, 9, 0, tzinfo=timezone.utc
    )
    assert edition.competition_window.end_at is None


@pytest.mark.parametrize(
    ("value", "field"),
    [
        ("2026-10-01T09:00:00", "registration_start"),
        ("预计11月", "registration_end"),
        ("大约年底", "competition_start"),
        ("报名近期结束", "competition_end"),
    ],
)
def test_naive_or_ambiguous_time_is_rejected(value: str, field: str) -> None:
    with pytest.raises(NormalizationError) as error:
        CompetitionNormalizer().normalize(raw_data(**{field: value}))

    assert error.value.code == "INVALID_DATETIME"
    assert error.value.field == field


def test_multiple_tracks_keep_explicit_ids_and_source() -> None:
    raw = raw_data(
        tracks=["Innovation", "Practice"],
        track_ids=["innovation", "practice"],
    )

    _, edition, tracks = CompetitionNormalizer().normalize(raw)

    assert [track.id for track in tracks] == ["innovation", "practice"]
    assert [track.name for track in tracks] == ["Innovation", "Practice"]
    assert all(track.edition_id == edition.id for track in tracks)
    assert all(track.source == edition.source for track in tracks)


def test_source_provenance_is_preserved_as_pending() -> None:
    raw = raw_data(
        source_url="https://example.org/official-announcement",
        source_type="official",
    )

    _, edition, _ = CompetitionNormalizer().normalize(raw)

    assert edition.source is not None
    assert str(edition.source.source_url) == raw.source_url
    assert edition.source.source_type is SourceType.OFFICIAL
    assert edition.source.observed_at == raw.observed_at
    assert edition.source.verification_status is VerificationStatus.PENDING


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"competition_id": None}, "competition_id"),
        ({"edition_id": None}, "edition_id"),
        ({"tracks": ["Innovation"]}, "track_ids"),
    ],
)
def test_missing_explicit_ids_are_rejected(
    overrides: dict[str, object], field: str
) -> None:
    with pytest.raises(NormalizationError) as error:
        CompetitionNormalizer().normalize(raw_data(**overrides))

    assert error.value.field == field


def test_invalid_source_type_is_not_guessed() -> None:
    with pytest.raises(NormalizationError) as error:
        CompetitionNormalizer().normalize(raw_data(source_type="blog"))

    assert error.value.code == "INVALID_SOURCE_TYPE"
    assert error.value.field == "source_type"
