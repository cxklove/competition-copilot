import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.domain.temporal import TimeWindow


def test_valid_minimal_competition() -> None:
    competition = Competition(id="huawei-ict", name="Huawei ICT Competition")

    assert competition.id == "huawei-ict"
    assert competition.name == "Huawei ICT Competition"
    assert competition.short_name is None
    assert competition.description is None
    assert competition.official_url is None


def test_valid_complete_competition() -> None:
    competition = Competition(
        id="huawei-ict",
        name="Huawei ICT Competition",
        short_name="Huawei ICT",
        description="An ICT competition for students.",
        official_url="https://example.com/competition",
    )

    assert competition.short_name == "Huawei ICT"
    assert competition.description == "An ICT competition for students."
    assert str(competition.official_url) == "https://example.com/competition"


def test_missing_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="id"):
        Competition(name="Huawei ICT Competition")


@pytest.mark.parametrize("identifier", ["", " \t\n "])
def test_empty_or_whitespace_only_id_is_rejected(identifier: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        Competition(id=identifier, name="Huawei ICT Competition")


def test_id_is_trimmed() -> None:
    competition = Competition(id="  huawei-ict \t", name="Huawei ICT Competition")

    assert competition.id == "huawei-ict"


def test_missing_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="name"):
        Competition(id="huawei-ict")


@pytest.mark.parametrize("name", ["", " \t\n "])
def test_empty_or_whitespace_only_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        Competition(id="huawei-ict", name=name)


def test_name_is_trimmed() -> None:
    competition = Competition(id="huawei-ict", name="  Huawei ICT Competition  ")

    assert competition.name == "Huawei ICT Competition"


def test_short_name_can_be_omitted() -> None:
    competition = Competition(id="huawei-ict", name="Huawei ICT Competition")

    assert competition.short_name is None


def test_whitespace_only_short_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="short_name"):
        Competition(id="huawei-ict", name="Huawei ICT Competition", short_name=" \t ")


def test_short_name_is_trimmed() -> None:
    competition = Competition(
        id="huawei-ict", name="Huawei ICT Competition", short_name="  ICT  "
    )

    assert competition.short_name == "ICT"


def test_description_can_be_omitted() -> None:
    competition = Competition(id="huawei-ict", name="Huawei ICT Competition")

    assert competition.description is None


def test_whitespace_only_description_is_rejected() -> None:
    with pytest.raises(ValidationError, match="description"):
        Competition(id="huawei-ict", name="Huawei ICT Competition", description=" \n ")


def test_description_is_trimmed() -> None:
    competition = Competition(
        id="huawei-ict",
        name="Huawei ICT Competition",
        description="  Student ICT competition.  ",
    )

    assert competition.description == "Student ICT competition."


@pytest.mark.parametrize("url", ["http://example.com", "https://example.com"])
def test_http_and_https_urls_are_accepted(url: str) -> None:
    competition = Competition(
        id="huawei-ict", name="Huawei ICT Competition", official_url=url
    )

    assert str(competition.official_url) == f"{url}/"


def test_invalid_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="official_url"):
        Competition(
            id="huawei-ict", name="Huawei ICT Competition", official_url="not a URL"
        )


def test_non_http_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="official_url"):
        Competition(
            id="huawei-ict",
            name="Huawei ICT Competition",
            official_url="ftp://example.com",
        )


def test_model_dump_is_json_serializable() -> None:
    competition = Competition(
        id="huawei-ict",
        name="Huawei ICT Competition",
        official_url="https://example.com",
    )
    expected = {
        "id": "huawei-ict",
        "name": "Huawei ICT Competition",
        "short_name": None,
        "description": None,
        "official_url": "https://example.com/",
    }

    assert competition.model_dump(mode="json") == expected
    assert json.loads(competition.model_dump_json()) == expected


