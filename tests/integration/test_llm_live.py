"""LIVE test: sends one prompt to the model endpoint configured in the environment or in the project's .env.

It runs only when the settings are complete. Otherwise it is skipped and reported as NOT_RUN.
It checks that the endpoint answers with text. It does not judge the quality of the answer.
"""

import os
from pathlib import Path

import pytest

from ssas_agent.llm import ChatMessage, ChatRole, LlmConfigError, LlmSettings, OpenAICompatibleClient
from ssas_agent.llm import load_project_settings
from ssas_agent.policy import PathPolicy

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _configured_settings() -> LlmSettings | None:
    try:
        return load_project_settings(PathPolicy(PROJECT_ROOT), os.environ)
    except LlmConfigError:
        return None


LIVE_SETTINGS = _configured_settings()


@pytest.mark.skipif(
    LIVE_SETTINGS is None,
    reason="NOT_RUN: set SSAS_AGENT_LLM_BASE_URL and SSAS_AGENT_LLM_MODEL in the environment or in .env",
)
def test_configured_endpoint_answers_a_simple_prompt():
    client = OpenAICompatibleClient(LIVE_SETTINGS)

    result = client.complete([ChatMessage(ChatRole.USER, "Reply with the single word: ok")])

    assert result.text.strip()
    assert result.response_characters == len(result.text)
