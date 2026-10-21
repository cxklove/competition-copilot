"""Thin P5 Facade bridge for the shared Application candidate assembler."""

from competition_copilot.agents.contracts import (
    CapabilityInvocationRequest,
    ResultReference,
)


class FacadeEligibilityEvaluator:
    """Allocate distinct prerequisite audit references; never decide eligibility."""

    def __init__(self, facade, *, request_id, namespace):
        self._facade = facade
        self._request_id = request_id
        self._namespace = namespace
        self._count = 0

    def evaluate(self, student_profile, competition_id, edition_id, track_id=None):
        self._count += 1
        ref = f"{self._namespace}/eligibility/{self._count}"
        args = ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id=ref + "/arguments")
        receipt = self._facade.execute(CapabilityInvocationRequest(
            invocation_id=ref + "/invoke", source_request_id=self._request_id,
            intent="CHECK_ELIGIBILITY", capability="check_eligibility", arguments_ref=args),
            {"artifact_ref": args.model_dump(mode="json"), "payload": {
                "student": student_profile.model_dump(mode="json"),
                "competition_id": competition_id, "edition_id": edition_id, "track_id": track_id}},
            result_ref=ResultReference(kind="TOOL_RESULT", ref_id=ref + "/result"))
        if receipt.status != "SUCCESS":
            raise ValueError("P5 prerequisite unavailable")
        return receipt.data
