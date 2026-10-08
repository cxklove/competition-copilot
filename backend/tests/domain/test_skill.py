import json

import pytest
from pydantic import ValidationError

from competition_copilot.domain.skill import Skill, SkillLevel, StudentSkill


def test_valid_minimal_skill() -> None:
    skill = Skill(id="python", name="Python")

    assert skill.id == "python"
    assert skill.name == "Python"
    assert skill.description is None
    assert skill.aliases == []


def test_valid_complete_skill() -> None:
    skill = Skill(
        id="rag",
        name="Retrieval Augmented Generation",
        description="Builds systems using retrieved context.",
        aliases=["RAG", "retrieval augmented generation"],
    )

    assert skill.description == "Builds systems using retrieved context."
    assert skill.aliases == ["RAG", "retrieval augmented generation"]


def test_missing_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="id"):
        Skill(name="Python")


@pytest.mark.parametrize("identifier", ["", " \t\n "])
def test_empty_or_whitespace_only_id_is_rejected(identifier: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        Skill(id=identifier, name="Python")


def test_id_is_trimmed_without_lowercasing() -> None:
    skill = Skill(id="  PyThOn  ", name="Python")

    assert skill.id == "PyThOn"


@pytest.mark.parametrize("name", ["", " \t\n "])
def test_empty_or_whitespace_only_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        Skill(id="python", name=name)


def test_name_is_trimmed_without_lowercasing() -> None:
    skill = Skill(id="python", name="  PyThOn  ")

    assert skill.name == "PyThOn"


def test_description_is_optional() -> None:
    assert Skill(id="python", name="Python").description is None


def test_description_is_trimmed() -> None:
    skill = Skill(id="python", name="Python", description="  Programming language.  ")

    assert skill.description == "Programming language."


def test_whitespace_only_description_is_rejected() -> None:
    with pytest.raises(ValidationError, match="description"):
        Skill(id="python", name="Python", description=" \t ")


def test_aliases_default_to_independent_empty_lists() -> None:
    first = Skill(id="python", name="Python")
    second = Skill(id="rag", name="RAG")

    assert first.aliases == []
    assert second.aliases == []
    first.aliases.append("Py")
    assert second.aliases == []


def test_aliases_are_trimmed() -> None:
    skill = Skill(id="python", name="Python", aliases=["  Py  ", "\tPython 3 "])

    assert skill.aliases == ["Py", "Python 3"]


@pytest.mark.parametrize("alias", ["", " \t\n "])
def test_blank_alias_is_rejected(alias: str) -> None:
    with pytest.raises(ValidationError, match="aliases"):
        Skill(id="python", name="Python", aliases=["Py", alias])


def test_duplicate_aliases_are_removed_after_trimming() -> None:
    skill = Skill(id="python", name="Python", aliases=[" Py ", "Py", "PY"])

    assert skill.aliases == ["Py", "PY"]


def test_alias_order_is_stable() -> None:
    skill = Skill(
        id="agent-workflow",
        name="Agent Workflow",
        aliases=["Workflow", "Agent Flow", "Workflow", "Orchestration"],
    )

    assert skill.aliases == ["Workflow", "Agent Flow", "Orchestration"]


def test_model_dump_is_json_serializable() -> None:
    skill = Skill(
        id="rag",
        name="RAG",
        description="  Retrieval augmented generation.  ",
        aliases=[" Retrieval ", "Retrieval", "RAG"],
    )
    expected = {
        "id": "rag",
        "name": "RAG",
        "description": "Retrieval augmented generation.",
        "aliases": ["Retrieval", "RAG"],
    }

    assert skill.model_dump(mode="json") == expected
    assert json.loads(skill.model_dump_json()) == expected


def test_model_validate_round_trip() -> None:
    original = Skill(
        id="mcp",
        name="MCP",
        description="Model Context Protocol",
        aliases=["Model Context Protocol", "MCP protocol"],
    )

    assert Skill.model_validate(original.model_dump(mode="json")) == original


def test_student_level_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="student_level"):
        Skill.model_validate({"id": "python", "name": "Python", "student_level": 3})


def test_valid_student_skill() -> None:
    student_skill = StudentSkill(
        skill_id="python",
        level=SkillLevel.INTERMEDIATE,
        self_assessed=False,
        note="Completed a course.",
    )

    assert student_skill.skill_id == "python"
    assert student_skill.level is SkillLevel.INTERMEDIATE
    assert student_skill.self_assessed is False
    assert student_skill.note == "Completed a course."


def test_student_skill_defaults_to_unknown() -> None:
    student_skill = StudentSkill(skill_id="python")

    assert student_skill.level is SkillLevel.UNKNOWN


@pytest.mark.parametrize(
    "level", [SkillLevel.BEGINNER, SkillLevel.INTERMEDIATE, SkillLevel.ADVANCED]
)
def test_student_skill_accepts_known_levels(level: SkillLevel) -> None:
    assert StudentSkill(skill_id="python", level=level).level is level


@pytest.mark.parametrize("skill_id", ["", " \t\n "])
def test_empty_student_skill_id_is_rejected(skill_id: str) -> None:
    with pytest.raises(ValidationError, match="skill_id"):
        StudentSkill(skill_id=skill_id)


def test_student_skill_id_is_trimmed() -> None:
    student_skill = StudentSkill(skill_id="  python \t")

    assert student_skill.skill_id == "python"


@pytest.mark.parametrize("level", ["expert", 3])
def test_invalid_student_skill_level_is_rejected(level: object) -> None:
    with pytest.raises(ValidationError, match="level"):
        StudentSkill.model_validate({"skill_id": "python", "level": level})


def test_self_assessed_defaults_to_true() -> None:
    assert StudentSkill(skill_id="python").self_assessed is True


def test_student_skill_note_is_optional() -> None:
    assert StudentSkill(skill_id="python").note is None


def test_student_skill_note_is_trimmed() -> None:
    student_skill = StudentSkill(skill_id="python", note="  Personal note.  ")

    assert student_skill.note == "Personal note."


@pytest.mark.parametrize("note", ["", " \t\n "])
def test_blank_student_skill_note_is_rejected(note: str) -> None:
    with pytest.raises(ValidationError, match="note"):
        StudentSkill(skill_id="python", note=note)


def test_student_skill_serialization() -> None:
    student_skill = StudentSkill(
        skill_id="python", level=SkillLevel.BEGINNER, note="Learning syntax."
    )
    expected = {
        "skill_id": "python",
        "level": "beginner",
        "self_assessed": True,
        "note": "Learning syntax.",
    }

    assert student_skill.model_dump(mode="json") == expected
    assert json.loads(student_skill.model_dump_json()) == expected


def test_student_skill_model_validate_round_trip() -> None:
    original = StudentSkill(
        skill_id="mcp", level=SkillLevel.ADVANCED, self_assessed=False
    )

    restored = StudentSkill.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.level is SkillLevel.ADVANCED


def test_student_skill_does_not_check_skill_exists() -> None:
    student_skill = StudentSkill(skill_id="skill-not-yet-stored")

    assert student_skill.skill_id == "skill-not-yet-stored"


def test_student_skill_rejects_numeric_score() -> None:
    with pytest.raises(ValidationError, match="score"):
        StudentSkill.model_validate({"skill_id": "python", "score": 90})
