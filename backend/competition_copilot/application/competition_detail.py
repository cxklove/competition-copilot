"""Student-independent authoritative read projection. No decisions or IO."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from competition_copilot.application.eligibility import EligibilityPolicyProvider
from competition_copilot.application.skill_requirements import SkillRequirementProvider
from competition_copilot.application.temporal_evidence import (
    TemporalCandidateSnapshot,
    TemporalEvidenceProvider,
)
from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.digital_twin import ObservationState, StableId
from competition_copilot.domain.eligibility_policy import (
    EducationLevelConstraint,
    EligibilityPolicy,
)
from competition_copilot.domain.skill_requirement_artifact import (
    SkillRequirementSetEnvelope,
)
from competition_copilot.domain.student import EducationLevel
from competition_copilot.repositories.competition import CompetitionRepository
from competition_copilot.repositories.provenance import (
    CompetitionProvenance,
    CompetitionProvenanceReader,
)


class DetailSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def detach(cls, value):
        return value.model_dump() if isinstance(value, BaseModel) else value

    def model_copy(self, *, update=None, deep=False):
        if update is not None:
            raise TypeError("Construct a validated detail snapshot")
        return super().model_copy(deep=deep)


class DetailCompetition(Competition, DetailSnapshot):
    pass


class DetailEdition(CompetitionEdition, DetailSnapshot):
    pass


class DetailTrack(CompetitionTrack, DetailSnapshot):
    pass


class DetailConstraint(EducationLevelConstraint, DetailSnapshot):
    allowed_levels: tuple[EducationLevel, ...] = Field(min_length=1)


class DetailPolicy(EligibilityPolicy, DetailSnapshot):
    constraints: tuple[DetailConstraint, ...] = ()


class CompetitionDetailQuery(DetailSnapshot):
    competition_id: StableId
    edition_id: StableId | None = None
    track_id: StableId | None = None

    @model_validator(mode="after")
    def hierarchy(self) -> Self:
        if self.track_id and not self.edition_id:
            raise ValueError("track_id requires edition_id")
        return self


class DetailSectionAvailability(DetailSnapshot):
    requested: bool
    state: ObservationState
    reason: str | None = None


class DetailAvailability(DetailSnapshot):
    competition: DetailSectionAvailability
    editions: DetailSectionAvailability
    tracks: DetailSectionAvailability
    time_windows: DetailSectionAvailability
    eligibility_policy: DetailSectionAvailability
    skill_requirements: DetailSectionAvailability
    provenance: DetailSectionAvailability
    event_history: DetailSectionAvailability


class CompetitionDetailProjection(DetailSnapshot):
    query: CompetitionDetailQuery
    competition: DetailCompetition
    editions: tuple[DetailEdition, ...]
    selected_edition: DetailEdition | None = None
    tracks: tuple[DetailTrack, ...] = ()
    selected_track: DetailTrack | None = None
    eligibility_policy: DetailPolicy | None = None
    skill_requirements: SkillRequirementSetEnvelope | None = None
    provenance: tuple[CompetitionProvenance, ...]
    availability: DetailAvailability
    temporal_candidates: tuple[TemporalCandidateSnapshot, ...] = ()
    temporal_candidates_availability: DetailSectionAvailability = Field(default_factory=lambda:
        DetailSectionAvailability(requested=False, state=ObservationState.UNKNOWN,
                                  reason="PROVIDER_NOT_CONFIGURED"))

    @model_validator(mode="after")
    def exact_identity(self) -> Self:
        q = self.query
        if self.competition.id != q.competition_id:
            raise ValueError("Competition identity mismatch")
        if any(e.competition_id != q.competition_id for e in self.editions):
            raise ValueError("Edition parent mismatch")
        if (self.selected_edition.id if self.selected_edition else None) != q.edition_id:
            raise ValueError("Selected edition mismatch")
        if self.selected_edition and self.selected_edition not in self.editions:
            raise ValueError("Selected edition not in repository list")
        if any(t.edition_id != q.edition_id for t in self.tracks):
            raise ValueError("Track parent mismatch")
        if (self.selected_track.id if self.selected_track else None) != q.track_id:
            raise ValueError("Selected track mismatch")
        if self.selected_track and self.selected_track not in self.tracks:
            raise ValueError("Selected track not in repository list")
        target = (q.competition_id, q.edition_id, q.track_id)
        if self.eligibility_policy:
            p = self.eligibility_policy
            if (p.competition_id, p.edition_id, p.track_id) != target:
                raise ValueError("Policy target mismatch")
        if self.skill_requirements:
            t = self.skill_requirements.requirement_set.target
            if (t.competition_id, t.edition_id, t.track_id) != target:
                raise ValueError("Requirement target mismatch")
        for p in self.provenance:
            if p.competition_id != q.competition_id or (
                q.edition_id is not None and p.edition_id != q.edition_id
            ):
                raise ValueError("Provenance target mismatch")
        for candidate in self.temporal_candidates:
            if (candidate.competition_id != q.competition_id or candidate.edition_id != q.edition_id
                or candidate.track_id not in (None, q.track_id)):
                raise ValueError("Temporal candidate target mismatch")
        return self


def _availability(requested: bool, known: bool, reason: str | None = None):
    return DetailSectionAvailability(requested=requested,
        state=ObservationState.KNOWN_VALUE if known else ObservationState.UNKNOWN,
        reason=(None if known else reason) if requested else "NOT_REQUESTED")


class CompetitionDetailReader:
    def __init__(self, repository: CompetitionRepository,
                 policies: EligibilityPolicyProvider, requirements: SkillRequirementProvider,
                 provenance: CompetitionProvenanceReader,
                 temporal_evidence: TemporalEvidenceProvider | None = None):
        self.repository, self.policies = repository, policies
        self.requirements, self.provenance = requirements, provenance
        self.temporal_evidence = temporal_evidence

    def read(self, query: CompetitionDetailQuery) -> CompetitionDetailProjection:
        q = CompetitionDetailQuery.model_validate(query)
        competition = self.repository.get_competition(q.competition_id)
        editions = tuple(self.repository.list_editions_by_competition(q.competition_id))
        edition = self.repository.get_edition(q.edition_id) if q.edition_id else None
        if edition and edition.competition_id != q.competition_id:
            raise ValueError("Edition parent mismatch")
        tracks = tuple(self.repository.list_tracks(q.edition_id)) if edition else ()
        track = self.repository.get_track(q.track_id) if q.track_id else None
        if track and track.edition_id != q.edition_id:
            raise ValueError("Track parent mismatch")
        policy = self.policies.get_policy(q.competition_id, q.edition_id, q.track_id) if edition else None
        artifacts = self.requirements.list_artifacts() if edition else ()
        matches = tuple(a for a in artifacts if (
            a.requirement_set.target.competition_id, a.requirement_set.target.edition_id,
            a.requirement_set.target.track_id) == (q.competition_id, q.edition_id, q.track_id))
        if len(matches) > 1:
            raise ValueError("Duplicate requirement target")
        requirement = matches[0] if matches else None
        provenance = self.provenance.read_provenance(q.competition_id, q.edition_id)
        candidates = self.temporal_evidence.read_candidates(q.competition_id, q.edition_id,
            q.track_id) if edition and self.temporal_evidence is not None else ()
        return CompetitionDetailProjection(
            query=q, competition=competition, editions=editions, selected_edition=edition,
            tracks=tracks, selected_track=track, eligibility_policy=policy,
            skill_requirements=requirement, provenance=provenance,
            temporal_candidates=candidates,
            temporal_candidates_availability=_availability(bool(edition), bool(candidates),
                "PROVIDER_NOT_CONFIGURED" if self.temporal_evidence is None else "NO_ADMITTED_CANDIDATE"),
            availability=DetailAvailability(
                competition=_availability(True, True), editions=_availability(True, True),
                tracks=_availability(bool(edition), bool(edition)),
                time_windows=_availability(bool(edition), bool(edition and (
                    edition.registration_window is not None or edition.competition_window is not None))),
                eligibility_policy=_availability(bool(edition), policy is not None, "NO_EXACT_POLICY"),
                skill_requirements=_availability(bool(edition), requirement is not None, "NO_EXACT_ARTIFACT"),
                provenance=_availability(True, bool(provenance)),
                event_history=_availability(True, False, "EVENT_HISTORY_PERSISTENCE_GAP"),
            ),
        )
