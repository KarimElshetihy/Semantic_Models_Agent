"""Errors raised by the LLM layer. Messages never contain the prompt, the reply or a secret value."""


class LlmError(RuntimeError):
    """Any failure while talking to a model."""


class LlmConfigError(LlmError):
    """A setting is missing or invalid."""


class EnvFileError(LlmConfigError):
    """The project's .env file is malformed. Messages give line numbers and key names, never values."""


class EndpointNotAllowedError(LlmError):
    """The model endpoint is refused by the endpoint policy."""
