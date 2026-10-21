"""Explicit, backend-only compatible provider wiring; never a business authority."""

import math
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

_PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "bigmodel": "https://open.bigmodel.cn/api/paas/v4/",
    "deepseek": "https://api.deepseek.com",
}


class LocalLLMConfigError(ValueError):
    def __init__(self, code="INVALID_LOCAL_LLM_CONFIG"):
        super().__init__(code)


@dataclass(frozen=True)
class LocalLLMConfig:
    mode: str = "offline"
    model: str | None = None
    timeout: float = 30
    api_key: str | None = field(default=None, repr=False)
    provider: str = "openai"
    base_url: str | None = None
    structured_method: str | None = None
    intent_structured_method: str | None = None
    intent_temperature: float | None = None

    def __post_init__(self):
        if self.mode not in ("offline", "cloud"):
            raise LocalLLMConfigError()
        if self.mode == "offline":
            return
        if self.provider not in _PROVIDER_URLS:
            raise LocalLLMConfigError()
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise LocalLLMConfigError("OPENAI_API_KEY_REQUIRED" if self.provider == "openai"
                                      else "LLM_API_KEY_REQUIRED")
        if (self.api_key != self.api_key.strip() or len(self.api_key) > 4096
            or not all(33 <= ord(c) < 127 for c in self.api_key)
            or not isinstance(self.model, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", self.model)
            or isinstance(self.timeout, bool) or not isinstance(self.timeout, (float, int))
            or not math.isfinite(self.timeout) or not 0 < self.timeout <= 120):
            raise LocalLLMConfigError()
        base_url = _PROVIDER_URLS[self.provider] if self.base_url is None else self.base_url
        try:
            url = urlsplit(base_url)
            default = urlsplit(_PROVIDER_URLS[self.provider])
            # Never send one provider's credential to another origin. Alternate
            # API paths on the selected official origin may be configured.
            if (url.scheme != "https" or url.hostname != default.hostname
                or url.port not in (None, 443) or url.username is not None
                or url.password is not None or url.query or url.fragment
                or not base_url.isascii() or any(c.isspace() for c in base_url)):
                raise ValueError()
        except (TypeError, ValueError, AttributeError):
            raise LocalLLMConfigError() from None
        method = self.structured_method
        if method is None and self.provider != "openai":
            method = "function_calling"
        if method not in (None, "json_schema", "function_calling", "json_mode"):
            raise LocalLLMConfigError()
        intent_method = self.intent_structured_method
        if intent_method is None:
            intent_method = "json_mode" if self.provider == "bigmodel" else method
        if intent_method not in (None, "json_schema", "function_calling", "json_mode"):
            raise LocalLLMConfigError()
        temperature = self.intent_temperature
        if temperature is None and self.provider == "bigmodel":
            temperature = 0.1
        if temperature is not None and (
            isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not math.isfinite(temperature) or not 0 < temperature < 1
        ):
            raise LocalLLMConfigError()
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "structured_method", method)
        object.__setattr__(self, "intent_structured_method", intent_method)
        object.__setattr__(self, "intent_temperature", temperature)

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        mode = env.get("COMPETITION_COPILOT_LLM_MODE", "offline")
        if mode == "offline":
            # Do not load a provider or even read credentials in offline mode.
            return cls()
        try:
            provider = env.get("COMPETITION_COPILOT_LLM_PROVIDER", "openai")
            key = env.get("COMPETITION_COPILOT_LLM_API_KEY")
            if key is None and provider == "openai":
                key = env.get("OPENAI_API_KEY")  # Existing OpenAI demo compatibility only.
            intent_temperature = env.get("COMPETITION_COPILOT_LLM_INTENT_TEMPERATURE")
            return cls(mode=mode, model=env.get("COMPETITION_COPILOT_LLM_MODEL"),
                timeout=float(env.get("COMPETITION_COPILOT_LLM_TIMEOUT_SECONDS", "30")),
                api_key=key, provider=provider,
                base_url=env.get("COMPETITION_COPILOT_LLM_BASE_URL") or None,
                structured_method=env.get("COMPETITION_COPILOT_LLM_STRUCTURED_METHOD") or None,
                intent_structured_method=env.get("COMPETITION_COPILOT_LLM_INTENT_STRUCTURED_METHOD") or None,
                intent_temperature=float(intent_temperature) if intent_temperature else None)
        except (TypeError, ValueError) as error:
            if isinstance(error, LocalLLMConfigError):
                raise
            raise LocalLLMConfigError() from None


@dataclass(frozen=True)
class CloudModels:
    # Provider-neutral P12 interfaces. Only this optional factory imports provider.
    intent: object
    explanation: object
    human_interpreter: object


def create_cloud_models(config: LocalLLMConfig, *, chat_model=None, intent_chat_model=None):
    if config.mode == "offline":
        return None
    from competition_copilot.agents.model import (
        LangChainExplanationModel,
        LangChainHumanResponseInterpreter,
        LangChainIntentModel,
    )

    if chat_model is None:
        try:
            from langchain_openai import ChatOpenAI

            options = {} if config.provider == "openai" else {
                # BigModel documents auto-only tool choice. DeepSeek thinking
                # mode also rejects forced tool choice. No tool call => fail
                # validation/fallback, never retry or execute model text.
                "disabled_params": {"tool_choice": None, "parallel_tool_calls": None},
            }
            chat_model = ChatOpenAI(model=config.model, api_key=config.api_key,
                base_url=config.base_url, timeout=config.timeout,
                max_retries=0, verbose=False, **options)
            if intent_chat_model is None and config.intent_temperature is not None:
                # Separate client configuration, not another invocation. Other
                # roles retain their previous provider temperature defaults.
                intent_chat_model = ChatOpenAI(model=config.model, api_key=config.api_key,
                    base_url=config.base_url, timeout=config.timeout,
                    max_retries=0, verbose=False, temperature=config.intent_temperature, **options)
        except ImportError:
            raise LocalLLMConfigError("CLOUD_LLM_DEPENDENCY_UNAVAILABLE") from None
        except Exception:
            raise LocalLLMConfigError("CLOUD_LLM_PROVIDER_UNAVAILABLE") from None
    try:
        options = {"structured_method": config.structured_method}
        return CloudModels(LangChainIntentModel(
            intent_chat_model if intent_chat_model is not None else chat_model,
            structured_method=config.intent_structured_method),
            LangChainExplanationModel(chat_model, **options),
            LangChainHumanResponseInterpreter(chat_model, **options))
    except Exception:
        raise LocalLLMConfigError("CLOUD_LLM_PROVIDER_UNAVAILABLE") from None
