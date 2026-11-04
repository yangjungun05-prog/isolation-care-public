"""10-29 브라우저 시험(담당 개포3동 실무자 말투) 뒤 고침 — 지역 전체냐 동 하나냐는 데스크와 동시에
데스크 모델(Haiku)이 고른다(팀장 '고치고 머지').

- '80세 이상만 따로 보면요? 많은데 5군데만' → '5곳은 드릴 수 없어요'(거짓) · '반지하가 있는 곳은
  어디야?' → '강남구에서 반지하가 있는 곳은 개포3동'(틀림): 말에 지역 이름이 없어 AI에게 묻지
  않았고, 데스크가 비운 동 칸을 '전체' 낱말이 없다고 되돌렸다
- '우리동 혼자사는 어르신이랑 혼자사는 청년 둘다 작년꺼랑 같이 표로': 지표가 둘이라 계산 길로 가
  계획기가 지역 전체 줄 세우기를 짜 강남 위 5곳 표가 붙었다(글은 개포3동으로 맞음)
- 같은 날 회귀: 지역 이름 없는 뒷말을 데스크가 동 그대로 둔 턴까지 AI 혼자 지역 전체로 바꾸면
  ('경로당은 몇 곳이에요?') 100턴 대화 5턴이 틀렸다 → 데스크와 AI 둘 다 지역 전체일 때만
"""

import time

from src.assistant import query as Q
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.policy import SCOPE_ASK, desk_sanity, region_scope
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

FIVE = "80세 이상만 따로 보면요? 많은데 5군데만"
SOLO = DeskCard(act="ask", topics=("solo_seniors",))
CLEARED = SOLO.model_copy(update={"dong_op": "clear"})


def test_no_region_name_goes_to_ai_only_when_desk_cleared_the_dong():
    assert region_scope(CLEARED, FIVE) == "cleared"
    # 데스크가 동을 그대로 둔 뒷말은 지역 이름이 없으면 고르지 않는다(AI 혼자 바꾸지 않음)
    assert region_scope(SOLO, "경로당은 몇 곳이에요?") == ""
    assert region_scope(SOLO, "강남구 " + FIVE) == "plain"
    # '전체 · 모든 동'이 있으면 낱말로 이미 지역 전체
    assert region_scope(CLEARED, "강남구 전체로는 몇 명이에요?") == ""
    # 동 이름만 말하고 지역 이름이 없으면 고르지 않는다(데스크 그대로)
    named = SOLO.model_copy(update={"dong_op": "set", "dong_mentions": ("개포3동",)})
    assert region_scope(named, "개포3동 독거노인 몇 명이에요?") == ""
    # 줄 세울 수 없는 주제는 고르지 않는다
    assert region_scope(DeskCard(act="ask", topics=("support",)), "어디로 연락해요?") == ""


def test_cleared_card_stays_cleared_only_when_ai_says_region():
    got, _ = desk_sanity(CLEARED, FIVE, pick=lambda a, c: "region")
    assert got.dong_op == "clear" and got.rank
    got, _ = desk_sanity(CLEARED, FIVE, pick=lambda a, c: "dong")
    assert got.dong_op == "keep"
    # AI가 답하지 못하면 예전처럼 '전체' 낱말로
    got, _ = desk_sanity(CLEARED, FIVE, pick=lambda a, c: None)
    assert got.dong_op == "keep"
    got, _ = desk_sanity(CLEARED, "강남구 전체로는 몇 명이에요?")
    assert got.dong_op == "clear"


def test_ai_alone_does_not_clear_a_kept_dong_without_region_name():
    for said in ("경로당은 몇 곳이에요?", "서울시 독거노인 현황으로는요?", FIVE):
        got, _ = desk_sanity(SOLO, said, pick=lambda a, c: "region")
        assert got.dong_op == "keep", said


class SlowDesk(FakeDesk):
    """데스크 읽기가 끝나기 전에 말뜻 고르기가 이미 불렸는지 본다."""

    def __init__(self, table, picks):
        super().__init__(table, picks)
        self.started: set[str] = set()
        self.asks: list[str] = []

    def read(self, state, text):
        end = time.monotonic() + 5
        while text not in self.started and time.monotonic() < end:
            time.sleep(0.01)
        assert text in self.started, "말뜻 고르기가 데스크와 동시에 불리지 않음"
        return super().read(state, text)

    def pick(self, state, text, ask, choices):
        self.started.add(text)
        self.asks.append(ask)
        return super().pick(state, text, ask, choices)


def test_scope_is_asked_alongside_the_desk(tmp_path):
    first = "개포3동 혼자 사는 어르신 몇 명이에요?"
    card = DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("개포3동",))
    desk = SlowDesk({first: card, FIVE: CLEARED}, {first: "dong", FIVE: "region"})
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(desk, TemplateWriter(), JsonDongData(), MemoryStore(), s)
    e.start("x", Profile(member_region="강남구", member_dong="개포3동"))
    assert e.turn("x", first).state.slots.dongs == ("개포3동",)
    r = e.turn("x", FIVE)
    assert r.state.slots.dongs == () and r.state.slots.rank
    # 같은 물음은 한 턴에 한 번만(동시에 물은 답을 policy도 쓴다)
    assert desk.asks == [SCOPE_ASK, SCOPE_ASK]


class FakePlanner:
    def __init__(self, plan):
        self.p = plan

    def plan(self, question, region, context=""):
        return self.p


BOTH = "그럼 우리동 혼자사는 어르신이랑 혼자사는 청년 둘다 작년꺼랑 같이 표로 좀 정리해주세요"


