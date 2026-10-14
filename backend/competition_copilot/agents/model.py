"""Optional LangChain Core bridge; caller owns provider/config/timeouts/secrets."""

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from competition_copilot.agents.prompts import INTENT_ROUTING_PROMPT
from competition_copilot.agents.routing import IntentModelInput, IntentRoutingProposal


class LangChainIntentModel:
    """One structured model call, no capability binding or tool execution loop."""

    def __init__(self, chat_model: BaseChatModel):
        self._structured = chat_model.with_structured_output(IntentRoutingProposal)

    def propose(self, value: IntentModelInput) -> IntentRoutingProposal:
        messages = [SystemMessage(content=INTENT_ROUTING_PROMPT),
                    HumanMessage(content=json.dumps(value.model_dump(mode="json"), sort_keys=True))]
        return IntentRoutingProposal.model_validate(self._structured.invoke(messages))
