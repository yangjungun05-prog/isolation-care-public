"""앞에서 말한 숫자의 근거를 잃지 않는다(10-25 페르소나 cli4 오린 T7 · T9).

T5에 '강남 22곳 중 8곳(36%) · 춘천 25곳 중 14곳(56%)'을 말해 놓고
T7(되짚는 말 · 숫자가 없는 질문)에는 '제가 가진 자료에서 확인되지 않으니',
T9('강남 8/22, 춘천 14/25')에는 '지금 가진 자료에 없으니 출처를 알려 주시면'이라고 했다.
"""

import re

from src.assistant.engine import carry_facts, num_keys, said_lines
from src.assistant.librarian import Facts
from src.assistant.writer import OUTLOOK_SYSTEM, WRITER_SYSTEM

LINE = (
    "견줌(겹친 걱정이 있는 동 몫): 강남구 어르신 22곳 중 8곳, 36% / 춘천시 어르신 25곳 중 14곳, 56%"
)


def test_fraction_and_percent_meet_the_line():
    assert num_keys("강남 8/22, 춘천 14/25") & num_keys(LINE)
    assert num_keys("36% 대 56%") & num_keys(LINE)


def test_dates_are_not_numbers_to_carry():
    assert num_keys("기준일 2026-09-30 · 2025년 주민등록") == set()


def test_last_answer_numbers_bring_their_line_without_back_words():
    # T7: 되짚는 말도 숫자도 없는 질문 — 그래도 [직전 답]의 36% · 56% 근거는 준다
    before = "겹친 걱정 몫(강남구 22곳 중 8곳 36%, 춘천시 25곳 중 14곳 56%)은 상대 기준이에요."
    now = [Facts(title="취약 돌보미 판단", lines=["[강남구 개포3동] 겹친 걱정 0가지"])]
    ask = "보고서에 쓸 비교 문장 한 줄 써 주세요"
    c = carry_facts(ask, before, ("[강남구] 경로당 31곳",), now, kept=(LINE,))
    assert c is not None and c.lines == [LINE]
    assert "뒤집지 않는다" in c.notes[0]


def test_kept_lines_outlive_older_facts():
    # T9: 120줄 기억에서는 밀려났어도 실제로 말한 숫자의 근거 줄은 남아 있다
    older = tuple(f"[강남구 ○○동] 다른 줄 {i}" for i in range(120))
    c = carry_facts("강남 8/22, 춘천 14/25 맞죠?", "", (), [], older=older, kept=(LINE,))
    assert c is not None and c.lines[0] == LINE


def test_said_lines_keep_only_lines_whose_numbers_were_spoken():
    facts = [
        Facts(title="취약 돌보미 판단 · 두 지역", lines=[LINE, "[강남구] 경로당 31곳"]),
        Facts(title="진단", lines=["[강남구 수서동]", "- 진단: 혼자 사는 몫 46%"]),
    ]
    got = said_lines("22곳 중 8곳(36%), 25곳 중 14곳(56%) · 수서동 46%예요.", facts)
    # 동 머리줄은 줄 앞에 붙여 둔다(어느 동 숫자인지)
    assert got == [LINE, "[강남구 수서동] - 진단: 혼자 사는 몫 46%"]
    assert said_lines("네, 알겠어요.", facts) == []


