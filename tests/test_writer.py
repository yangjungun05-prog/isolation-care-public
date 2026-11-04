from types import SimpleNamespace

from src.assistant import llm
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots
from src.assistant.writer import ClaudeWriter

FACTS = [gather("solo_seniors", Slots(dongs=("수서동",)), JsonDongData())]


def _fake(text):
    def call(api_key, usage, **kw):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    return call


def test_lead_mode_keeps_library_lines(monkeypatch):
    monkeypatch.setattr(llm, "call", _fake("수서동 혼자 사는 어르신은 2,543명이에요.\n· 덧붙인 줄"))
    w = ClaudeWriter(AssistantSettings(writer_mode="lead"))
    out = w.write("수서동 혼자 사는 어르신 몇 명?", FACTS)
    assert out.startswith("수서동 혼자 사는 어르신은 2,543명이에요.\n")
    assert "덧붙인 줄" not in out and "2,462명 → 2,543명" in out  # 숫자 줄은 사서 그대로


def test_bad_answer_falls_back_to_template(monkeypatch):
    monkeypatch.setattr(llm, "call", _fake("[자료]에는 없어서 답할 수 없습니다."))
    w = ClaudeWriter(AssistantSettings())
    out = w.write("몇 명?", FACTS)
    assert w.last and not w.last.used_ai and out.startswith("혼자 사는 어르신")


def _fake_stream(pieces):
    def stream_text(api_key, usage, **kw):
        yield from pieces

    return stream_text


def test_stream_shows_sentences_and_matches_write(monkeypatch):
    # 【기능】 흘려 보이기: 문장마다 내보내고, 다 모은 글은 write() 결과와 같다
    text = "수서동 혼자 사는 어르신은 2,543명이에요. 주민등록 기준이에요."
    monkeypatch.setattr(
        llm,
        "stream_text",
        _fake_stream(["수서동 혼자 사는 어", "르신은 2,543명이에요. ", "주민등록 기준이에요."]),
    )
    monkeypatch.setattr(llm, "call", _fake(text))
    w = ClaudeWriter(AssistantSettings())
    events = list(w.write_stream("수서동 혼자 사는 어르신 몇 명?", FACTS))
    assert [e for e, _ in events] == ["text", "text"]
    assert events[0][1] == "수서동 혼자 사는 어르신은 2,543명이에요. "  # 첫 문장이 끝나자마자
    assert "".join(c for _, c in events) == text == w.write("수서동 혼자 사는 어르신 몇 명?", FACTS)


def test_stream_stops_at_bad_sentence_and_replaces(monkeypatch):
    # 【기능】 검사에 걸리는 문장은 보이지 않고, 글 전체를 코드 기본 답으로 바꾼다
    monkeypatch.setattr(
        llm, "stream_text", _fake_stream(["2,543명이에요. ", "두 배인 5,086명이에요. ", "끝."])
    )
    # 10-20: 걸리면 한 번 다시 쓰게 한다 — 다시 써도 걸리면 코드 기본 답
    asked = []

    def again(api_key, usage, **kw):
        asked.append(kw["messages"][-1]["content"])
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="세 배인 7,629명이에요.")]
        )

    monkeypatch.setattr(llm, "call", again)
    w = ClaudeWriter(AssistantSettings())
    events = list(w.write_stream("몇 명?", FACTS))
    assert len(asked) == 1 and "[고칠 것]" in asked[0] and "[자료]에 없는 숫자" in asked[0]
    assert events[0] == ("text", "2,543명이에요. ")
    assert events[-1][0] == "replace" and events[-1][1].startswith("혼자 사는 어르신")
    assert not any("4,942" in c for _, c in events)
    assert w.last and not w.last.used_ai and "없는 숫자 7629" in w.last.problems


def test_stream_retry_that_passes_replaces_with_the_fixed_answer(monkeypatch):
    monkeypatch.setattr(llm, "stream_text", _fake_stream(["두 배인 5,086명이에요. "]))
    monkeypatch.setattr(llm, "call", _fake("수서동 혼자 사는 어르신은 2,543명이에요."))
    w = ClaudeWriter(AssistantSettings())
    events = list(w.write_stream("몇 명?", FACTS))
    assert events[-1][1] == "수서동 혼자 사는 어르신은 2,543명이에요." and w.last.used_ai
