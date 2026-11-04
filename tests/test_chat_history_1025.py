"""비서 대화 기록 — 질문 하나에 chat_turn 한 줄 · 회원마다 따로 · 지난 대화 다시 열기(10-25).

팀장 "대화기록도 해줘". 표는 팀 ERD 의 chat_turn 그대로(칸을 더하지 않음).

【판단】 CI 에는 PostgreSQL 이 없다 → 표만 SQLite 임시 DB 에 만들어 기록을 그쪽에 남긴다
       (test_auth_flow 와 같은 방식)
"""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.api.assistant import create_app
from src.assistant import done, history, today_api
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.models import ChatTurn
from src.assistant.slots import DeskCard
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter
from src.auth import routes as auth_routes
from src.common.database import Base
from src.common.models import Dong, Region
from src.common.regions import seed_regions

TABLE = {
    "수서동 청년은?": DeskCard(
        act="ask",
        topics=("youth",),
        dong_op="set",
        dong_mentions=("수서동",),
        target_op="set",
        target="청년",
    ),
    "수서동 김순자 할머니 집 주소 알려줘": DeskCard(act="blocked", block="person"),
}


@pytest.fixture
def maker(tmp_path):
    eng = create_engine(
        f"sqlite:///{(tmp_path / 'chat.db').as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng, tables=[Region.__table__, Dong.__table__, ChatTurn.__table__])
    m = sessionmaker(eng, expire_on_commit=False)
    with m.begin() as db:
        seed_regions(db)
    return m


def _client(tmp_path, maker, monkeypatch, member_id=1):
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk(TABLE), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    who = SimpleNamespace(member_id=member_id, login_id=f"m{member_id}", name="시험 회원")
    monkeypatch.setattr(auth_routes, "require_member", lambda: who)
    return TestClient(create_app(e, record=history.DbHistory(maker))), e


def _done(res) -> dict:
    evs = [json.loads(x[len("data: ") :]) for x in res.text.split("\n\n") if x.strip()]
    assert evs[-1]["event"] == "done", evs[-1]
    return evs[-1]["data"]


def _rows(maker) -> list[ChatTurn]:
    with maker.begin() as db:
        return list(db.scalars(select(ChatTurn).order_by(ChatTurn.turn_id)))


def test_each_question_leaves_one_chat_turn(tmp_path, maker, monkeypatch):
    c, _ = _client(tmp_path, maker, monkeypatch)
    _done(c.post("/assistant/chat", json={"session_id": "s1", "text": "수서동 청년은?"}))
    _done(c.post("/assistant/chat", json={"session_id": "s1", "text": "안녕"}))
    rows = _rows(maker)
    assert [r.seq for r in rows] == [1, 2] and {r.session_id for r in rows} == {"s1"}
    first, second = rows
    assert first.member_id == 1 and first.question == "수서동 청년은?"
    assert first.intent == "answer" and first.blocked_why is None
    assert first.ctx_dong_cd == "11230750"  # 수서동
    assert "1,897명" in first.headline and "\n" not in first.headline
    assert first.ms >= 0 and first.at is not None
    assert second.question == "안녕" and second.ctx_dong_cd == "11230750"  # 보던 동을 잇는다


def test_blocked_and_too_long_keep_no_question_text(tmp_path, maker, monkeypatch):
    c, _ = _client(tmp_path, maker, monkeypatch)
    blocked = _done(
        c.post(
            "/assistant/chat",
            json={"session_id": "s2", "text": "수서동 김순자 할머니 집 주소 알려줘"},
        )
    )
    assert blocked["kind"] == "blocked"
    _done(c.post("/assistant/chat", json={"session_id": "s2", "text": "가" * 1001}))
    a, b = _rows(maker)
    assert a.question is None and a.blocked_why == "개인 찾기" and a.intent == "blocked"
    assert b.question is None and b.blocked_why == "1,000자 넘음" and b.intent == "too_long"


def test_history_lists_sessions_and_turns_for_that_member_only(tmp_path, maker, monkeypatch):
    c, _ = _client(tmp_path, maker, monkeypatch)
    _done(c.post("/assistant/chat", json={"session_id": "old", "text": "수서동 청년은?"}))
    _done(c.post("/assistant/chat", json={"session_id": "new", "text": "안녕"}))
    got = c.get("/assistant/history").json()["sessions"]
    assert [x["session_id"] for x in got] == ["new", "old"]  # 최근 것부터
    old = got[1]
    assert old["first"] == "수서동 청년은?" and old["turns"] == 1
    turns = c.get("/assistant/history", params={"session_id": "old"}).json()["turns"]
    assert len(turns) == 1 and "1,897명" in turns[0]["headline"]
    # 다른 회원에게는 보이지 않는다
    other, _ = _client(tmp_path, maker, monkeypatch, member_id=2)
    assert other.get("/assistant/history").json()["sessions"] == []
    assert other.get("/assistant/history", params={"session_id": "old"}).json()["turns"] == []


def test_same_session_id_does_not_continue_another_members_dialogue(tmp_path, maker, monkeypatch):
    c, e = _client(tmp_path, maker, monkeypatch)
    _done(c.post("/assistant/chat", json={"session_id": "same", "text": "수서동 청년은?"}))
    assert e.store.load("m1_same").slots.dongs == ("수서동",)
    who = SimpleNamespace(member_id=2, login_id="m2", name="다른 회원")
    monkeypatch.setattr(auth_routes, "require_member", lambda: who)
    c2 = TestClient(create_app(e, record=history.DbHistory(maker)))
    _done(c2.post("/assistant/chat", json={"session_id": "same", "text": "안녕"}))
    # 회원 2의 대화는 새로 시작한다(회원 1이 보던 수서동을 이어받지 않음)
    assert e.store.load("m2_same").slots.dongs == ()
    assert [r.member_id for r in _rows(maker)] == [1, 2]


def test_session_id_must_fit_chat_turn(tmp_path, maker, monkeypatch):
    c, _ = _client(tmp_path, maker, monkeypatch)
    for bad in ("x" * 37, "../etc", "가나"):
        r = c.post("/assistant/chat", json={"session_id": bad, "text": "안녕"})
        assert r.status_code == 422


def test_record_failure_does_not_stop_the_answer(tmp_path, monkeypatch):
    broken = sessionmaker(create_engine("sqlite:///" + (tmp_path / "none" / "x.db").as_posix()))
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk(TABLE), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    rec = history.DbHistory(broken)
    c = TestClient(create_app(e, record=rec))
    assert (
        _done(c.post("/assistant/chat", json={"session_id": "z", "text": "수서동 청년은?"}))["kind"]
        == "answer"
    )
    assert rec.last_error and "대화 기록 실패" in rec.last_error


def test_kept_question_hides_personal_bits():
    # 막지 않은 질문도 전화번호 같은 것은 가려서 남긴다
    # (엔진은 전화번호가 든 말을 막는다 — 그때는 비움)
    kept = history.question_kept("수서동 청년은? 010-1234-5678", "answer")
    assert "010-1234-5678" not in kept and "[전화번호]" in kept
    assert history.question_kept("아무 말", "blocked") is None
    assert history.question_kept("가" * 1001, "too_long") is None


def test_headline_is_one_line_within_300():
    assert history.headline("가\n나  다") == "가 나 다"
    long = history.headline("가" * 400)
    assert len(long) == 300 and long.endswith("…")


def test_done_is_saved_as_the_logged_in_member(tmp_path):
    # 10-25: 로그인이 붙었는데 [했어요]가 모두 회원 1번으로 적히고 있었다 → 로그인한 회원 번호로
    store = done.JsonlDoneStore(tmp_path / "done.jsonl")
    app = FastAPI()
    app.include_router(today_api.router(done_store=store, who=lambda: SimpleNamespace(member_id=7)))
    c = TestClient(app)
    q = {"region": "강남구", "dong": "수서동", "date": "2025-07-15", "member": 1}
    card = c.get("/assistant/today", params=q).json()["cards"][0]
    r = c.post(f"/assistant/today/{card['id']}/done", json={"status": "했어요", "member": 1})
    assert r.status_code == 200 and r.json()["member_id"] == 7
    # 주소의 member=1 은 읽지 않는다 — 카드에는 회원 7의 기록이 보인다
    assert c.get("/assistant/today", params=q).json()["cards"][0]["done"]["member_id"] == 7


def test_past_turns_keep_whole_answer_and_files(tmp_path, maker, monkeypatch):
    # 10-29 팀장 '가독성이 별로야': 지난 대화가 한 줄 답(300자)이라 표가 '|' 글자로 뭉개지고
    #       파일 단추가 없었다 → 답 전체 · 파일 이름을 chat_answer 표(팀 ERD 밖)에 둔다
    c, _ = _client(tmp_path, maker, monkeypatch)
    d = _done(c.post("/assistant/chat", json={"session_id": "s1", "text": "수서동 청년은?"}))
    got = c.get("/assistant/history", params={"session_id": "s1"}).json()["turns"]
    assert got[0]["answer"] == d["text"]
    assert got[0]["files"] == d["files"]
    assert len(got[0]["headline"]) <= history.HEADLINE_MAX
