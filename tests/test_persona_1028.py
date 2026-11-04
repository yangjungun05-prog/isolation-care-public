"""10-27 밤 페르소나 4명(h01 · h02 · s01 · s02, Haiku · Sonnet 사용자 역)에서 찾은 것."""

from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.outlook_text import BRIEF_TAIL
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()


def _engine(table):
    e = Engine(FakeDesk(table), TemplateWriter(), DATA, MemoryStore(), AssistantSettings())
    e.start("s", Profile(member_region="춘천시", member_dong="신북읍"))
    return e


def test_evidence_hint_only_once_per_session():
    # h01 T8: '매번 붙는 근거 보여 줘 문장은 귀찮다 · 이제 빼줘'
    card = DeskCard(act="ask", topics=("outlook",), dong_op="set", dong_mentions=("신북읍",))
    e = _engine(
        {
            "신북읍 어르신들 잘 지내?": card,
            "효자2동은?": card.model_copy(update={"dong_mentions": ("효자2동",)}),
        }
    )
    first = e.turn("s", "신북읍 어르신들 잘 지내?")
    assert BRIEF_TAIL in first.text and e.store.load("s").tail_shown
    second = e.turn("s", "효자2동은?")
    assert second.kind == "answer" and BRIEF_TAIL not in second.text


def test_overlap_question_on_other_topic_gets_the_rule():
    # s01 T2: '왜 겹친 걱정은 없다고 하나요?'를 순위 주제로 받아 '기준은 자료에 없다'
    from src.assistant import conditions as C

    q = "개포3동이 독거 비율 2번째인데 왜 겹친 걱정은 없다고 하나요?"
    card = DeskCard(act="ask", topics=("priority",), dong_op="set", dong_mentions=("개포3동",))
    e = Engine(FakeDesk({q: card}), TemplateWriter(), DATA, MemoryStore(), AssistantSettings())
    e.start("s", Profile(member_region="강남구"))
    r = e.turn("s", q)
    assert any(C.OVERLAP_RULE in x for f in r.facts for x in f.lines)


def test_rank_glossary_is_region_specific():
    # s02 T7 · T8: '외출 모습'이 춘천 순위 기준에 들어가는지 오락가락
    from src.assistant.librarian import GLOSSARY

    line = dict(GLOSSARY)["취약 돌보미 동 순위"]
    assert "춘천에는 생활인구 자료가 없어 외출 모습은 넣지 않음" in line


def test_numbered_dong_the_desk_left_out_is_checked():
    # 짓궂은 시험 T15 '역삼3동 어르신': 데스크가 동을 칸에 안 넣어 앞 동 숫자로 답했다
    from src.assistant.state import NUMBERED_DONG

    assert NUMBERED_DONG.findall("역삼3동은 어때요? 개포1동이랑") == ["역삼3동", "개포1동"]
    assert NUMBERED_DONG.findall("101동 3층") == []
    keep = DeskCard(act="ask", topics=("solo_seniors",))
    first = DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("삼성1동",))
    e = Engine(
        FakeDesk({"삼성1동 어르신": first, "역삼3동 어르신": keep}),
        TemplateWriter(),
        DATA,
        MemoryStore(),
        AssistantSettings(),
    )
    e.start("s", Profile(member_region="강남구"))
    e.turn("s", "삼성1동 어르신")
    r = e.turn("s", "역삼3동 어르신")
    assert r.kind == "unknown_dong" and "역삼3동" in r.text


def test_visit_order_gets_village_facts_and_no_facility_advice():
    # h01 T5: '오늘 어디부터 들르면 좋냐? 한곳만'에 자료에 없는 '행정복지센터부터 들러 보세요'
    q = "오늘 신북읍에서 어디부터 들르면 좋냐? 한곳만"
    card = DeskCard(
        act="ask", topics=("outlook", "places"), dong_op="set", dong_mentions=("신북읍",)
    )
    e = _engine({q: card})
    r = e.turn("s", q)
    vf = [f for f in r.facts if f.title.startswith("방문 순서를 물음")]
    assert vf and any("천전리 187채" in x for x in vf[0].lines)
    assert any("버스가 드문 마을" in x for x in vf[0].lines)
    assert "시설에 들르라고 권하지 않는다" in vf[0].notes[0]
