import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain.skill import SkillLevel, StudentSkill
from competition_copilot.domain.student import EducationLevel, StudentProfile


def test_minimal_profile_keeps_missing_information_unknown() -> None:
    profile = StudentProfile(id=" student-1 ")

    assert profile.id == "student-1"
    assert profile.education_level is None
    assert profile.grade is None
    assert profile.school is None
    assert profile.major is None
    assert profile.interests == []
    assert profile.goals == []
    assert profile.weekly_available_hours is None
    assert profile.skills == []


def test_complete_profile() -> None:
    profile = StudentProfile(
        id="student-1",
        education_level=EducationLevel.UNDERGRADUATE,
        grade="Year 2",
        school="Example University",
        major="Computer Science",
        interests=["AI", "Robotics"],
        goals=["Build a prototype"],
        weekly_available_hours=12.5,
        skills=[StudentSkill(skill_id="python", level=SkillLevel.INTERMEDIATE)],
    )

    assert profile.education_level is EducationLevel.UNDERGRADUATE
    assert profile.grade == "Year 2"
    assert profile.school == "Example University"
    assert profile.major == "Computer Science"
    assert profile.interests == ["AI", "Robotics"]
    assert profile.goals == ["Build a prototype"]
    assert profile.weekly_available_hours == 12.5
    assert profile.skills[0].skill_id == "python"


@pytest.mark.parametrize("identifier", ["", " \t\n "])
def test_empty_id_is_rejected(identifier: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        StudentProfile(id=identifier)


@pytest.mark.parametrize(
    "education_level", [None, EducationLevel.UNDERGRADUATE, EducationLevel.GRADUATE]
)
def test_education_level_values(education_level: EducationLevel | None) -> None:
    assert StudentProfile(id="student-1", education_level=education_level).education_level is (
        education_level
    )


def test_other_education_level_is_rejected() -> None:
    with pytest.raises(ValidationError, match="education_level"):
        StudentProfile(id="student-1", education_level="secondary")


def test_grade_does_not_infer_education_level() -> None:
    profile = StudentProfile(id="student-1", grade="Graduate year 1")

    assert profile.grade == "Graduate year 1"
    assert profile.education_level is None


@pytest.mark.parametrize("field", ["grade", "school", "major"])
def test_optional_text_fields_are_trimmed(field: str) -> None:
    profile = StudentProfile.model_validate({"id": "student-1", field: "  Example  "})

    assert getattr(profile, field) == "Example"


@pytest.mark.parametrize("field", ["grade", "school", "major"])
@pytest.mark.parametrize("value", ["", " \t\n "])
def test_blank_optional_text_fields_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        StudentProfile.model_validate({"id": "student-1", field: value})


@pytest.mark.parametrize("field", ["interests", "goals"])
def test_string_lists_are_trimmed_deduplicated_and_ordered(field: str) -> None:
    profile = StudentProfile.model_validate(
        {"id": "student-1", field: ["  AI  ", "Robotics", "AI", "ai"]}
    )

    assert getattr(profile, field) == ["AI", "Robotics", "ai"]


@pytest.mark.parametrize("field", ["interests", "goals"])
@pytest.mark.parametrize("value", ["", " \t\n "])
def test_blank_string_list_items_are_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match=field):
        StudentProfile.model_validate({"id": "student-1", field: ["AI", value]})


@pytest.mark.parametrize("hours", [None, 0, 12.5, 168])
def test_valid_weekly_available_hours(hours: float | None) -> None:
    assert StudentProfile(id="student-1", weekly_available_hours=hours).weekly_available_hours == hours


@pytest.mark.parametrize("hours", [-0.1, 168.1, float("nan"), float("inf")])
def test_invalid_weekly_available_hours_are_rejected(hours: float) -> None:
    with pytest.raises(ValidationError, match="weekly_available_hours"):
        StudentProfile(id="student-1", weekly_available_hours=hours)


def test_skills_accept_student_skill_list_without_repository_lookup() -> None:
    profile = StudentProfile(
        id="student-1",
        major="Computer Science",
        skills=[StudentSkill(skill_id="not-yet-stored"), StudentSkill(skill_id="python")],
    )

    assert [skill.skill_id for skill in profile.skills] == ["not-yet-stored", "python"]
    assert StudentProfile(id="student-2", major="Computer Science").skills == []


def test_default_lists_are_independent() -> None:
    first = StudentProfile(id="student-1")
    second = StudentProfile(id="student-2")

    first.interests.append("AI")
    first.goals.append("Compete")
    first.skills.append(StudentSkill(skill_id="python"))

    assert second.interests == []
    assert second.goals == []
    assert second.skills == []


def test_duplicate_skill_ids_are_rejected_after_trimming() -> None:
    with pytest.raises(ValidationError, match="skill_id"):
        StudentProfile(
            id="student-1",
            skills=[StudentSkill(skill_id=" python "), StudentSkill(skill_id="python")],
        )


def test_non_student_skill_item_is_rejected() -> None:
    with pytest.raises(ValidationError, match="skills"):
        StudentProfile.model_validate({"id": "student-1", "skills": ["python"]})


def test_serialization() -> None:
    profile = StudentProfile(
        id=" student-1 ",
        education_level=EducationLevel.GRADUATE,
        interests=[" AI ", "AI"],
        weekly_available_hours=0,
        skills=[StudentSkill(skill_id="python", level=SkillLevel.BEGINNER)],
    )
    expected = {
        "id": "student-1",
        "education_level": "graduate",
        "grade": None,
        "school": None,
        "major": None,
        "interests": ["AI"],
        "goals": [],
        "weekly_available_hours": 0.0,
        "skills": [
            {"skill_id": "python", "level": "beginner", "self_assessed": True, "note": None}
        ],
    }

    assert profile.model_dump(mode="json") == expected
    assert json.loads(profile.model_dump_json()) == expected


def test_model_validate_round_trip() -> None:
    original = StudentProfile(
        id="student-1",
        education_level=EducationLevel.UNDERGRADUATE,
        goals=["Find a competition"],
        skills=[StudentSkill(skill_id="python", level=SkillLevel.ADVANCED)],
    )

    restored = StudentProfile.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.education_level is EducationLevel.UNDERGRADUATE
    assert restored.skills[0].level is SkillLevel.ADVANCED
