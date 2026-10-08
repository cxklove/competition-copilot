"""Deterministic formatting of raw competition data into provisional models."""

import re
from datetime import datetime

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
from competition_copilot.ingestion.models import RawCompetitionData

_YEAR_PATTERN = re.compile(r"[0-9]+\Z")
_AWARE_ISO_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z"
)


class NormalizationError(ValueError):
    """An explicit raw field could not be formatted without guessing."""

    def __init__(self, code: str, field: str, message: str) -> None:
        self.code = code
        self.field = field
        super().__init__(message)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _required_text(value: str | None, field: str) -> str:
    trimmed = _optional_text(value)
    if trimmed is None:
        raise NormalizationError("MISSING_FIELD", field, f"{field} is required")
    return trimmed


def _year(value: str | int | None) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if _YEAR_PATTERN.fullmatch(trimmed):
            return int(trimmed)
    raise NormalizationError(
        "INVALID_YEAR", "edition_year", "edition_year must be an explicit integer"
    )


def _datetime(value: str | None, field: str) -> datetime | None:
    trimmed = _optional_text(value)
    if trimmed is None:
        return None
    if not _AWARE_ISO_PATTERN.fullmatch(trimmed):
        raise NormalizationError(
            "INVALID_DATETIME", field, f"{field} must be a timezone-aware ISO datetime"
        )
    try:
        parsed = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizationError(
            "INVALID_DATETIME", field, f"{field} is not a valid ISO datetime"
        ) from exc
    if parsed.utcoffset() is None:
        raise NormalizationError(
            "INVALID_DATETIME", field, f"{field} must include a timezone offset"
        )
    return parsed


def _window(
    start: str | None, end: str | None, field: str
) -> TimeWindow | None:
    start_at = _datetime(start, f"{field}_start")
    end_at = _datetime(end, f"{field}_end")
    if start_at is None and end_at is None:
        return None
    try:
        return TimeWindow(start_at=start_at, end_at=end_at)
    except ValidationError as exc:
        raise NormalizationError("INVALID_WINDOW", field, str(exc)) from exc


class CompetitionNormalizer:
    """Produce provisional models; approval and validation remain separate."""

    def normalize(
        self, raw: RawCompetitionData
    ) -> tuple[Competition, CompetitionEdition, list[CompetitionTrack]]:
        competition_id = _required_text(raw.competition_id, "competition_id")
        edition_id = _required_text(raw.edition_id, "edition_id")
        name = _required_text(raw.name, "name")
        edition_name = _required_text(raw.edition_name, "edition_name")
        year = _year(raw.edition_year)
        source_type_text = _required_text(raw.source_type, "source_type")
        try:
            source_type = SourceType(source_type_text)
        except ValueError as exc:
            raise NormalizationError(
                "INVALID_SOURCE_TYPE", "source_type", "source_type is not supported"
            ) from exc
        try:
            source = SourceMetadata(
                source_url=raw.source_url.strip(),
                source_type=source_type,
                observed_at=raw.observed_at,
                verification_status=VerificationStatus.PENDING,
            )
        except ValidationError as exc:
            raise NormalizationError("INVALID_SOURCE", "source_url", str(exc)) from exc

        registration_window = _window(
            raw.registration_start, raw.registration_end, "registration"
        )
        competition_window = _window(
            raw.competition_start, raw.competition_end, "competition"
        )
        official_url = _optional_text(raw.official_url)
        try:
            competition = Competition(
                id=competition_id,
                name=name,
                short_name=_optional_text(raw.short_name),
                official_url=official_url,
            )
            edition = CompetitionEdition(
                id=edition_id,
                competition_id=competition_id,
                year=year,
                name=edition_name,
                registration_window=registration_window,
                competition_window=competition_window,
                source=source,
            )
        except ValidationError as exc:
            raise NormalizationError("INVALID_COMPETITION", "competition", str(exc)) from exc

        if len(raw.tracks) != len(raw.track_ids):
            raise NormalizationError(
                "TRACK_ID_MISMATCH",
                "track_ids",
                "each track must have an explicit matching id",
            )
        tracks = []
        for index, (track_id, track_name) in enumerate(
            zip(raw.track_ids, raw.tracks, strict=True)
        ):
            try:
                track = CompetitionTrack(
                    id=_required_text(track_id, f"track_ids[{index}]"),
                    edition_id=edition_id,
                    name=_required_text(track_name, f"tracks[{index}]"),
                    source=source,
                )
            except ValidationError as exc:
                raise NormalizationError(
                    "INVALID_TRACK", f"tracks[{index}]", str(exc)
                ) from exc
            tracks.append(track)
        return competition, edition, tracks
