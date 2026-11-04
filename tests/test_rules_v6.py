"""데스크 v6 규칙(10-12): 켠 칸만 적는 카드 · 칸 규칙 · 개인정보 가림 ·
지표 줄 세우기 · 밝힘 · 되짚기."""

from src.assistant import memory
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.librarian import gather
from src.assistant.pii import mask
from src.assistant.policy import disclose, preflight
from src.assistant.slots import DeskCard, Slots, card_from_tool, desk_tool_schema
from src.assistant.state import Profile, apply_card, new_state
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()


def test_mask_hides_name_phone_unit_and_rrn():
    out, kinds = mask("제가 맡은 분은 302호 김순자 할머니(010-1234-5678)예요")
    assert "김순자" not in out and "010-1234-5678" not in out and "302호" not in out
    assert kinds == ["전화번호", "호수", "이름"]
    out, kinds = mask("주민번호 900101-1234567인 분")
    assert "900101" not in out and kinds == ["주민번호"]


def test_mask_keeps_dong_names_and_ordinary_words():
    for text in (
        "역삼1동 혼자 사는 어르신 몇 명?",
        "정말 어르신들 많네요",
        "지하철 3호선 근처 경로당",
        "세곡동 할머니들",
        "80세 이상 할머니만",
        "2025년 12월 기준 2,471명",
    ):
        assert mask(text) == (text, [])


def test_card_schema_requires_only_three():
    assert desk_tool_schema()["required"] == ["restate", "act", "topics"]


def test_card_value_turns_on_off_turns_off_missing_keeps():
    # 【기능】 값을 적으면 켜짐(set), off 에 이름이면 지움(clear), 안 적으면 그대로(keep)
    c = card_from_tool(
        {
            "restate": "r",
            "act": "ask",
            "topics": ["solo_seniors"],
            "dongs": ["세곡동"],
            "off": ["ages"],
        }
    )
    assert (c.dong_op, c.dong_mentions) == ("set", ("세곡동",))
    assert (
        c.ages_op == "clear" and c.sex_op == "keep" and c.region_op == "keep" and c.block == "none"
    )


def test_new_dong_replaces_old_unless_compare():
    st = new_state(Profile(member_region="강남구"))
    both = DeskCard(
        act="ask", topics=("diagnosis",), dong_op="set", dong_mentions=("세곡동", "수서동")
    )
    st = apply_card(
        st, both.model_copy(update={"compare": True}), "세곡동이 수서동보다 위험해?"
    ).state
    assert set(st.slots.dongs) == {"세곡동", "수서동"}
    # 데스크가 앞 동까지 적어도, 사용자가 수서동만 말했으면 수서동만(10-12 멘토 · 떠보기)
    out = apply_card(st, both, "수서동은 임대아파트 때문이지?")
    assert out.state.slots.dongs == ("수서동",)


def test_pointing_word_keeps_desk_dongs():
    st = new_state(Profile(member_region="강남구"))
    card = DeskCard(act="ask", topics=("youth",), dong_op="set", dong_mentions=("수서동",))
    assert apply_card(st, card, "거기 청년은?").state.slots.dongs == ("수서동",)


def test_topic_change_clears_conditions_but_side_question_keeps():
    st = new_state(Profile(member_region="강남구"))
    first = DeskCard(
        act="ask",
        topics=("solo_seniors",),
        dong_op="set",
        dong_mentions=("수서동",),
        sex_op="set",
        sex="남",
        period_op="set",
        period="작년 여름",
        ages_op="set",
        age_lo=80,
    )
    st = apply_card(st, first, "수서동 80세 이상 할아버지 작년 여름").state
    assert st.slots.sex == "남" and st.slots.ages is not None
    hall = apply_card(st, DeskCard(act="ask", topics=("senior_hall",)), "수서동 경로당은?").state
    s = hall.slots
    assert s.sex is None and s.period is None and s.ages is None and s.dongs == ("수서동",)
    side = apply_card(st, DeskCard(act="ask", topics=("sources",)), "그게 무슨 뜻이에요?").state
    assert side.slots.sex == "남"  # 말뜻 같은 곁질문은 조건을 비우지 않는다


