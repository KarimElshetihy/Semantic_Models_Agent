"""Errors raised by the LLM layer. Messages never contain the API key or the content of a reply."""


class LlmError(RuntimeError):
    """The model could not be reached or did not give a usable answer."""


class LlmConfigError(LlmError):
    """A required setting is missing or invalid."""


class EndpointNotAllowedError(LlmError):
    """The configured endpoint is refused by the endpoint policy. Nothing is sent to it."""
