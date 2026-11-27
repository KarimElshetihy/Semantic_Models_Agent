"""LIVE test: sends one prompt to the model endpoint set in the environment.

It runs only when SSAS_AGENT_LLM_BASE_URL and SSAS_AGENT_LLM_MODEL are set. Otherwise it is skipped
and reported as NOT_RUN. It checks that the endpoint answers and returns text. It does not judge the
quality of the answer.
"""

import os

import pytest

from ssas_agent.llm import ChatMessage, OpenAICompatibleClient, load_settings
from ssas_agent.llm.config import ENV_BASE_URL, ENV_MODEL

LIVE_CONFIGURED = bool(os.environ.get(ENV_BASE_URL, "").strip() and os.environ.get(ENV_MODEL, "").strip())


@pytest.mark.skipif(not LIVE_CONFIGURED, reason="NOT_RUN: set SSAS_AGENT_LLM_BASE_URL and SSAS_AGENT_LLM_MODEL")
def test_configured_endpoint_answers_a_simple_prompt():
    client = OpenAICompatibleClient(load_settings(os.environ))

    result = client.complete([ChatMessage("user", "Reply with the single word: ok")])

    assert result.text.strip()
    assert result.response_characters == len(result.text)