def test_rank_lists_dongs_by_one_indicator():
    f = gather("solo_seniors", Slots(region="강남구", rank=True), DATA)
    assert "1위 수서동 2,543" in f.lines[0]  # 10-19 주민등록 2026-09
    f = gather("livelihood", Slots(region="춘천시", rank=True), DATA)
    assert "1위 퇴계동 2,399" in f.lines[0]


def test_rank_combination_picks_topic_the_region_has():
    # 【바꿈 10-14】 강남은 '기초생활수급자'를 수급권자 독거노인(서울시 독거노인 현황)으로 줄 세운다
    #        (test_fixes_1014). 지역에 없는 주제는 춘천의 서울시 독거노인 현황으로 본다
    st = new_state(Profile(member_region="강남구"))
    card = DeskCard(act="ask", topics=("livelihood", "solo_seniors"), rank=True)
    plan = preflight(apply_card(st, card, "기초수급 독거 어르신 많은 동"), card, DATA)
    assert plan.kind == "answer" and plan.topics == ("livelihood",)
    st = new_state(Profile(member_region="춘천시"))
    card = DeskCard(act="ask", topics=("seoul_lonely", "solo_seniors"), rank=True)
    plan = preflight(apply_card(st, card, "독거노인 많은 동"), card, DATA)
    assert plan.kind == "answer" and plan.topics == ("solo_seniors",)  # 춘천엔 서울시 현황이 없다
    only = DeskCard(act="ask", topics=("seoul_lonely",), rank=True)
    plan = preflight(apply_card(st, only, "서울시 독거노인 많은 동"), only, DATA)
    assert plan.kind == "coverage"


def test_disclose_says_what_was_left_out():
    d = disclose(DeskCard(unmet=("기초수급 받는",)), Slots(sex="남", period="작년 여름"))
    # 10-19: 견주는 달은 자료에서 읽는다(주민등록 2026-09 → 견줌 2025-09)
    assert "'기초수급 받는'" in d and "남녀" in d and "2025년 9월" in d
    assert disclose(DeskCard(), Slots(period="작년")) == ""  # '작년'은 자료의 견줌 그대로


class SpyDesk(FakeDesk):
    def __init__(self, table):
        super().__init__(table)
        self.texts: list[str] = []

    def read(self, state, text):
        self.texts.append(text)
        return super().read(state, text)


def _engine(table) -> Engine:
    return Engine(
        SpyDesk(table),
        TemplateWriter(),
        DATA,
        MemoryStore(),
        AssistantSettings(anthropic_api_key=""),
    )


def test_personal_info_never_reaches_desk_or_memory():
    e = _engine({})
    e.start("p", Profile(member_region="강남구"))
    r = e.turn("p", "302호 김순자 할머니(010-1234-5678) 기억해 둬")
    assert "김순자" not in e.desk.texts[0] and "010-1234-5678" not in e.desk.texts[0]
    mem = memory.render(e.store.load("p"))
    assert "김순자" not in mem and "010-1234-5678" not in mem
    assert "가리고 받았어요" in r.text


def test_recall_narrowed_to_one_region_keeps_slots():
    e = _engine(
        {
            "수서동 혼자": DeskCard(
                act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("수서동",)
            ),
            "퇴계동 혼자": DeskCard(
                act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("퇴계동",)
            ),
            "춘천은?": DeskCard(act="ask", topics=("recall",), region_op="set", region="춘천시"),
        }
    )
    e.start("q", Profile(member_region="강남구"))
    e.turn("q", "수서동 혼자")
    e.turn("q", "퇴계동 혼자")
    r = e.turn("q", "춘천은?")
    assert r.kind == "recall" and "퇴계동" in r.text and "수서동" not in r.text
    assert r.state.slots.dongs == ("퇴계동",)


def test_empty_values_mean_unchanged_not_on():
    # 【기능】 10-12 r9 버그: block 에 none 이 없어 평범한 질문이 '개인 질문' · '위급'으로 막혔다
    assert "none" in desk_tool_schema()["properties"]["block"]["enum"]
    c = card_from_tool(
        {
            "restate": "r",
            "act": "ask",
            "topics": ["youth"],
            "block": "none",
            "region": "",
            "sex": "",
            "target": "",
            "alone": False,
            "fmt": "답",
        }
    )
    assert c.block == "none" and c.fmt == "답"
    assert (c.region_op, c.sex_op, c.target_op, c.alone_op) == ("keep", "keep", "keep", "keep")
