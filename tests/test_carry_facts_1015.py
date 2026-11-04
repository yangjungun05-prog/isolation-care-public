"""앞 답을 되짚는 말에는 앞 답의 자료를 이어 준다(10-15, 문제 목록 1-3 · 페르소나 20b 재생).

재생에서 '앞 답 숫자를 없다고 함'이 원본 18 · 중간 9 · 마지막 19(같은 211턴)로 흔들렸다. 뒤집힌 턴은
데스크가 그 턴에 다른 주제를 골라 앞 답의 숫자(순위 · 진단)가 사실 묶음에서 빠진 경우였다
(q01 T13 '12위 맞죠?' → 진단 대신 버스 주제 → '12위는 확인되지 않아요').
"""

from src.assistant.engine import carry_facts
from src.assistant.librarian import Facts

LAST = ("## 진단 · 왜 이 동인가", "[춘천시 동면] 취약 돌보미 동 순위 17위 · 다시 매기면 12위")
ANSWER = "동면은 17위이고, 다시 매기면 12위예요. 65세 이상 1인세대는 1,082명이에요."


def test_back_reference_brings_last_facts():
    now = [Facts(title="춘천 버스", lines=["동면을 지나는 노선 9개"])]
    c = carry_facts("1,082명이랑 12위 맞죠?", ANSWER, LAST, now)
    assert c is not None and any("12위" in x for x in c.lines)
    c2 = carry_facts("아까 말한 순위 다시 알려줘", ANSWER, LAST, now)
    assert c2 is not None


def test_new_question_carries_only_the_last_answers_backing():
    # 10-25 오린 T7: 새 질문이라도 글쓴이는 [직전 답]을 본다 → 그 숫자(17위 · 12위)의 근거 줄만
    #        이어 준다. 앞 자료의 다른 줄(경로당 31곳)은 붙이지 않는다
    now = [Facts(title="춘천 버스", lines=["동면을 지나는 노선 9개"])]
    last = (*LAST, "[춘천시 동면] 경로당 31곳")
    c = carry_facts("북산면 버스는요?", ANSWER, last, now)
    assert c is not None and c.lines == [LAST[1]]
    assert carry_facts("1,082명 맞죠?", "", (), now) is None  # 앞 답이 없으면 없음


def test_lines_already_in_this_turn_are_not_repeated():
    now = [Facts(title="진단 · 왜 이 동인가", lines=[LAST[1]])]
    assert carry_facts("12위 맞죠?", ANSWER, LAST, now) is None


def test_engine_keeps_last_facts_and_hands_them_over():
    from src.assistant.config import AssistantSettings
    from src.assistant.data_source import JsonDongData
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import Engine
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter, template_answer

    class Spy(TemplateWriter):
        def __init__(self):
            self.got = []

        def write(self, question, facts, said="", before=""):
            self.got.append([f.title for f in facts])
            return template_answer(facts)

    table = {
        "수서동 진단은?": DeskCard(
            act="ask", topics=("diagnosis",), dong_op="set", dong_mentions=("수서동",)
        ),
        # 데스크가 되짚는 말에 다른 주제(버스 · 강남엔 없음 → 혼자 사는 어르신)를 골랐다고 친다
        "그럼 2위 맞죠?": DeskCard(act="ask", topics=("solo_seniors",)),
    }
    w = Spy()
    e = Engine(FakeDesk(table), w, JsonDongData(), MemoryStore(), AssistantSettings())
    e.start("s1", Profile(member_region="강남구"))
    r1 = e.turn("s1", "수서동 진단은?")
    assert r1.kind == "answer" and r1.state.last_facts and "2위" in r1.text
    e.turn("s1", "그럼 2위 맞죠?")
    assert "앞서 답할 때 본 자료(다시 확인용)" in w.got[-1]
