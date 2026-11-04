from src.assistant import memory
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.policy import OUT_OF_SCOPE
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import JsonFileStore, MemoryStore
from src.assistant.writer import TemplateWriter

TABLE = {
    "안녕하세요. 저는 수서동 주민센터에서 어르신 방문을 맡고 있어요": DeskCard(
        act="chitchat",
        new_facts=("수서동 주민센터 · 어르신 방문 담당",),
        dong_op="set",
        dong_mentions=("수서동",),
        target_op="set",
        target="어르신",
    ),
    "혼자 사시는 분 몇 명이에요?": DeskCard(
        act="ask", topics=("solo_seniors",), alone_op="set", alone=True
    ),
    "청년은요?": DeskCard(act="ask", topics=("youth",), target_op="set", target="청년"),
    "음식물 쓰레기 처리 비용은?": DeskCard(act="out_of_scope", suggest=("housing",)),
    "북산면도 알려줘": DeskCard(act="ask", dong_op="set", dong_mentions=("북산면",)),
    "아까 그 첫 번째 동 경로당은?": DeskCard(
        act="ask", topics=("senior_hall",), dong_op="set", dong_mentions=("수서동",)
    ),
    "내 담당 지역을 춘천 효자2동으로 바꿔줘": DeskCard(
        act="ask",
        topics=("my_region",),
        dong_op="set",
        dong_mentions=("효자2동",),
        region_op="set",
        region="춘천시",
    ),
    "먼저 볼 동은?": DeskCard(act="ask", topics=("priority",), dong_op="clear"),
    "제가 처음에 어디 담당이라고 했죠?": DeskCard(act="ask", topics=("recall",)),
}


def make(store=None) -> Engine:
    s = AssistantSettings(anthropic_api_key="")
    return Engine(FakeDesk(TABLE), TemplateWriter(), JsonDongData(), store or MemoryStore(), s)


def test_scripted_conversation():
    e = make()
    e.start("t1", Profile(member_region="강남구"))
    r = e.turn("t1", "안녕하세요. 저는 수서동 주민센터에서 어르신 방문을 맡고 있어요")
    assert r.kind == "chitchat" and r.state.facts == ("수서동 주민센터 · 어르신 방문 담당",)
    r = e.turn("t1", "혼자 사시는 분 몇 명이에요?")
    assert r.kind == "answer" and "2,543명" in r.text  # 앞에서 말한 수서동을 들고 간다
    r = e.turn("t1", "청년은요?")
    assert r.kind == "answer" and "1,897명" in r.text
    r = e.turn("t1", "음식물 쓰레기 처리 비용은?")
    assert r.kind == "out_of_scope" and r.text.startswith(OUT_OF_SCOPE)
    assert r.state.slots.dongs == ("수서동",)  # 범위 밖 질문이 상태를 망치지 않는다
    r = e.turn("t1", "북산면도 알려줘")  # 주제 생략 → 직전 주제(청년)를 잇는다
    assert r.kind == "answer" and "북산면" in r.text and "10명 미만" in r.text
    r = e.turn("t1", "아까 그 첫 번째 동 경로당은?")
    # 【판단】 10-13: 경로당 수는 서울시 경로당 현황 2025-06(수서동은 2022와 같은 8곳)
    assert r.kind == "answer" and "경로당 8곳" in r.text
    r = e.turn("t1", "내 담당 지역을 춘천 효자2동으로 바꿔줘")
    assert r.kind == "settings" and r.state.profile.member_dong == "효자2동"
    r = e.turn("t1", "먼저 볼 동은?")
    # 10-19 2026 최신 판(전에는 1위 북산면)
    assert r.kind == "answer" and "춘천시" in r.text and "1위 효자2동" in r.text


def test_survives_restart_with_file_store(tmp_path):
    e = make(JsonFileStore(tmp_path))
    e.start("t2", Profile(member_region="강남구"))
    e.turn("t2", "안녕하세요. 저는 수서동 주민센터에서 어르신 방문을 맡고 있어요")
    e2 = make(JsonFileStore(tmp_path))  # 서버가 다시 켜진 것처럼 새 엔진
    r = e2.turn("t2", "혼자 사시는 분 몇 명이에요?")
    assert "2,543명" in r.text and r.state.turn == 2


