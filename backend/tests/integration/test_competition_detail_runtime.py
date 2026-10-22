"""Real local hosting includes the AgentArts envelope/adapter and Graph/Facade."""

from unittest.mock import patch

import pytest
from test_generated_huawei_replanning import artifacts
from test_local_cloud_llm import Chat, host, invoke, request

from competition_copilot.agents.capabilities import AgentCapabilityFacade
from competition_copilot.application.competition_detail import (
    CompetitionDetailProjection,
)


@pytest.mark.parametrize("context", [
    {"competition_id": "comap-mcm"},
    {"competition_id": "comap-mcm", "edition_id": "comap-mcm-2027"},
    {"competition_id": "huawei-ict", "edition_id": "huawei-ict-2026",
     "track_id": "huawei-ict-2026-innovation"},
])
def test_explicit_detail_zero_cloud_calls_through_real_facade(context):
    chat = Chat(intent_failure=True)
    target = host(chat)
    body = request("read details", context)
    body["request"]["intent"] = "GET_COMPETITION_DETAILS"
    calls = []
    original = AgentCapabilityFacade.execute

    def observe(self, invocation, *args, **kwargs):
        calls.append(invocation.capability)
        metadata = next(m for m in self.list_capabilities() if m.capability == invocation.capability)
        assert metadata.access == "READ"
        return original(self, invocation, *args, **kwargs)

    with patch.object(AgentCapabilityFacade, "execute", observe):
        result = invoke(target, body)
    assert result["runtime"]["response"]["outcome"] == "COMPLETED", result
    projection = artifacts(result, "CompetitionDetailProjection")[0]
    parsed = CompetitionDetailProjection.model_validate(projection)
    assert parsed.query.model_dump(exclude_none=True) == context
    assert calls == ["get_competition_details"]
    assert chat.calls == []


def test_detail_missing_and_conflicting_ids_fail_closed():
    target = host(Chat(intent_failure=True))
    for index, context in enumerate(({}, {"competition_id": "comap-mcm", "edition_id": "huawei-ict-2026"})):
        body = request("read", context, str(index))
        body["request"]["intent"] = "GET_COMPETITION_DETAILS"
        result = invoke(target, body)
        assert result["runtime"]["response"]["outcome"] != "COMPLETED"
        assert not artifacts(result, "CompetitionDetailProjection")
