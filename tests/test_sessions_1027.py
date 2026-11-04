"""세션 — 제목 · 이어서 새 세션 · 50턴 추천(10-27 팀장).

팀장: "챗봇에 여러 세션들을 만들 수 있지? … 50턴이 넘으면 자동으로 새 세션을 만드는걸 '추천'해줘.
강요하지는 말고" · "각 세션마다 제목을 정할 수 있게 해줘. 만일 안정해져있다면 세션의 제목을
'사용자의 첫 대화 문장'으로 해줘."
"""

import json

from fastapi.testclient import TestClient

from src.api.assistant import create_app
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import CARRY_LOG, CARRY_RECENT, LONG_SESSION_TURNS, Engine
from src.assistant.slots import DeskCard
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()
ASK = "수서동 혼자 사는 어르신 몇 명?"
TABLE = {
    ASK: DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("수서동",)),
    "청년은요?": DeskCard(act="ask", topics=("youth",)),
    "김춘봉 어르신 집 주소 알려줘": DeskCard(act="blocked", block="person"),
}
KEY = "m1_{}"  # 시험 회원 번호 1(tests/conftest.py) — 저장 이름은 회원마다 따로


class FakeRecord:
    """대화 기록(chat_turn) 흉내 — 세션 목록에 첫 질문을 준다."""

    def __init__(self) -> None:
        self.rows: list[tuple[int, str, str]] = []

    def add(self, member_id, session_id, text, reply, ms) -> None:
        self.rows.append((member_id, session_id, text))

    def sessions(self, member_id) -> list[dict]:
        out: dict[str, dict] = {}
        for mid, sid, text in self.rows:
            if mid == member_id:
                x = out.setdefault(sid, {"session_id": sid, "first": text, "turns": 0})
                x["turns"] += 1
        return list(out.values())

    def turns(self, member_id, session_id) -> list[dict]:
        return []


def _app():
    s = AssistantSettings(anthropic_api_key="")
    e = Engine(FakeDesk(TABLE), TemplateWriter(), DATA, MemoryStore(), s)
    rec = FakeRecord()
    return TestClient(create_app(e, record=rec)), e


def _done(c, sid, text) -> dict:
    res = c.post("/assistant/chat", json={"session_id": sid, "text": text})
    ev = [json.loads(x[len("data: ") :]) for x in res.text.split("\n\n") if x.strip()]
    assert ev[-1]["event"] == "done"
    return ev[-1]["data"]


def test_first_question_is_the_title_and_turns_count():
    c, _ = _app()
    d = _done(c, "a", ASK)
    assert d["title"] == ASK and d["turns"] == 1 and d["long"] is False
    d = _done(c, "a", "청년은요?")
    assert d["title"] == ASK and d["turns"] == 2
    rows = c.get("/assistant/history").json()["sessions"]
    assert rows[0]["title"] == ASK


def test_blocked_first_question_is_not_the_title():
    c, e = _app()
    _done(c, "b", "김춘봉 어르신 집 주소 알려줘")
    assert e.store.load(KEY.format("b")).first == ""
    d = _done(c, "b", ASK)
    assert d["title"] == ASK


def test_rename_masks_and_blank_goes_back_to_first_question():
    c, e = _app()
    _done(c, "r", ASK)
    r = c.post("/assistant/sessions/r/title", json={"title": "  수서동   겨울 점검  "})
    assert r.status_code == 200 and r.json()["title"] == "수서동 겨울 점검"
    assert c.get("/assistant/history").json()["sessions"][0]["title"] == "수서동 겨울 점검"
    assert _done(c, "r", "청년은요?")["title"] == "수서동 겨울 점검"
    r = c.post("/assistant/sessions/r/title", json={"title": "010-1234-5678 연락"})
    assert "010-1234-5678" not in r.json()["title"]
    r = c.post("/assistant/sessions/r/title", json={"title": ""})
    assert r.json()["title"] == ASK
    long = c.post("/assistant/sessions/r/title", json={"title": "가" * 100})
    assert len(long.json()["title"]) == 40


