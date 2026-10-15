"""Optional LangChain Core bridge; caller owns provider/config/timeouts/secrets."""

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from competition_copilot.agents.explanation import ExplanationContext, ExplanationDraft
from competition_copilot.agents.human_contracts import ClarificationResolutionProposal
from competition_copilot.agents.prompts import (
    EXPLANATION_PROMPT,
    HUMAN_CLARIFICATION_PROMPT,
    INTENT_ROUTING_PROMPT,
)
from competition_copilot.agents.routing import IntentModelInput, IntentRoutingProposal


class LangChainIntentModel:
    """One structured model call, no capability binding or tool execution loop."""

    def __init__(self, chat_model: BaseChatModel):
        self._structured = chat_model.with_structured_output(IntentRoutingProposal)

    def propose(self, value: IntentModelInput) -> IntentRoutingProposal:
        messages = [SystemMessage(content=INTENT_ROUTING_PROMPT),
                    HumanMessage(content=json.dumps(value.model_dump(mode="json"), sort_keys=True))]
        return IntentRoutingProposal.model_validate(self._structured.invoke(messages))


class LangChainHumanResponseInterpreter:
    """Optional clarification interpreter; approval uses no model inference."""
    def __init__(self, chat_model: BaseChatModel):
        self._structured = chat_model.with_structured_output(ClarificationResolutionProposal)

    def clarify(self, message, question, options):
        payload = {"message": message.model_dump(mode="json"),
                   "question": question.model_dump(mode="json"),
                   "options": [o.model_dump(mode="json") for o in options]}
        result = self._structured.invoke([SystemMessage(content=HUMAN_CLARIFICATION_PROMPT),
                                         HumanMessage(content=json.dumps(payload, sort_keys=True))])
        return ClarificationResolutionProposal.model_validate(result)


class LangChainExplanationModel:
    """Optional injected model; schema-constrained composition, no tool binding."""
    def __init__(self, chat_model: BaseChatModel):
        self._structured = chat_model.with_structured_output(ExplanationDraft)

    def explain(self, context: ExplanationContext) -> ExplanationDraft:
        projection = context.model_dump(mode="json")
        evidence = projection.pop("evidence")
        payload = {"AUTHORITATIVE RESULT": projection,
            "EVIDENCE DATA": [e for e in evidence if e["kind"] != "SOURCE"],
            "SOURCE DATA": [e for e in evidence if e["kind"] == "SOURCE"]}
        result = self._structured.invoke([SystemMessage(content=EXPLANATION_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False, sort_keys=True))])
        return ExplanationDraft.model_validate(result)
