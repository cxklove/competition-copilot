"""Canonical URL extension must preserve all pre-fix successful hash semantics."""

from datetime import date, datetime, timedelta, timezone
from enum import Enum

import pytest
from pydantic import AnyHttpUrl, AnyUrl, BaseModel, HttpUrl, TypeAdapter

from competition_copilot.domain.plan import CompetitionPlan, PlanMilestone, PlanStatus
from competition_copilot.domain.replanning import (
    PlanReference,
    _canonical,
    _digest,
    revised_plan_identity,
)


def legacy_plan():
    return CompetitionPlan(id="legacy-plan", student_id="legacy-student",
        competition_id="legacy-competition", edition_id="legacy-edition",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        milestones=(PlanMilestone(id="m1", title="Legacy task"),))


def test_pre_fix_url_free_identity_constants_are_preserved():
    # Recorded against unmodified production code before the URL extension.
    plan = legacy_plan()
    assert PlanReference.from_plan(plan).content_digest == (
        "2361f6b8e93a1f0c887635ca5e4676068f7210cbcc03eb6c50fbdfda16248c79"
    )
    milestones = (PlanMilestone(id="m1", title="Legacy task",
                                due_at=datetime(2026, 1, 10, tzinfo=timezone.utc)),)
    assert revised_plan_identity(plan, milestones) == (
        "revised-plan-v1:73be6b6e24f552a704322fcd9cd6c5509357be72aa708073fc1f1c6ac8eb938b"
    )


def test_pre_fix_instruction_and_input_ids_are_preserved():
    from tests.domain.test_replanning_input_contract import batch, instruction
    value = instruction()
    result = batch(instructions=(value,), status="executable")
    assert value.id == (
        "replanning-instruction-v1:054ffd83269bdb7cc222ac17063edaba332bf5abcff5a49de6f36ffe6846c6a5"
    )
    assert result.id == (
        "replanning-input-v1:ef70cbc98c4209d68109eae4fb4042c393e796b553b68a2f23c2eef2cb957001"
    )


@pytest.mark.parametrize("url_type", [AnyUrl, HttpUrl, AnyHttpUrl])
def test_typed_url_matches_formal_json_serialization(url_type):
    first = url_type("HTTPS://EXAMPLE.COM:443/test")
    second = url_type("https://example.com/test")
    formal = TypeAdapter(url_type).dump_python(first, mode="json")
    assert formal == "https://example.com/test"
    assert _canonical(first) == formal
    assert _digest({"url": first}) == _digest({"url": formal}) == _digest({"url": second})


def test_datetime_enum_collection_and_key_order_semantics_are_unchanged():
    utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    offset = utc.astimezone(timezone(timedelta(hours=8)))
    first = {"z": (None, True, 3, 1.5, PlanStatus.ACTIVE), "a": offset}
    second = {"a": utc, "z": [None, True, 3, 1.5, "active"]}
    assert _canonical(first) == {"z": [None, True, 3, 1.5, PlanStatus.ACTIVE], "a": "2026-01-01T00:00:00+00:00"}
    assert _digest(first) == _digest(second)


class UnsupportedEnum(Enum):
    MEMBER = "member"


class UnsupportedModel(BaseModel):
    value: int


@pytest.mark.parametrize("value", [object(), date(2026, 1, 1), UnsupportedEnum.MEMBER, UnsupportedModel(value=1)])
def test_unknown_or_previously_unsupported_types_still_fail(value):
    with pytest.raises(TypeError):
        _digest({"unsupported": value})
