"""Reference-only freshness is deterministic immutable read metadata."""
import pytest
from pydantic import ValidationError

from competition_copilot.application.profile_freshness import (
    ProfileFreshness,
    resolve_profile_freshness,
)
from competition_copilot.repositories.student import ProfileReference


def ref(**changes):
    return ProfileReference(student_id="student", version=1, content_digest="a" * 64,
        host_scope="host", **changes) if not changes else ProfileReference.model_validate({
            **ref().model_dump(), **changes})


@pytest.mark.parametrize("before,after,status,reason", [
    (ref(), ref(), "CURRENT", "EXACT_REFERENCE_MATCH"),
    (ref(), ref(version=2), "STALE", "PROFILE_REFERENCE_CHANGED"),
    (ref(), ref(content_digest="b" * 64), "STALE", "PROFILE_REFERENCE_CHANGED"),
    (None, ref(), "UNKNOWN", "RESULT_PROFILE_REFERENCE_UNKNOWN"),
    (ref(), None, "UNKNOWN", "CURRENT_PROFILE_NOT_FOUND"),
    (ref(), ref(student_id="other"), "UNKNOWN", "RESULT_PROFILE_IDENTITY_MISMATCH"),
    (ref(student_id="other"), ref(), "UNKNOWN", "RESULT_PROFILE_IDENTITY_MISMATCH"),
    (ref(), ref(host_scope="new-host"), "UNKNOWN", "HOST_SCOPE_INCOMPARABLE"),
])
def test_freshness_exact_semantics(before, after, status, reason):
    value = resolve_profile_freshness(before, after, student_id="student")
    assert (value.status, value.reason) == (status, reason)
    assert resolve_profile_freshness(before, after, student_id="student") == value
    assert ProfileFreshness.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        value.status = "STALE"
    if before:
        with pytest.raises(ValidationError):
            value.input_profile_ref.version = 12
