import json

from competition_copilot.domain.resource import LearningResource, ResourceType
from competition_copilot.domain.skill import Skill, SkillLevel, StudentSkill
from competition_copilot.domain.student import EducationLevel, StudentProfile


def test_student_skill_and_learning_resource_relationships_round_trip() -> None:
    python = Skill(id="python", name="Python")
    rag = Skill(id="rag", name="Retrieval Augmented Generation")

    python_state = StudentSkill(skill_id=python.id, level=SkillLevel.ADVANCED)
    rag_state = StudentSkill(skill_id=rag.id, level=SkillLevel.BEGINNER)
    profile = StudentProfile(
        id="student-1",
        education_level=EducationLevel.GRADUATE,
        major="artificial intelligence",
        weekly_available_hours=10,
        skills=[python_state, rag_state],
    )
    resource = LearningResource(
        id="rag-introduction",
        title="RAG Introduction",
        resource_type=ResourceType.ARTICLE,
        url="https://example.com/rag-introduction",
        skill_ids=[rag.id],
    )

    assert python.id == "python"
    assert rag.id == "rag"
    assert [(skill.skill_id, skill.level) for skill in profile.skills] == [
        (python.id, SkillLevel.ADVANCED),
        (rag.id, SkillLevel.BEGINNER),
    ]
    assert profile.education_level is EducationLevel.GRADUATE
    assert profile.major == "artificial intelligence"
    assert profile.weekly_available_hours == 10
    assert profile.grade is None
    assert profile.school is None
    assert profile.interests == []
    assert profile.goals == []
    assert resource.skill_ids == [rag.id]
    assert resource.description is None
    assert resource.source is None

    for model in [python, rag, python_state, rag_state, profile, resource]:
        payload = model.model_dump(mode="json")
        assert json.loads(json.dumps(payload)) == payload
        assert type(model).model_validate(payload) == model
