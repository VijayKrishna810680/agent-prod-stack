import pytest
from pydantic import ValidationError

from app.schemas import AgentRequest


def test_valid_request_passes():
    req = AgentRequest(session_id="s1", user_id="u1", message="Hello there")
    assert req.message == "Hello there"
    assert req.require_human_approval is False


def test_blank_message_rejected():
    with pytest.raises(ValidationError):
        AgentRequest(session_id="s1", user_id="u1", message="   ")


def test_missing_fields_rejected():
    with pytest.raises(ValidationError):
        AgentRequest(user_id="u1", message="hi")