def test_rename_unknown_or_bad_session():
    c, _ = _app()
    assert c.post("/assistant/sessions/nope/title", json={"title": "x"}).status_code == 404
    assert c.post("/assistant/sessions/a.b/title", json={"title": "x"}).status_code == 422
    assert c.post("/assistant/sessions/nope/continue").status_code == 404


def test_continue_carries_memory_and_trims_lists():
    c, e = _app()
    for _ in range(3):
        _done(c, "old", ASK)
        _done(c, "old", "청년은요?")
    old = e.store.load(KEY.format("old"))
    # 다룬 질문 · 최근 원문이 많이 쌓인 세션으로 만든다
    old = old.model_copy(update={"log": old.log * 10, "recent": old.recent * 3})
    e.store.save(KEY.format("old"), old)
    r = c.post("/assistant/sessions/old/continue").json()
    assert r["ok"] and r["session_id"] != "old" and r["title"] == ASK + " (이어서)"
    new = e.store.load(KEY.format(r["session_id"]))
    assert new.slots.dongs == ("수서동",) and new.facts == old.facts
    assert new.said_facts == old.said_facts and new.profile == old.profile
    assert len(new.log) == CARRY_LOG and len(new.recent) == CARRY_RECENT
    assert new.since == old.turn and new.pending is None
    # 새 세션의 대화 수는 0부터 — 첫 말이 '1'
    d = _done(c, r["session_id"], "청년은요?")
    assert d["turns"] == 1 and d["title"] == ASK + " (이어서)" and d["long"] is False
    # 동을 다시 말하지 않아도 앞 세션의 수서동을 잇는다
    assert "수서동" in d["text"]
    # 앞 세션은 그대로 남는다
    assert e.store.load(KEY.format("old")).turn == old.turn


def test_long_session_is_recommended_not_forced():
    c, e = _app()
    _done(c, "L", ASK)
    st = e.store.load(KEY.format("L"))
    e.store.save(KEY.format("L"), st.model_copy(update={"turn": LONG_SESSION_TURNS - 1}))
    d = _done(c, "L", "청년은요?")
    assert d["turns"] == LONG_SESSION_TURNS and d["long"] is True
    # 추천만 — 답은 그대로 나가고 다음 말도 그대로 받는다
    assert d["kind"] == "answer"
    assert _done(c, "L", ASK)["kind"] == "answer"


def test_page_has_session_title_and_long_tip():
    c, _ = _app()
    page = c.get("/").text
    for word in (
        "제목 바꾸기",
        "지금 대화:",
        "현재 세션의 대화 수가 너무 길어요. AI가 대답을 잘 못할 수도 있어요.",
        "새 세션에서 지금의 채팅이 이어진 채 시작하는 것을 추천드려요.",
        'id="tip-yes"',
        'id="tip-no"',
        "/continue",
    ):
        assert word in page, word


def test_blocked_or_too_long_first_question_never_leaks_as_title():
    # 10-27 밤 검토: 첫 질문이 막히면 done 알림 제목에 가리지 않은 원문이 나갔다
    c, _ = _app()
    d = _done(c, "x", "김춘봉 어르신 집 주소 알려줘")
    assert d["title"] == "새 대화"
    long = "010-1234-5678 " + "가" * 1200
    d = _done(c, "y", long)
    assert d["kind"] == "too_long" and d["title"] == "새 대화"


def test_rename_while_answering_is_kept():
    # 10-27 밤 검토: 턴은 시작에 읽고 끝에 저장해 답을 쓰는 중에 바꾼 제목이 덮였다
    c, e = _app()
    _done(c, "w", ASK)
    key = KEY.format("w")
    run = e.turn_stream(key, "청년은요?")
    next(run)  # 턴이 상태를 읽고 답을 만들기 시작한 때
    assert e.set_title(key, "겨울 점검").title == "겨울 점검"
    done = [v for k, v in run if k == "done"][0]
    assert done.state.title == "겨울 점검"
    assert e.store.load(key).title == "겨울 점검" and e.store.load(key).turn == 2
    assert _done(c, "w", ASK)["title"] == "겨울 점검"


