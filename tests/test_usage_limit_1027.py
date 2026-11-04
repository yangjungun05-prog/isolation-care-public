"""API 사용 한도(Console의 월 한도) 400 — 크레딧 바닥처럼 멈추고 사람에게 알린다(10-27).

10-27 실응답 시험(village_6)에서 API가 400 'You have reached your specified API usage
limits. You will regain access on 2026-11-01 at 00:00 UTC.'를 돌려줬는데, 코드가 '요청 모양
오류'(LLMError)로 읽어 데스크가 삼키고 6턴 모두 '못 알아들음'으로 나갔다(API 호출 0회 · 돈 0).
멈춰야 할 오류다.
"""

import anthropic
import httpx
import pytest

from src.assistant import llm
from src.assistant.desk import ClaudeDesk


def _bad_request(message: str) -> anthropic.BadRequestError:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(400, request=req, json={"type": "error", "error": {"message": message}})
    return anthropic.BadRequestError(message, response=resp, body=None)


LIMIT_MSG = (
    "You have reached your specified API usage limits. "
    "You will regain access on 2026-11-01 at 00:00 UTC."
)


def test_usage_limit_is_credit_exhausted():
    with pytest.raises(llm.UsageLimited) as e, llm._errors():
        raise _bad_request(LIMIT_MSG)
    assert isinstance(e.value, llm.CreditExhausted)
    assert "2026-11-01" in str(e.value) and "한도" in str(e.value)


def test_credit_balance_still_credit_exhausted():
    with pytest.raises(llm.CreditExhausted), llm._errors():
        raise _bad_request("Your credit balance is too low to access the Anthropic API.")


def test_other_400_is_plain_llm_error():
    with pytest.raises(llm.LLMError) as e, llm._errors():
        raise _bad_request("max_tokens: must be positive")
    assert not isinstance(e.value, llm.CreditExhausted)


def test_desk_does_not_swallow_usage_limit(monkeypatch):
    """데스크는 LLMError 는 삼키고 '못 알아들음'을 내지만, 한도 오류는 위로 올려야 한다."""
    from src.assistant.config import AssistantSettings
    from src.assistant.state import new_state

    def boom(api_key, usage, **kw):
        with llm._errors():
            raise _bad_request(LIMIT_MSG)

    monkeypatch.setattr(llm, "call", boom)
    d = ClaudeDesk(AssistantSettings(anthropic_api_key="k", desk_votes=1, desk_escalate=False))
    with pytest.raises(llm.UsageLimited):
        d.read(new_state(), "수서동 어때?")
