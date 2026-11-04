"""글쓴이 한도 · 잘린 답(10-15, 페르소나 20b 재생의 '빈 답').

재생에서 코드 기본 답 9번 중 6번이 '빈 답'이었다. 같은 요청을 다시 보내 보니 다섯 중 넷이
stop_reason=max_tokens — 생각(thinking)에 2,000토큰을 다 써서 글이 비거나 몇십 자에서 잘렸다.
"""

from types import SimpleNamespace

from src.assistant import llm
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots
from src.assistant.writer import ClaudeWriter

FACTS = [gather("solo_seniors", Slots(dongs=("수서동",)), JsonDongData())]


def test_writer_leaves_room_for_thinking():
    kw, _, _ = ClaudeWriter(AssistantSettings())._request("수서동 몇 명?", FACTS)
    assert kw["max_tokens"] >= 8000


def test_cut_off_stream_is_not_shown_as_a_full_answer(monkeypatch):
    # 한도에 닿아 잘린 글은 다 쓴 답처럼 내보내지 않는다(코드 기본 답으로)
    def stream_text(api_key, usage, meta=None, **kw):
        meta["stop"] = "max_tokens"
        yield "수서동 혼자 사는 어르신은 2,471명이에요. 그리고"

    monkeypatch.setattr(llm, "stream_text", stream_text)
    # 10-20: 다시 쓰기도 잘리면 코드 기본 답(실제 API를 부르지 않게 가짜로)
    monkeypatch.setattr(
        llm,
        "call",
        lambda api_key, usage, **kw: SimpleNamespace(
            content=[SimpleNamespace(type="text", text="수서동은 그리고")], stop_reason="max_tokens"
        ),
    )
    w = ClaudeWriter(AssistantSettings())
    events = list(w.write_stream("수서동 몇 명?", FACTS))
    assert events[-1][0] in ("replace", "text") and events[-1][1].startswith("혼자 사는 어르신")
    assert w.last and not w.last.used_ai and any("잘림" in p for p in w.last.problems)


def test_cut_off_call_is_not_used(monkeypatch):
    def call(api_key, usage, **kw):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="수서동은 2,471명이에요. 그리고")],
            stop_reason="max_tokens",
        )

    monkeypatch.setattr(llm, "call", call)
    w = ClaudeWriter(AssistantSettings())
    out = w.write("수서동 몇 명?", FACTS)
    assert out.startswith("혼자 사는 어르신") and any("잘림" in p for p in w.last.problems)


def test_connection_cut_mid_stream_falls_back(monkeypatch):
    # 재생 q19: 흘려 보내는 도중 연결이 끊겨(RemoteProtocolError) 대화가 통째로 멈췄다
    import httpx

    def stream_text(api_key, usage, meta=None, **kw):
        yield "수서동 혼자 사는 어르신은 "
        raise httpx.RemoteProtocolError("peer closed connection")

    monkeypatch.setattr(llm, "client", lambda key: _CutClient())
    w = ClaudeWriter(AssistantSettings(anthropic_api_key="k"))
    events = list(w.write_stream("수서동 몇 명?", FACTS))
    assert events[-1][1].startswith("혼자 사는 어르신") and not w.last.used_ai


class _CutStream:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def text_stream(self):
        import httpx2  # SDK(anthropic 1.x)가 쓰는 것 — 실제로 올라온 오류

        yield "수서동 혼자 사는 어르신은 "
        raise httpx2.RemoteProtocolError("peer closed connection")

    current_message_snapshot = None


class _CutClient:
    def __init__(self):
        self.messages = self

    def stream(self, **kw):
        return _CutStream()
