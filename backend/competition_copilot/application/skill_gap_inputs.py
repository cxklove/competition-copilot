"""Explicit P7 input assembly; missing provider artifacts remain MISSING."""

from competition_copilot.application.skill_requirements import SkillRequirementProvider
from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.skill_gap import (
    SkillGapContext,
    SkillRequirementSet,
    SkillRequirementTarget,
)
from competition_copilot.domain.student import StudentProfile
from competition_copilot.repositories.competition import CompetitionRepository


def prepare_skill_gap_context(repository: CompetitionRepository, provider: SkillRequirementProvider,
                              student: StudentProfile, competition_id: str, edition_id: str,
                              track_id: str | None, evidence: tuple[Evidence, ...]) -> SkillGapContext:
    requirements = provider.get_requirements(competition_id, edition_id, track_id)
    if requirements is None:
        requirements = SkillRequirementSet(target=SkillRequirementTarget(
            scope="track" if track_id else "edition", competition_id=competition_id,
            edition_id=edition_id, track_id=track_id), coverage="missing",
            coverage_note="No reviewed skill requirement artifact is available for this exact target.")
    return SkillGapContext(student_profile=student,
        competition=repository.get_competition(competition_id), edition=repository.get_edition(edition_id),
        track=repository.get_track(track_id) if track_id else None,
        requirements=requirements, student_skill_evidence=evidence)
