"""Deterministic structural checks for provisional competition candidates."""

from collections.abc import Set

from pydantic import HttpUrl, TypeAdapter, ValidationError

from competition_copilot.ingestion.candidate import (
    CompetitionCandidate,
    IssueSeverity,
    ValidationIssue,
)

_HTTP_URL = TypeAdapter(HttpUrl)


def _error(code: str, message: str, field: str) -> ValidationIssue:
    return ValidationIssue(
        code=code, message=message, field=field, severity=IssueSeverity.ERROR
    )


def _check_url(value: object, field: str) -> ValidationIssue | None:
    if value is None:
        return None
    try:
        _HTTP_URL.validate_python(str(value).strip())
    except ValidationError:
        return _error("INVALID_URL", "URL must use HTTP or HTTPS", field)
    return None


class CompetitionCandidateValidator:
    """Return issues without changing candidate status or stored data."""

    def validate(
        self,
        candidate: CompetitionCandidate,
        *,
        known_competition_ids: Set[str] = frozenset(),
        known_edition_ids: Set[str] = frozenset(),
    ) -> list[ValidationIssue]:
        issues = list(candidate.validation_issues)
        competition = candidate.competition
        edition = candidate.edition

        if competition is None:
            issues.append(
                _error("MISSING_COMPETITION", "Competition is required", "competition")
            )
        elif competition.id in known_competition_ids:
            issues.append(
                _error("DUPLICATE_COMPETITION_ID", "Competition ID already exists", "competition.id")
            )

        if edition is None:
            issues.append(_error("MISSING_EDITION", "Edition is required", "edition"))
        else:
            if edition.id in known_edition_ids:
                issues.append(
                    _error("DUPLICATE_EDITION_ID", "Edition ID already exists", "edition.id")
                )
            if competition is not None and edition.competition_id != competition.id:
                issues.append(
                    _error(
                        "COMPETITION_ID_MISMATCH",
                        "Edition competition ID does not match Competition ID",
                        "edition.competition_id",
                    )
                )
            if edition.source is None:
                issues.append(
                    _error(
                        "MISSING_SOURCE_METADATA",
                        "Edition source metadata is required",
                        "edition.source",
                    )
                )

        for index, track in enumerate(candidate.tracks):
            if edition is not None and track.edition_id != edition.id:
                issues.append(
                    _error(
                        "TRACK_EDITION_ID_MISMATCH",
                        "Track edition ID does not match Edition ID",
                        f"tracks[{index}].edition_id",
                    )
                )
            if track.source is None:
                issues.append(
                    _error(
                        "MISSING_SOURCE_METADATA",
                        "Track source metadata is required",
                        f"tracks[{index}].source",
                    )
                )

        url_fields: list[tuple[str, object]] = [
            ("raw_data.source_url", candidate.raw_data.source_url),
            ("raw_data.official_url", candidate.raw_data.official_url),
        ]
        if competition is not None:
            url_fields.append(("competition.official_url", competition.official_url))
        if edition is not None:
            url_fields.append(("edition.official_url", edition.official_url))
            if edition.source is not None:
                url_fields.append(("edition.source.source_url", edition.source.source_url))
        for index, track in enumerate(candidate.tracks):
            url_fields.append((f"tracks[{index}].official_url", track.official_url))
            if track.source is not None:
                url_fields.append((f"tracks[{index}].source.source_url", track.source.source_url))
        for field, value in url_fields:
            issue = _check_url(value, field)
            if issue is not None:
                issues.append(issue)

        return issues