def test_120_turns_memory_stays_bounded():
    # 【기능】 100턴이 넘어도 데스크에게 가는 기억의 크기가 늘지 않는다
    e = make()
    e.start("t3", Profile(member_region="강남구"))
    lines = list(TABLE)
    sizes = []
    for i in range(120):
        e.turn("t3", lines[i % len(lines)])
        sizes.append(len(memory.render(e.store.load("t3"))))
    st = e.store.load("t3")
    assert st.turn == 120
    assert max(sizes[60:]) <= max(sizes[:60]) * 1.2
    assert len(st.recent) == e.s.history_turns and len(st.facts) <= e.s.facts_head + e.s.facts_tail


def test_empty_input_does_not_call_desk():
    e = make()
    r = e.turn("t4", "   ")
    assert r.kind == "unclear" and e.desk.seen == []


def test_recall_answers_from_code_memory():
    e = make()
    e.start("t5", Profile(member_region="강남구"))
    e.turn("t5", "안녕하세요. 저는 수서동 주민센터에서 어르신 방문을 맡고 있어요")
    e.turn("t5", "혼자 사시는 분 몇 명이에요?")
    r = e.turn("t5", "제가 처음에 어디 담당이라고 했죠?")
    assert (
        r.kind == "recall" and "수서동 주민센터 · 어르신 방문 담당" in r.text and "수서동" in r.text
    )


def test_turn_stream_sends_pieces_then_the_same_reply():
    # 【기능】 흘려 보이기: 글쓴이 조각이 오는 대로 나가고, 마지막 Reply 는 turn() 과 같은 글
    from src.assistant.writer import WriteResult

    class StreamWriter(TemplateWriter):
        last = None

        def write_stream(self, question, facts, said="", before=""):
            yield ("text", "첫 문장. ")
            yield ("replace", "코드 기본 답")
            self.last = WriteResult("코드 기본 답", False, ["없는 숫자"])

    e = Engine(FakeDesk(TABLE), StreamWriter(), JsonDongData(), MemoryStore(), make().s)
    e.start("t8", Profile(member_region="강남구"))
    e.turn("t8", "안녕하세요. 저는 수서동 주민센터에서 어르신 방문을 맡고 있어요")
    # 10-27: 진행 단계(status)는 화면에서만 쓰는 알림이라 빼고 본다
    events = [x for x in e.turn_stream("t8", "혼자 사시는 분 몇 명이에요?") if x[0] != "status"]
    assert events[0] == ("text", "첫 문장. ") and events[1] == ("replace", "코드 기본 답")
    done = events[-1]
    assert done[0] == "done" and done[1].kind == "answer" and done[1].text == "코드 기본 답"
    assert e.store.load("t8").recent[-1].bot == "코드 기본 답"  # 기억에도 진짜 답이 남는다


def test_long_input_is_refused_not_clipped():
    # 【기능】 10-12 팀장 "1000자까지만": 넘는 글은 몰래 자르지 않고 받지 않는다.
    #        데스크 · 기억은 그대로
    from src.assistant.policy import MAX_INPUT

    e = make()
    e.start("t7", Profile(member_region="강남구"))
    e.turn("t7", "혼자 사시는 분 몇 명이에요?")
    before = e.store.load("t7")
    seen = len(e.desk.seen)
    text = "공문 내용 " * 400 + "그래서 수서동 청년은 몇 명이에요?"
    r = e.turn("t7", text)
    assert r.kind == "too_long" and f"{len(text):,}자" in r.text and "1,000자" in r.text
    assert len(e.desk.seen) == seen  # 데스크를 부르지 않음(값 0)
    assert e.store.load("t7") == before  # 긴 글이 최근 대화에 남지 않음
    r = e.turn("t7", "가" * MAX_INPUT)  # 딱 1,000자는 받는다
    assert r.kind != "too_long"


def test_priority_answer_is_remembered_in_log_note():
    # 【기능】 '아까 3위였던 동'을 풀려면 우리가 답한 순위를 기억해야 한다(100턴 1차 T64)
    e = make()
    e.start("t6", Profile(member_region="강남구"))
    e.turn("t6", "먼저 볼 동은?")
    st = e.store.load("t6")
    assert "3위 논현2동" in st.log[-1].note
    assert "답한 것: 강남구 1위 개포3동" in memory.render(st)
