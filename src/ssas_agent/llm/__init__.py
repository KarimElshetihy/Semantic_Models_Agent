"""LLM access. Every model call goes through LlmClient, the endpoint policy and the structured-reply check."""

from ssas_agent.llm.client import LlmClient
from ssas_agent.llm.config import LlmSettings, load_settings
from ssas_agent.llm.endpoint import check_endpoint
from ssas_agent.llm.errors import EndpointNotAllowedError, LlmConfigError, LlmError
from ssas_agent.llm.messages import ChatMessage, CompletionResult
from ssas_agent.llm.openai_compatible import OpenAICompatibleClient
from ssas_agent.llm.scripted import ScriptedLlmClient
from ssas_agent.llm.structured import StructuredOutputError, ask_structured, check_fields, parse_object

__all__ = [
    "ChatMessage",
    "CompletionResult",
    "EndpointNotAllowedError",
    "LlmClient",
    "LlmConfigError",
    "LlmError",
    "LlmSettings",
    "OpenAICompatibleClient",
    "ScriptedLlmClient",
    "StructuredOutputError",
    "ask_structured",
    "check_endpoint",
    "check_fields",
    "load_settings",
    "parse_object",
]
