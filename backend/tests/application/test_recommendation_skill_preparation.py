"""Versioned requirement preparation through the existing abstract provider."""

import pytest

from competition_copilot.application.eligibility import CompetitionEligibilityEvaluator
from competition_copilot.application.recommendation import (
    RecommendationContextAssembler,
)
from competition_copilot.domain.skill_requirement_artifact import (
    SkillRequirementSetEnvelope,
)
from competition_copilot.domain.student import StudentProfile
from tests.application.test_recommendation_assembler import Policies, Repository
from tests.domain.test_skill_requirement_artifact import artifact_data


def artifact():
    raw = artifact_data(edition_id="a-2026")
    raw["requirement_set"]["target"]["competition_id"] = "a"
    raw["requirement_set"]["requirements"][0].update(required_level=None, evidence=[])
    return SkillRequirementSetEnvelope.model_validate(raw)


class Requirements:
    def list_artifacts(self):
        return (artifact(),)

    def get_requirements(self, competition_id, edition_id, track_id=None):
        return artifact().requirement_set if (competition_id, edition_id, track_id) == ("a", "a-2026", None) else None


def assemble(provider):
    repository = Repository()
    return RecommendationContextAssembler(repository,
        CompetitionEligibilityEvaluator(repository, Policies()), provider).assemble(StudentProfile(id="s"))


def test_optional_provider_backward_compatible_and_exact_versioned_facts_prepared():
    assert all(c.skill_requirements is None for c in assemble(None))
    contexts = assemble(Requirements())
    assert contexts[0].skill_requirements.requirement_version == "synthetic-v1"
    assert contexts[0].skill_requirements.requirement_set == artifact().requirement_set
    assert all(c.skill_requirements is None for c in contexts[1:])
    assert Requirements().get_requirements("a", "a-2026", "another-track") is None


def test_provider_wrong_target_fails_closed():
    class WrongTarget(Requirements):
        def get_requirements(self, *args):
            return artifact().requirement_set

    with pytest.raises(ValueError, match="Requirement target mismatch"):
        assemble(WrongTarget())


def test_unversioned_inconsistent_or_duplicate_snapshot_fails_closed():
    class Unversioned(Requirements):
        def list_artifacts(self):
            return ()

    with pytest.raises(ValueError, match="version snapshot mismatch"):
        assemble(Unversioned())

    class Duplicate(Requirements):
        def list_artifacts(self):
            return (artifact(), artifact())

    with pytest.raises(ValueError, match="Duplicate"):
        assemble(Duplicate())

    class Changed(Requirements):
        def get_requirements(self, competition_id, edition_id, track_id=None):
            original = super().get_requirements(competition_id, edition_id, track_id)
            if original is None:
                return None
            data = original.model_dump()
            data["coverage_note"] = "Changed after version snapshot"
            return type(original).model_validate(data)

    with pytest.raises(ValueError, match="version snapshot mismatch"):
        assemble(Changed())

    class Dropped(Requirements):
        def get_requirements(self, *args):
            return None

    with pytest.raises(ValueError, match="version snapshot mismatch"):
        assemble(Dropped())
