import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)


def test_valid_metadata() -> None:
    observed_at = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    metadata = SourceMetadata(
        source_url="https://example.com/notice",
        source_type=SourceType.UNIVERSITY,
        observed_at=observed_at,
        verification_status=VerificationStatus.PENDING,
    )

    assert str(metadata.source_url) == "https://example.com/notice"
    assert metadata.source_type is SourceType.UNIVERSITY
    assert metadata.observed_at == observed_at
    assert metadata.verification_status is VerificationStatus.PENDING


def test_valid_official_source() -> None:
    metadata = SourceMetadata(
        source_url="https://example.com/official",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )

    assert metadata.source_type is SourceType.OFFICIAL
    assert metadata.verification_status is VerificationStatus.VERIFIED


def test_valid_manual_source() -> None:
    metadata = SourceMetadata(
        source_url="http://example.com/manual-record",
        source_type=SourceType.MANUAL,
        observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        verification_status=VerificationStatus.PENDING,
    )

    assert metadata.source_type is SourceType.MANUAL
    assert metadata.verification_status is VerificationStatus.PENDING


def test_invalid_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="source_url"):
        SourceMetadata(
            source_url="not a URL",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            verification_status=VerificationStatus.PENDING,
        )


def test_ftp_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="source_url"):
        SourceMetadata(
            source_url="ftp://example.com/notice",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            verification_status=VerificationStatus.PENDING,
        )


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError, match="observed_at"):
        SourceMetadata(
            source_url="https://example.com/notice",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 10, 8, 12, 0),
            verification_status=VerificationStatus.PENDING,
        )


def test_timezone_aware_utc_is_accepted() -> None:
    observed_at = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    metadata = SourceMetadata(
        source_url="https://example.com/notice",
        source_type=SourceType.OFFICIAL,
        observed_at=observed_at,
        verification_status=VerificationStatus.PENDING,
    )

    assert metadata.observed_at == observed_at
    assert metadata.observed_at.utcoffset() == timedelta(0)


def test_timezone_aware_plus_eight_is_accepted() -> None:
    observed_at = datetime(
        2026, 10, 8, 20, 0, tzinfo=timezone(timedelta(hours=8))
    )
    metadata = SourceMetadata(
        source_url="https://example.com/notice",
        source_type=SourceType.OFFICIAL,
        observed_at=observed_at,
        verification_status=VerificationStatus.PENDING,
    )

    assert metadata.observed_at == observed_at
    assert metadata.observed_at.utcoffset() == timedelta(hours=8)


def test_invalid_source_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="source_type"):
        SourceMetadata(
            source_url="https://example.com/notice",
            source_type="social_media",
            observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            verification_status=VerificationStatus.PENDING,
        )


def test_invalid_verification_status_is_rejected() -> None:
    with pytest.raises(ValidationError, match="verification_status"):
        SourceMetadata(
            source_url="https://example.com/notice",
            source_type=SourceType.OFFICIAL,
            observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            verification_status="approved",
        )


def test_serialization_round_trip_preserves_pending_status() -> None:
    original = SourceMetadata(
        source_url="https://example.com/notice",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc),
        verification_status=VerificationStatus.PENDING,
    )

    payload = json.loads(original.model_dump_json())
    restored = SourceMetadata.model_validate(payload)

    assert payload["source_type"] == "official"
    assert payload["verification_status"] == "pending"
    assert restored == original
    assert restored.source_type is SourceType.OFFICIAL
    assert restored.verification_status is VerificationStatus.PENDING
