"""판단 층(router) · 엔진 계산 길 시험(10-26). AI를 부르지 않는다(가짜 데스크 · 가짜 계획기)."""

from types import SimpleNamespace

from src.assistant import query as Q
from src.assistant import router as R
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter


def card(act="ask", topics=(), rank=False, unmet=()):
    return SimpleNamespace(act=act, topics=topics, rank=rank, unmet=unmet)


def test_signals_words():
    assert "solo80" in R.signals("춘천 면 중에 혼자 사는 80 넘은 분 제일 많은 데").concepts
    assert R.signals("춘천 면 중에 혼자 사는 80 넘은 분").subset
    # 때 '대비'(2024년 대비)는 지역과 견줌이 아니다(route_50 r1)
    assert not R.signals("2024년 대비 늘었어?").region_cmp
    assert R.signals("구 평균 대비 높은 동").region_cmp
    # 강남동(춘천)은 강남구가 아니다 — 춘천의 동으로 본다
    assert R.signals("강남동 혼자 사는 어르신").regions == ("춘천시",)


def test_decide_routes():
    d = R.decide("강남 65세 이상 천 명당 경로당 제일 적은 동 세 곳", card(topics=("senior_hall",)))
    assert d.route == "깊은 고민"
    d = R.decide("개포3동 혼자 사시는 어르신 몇 분?", card(topics=("solo_seniors",)))
    assert d.route == "바로"
    d = R.decide("안녕하세요", card(act="chitchat"))
    assert d.route == "그 밖"
    d = R.decide("제가 처음에 어디 담당이라고 했죠?", card(topics=("recall",)))
    assert d.route == "기억"
    # 앞 계산 결과 안에서 다시 거르기
    d = R.decide("그 중에 약국 10곳 넘는 데는?", card(topics=("places",)), has_prev_calc=True)
    assert d.route == "깊은 고민"
    # 앞 계산이 없으면 '그 중에'만으로 계산하지 않는다
    d = R.decide("그 중에 약국 10곳 넘는 데는?", card(topics=("places",)), has_prev_calc=False)
    assert d.route != "깊은 고민" or d.sig.concepts


def test_check_flags_missing_concept():
    sig = R.signals("반지하 많고 혼자 사는 할머니 많은 동")
    p = Q.Plan(conds=(Q.Cond(metric="basement_old", op="많음"),))
    assert R.check(p, sig)  # 할머니(lonely_female)를 빠뜨림
    p2 = Q.Plan(
        conds=(Q.Cond(metric="basement_old", op="많음"), Q.Cond(metric="lonely_female", op="많음"))
    )
    assert not R.check(p2, sig)


class FakePlanner:
    def __init__(self, plan):
        self.p = plan
        self.asked: list[str] = []

    def plan(self, question, region, context=""):
        self.asked.append(question)
        return self.p


def test_engine_calc_path_and_follow_up():
    say1 = "강남 65세 이상 천 명당 경로당 제일 적은 동 세 곳"
    say2 = "그 중에 약국 10곳 넘는 데는?"
    table = {
        say1: DeskCard(act="ask", topics=("senior_hall",)),
        say2: DeskCard(act="ask", topics=("places",)),
    }
    first = Q.Plan(sort=Q.Ref(metric="halls", per="pop65", scale=1000), order="적은 순", limit=3)
    small = FakePlanner(first)
    s = AssistantSettings(anthropic_api_key="")
    e = Engine(FakeDesk(table), TemplateWriter(), JsonDongData(), MemoryStore(), s, planner=small)
    e.start("c1", Profile(member_region="강남구"))
    r = e.turn("c1", say1)
    assert small.asked == [say1]
    assert r.state.last_calc[:3] == ("일원1동", "압구정동", "개포1동")  # 코드가 센 값(calc_27 C17)
    small.p = Q.Plan(use_prev=True, conds=(Q.Cond(metric="pharmacies", op="이상", value=10),))
    r = e.turn("c1", say2)
    assert small.asked[-1] == say2
    assert set(r.state.last_calc) <= {"일원1동", "압구정동", "개포1동"}


def test_engine_without_planner_is_unchanged():
    say = "강남 65세 이상 천 명당 경로당 제일 적은 동 세 곳"
    e = Engine(
        FakeDesk({say: DeskCard(act="ask", topics=("senior_hall",))}),
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        AssistantSettings(anthropic_api_key=""),
    )
    e.start("c2", Profile(member_region="강남구"))
    r = e.turn("c2", say)
    assert r.kind == "answer" and r.state.last_calc == ()


def test_big_planner_only_when_check_fails():
    say = "반지하 많고 혼자 사는 할머니 많은 동"
    weak = FakePlanner(Q.Plan(conds=(Q.Cond(metric="basement_old", op="많음"),)))
    strong = FakePlanner(
        Q.Plan(
            conds=(
                Q.Cond(metric="basement_old", op="많음"),
                Q.Cond(metric="lonely_female", op="많음"),
            )
        )
    )
    e = Engine(
        FakeDesk({say: DeskCard(act="ask", topics=("housing", "seoul_lonely"), rank=True)}),
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        AssistantSettings(anthropic_api_key=""),
        planner=weak,
        planner_big=strong,
    )
    e.start("c3", Profile(member_region="강남구"))
    e.turn("c3", say)
    assert weak.asked == [say] and strong.asked == [say]


def test_planners_off():
    assert Q.planners(AssistantSettings(anthropic_api_key="", calc_on=False), None) == {}


def test_planner_says_not_calc_falls_back():
    say = "순위랑 진단이랑 살핌 판단 중에 보고서엔 뭘 써?"
    p = FakePlanner(Q.Plan(need="바로"))
    e = Engine(
        FakeDesk({say: DeskCard(act="ask", topics=("priority", "diagnosis"), rank=True)}),
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        AssistantSettings(anthropic_api_key=""),
        planner=p,
        planner_big=FakePlanner(Q.Plan(need="계산")),
    )
    e.start("c4", Profile(member_region="강남구"))
    r = e.turn("c4", say)
    assert r.kind == "answer" and r.state.last_calc == ()
    assert not any(f.title == "여러 조건 계산" for f in r.facts)


def test_persona_fixes_1026():
    """10-26 페르소나 6명에서 찾은 길 문제(c04 T2 · c06 T2)."""
    d = R.decide(
        "강남이랑 춘천 중에 혼자 사는 어르신 비율 어디가 더 높아?", card(topics=("solo_seniors",))
    )
    assert d.route == "깊은 고민"
    d = R.decide("위 3곳만 표로 다시 정리해 줘", card(topics=("solo_seniors",)), has_prev_calc=True)
    assert d.route == "깊은 고민"
    assert R.signals("45.6÷8.1이면 5.63 아냐?").strong


def test_listed_female_is_a_concept_1028():
    """10-28 p09: 쉼표 나열 속 단독 '여성'도 개념(계획기가 빼면 검사에 걸림). '여성 청년'은 아님."""
    t = "강남구에서 80세 이상, 여성, 혼자 사는, 기초수급, 반지하가 모두 많은 동이 어디예요?"
    assert "lonely_female" in R.signals(t).concepts
    assert "lonely_female" not in R.signals("여성 청년 많은 동").concepts
    p = Q.Plan(
        conds=(
            Q.Cond(metric="lonely80", op="많음"),
            Q.Cond(metric="lonely_poor", op="많음"),
            Q.Cond(metric="basement_old", op="많음"),
        )
    )
    assert any("lonely_female" in x for x in R.check(p, R.signals(t)))