def _both_turn(tmp_path, pick, plan):
    first = "개포3동 혼자 사는 어르신 몇 명이에요?"
    gaepo = {"dong_op": "set", "dong_mentions": ("개포3동",)}
    card = DeskCard(act="ask", topics=("solo_seniors", "youth"), target_op="set", target="둘 다")
    desk = FakeDesk(
        {first: SOLO.model_copy(update=gaepo), BOTH: card.model_copy(update=gaepo)},
        {BOTH: pick} if pick else {},
    )
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(
        desk,
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        s,
        planner=FakePlanner(plan),
    )
    e.start("x", Profile(member_region="강남구", member_dong="개포3동"))
    e.turn("x", first)
    return e.turn("x", BOTH)


LISTING = Q.Plan(
    region="강남구",
    show=(Q.Ref(metric="solo65"), Q.Ref(metric="youth_solo")),
    sort=Q.Ref(metric="solo65"),
)


def _calc(r) -> bool:
    return any(f.title == "여러 조건 계산" for f in r.facts)


def test_one_dong_question_does_not_list_the_whole_region(tmp_path):
    r = _both_turn(tmp_path, "dong", LISTING)
    assert not _calc(r)
    assert r.state.slots.dongs == ("개포3동",)
    # AI가 답하지 못하거나 지역 전체라고 보면 계산 길 그대로
    assert _calc(_both_turn(tmp_path, None, LISTING))
    assert _calc(_both_turn(tmp_path, "region", LISTING))


def test_one_dong_question_drops_region_total_or_other_dongs(tmp_path):
    # 같은 날 다시: 합계만 낸 계산 · 그 동이 빠진 앞 결과 동 목록도 지금 길로
    total = LISTING.model_copy(update={"agg": ("합계",)})
    assert not _calc(_both_turn(tmp_path, "dong", total))
    others = LISTING.model_copy(update={"dongs": ("역삼1동", "논현1동"), "use_prev": True})
    assert not _calc(_both_turn(tmp_path, "dong", others))


def test_one_dong_question_keeps_calc_that_filters_or_compares(tmp_path):
    # 조건으로 거르거나(평균보다 · 이면서) 평균과 견주거나 그 동을 짚은 계산은 동 하나 질문이어도
    conds = LISTING.model_copy(update={"conds": (Q.Cond(metric="solo65", op="많음"),)})
    assert _calc(_both_turn(tmp_path, "dong", conds))
    agg = LISTING.model_copy(update={"agg": ("평균",)})
    assert _calc(_both_turn(tmp_path, "dong", agg))
    named = LISTING.model_copy(update={"dongs": ("개포3동",)})
    assert _calc(_both_turn(tmp_path, "dong", named))


def test_two_topic_chat_table_shows_both_topics():
    from src.assistant import table

    t = table.build(("solo_seniors", "youth"), "강남구", ["개포3동"], JsonDongData())
    view, n = table.chat_view(t, alone=True)
    md = table.markdown(view, max_cols=n)
    head = md.splitlines()[0]
    # 혼자 사는 분 · 작년과 함께: 주제마다 1인세대 작년 · 올해 두 열(동 + 4열)
    assert n == 5
    assert head.count("65세 이상 1인세대") == 2 and head.count("청년 1인세대") == 2
    assert "19~24세" not in head
    # 엑셀 파일 · 한 주제 표 · 사용자가 고른 열은 그대로
    assert t.header[2].startswith("65세 이상 1인세대")
    one = table.build(("youth",), "강남구", ["개포3동"], JsonDongData())
    assert table.chat_view(one, alone=True) == (one, table.CHAT_COLS)
    picked = table.pick(t, "열은 동, 청년 1인세대, 65세 이상 1인세대만")
    assert table.chat_view(picked, alone=True)[0] is picked
    # 데스크가 혼자 칸을 놓쳐도 혼자 사는 어르신 주제와 함께면 청년도 1인세대 열로
    view, n = table.chat_view(t)
    head = table.markdown(view, max_cols=n).splitlines()[0]
    assert head.count("청년 1인세대") == 2
    # 혼자 사는 분과 상관없는 두 주제면 주제마다 앞 열(나이 구간은 뒤로)
    t = table.build(("youth", "senior_hall"), "강남구", ["개포3동"], JsonDongData())
    view, n = table.chat_view(t)
    head = table.markdown(view, max_cols=n).splitlines()[0]
    assert "청년(19~34세)" in head and "19~24세" not in head and "경로당 수" in head


def test_fixed_prompts_use_the_one_hour_cache():
    # 10-30 팀장 '왜 오래 걸려?' · '캐시부터': 5분 넘게 쉬면 첫 질문이 지시문을 다시 써 10초 —
    # 데스크 · 글쓴이 · 계산 계획 지시문은 1시간 캐시
    from src.assistant import llm
    from src.assistant.desk import ClaudeDesk
    from src.assistant.query import ClaudePlanner
    from src.assistant.writer import ClaudeWriter

    s = AssistantSettings(anthropic_api_key="")
    assert llm.CACHE_1H == {"type": "ephemeral", "ttl": "1h"}
    assert ClaudeDesk(s)._kwargs("x")["system"][-1]["cache_control"] == llm.CACHE_1H
    assert ClaudePlanner(s, llm.Usage())._kwargs("x")["system"][0]["cache_control"] == llm.CACHE_1H
    kw, _, _ = ClaudeWriter(s)._request("질문", [])
    assert kw["system"][0]["cache_control"] == llm.CACHE_1H
