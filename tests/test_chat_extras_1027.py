"""챗봇 기본기(10-27 팀장 "사용자의 입장에서 데이터를 어떻게 받느냐에 집중하자").

답 둘레의 것은 모두 코드가 만든다(AI 없음): 이어 물을 질문 · '어느 동?' 동 단추 · 이 답의 자료 ·
도움말 · 화면 기본기(멈추기 · 복사 · 글자 크기 · 대화 저장 · 개인정보 경고).
"""

import json

from fastapi.testclient import TestClient

from src.api.assistant import create_app
from src.assistant import extras
from src.assistant.catalog import BY_ID
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.slots import DeskCard
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()
TABLE = {
    "수서동 혼자 사는 어르신 몇 명?": DeskCard(
        act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("수서동",)
    ),
    "혼자 사는 어르신 몇 명?": DeskCard(act="ask", topics=("solo_seniors",)),
    "주식 추천해 줘": DeskCard(act="out_of_scope"),
}


def _client(tmp_path) -> TestClient:
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk(TABLE), TemplateWriter(), DATA, MemoryStore(), s)
    return TestClient(create_app(e))


def _done(res) -> dict:
    ev = [json.loads(x[len("data: ") :]) for x in res.text.split("\n\n") if x.strip()]
    assert ev[-1]["event"] == "done"
    return ev[-1]["data"]


def test_answer_brings_followups_sources_and_no_choices(tmp_path):
    c = _client(tmp_path)
    d = _done(
        c.post(
            "/assistant/chat", json={"session_id": "a", "text": "수서동 혼자 사는 어르신 몇 명?"}
        )
    )
    assert d["kind"] == "answer"
    assert 1 <= len(d["follow"]) <= 3 and all("수서동" in q for q in d["follow"])
    # 방금 답한 주제(혼자 사는 어르신)를 다시 권하지 않는다
    assert not any("혼자 사는 어르신 몇 명" in q for q in d["follow"])
    assert d["choices"] == []
    assert d["sources"]["items"] and d["sources"]["basis"].startswith("주민등록 ")


def test_ask_slot_brings_dong_choices_member_first(tmp_path):
    c = _client(tmp_path)
    body = {"session_id": "b", "text": "혼자 사는 어르신 몇 명?", "region": "강남구"}
    body["dongs"] = ["세곡동"]
    d = _done(c.post("/assistant/chat", json=body))
    assert d["kind"] == "ask_slot"
    assert d["choices"][0] == "세곡동" and len(d["choices"]) <= extras.MAX_CHOICES
    assert set(d["choices"]) <= set(DATA.region_dongs("강남구"))
    assert d["follow"] == []


def test_out_of_scope_suggests_region_questions(tmp_path):
    c = _client(tmp_path)
    d = _done(c.post("/assistant/chat", json={"session_id": "c", "text": "주식 추천해 줘"}))
    assert d["kind"] == "out_of_scope" and d["follow"]
    assert d["sources"] == {}


def test_followups_only_use_ready_topics_of_that_region():
    # 강남 동에는 춘천 버스 질문을 내지 않는다
    rows = extras._for_dong("수서동", "강남구")
    assert not any(t == "bus" for t, _ in rows)
    assert any(t == "bus" for t, _ in extras._for_dong("북산면", "춘천시"))
    for t, _ in rows + extras._for_region("춘천시", "효자2동"):
        assert t in BY_ID


def test_help_lists_can_and_cannot(tmp_path):
    h = _client(tmp_path).get("/assistant/help", params={"region": "춘천시"}).json()
    assert "춘천 버스 (춘천시만)" in h["can"] and any("개인" in x for x in h["cannot"])
    assert h["examples"] and h["basis"].startswith("주민등록 ")


def test_feedback_is_gone(tmp_path):
    """10-27 팀장: 답 평가(도움 됐어요 · 아쉬워요)는 넣지 않는다 — 단추도 주소도 없음."""
    c = _client(tmp_path)
    assert c.post("/assistant/feedback", json={"session_id": "d", "rating": "bad"}).status_code in (
        404,
        405,
    )
    page = c.get("/").text
    assert "도움 됐어요" not in page and "아쉬워요" not in page


def test_page_has_chatbot_basics(tmp_path):
    page = _client(tmp_path).get("/").text
    for word in ("멈추기", "다시 보내기", "복사", "이 답의 자료",
                 "이어서 물어보기", "글자 크기", "대화 저장", "도움말", "인터넷 연결이 끊겼어요",
                 "주민등록번호", "aria-live"):  # fmt: skip
        assert word in page, word
