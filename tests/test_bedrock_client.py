"""Task 0.2: test_bedrock_client_parses_response."""
import json
from pathlib import Path
from unittest.mock import MagicMock

from negagent.clients.bedrock_client import BedrockClient

FIXTURE = Path(__file__).parent / "fixtures" / "bedrock_converse_response.json"


def _client_with_fixture():
    raw = json.loads(FIXTURE.read_text())
    boto = MagicMock()
    boto.converse.return_value = raw
    bc = BedrockClient(model_id="anthropic.claude-x", region="us-west-2", client=boto)
    return bc, boto


def test_bedrock_client_parses_response():
    """complete() returns the assistant text from a recorded converse response."""
    bc, boto = _client_with_fixture()
    messages = [{"role": "user", "content": [{"text": "reply with OK"}]}]

    out = bc.complete(messages)

    assert out == "OK"
    # wrapper passes model id + messages straight through to converse
    _, kwargs = boto.converse.call_args
    assert kwargs["modelId"] == "anthropic.claude-x"
    assert kwargs["messages"] == messages
    assert "system" not in kwargs


def test_complete_passes_system_prompt():
    """A system string is forwarded as a converse system block."""
    bc, boto = _client_with_fixture()

    bc.complete([{"role": "user", "content": [{"text": "hi"}]}], system="be terse")

    _, kwargs = boto.converse.call_args
    assert kwargs["system"] == [{"text": "be terse"}]


def test_complete_vision_returns_text():
    """complete_vision() forwards image-bearing messages and returns text."""
    bc, boto = _client_with_fixture()
    messages = [
        {
            "role": "user",
            "content": [
                {"image": {"format": "jpeg", "source": {"bytes": b"\xff\xd8"}}},
                {"text": "What condition is this?"},
            ],
        }
    ]

    out = bc.complete_vision(messages)

    assert out == "OK"
    _, kwargs = boto.converse.call_args
    assert kwargs["messages"] == messages