def test_engine_remembers_spoken_numbers_across_many_turns():
    from src.assistant.config import AssistantSettings
    from src.assistant.data_source import JsonDongData
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import CARRY_TITLE
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter, template_answer

    class Spy(TemplateWriter):
        def __init__(self):
            self.got = []

        def write(self, question, facts, said="", before=""):
            self.got.append(facts)
            return template_answer(facts)

    table = {
        f"{d} 진단은?": DeskCard(
            act="ask", topics=("diagnosis",), dong_op="set", dong_mentions=(d,)
        )
        for d in ("수서동", "일원1동")
    }
    from src.assistant.engine import Engine

    w = Spy()
    store = MemoryStore()
    e = Engine(FakeDesk(table), w, JsonDongData(), store, AssistantSettings())
    e.start("s1", Profile(member_region="강남구"))
    e.turn("s1", "수서동 진단은?")
    st = store.load("s1")
    kept = next(x for x in st.said_facts if x.startswith("[강남구 수서동]") and "%" in x)
    token = next(t for t in sorted(num_keys(kept)) if t.endswith("%") and re.match(r"\d{2}", t))
    # 몇 턴이 지나 기억 120줄 · 직전 60줄이 다른 동 자료로 다 찼다고 친다
    filler = tuple(f"[강남구 ○○동] 다른 줄 {i}" for i in range(120))
    store.save("s1", st.model_copy(update={"last_facts": filler[:60], "older_facts": filler}))
    table[f"수서동 {token} 맞죠?"] = table["일원1동 진단은?"]
    e.turn("s1", f"수서동 {token} 맞죠?")
    carried = [f for f in w.got[-1] if f.title == CARRY_TITLE]
    assert carried and kept in carried[0].lines


def test_compare_line_carries_its_meaning():
    # 재생 T9: 이 줄만 이어 주자 '자료에 상대 기준이라는 말은 없다' → 숫자 줄이 뜻을 함께 담는다
    from src.assistant import librarian
    from src.assistant.data_source import JsonDongData
    from src.assistant.slots import Slots

    librarian.AS_OF = "2025-12-31"
    try:
        f = librarian.gather(
            "outlook", Slots(region="강남구", target="어르신", compare=True), JsonDongData()
        )
    finally:
        librarian.AS_OF = "live"
    line = next(x for x in f.lines if x.startswith("견줌(겹친 걱정이 있는 동 몫): "))
    assert "우열은 가리지 않음" in line
    assert not any("견줌 줄" in n for n in f.notes)  # 안쪽 말이 답에 새지 않게


def test_both_writer_prompts_forbid_turning_over_the_last_answer():
    for system in (WRITER_SYSTEM, OUTLOOK_SYSTEM):
        assert "[직전 답]" in system and "뒤집" in system


def test_region_compare_survives_a_dong_named_in_passing():
    # T7: 앞 문장의 '개포3동'이 동 칸에 들어가도 '강남구와 춘천시 비교'면 두 지역 자료를 준다
    from src.assistant import librarian
    from src.assistant.data_source import JsonDongData
    from src.assistant.slots import Slots

    data = JsonDongData()
    asked = '개포3동은 5구간으로 쓰겠습니다. "강남구와 춘천시 비교:" 뒤에 들어갈 문장 한 줄'
    slots = Slots(region="강남구", dongs=("개포3동",), target="어르신", compare=True)
    librarian.AS_OF = "2025-12-31"
    try:
        fs = librarian.gather_all(("outlook",), slots, data, asked)
        lines = [ln for f in fs for ln in f.lines]
        assert any(ln.startswith("견줌(겹친 걱정이 있는 동 몫): ") for ln in lines)
        assert any("개포3동" in ln for ln in lines)  # 그 동 자료도 그대로
        # 두 지역의 동을 견주는 말은 동끼리 견줌이라 지역 견줌을 더하지 않는다
        both = slots.model_copy(update={"dongs": ("개포3동", "동면")})
        fs2 = librarian.gather_all(("outlook",), both, data, "강남 개포3동이랑 춘천 동면 비교")
        assert not any(
            ln.startswith("견줌(겹친 걱정이 있는 동 몫): ") for f in fs2 for ln in f.lines
        )
    finally:
        librarian.AS_OF = "live"


def test_our_risk_tier_name_is_not_risky_wording():
    # T9: '가장 위험한 5구간'은 위험 구간 이름 — '네, …'로 답해도 허락으로 읽히지 않는다
    from src.assistant import checks

    q = "개포3동은 가장 위험한 5구간에서 자원 공백 0.61로 제일 큼. 이 세 줄 그대로 써도 되는지"
    assert not checks.yes_to_risky_wording("네, 맞아요.", q)
    # 자료에 없는 단정('제일 위험한 동')은 그대로 막는다
    assert checks.yes_to_risky_wording("네, 써도 돼요.", "수서동이 제일 위험한 동이라고 써도 되죠?")
