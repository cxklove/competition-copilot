import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.event import CompetitionEvent, CompetitionEventType
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)

SOURCE = SourceMetadata(
    source_url="https://example.com/notice",
    source_type=SourceType.OFFICIAL,
    observed_at=datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
    verification_status=VerificationStatus.VERIFIED,
)
MINIMAL_EVENT = {
    "id": "event-1",
    "competition_id": "competition-1",
    "edition_id": "edition-1",
    "event_type": CompetitionEventType.DEADLINE_CHANGED,
    "observed_at": datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
    "source": SOURCE,
}


def test_valid_minimal_event() -> None:
    event = CompetitionEvent(**MINIMAL_EVENT)

    assert event.id == "event-1"
    assert event.competition_id == "competition-1"
    assert event.edition_id == "edition-1"
    assert event.event_type is CompetitionEventType.DEADLINE_CHANGED
    assert event.occurred_at is None
    assert event.observed_at == MINIMAL_EVENT["observed_at"]
    assert event.source is SOURCE
    assert event.description is None


def test_valid_complete_event() -> None:
    occurred_at = datetime(2026, 10, 8, 18, tzinfo=timezone(timedelta(hours=8)))
    event = CompetitionEvent(
        id="  event-1  ",
        competition_id="  competition-1  ",
        edition_id="  edition-1  ",
        event_type=CompetitionEventType.RULE_UPDATED,
        occurred_at=occurred_at,
        observed_at=datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
        source=SOURCE,
        description="  Rules were updated.  ",
    )

    assert event.id == "event-1"
    assert event.competition_id == "competition-1"
    assert event.edition_id == "edition-1"
    assert event.event_type is CompetitionEventType.RULE_UPDATED
    assert event.occurred_at == occurred_at
    assert event.description == "Rules were updated."


@pytest.mark.parametrize("event_type", list(CompetitionEventType))
def test_every_event_type_is_accepted(event_type: CompetitionEventType) -> None:
    event = CompetitionEvent(**{**MINIMAL_EVENT, "event_type": event_type})

    assert event.event_type is event_type


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="event_type"):
        CompetitionEvent(**{**MINIMAL_EVENT, "event_type": "notification_sent"})


@pytest.mark.parametrize("field", ["id", "competition_id", "edition_id"])
@pytest.mark.parametrize("value", ["", " \t\n "])
def test_blank_ids_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        CompetitionEvent.model_validate({**MINIMAL_EVENT, field: value})


def test_missing_event_id_is_rejected() -> None:
    payload = {key: value for key, value in MINIMAL_EVENT.items() if key != "id"}

    with pytest.raises(ValidationError, match="id"):
        CompetitionEvent.model_validate(payload)


def test_timezone_aware_observed_at_is_accepted() -> None:
    observed_at = datetime(2026, 10, 8, 20, tzinfo=timezone(timedelta(hours=8)))
    event = CompetitionEvent(**{**MINIMAL_EVENT, "observed_at": observed_at})

    assert event.observed_at == observed_at
    assert event.observed_at.utcoffset() == timedelta(hours=8)


def test_naive_observed_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="observed_at"):
        CompetitionEvent(
            **{**MINIMAL_EVENT, "observed_at": datetime(2026, 10, 8, 12)}
        )


def test_occurred_at_can_be_none() -> None:
    assert CompetitionEvent(**MINIMAL_EVENT).occurred_at is None


def test_timezone_aware_occurred_at_is_accepted() -> None:
    occurred_at = datetime(2026, 10, 8, 18, tzinfo=timezone(timedelta(hours=8)))
    event = CompetitionEvent(**{**MINIMAL_EVENT, "occurred_at": occurred_at})

    assert event.occurred_at == occurred_at


def test_naive_occurred_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="occurred_at"):
        CompetitionEvent(
            **{**MINIMAL_EVENT, "occurred_at": datetime(2026, 10, 8, 12)}
        )


def test_occurred_at_may_be_after_observed_at() -> None:
    occurred_at = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    event = CompetitionEvent(**{**MINIMAL_EVENT, "occurred_at": occurred_at})

    assert event.occurred_at == occurred_at
    assert event.occurred_at > event.observed_at


def test_source_is_required() -> None:
    payload = {key: value for key, value in MINIMAL_EVENT.items() if key != "source"}

    with pytest.raises(ValidationError, match="source"):
        CompetitionEvent.model_validate(payload)


def test_source_must_be_source_metadata() -> None:
    with pytest.raises(ValidationError, match="source"):
        CompetitionEvent.model_validate({**MINIMAL_EVENT, "source": {"source_url": "bad"}})


def test_description_is_optional_and_trimmed() -> None:
    assert CompetitionEvent(**MINIMAL_EVENT).description is None
    event = CompetitionEvent(
        **{**MINIMAL_EVENT, "description": "  Registration deadline moved.  "}
    )

    assert event.description == "Registration deadline moved."


@pytest.mark.parametrize("description", ["", " \t\n "])
def test_blank_description_is_rejected(description: str) -> None:
    with pytest.raises(ValidationError, match="description"):
        CompetitionEvent(**{**MINIMAL_EVENT, "description": description})


def test_ids_do_not_require_database_lookup() -> None:
    event = CompetitionEvent(
        **{
            **MINIMAL_EVENT,
            "competition_id": "not-yet-stored",
            "edition_id": "unknown-edition",
        }
    )

    assert event.competition_id == "not-yet-stored"
    assert event.edition_id == "unknown-edition"


def test_serialization() -> None:
    event = CompetitionEvent(**MINIMAL_EVENT)
    expected = {
        "id": "event-1",
        "competition_id": "competition-1",
        "edition_id": "edition-1",
        "event_type": "deadline_changed",
        "occurred_at": None,
        "observed_at": "2026-10-08T12:00:00Z",
        "source": {
            "source_url": "https://example.com/notice",
            "source_type": "official",
            "observed_at": "2026-10-08T12:00:00Z",
            "verification_status": "verified",
        },
        "description": None,
    }

    assert event.model_dump(mode="json") == expected
    assert json.loads(event.model_dump_json()) == expected


def test_model_validate_round_trip() -> None:
    original = CompetitionEvent(
        **{
            **MINIMAL_EVENT,
            "event_type": CompetitionEventType.MATERIAL_UPDATED,
            "occurred_at": datetime(
                2026, 10, 8, 18, tzinfo=timezone(timedelta(hours=8))
            ),
            "description": "Material list updated.",
        }
    )

    restored = CompetitionEvent.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.event_type is CompetitionEventType.MATERIAL_UPDATED
    assert isinstance(restored.source, SourceMetadata)
