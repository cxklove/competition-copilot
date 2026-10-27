"""Shared synthetic repositories and policies for recommendation tests."""

from datetime import datetime, timezone

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.eligibility_policy import (
    EducationLevelConstraint,
    EligibilityPolicy,
)
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.repositories.competition import RepositoryEntityNotFoundError


class Repository:
    def list_competitions(self):
        return [Competition(id=key, name=key) for key in ("c", "b", "a")]

    def list_editions_by_competition(self, key):
        return [self.get_edition(key + "-2026")]

    def get_competition(self, key):
        return next(c for c in self.list_competitions() if c.id == key)

    def get_edition(self, key):
        return CompetitionEdition(id=key, competition_id=key[0], name=key, year=2026)

    def get_track(self, key):
        if key != "c-track":
            raise RepositoryEntityNotFoundError("track", key)
        return CompetitionTrack(id=key, edition_id="c-2026", name="Explicit anchor")


class Policies:
    def get_policy(self, competition_id, edition_id, track_id=None):
        if competition_id == "b":
            return None  # Real P5 UNKNOWN, not an execution failure.
        source = SourceMetadata(source_url="https://example.org/test-rules", source_type="official",
            observed_at=datetime(2026, 10, 20, tzinfo=timezone.utc), verification_status="verified")
        return EligibilityPolicy(competition_id=competition_id, edition_id=edition_id,
            track_id=track_id, coverage="complete", coverage_note="Synthetic complete policy", source=source,
            constraints=[EducationLevelConstraint(rule_id="education", scope="edition", target_id=edition_id,
                allowed_levels=["graduate" if competition_id == "a" else "undergraduate"],
                source=source, evidence_text="Synthetic education restriction")])
