"""'없다'가 맞는 답인 물음 · 가린 것을 묻는 말(10-25 페르소나 cli2 다리엔 T9 · 세라핀 T8 · T9).

둘 다 글쓴이 답이 '없다고만 함' 검사에 걸려, 묻지 않은 긴 자료 설명(기본 답)이 나갔다.
"""

from src.assistant import checks
from src.assistant.engine import MASK_ASK, mask_answer, mask_spots


def test_confirming_a_sentence_that_says_unknown_is_not_none_only():
    darien = (
        '다만 아래 문장이 자료 내용과 맞는지만 확인해 주세요. "취약 돌보미의 날씨 관측 자료는 '
        '2026-10-20까지라, 18일 비 이후 개포3동 어르신 상황은 이 자료로 확인할 수 없다." '
        "이 문장 그대로 써도 될까요?"
    )
    seraphine = "결국 혼자 사는 청년 수의 흐름과 어림치 말고는 없다는 뜻으로 받겟습니다."
    assert checks.asks_if_unknown(darien)
    assert checks.asks_if_unknown(seraphine)
    # '없다'가 든 확인이 아니면 그대로 검사한다
    assert not checks.asks_if_unknown("수서동 경로당 몇 곳이야?")
    assert not checks.asks_if_unknown("춘천이 더 심각하다고 써도 될까요?")


def test_what_was_masked_is_answered_from_the_masked_spots():
    # 재생: 대화 기억은 글의 앞 200자만 남겨 520자째의 '[이름]'이 잘렸다 → 가린 자리를 따로 둔다
    text = "가" * 500 + " 청년 가족이나 [이름] 전화를 해 올 때 어디로 안내할까요"
    spots = mask_spots(text)
    said = mask_answer(spots)
    assert "이름 1곳" in said and "[이름] 전화를" in said
    assert "무엇이었는지는 저도 알 수 없어요" in said
    # 가린 적이 없으면 없다고 분명히(재생: AI가 '직전 답에 그런 말이 없어 근거가 없다')
    assert mask_spots("수서동 경로당 알려줘") == ()
    assert mask_answer(()).startswith("이 대화에서는 가린 말이 없어요")


def test_mask_questions_are_recognised():
    for q in (
        "제 글에서 무엇을 가리셨는지 아직 말씀이 없습니다",
        "그 가린 것이 무엇이었습니까",
        "제 이름을 가리신 거면 그렇다고 써 주세요",
    ):
        assert MASK_ASK.search(q), q
    assert not MASK_ASK.search("수서동 경로당 가는 길 알려줘")
    # '가리키다'는 가림이 아니다
    assert not MASK_ASK.search("이 숫자는 무엇을 가리키나요?")
    assert not MASK_ASK.search("겹친 걱정이 뭘 가리킨 건지 모르겠어요")


def test_engine_answers_what_was_masked_without_the_desk():
    from src.assistant.config import AssistantSettings
    from src.assistant.data_source import JsonDongData
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import Engine
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    class NoDesk(FakeDesk):
        def __init__(self):
            super().__init__({})
            self.read_calls = 0

        def read(self, state, text):
            self.read_calls += 1
            return super().read(state, text)

    desk = NoDesk()
    e = Engine(desk, TemplateWriter(), JsonDongData(), MemoryStore(), AssistantSettings())
    e.start("s1", Profile(member_region="강남구"))
    r1 = e.turn("s1", "박영희 씨 부탁으로 수서동 경로당을 봅니다")
    assert "가리고 받았어요" in r1.text
    calls = desk.read_calls
    r2 = e.turn("s1", "제 글에서 무엇을 가리셨나요?")
    assert r2.kind == "recall" and "이름 1곳" in r2.text and "[이름]" in r2.text
    assert "박영희" not in r2.text
    assert desk.read_calls == calls  # 데스크를 부르지 않는다


def test_engine_keeps_masked_spots_past_the_200_char_cut():
    from src.assistant.config import AssistantSettings
    from src.assistant.data_source import JsonDongData
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import Engine
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    e = Engine(FakeDesk({}), TemplateWriter(), JsonDongData(), MemoryStore(), AssistantSettings())
    e.start("s1", Profile(member_region="강남구"))
    e.turn("s1", "수서동 " * 80 + "박영희 씨 부탁으로 경로당을 봅니다")
    e.turn("s1", "고마워요")  # 사이에 다른 턴이 있어도
    r = e.turn("s1", "그 가린 것이 무엇이었습니까")
    assert r.kind == "recall" and "이름 1곳" in r.text and "박영희" not in r.text


def test_common_words_for_people_are_not_names():
    # 세라핀 T6: '이웃이 전화를'을 이름으로 가렸다
    from src.assistant import pii

    for s in (
        "연락이 끊긴 청년 가족이나 이웃이 전화를 해 올 때",
        "이장이 전화로 알려 왔어요",
        "조카가 주소를 물어봐요",
        "손자가 연락처를 남겼어요",
    ):
        masked, kinds = pii.mask(s)
        assert kinds == [] and masked == s, s
    # 진짜 이름은 그대로 가린다
    assert pii.mask("김순자 전화번호 알려줘")[1] == ["이름"]
    assert pii.mask("이영희 씨 주소")[1] == ["이름"]


def test_present_but_denied_looks_at_facts_not_at_the_question():
    # 다리엔 T2(재생): 질문 글에 있던 '이 판단이 현장과 맞는지'를 '자료에 있다'로 보고 답을 버렸다
    facts = "[강남구 개포3동] 취약 돌보미 판단: 겹친 걱정 없음 · 따로 해당하는 조건 5가지"
    asked = "개포3동 취약 돌보미 판단에서 겹친 걱정이 없다는 이 판단이 현장과 맞는지 확인해 달라"
    answer = "이 판단이 현장과 맞는지는 이 자료로 확인할 수 없어요. 해당 조건은 5가지예요."
    allowed = f"{facts}\n{asked}"
    assert any(p.startswith("있는데 없다고 함") for p in checks.problems(answer, allowed, []))
    assert not any(
        p.startswith("있는데 없다고 함")
        for p in checks.problems(answer, allowed, [], facts_text=facts)
    )