def test_model_validate_round_trip() -> None:
    original = Competition(
        id="huawei-ict",
        name="Huawei ICT Competition",
        short_name="Huawei ICT",
        description="An ICT competition for students.",
        official_url="https://example.com/competition",
    )

    assert Competition.model_validate(original.model_dump(mode="json")) == original


def test_edition_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="year"):
        Competition(id="huawei-ict", name="Huawei ICT Competition", year=2026)


MINIMAL_EDITION = {
    "id": "huawei-ict-2026",
    "competition_id": "huawei-ict",
    "year": 2026,
    "name": "Huawei ICT Competition 2026 Season",
}


def test_valid_minimal_edition() -> None:
    edition = CompetitionEdition(**MINIMAL_EDITION)

    assert edition.id == "huawei-ict-2026"
    assert edition.competition_id == "huawei-ict"
    assert edition.year == 2026
    assert edition.name == "Huawei ICT Competition 2026 Season"
    assert edition.registration_window is None
    assert edition.competition_window is None
    assert edition.official_url is None
    assert edition.source is None


def test_valid_complete_edition() -> None:
    registration_window = TimeWindow(
        start_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    competition_window = TimeWindow(
        start_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    source = SourceMetadata(
        source_url="https://example.com/notice",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )
    edition = CompetitionEdition(
        **MINIMAL_EDITION,
        registration_window=registration_window,
        competition_window=competition_window,
        official_url="https://example.com/edition",
        source=source,
    )

    assert edition.registration_window == registration_window
    assert edition.competition_window == competition_window
    assert str(edition.official_url) == "https://example.com/edition"
    assert edition.source == source


@pytest.mark.parametrize("identifier", ["", " \t "])
def test_empty_edition_id_is_rejected(identifier: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        CompetitionEdition.model_validate({**MINIMAL_EDITION, "id": identifier})


@pytest.mark.parametrize("competition_id", ["", " \t "])
def test_empty_competition_id_is_rejected(competition_id: str) -> None:
    with pytest.raises(ValidationError, match="competition_id"):
        CompetitionEdition.model_validate(
            {**MINIMAL_EDITION, "competition_id": competition_id}
        )


@pytest.mark.parametrize("name", ["", " \t "])
def test_empty_edition_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        CompetitionEdition.model_validate({**MINIMAL_EDITION, "name": name})


def test_edition_identity_fields_are_trimmed() -> None:
    edition = CompetitionEdition.model_validate(
        {
            **MINIMAL_EDITION,
            "id": "  huawei-ict-2026  ",
            "competition_id": "  huawei-ict\t",
            "name": "  Huawei ICT Competition 2026 Season  ",
        }
    )

    assert edition.id == "huawei-ict-2026"
    assert edition.competition_id == "huawei-ict"
    assert edition.name == "Huawei ICT Competition 2026 Season"


@pytest.mark.parametrize("year", [-1, 0, 1899, 2101, True, 2026.5, "2026"])
def test_invalid_edition_year_is_rejected(year: object) -> None:
    with pytest.raises(ValidationError, match="year"):
        CompetitionEdition.model_validate({**MINIMAL_EDITION, "year": year})


@pytest.mark.parametrize("year", [1900, 1980])
def test_historical_reasonable_year_is_accepted(year: int) -> None:
    assert CompetitionEdition.model_validate({**MINIMAL_EDITION, "year": year}).year == year


@pytest.mark.parametrize("year", [2050, 2100])
def test_future_reasonable_year_is_accepted(year: int) -> None:
    assert CompetitionEdition.model_validate({**MINIMAL_EDITION, "year": year}).year == year


def test_registration_time_window_is_accepted() -> None:
    window = TimeWindow(start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    edition = CompetitionEdition(**MINIMAL_EDITION, registration_window=window)

    assert edition.registration_window == window


def test_competition_time_window_is_accepted() -> None:
    window = TimeWindow(end_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
    edition = CompetitionEdition(**MINIMAL_EDITION, competition_window=window)

    assert edition.competition_window == window


def test_invalid_nested_time_window_is_rejected() -> None:
    with pytest.raises(ValidationError, match="registration_window"):
        CompetitionEdition.model_validate(
            {
                **MINIMAL_EDITION,
                "registration_window": {"start_at": datetime(2026, 1, 1)},
            }
        )


def test_source_metadata_is_accepted() -> None:
    source = SourceMetadata(
        source_url="https://example.com/notice",
        source_type=SourceType.ORGANIZER,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        verification_status=VerificationStatus.PENDING,
    )
    edition = CompetitionEdition(**MINIMAL_EDITION, source=source)

    assert edition.source == source
    assert edition.source.verification_status is VerificationStatus.PENDING


def test_invalid_source_is_rejected() -> None:
    with pytest.raises(ValidationError, match="source"):
        CompetitionEdition.model_validate({**MINIMAL_EDITION, "source": "unverified"})


@pytest.mark.parametrize("url", ["http://example.com", "https://example.com"])
def test_edition_http_urls_are_accepted(url: str) -> None:
    edition = CompetitionEdition(**MINIMAL_EDITION, official_url=url)

    assert str(edition.official_url) == f"{url}/"


@pytest.mark.parametrize("url", ["not a URL", "ftp://example.com"])
def test_invalid_edition_url_is_rejected(url: str) -> None:
    with pytest.raises(ValidationError, match="official_url"):
        CompetitionEdition(**MINIMAL_EDITION, official_url=url)


def test_edition_serialization() -> None:
    edition = CompetitionEdition(
        **MINIMAL_EDITION,
        registration_window=TimeWindow(
            start_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=8)))
        ),
        official_url="https://example.com/edition",
    )

    payload = edition.model_dump(mode="json")
    assert payload["registration_window"] == {
        "start_at": "2026-01-01T00:00:00+08:00",
        "end_at": None,
    }
    assert payload["competition_window"] is None
    assert payload["official_url"] == "https://example.com/edition"
    assert json.loads(edition.model_dump_json()) == payload


def test_edition_model_validate_round_trip() -> None:
    original = CompetitionEdition(
        **MINIMAL_EDITION,
        competition_window=TimeWindow(
            start_at=datetime(2026, 3, 1, tzinfo=timezone.utc)
        ),
        source=SourceMetadata(
            source_url="https://example.com/notice",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            verification_status=VerificationStatus.VERIFIED,
        ),
    )

    restored = CompetitionEdition.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert isinstance(restored.competition_window, TimeWindow)
    assert isinstance(restored.source, SourceMetadata)


def test_dynamic_status_is_rejected() -> None:
    with pytest.raises(ValidationError, match="current_status"):
        CompetitionEdition.model_validate(
            {**MINIMAL_EDITION, "current_status": "registration_open"}
        )


MINIMAL_TRACK = {
    "id": "huawei-ict-2026-innovation",
    "edition_id": "huawei-ict-2026",
    "name": "Innovation Track",
}


def test_valid_minimal_track() -> None:
    track = CompetitionTrack(**MINIMAL_TRACK)

    assert track.id == "huawei-ict-2026-innovation"
    assert track.edition_id == "huawei-ict-2026"
    assert track.name == "Innovation Track"
    assert track.description is None
    assert track.official_url is None
    assert track.source is None


def test_valid_complete_track() -> None:
    source = SourceMetadata(
        source_url="https://example.com/track-notice",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )
    track = CompetitionTrack(
        **MINIMAL_TRACK,
        description="Build an innovative ICT solution.",
        official_url="https://example.com/innovation",
        source=source,
    )

    assert track.description == "Build an innovative ICT solution."
    assert str(track.official_url) == "https://example.com/innovation"
    assert track.source == source


@pytest.mark.parametrize("identifier", ["", " \t "])
def test_empty_track_id_is_rejected(identifier: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        CompetitionTrack.model_validate({**MINIMAL_TRACK, "id": identifier})


@pytest.mark.parametrize("edition_id", ["", " \t "])
def test_empty_track_edition_id_is_rejected(edition_id: str) -> None:
    with pytest.raises(ValidationError, match="edition_id"):
        CompetitionTrack.model_validate({**MINIMAL_TRACK, "edition_id": edition_id})


@pytest.mark.parametrize("name", ["", " \t "])
def test_empty_track_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        CompetitionTrack.model_validate({**MINIMAL_TRACK, "name": name})


def test_track_identity_fields_are_trimmed() -> None:
    track = CompetitionTrack.model_validate(
        {
            **MINIMAL_TRACK,
            "id": "  huawei-ict-2026-innovation  ",
            "edition_id": "  huawei-ict-2026\t",
            "name": "  Innovation Track  ",
        }
    )

    assert track.id == "huawei-ict-2026-innovation"
    assert track.edition_id == "huawei-ict-2026"
    assert track.name == "Innovation Track"


def test_track_description_can_be_omitted() -> None:
    assert CompetitionTrack(**MINIMAL_TRACK).description is None


def test_whitespace_only_track_description_is_rejected() -> None:
    with pytest.raises(ValidationError, match="description"):
        CompetitionTrack(**MINIMAL_TRACK, description=" \t ")


def test_track_description_is_trimmed() -> None:
    track = CompetitionTrack(**MINIMAL_TRACK, description="  ICT innovation.  ")

    assert track.description == "ICT innovation."


@pytest.mark.parametrize("url", ["http://example.com", "https://example.com"])
def test_track_http_urls_are_accepted(url: str) -> None:
    track = CompetitionTrack(**MINIMAL_TRACK, official_url=url)

    assert str(track.official_url) == f"{url}/"


@pytest.mark.parametrize("url", ["not a URL", "ftp://example.com"])
def test_invalid_track_url_is_rejected(url: str) -> None:
    with pytest.raises(ValidationError, match="official_url"):
        CompetitionTrack(**MINIMAL_TRACK, official_url=url)


def test_track_source_metadata_is_accepted() -> None:
    source = SourceMetadata(
        source_url="https://example.com/track-notice",
        source_type=SourceType.ORGANIZER,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        verification_status=VerificationStatus.PENDING,
    )
    track = CompetitionTrack(**MINIMAL_TRACK, source=source)

    assert track.source == source
    assert track.source.verification_status is VerificationStatus.PENDING


def test_invalid_track_source_is_rejected() -> None:
    with pytest.raises(ValidationError, match="source"):
        CompetitionTrack.model_validate({**MINIMAL_TRACK, "source": "unverified"})


def test_track_serialization() -> None:
    track = CompetitionTrack(
        **MINIMAL_TRACK,
        description="Innovation",
        official_url="https://example.com/innovation",
    )
    expected = {
        **MINIMAL_TRACK,
        "description": "Innovation",
        "official_url": "https://example.com/innovation",
        "source": None,
    }

    assert track.model_dump(mode="json") == expected
    assert json.loads(track.model_dump_json()) == expected


def test_track_model_validate_round_trip() -> None:
    original = CompetitionTrack(
        **MINIMAL_TRACK,
        description="Innovation",
        source=SourceMetadata(
            source_url="https://example.com/track-notice",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            verification_status=VerificationStatus.VERIFIED,
        ),
    )

    restored = CompetitionTrack.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert isinstance(restored.source, SourceMetadata)


def test_track_does_not_check_edition_exists() -> None:
    track = CompetitionTrack.model_validate(
        {**MINIMAL_TRACK, "edition_id": "edition-not-yet-stored"}
    )

    assert track.edition_id == "edition-not-yet-stored"


def test_track_requirement_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="team_size"):
        CompetitionTrack.model_validate({**MINIMAL_TRACK, "team_size": 3})
