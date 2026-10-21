"""One untrusted proposal for argument preparation and the unchanged P12 graph."""

from competition_copilot.agents.contracts import (
    CapabilityInvocationRequest,
    ResultReference,
)
from competition_copilot.agents.graph import GraphInput
from competition_copilot.agents.human_contracts import ClarificationOption
from competition_copilot.agents.routing import (
    IntentModelInput,
    IntentRoutingProposal,
    RoutingProposalValidator,
    routing_catalog,
)


class PreparedIntentModel:
    def __init__(self, model, request):
        self.model = model
        self.request = request
        self.catalog = None
        self.proposal = None
        self.preparation_capability = None
        self.confirmed_fields = set()
        self.resume_fields = ()

    def prepare(self, facade, frame):
        if self.catalog is not None:
            raise ValueError("INTENT_ALREADY_PREPARED")
        self.catalog = routing_catalog(facade)
        try:
            self.proposal = IntentRoutingProposal.model_validate(
                self.model.propose(IntentModelInput(request=self.request, catalog=self.catalog)))
            # Model hints cannot establish whether authoritative input exists.
            # Normalize before BOTH preflight and final graph validation; the
            # unchanged validator derives missing fields from prepared arguments.
            self.proposal = IntentRoutingProposal(**{
                **self.proposal.model_dump(), "missing_context": (),
            })
            # Reuse P12 safety/catalog admission before preparing any arguments.
            # Missing typed payload is expected here. Graph performs final P12
            # validation with the completed payload before authorizing execution.
            validation = RoutingProposalValidator(facade).validate(self.proposal, self.request,
                invocation_id=frame.routing_invocation_id, arguments_ref=frame.routing_arguments_ref,
                arguments={"artifact_ref": frame.routing_arguments_ref.model_dump(mode="json"), "payload": {}})
            if validation.reason in ("VALIDATED", "MISSING_CONTEXT", "APPROVAL_REQUIRED"):
                self.preparation_capability = self.proposal.candidate_capability
        except Exception:
            # Preserve P12's normal INTENT_MODEL_FAILED path with no raw exception.
            self.proposal = None

    def observe_resume(self, prior, reply):
        self.resume_fields = (prior.state.clarification.fields
                              if prior.state.status == "NEEDS_CLARIFICATION" else ())

    def observe_retained(self, frame):
        if frame.state.clarification_response:
            self.confirmed_fields.update(frame.state.clarification_response.values.provided_fields)

    def propose(self, value):
        if (self.proposal is None or value.request.request_id != self.request.request_id
            or value.request.user_message != self.request.user_message or value.catalog != self.catalog):
            raise ValueError("PREPARED_INTENT_UNAVAILABLE")
        # P12 enters intent again only AFTER its clarification resolver has
        # accepted every field of the pending question. Partial resolutions return
        # to clarification instead. Never clear hints on raw browser input alone.
        self.confirmed_fields.update(self.resume_fields)
        self.resume_fields = ()
        return IntentRoutingProposal(**{**self.proposal.model_dump(), "missing_context": tuple(
            item for item in self.proposal.missing_context if item not in self.confirmed_fields)})


def retain_competition_choices(prepared, facade, frame):
    """Caller-owned P4 read choices for P12's existing exact-label interpreter.

    No inferred ID or new clarification policy: only COMPETITION read choices are
    available here. Other fields continue to require structured public responses.
    """
    prepared.observe_retained(frame)
    question = frame.state.clarification
    if question is None or "COMPETITION" not in question.fields:
        return frame
    ref = ResultReference(kind="TOOL_RESULT", ref_id=frame.result_ref.ref_id + "/choices")
    args = ResultReference(kind="CAPABILITY_ARGUMENTS", ref_id=ref.ref_id + "/arguments")
    receipt = facade.execute(CapabilityInvocationRequest(invocation_id=ref.ref_id + "/invoke",
        source_request_id=frame.state.request.request_id, intent="DISCOVER_COMPETITIONS",
        capability="list_competitions", arguments_ref=args),
        {"artifact_ref": args.model_dump(mode="json"), "payload": {}}, result_ref=ref)
    if receipt.status != "SUCCESS":
        return frame
    choices = tuple(ClarificationOption(field="COMPETITION", value=item.id, label=item.name,
        source_ref=ref) for item in receipt.data.competitions)
    return GraphInput(**{**frame.model_dump(), "clarification_options": choices})