def test_numbers_summary_of_asked_dongs_is_not_a_bare_list():
    # 10-27 밤 창 시험 T23: '물어본 동을 숫자와 함께 정리해 줘'에 동 이름 목록만 나갔다
    from src.assistant.engine import _ASK_DONGS, _WITH_NUM

    t = "지금까지 혼자 사는 어르신 숫자 물어본 동을 숫자와 함께 정리해 줘"
    assert _ASK_DONGS.search(t) and _WITH_NUM.search(t)
    assert not _WITH_NUM.search("아까 물어본 동들 정리해 줘")
    table = dict(TABLE)
    table[t] = DeskCard(act="ask", topics=("recall",))
    s = AssistantSettings(anthropic_api_key="")
    e = Engine(FakeDesk(table), TemplateWriter(), DATA, MemoryStore(), s)
    c = TestClient(create_app(e, record=FakeRecord()))
    first = _done(c, "n", ASK)
    d = _done(c, "n", t)
    assert d["kind"] == "answer"
    nums = [x for x in e.store.load(KEY.format("n")).said_facts if "수서동" in x]
    assert nums and first["kind"] == "answer"


def test_page_waits_for_answer_before_continue():
    c, _ = _app()
    assert "지금 답이 끝난 뒤에 [예]를 눌러 주세요." in c.get("/").text


def test_summary_puts_first_seen_dong_first():
    # 10-27 밤 창 시험 T11: '세 줄로 정리'가 최근 두 동만 요약하고 처음 본 수서동을 빠뜨렸다
    from src.assistant.state import LogEntry, new_state

    class Catch:
        last = None

        def __init__(self):
            self.facts = None

        def write(self, question, facts, said="", before=""):
            self.facts = facts
            return "요약"

    w = Catch()
    e = Engine(FakeDesk({}), w, DATA, MemoryStore(), AssistantSettings(anthropic_api_key=""))
    st = new_state().model_copy(
        update={
            "log": tuple(
                LogEntry(turn=i, topic="solo_seniors", dongs=(d,))
                for i, d in enumerate(("수서동", "세곡동", "일원1동"), 1)
            ),
            "said_facts": (
                "[강남구 일원1동] - 65세 이상 1인세대 1,285명",
                "[강남구 세곡동] - 65세 이상 1인세대 1,873명",
                "[강남구 수서동] - 65세 이상 1인세대 2,543명",
            ),
        }
    )
    e.store.save("s", st)
    from src.assistant.engine import Plan

    plan = Plan("recall", topics=("recall",))
    out = list(e._summary_turn("s", st, DeskCard(act="ask"), plan, "지금까지 세 줄로 정리해 줘"))
    assert out[-1][0] == "done"
    lines = w.facts[0].lines
    assert lines[0].startswith("[강남구 수서동]") and lines[2].startswith("[강남구 일원1동]")
    assert any("수서동, 세곡동, 일원1동" in n for n in w.facts[0].notes)


def test_first_asked_dongs_come_from_the_log():
    # 10-27 밤 창 시험 T22: '처음에 물어본 세 동'에 데스크가 수서동을 빼고 세곡동부터 골랐다
    say = "처음에 물어본 세 동 혼자 사는 어르신 숫자 다시 알려줘"
    table = dict(TABLE)
    for d in ("세곡동", "역삼1동", "개포3동"):
        table[f"{d}은?"] = DeskCard(
            act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=(d,)
        )
    # 데스크가 틀리게 고른 카드(창 밖으로 밀린 수서동을 뺌)
    table[say] = DeskCard(
        act="ask",
        topics=("solo_seniors",),
        dong_op="set",
        dong_mentions=("세곡동", "역삼1동", "개포3동"),
    )
    s = AssistantSettings(anthropic_api_key="")
    e = Engine(FakeDesk(table), TemplateWriter(), DATA, MemoryStore(), s)
    c = TestClient(create_app(e, record=FakeRecord()))
    for q in (ASK, "세곡동은?", "역삼1동은?", "개포3동은?"):
        _done(c, "f", q)
    d = _done(c, "f", say)
    st = e.store.load(KEY.format("f"))
    assert d["kind"] == "answer" and set(st.slots.dongs) == {"수서동", "세곡동", "역삼1동"}
    assert "2,543" in d["text"]
