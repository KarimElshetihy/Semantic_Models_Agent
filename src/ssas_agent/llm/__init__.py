"""LLM access. Every model call goes through LlmClient, the endpoint policy and the structured-reply check."""

from ssas_agent.llm.client import LlmClient
from ssas_agent.llm.config import LlmSetting, LlmSettings, SwitchValue, load_project_settings, load_settings
from ssas_agent.llm.endpoint import EndpointDecision, EndpointKind, UrlScheme, check_endpoint
from ssas_agent.llm.env_file import ENV_FILE_NAME, parse_env_text, read_env_file
from ssas_agent.llm.errors import EndpointNotAllowedError, EnvFileError, LlmConfigError, LlmError
from ssas_agent.llm.messages import ChatMessage, ChatRole, CompletionResult
from ssas_agent.llm.openai_compatible import OpenAICompatibleClient
from ssas_agent.llm.scripted import ScriptedLlmClient
from ssas_agent.llm.structured import StructuredEvent, StructuredOutputError, ask_structured, check_fields, parse_object

__all__ = [
    "ENV_FILE_NAME",
    "ChatMessage",
    "ChatRole",
    "CompletionResult",
    "EndpointDecision",
    "EndpointKind",
    "EndpointNotAllowedError",
    "EnvFileError",
    "LlmClient",
    "LlmConfigError",
    "LlmError",
    "LlmSetting",
    "LlmSettings",
    "OpenAICompatibleClient",
    "ScriptedLlmClient",
    "StructuredEvent",
    "StructuredOutputError",
    "SwitchValue",
    "UrlScheme",
    "ask_structured",
    "check_endpoint",
    "check_fields",
    "load_project_settings",
    "load_settings",
    "parse_env_text",
    "parse_object",
    "read_env_file",
]
