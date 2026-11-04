"""10-25 페르소나 8명 CLI 판(cli1)에서 나온 일곱 가지 — 다시 생기지 않게.

팀장(10-25): "비서 문제들 싹다 고쳐줘."
"""

from src.assistant import checks, librarian, table
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import (
    FAMILY_LINE,
    ROSTER_LINE,
    TELL_112_LINE,
    WHO_FIRST,
    Engine,
)
from src.assistant.slots import DeskCard, Slots
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()
ORIN_T6 = (
    "춘천 비교가 안 되면 할 수 없죠. 그럼 강남구 22개 동만이라도 동별 숫자를 표로 주세요. "
    "동 이름, 취약 돌보미 동 순위, 혼자 사는 어르신 수, 진단, 취약 돌보미 판단 정도면 됩니다. 설명은 빼고 표만요."  # noqa: E501
)
ORIN_T7 = (
    "제가 부탁한 대로 동 이름, 취약 돌보미 동 순위, 65세 이상 1인세대 2026-09, 진단(해당 신호 수), "
    "취약 돌보미 판단(겹친 걱정 수) 다섯 열만으로 다시 주세요. 그리고 아래 합계에 '위험 구간 66'처럼 "  # noqa: E501
    "더하면 안 되는 걸 더해 놓으셨는데, 그건 빼 주세요. 표만요."
)
NOEL_T4 = (
    "요청한 열이 빠졌습니다. 동 · 19~24세 · 25~29세 · 30~34세 · 청년 1인세대 2025-09 · 2026-09 · "
    "1년 증감(명) 7개 열 전부 들어간 엑셀로 다시 주세요."
)
ELDER = ("priority", "solo_seniors", "diagnosis")


# ① 표 열 고르기
def test_column_list_before_the_word_or_without_it_is_read():
    t = table.pick(table.build(ELDER, "강남구", [], DATA), ORIN_T6)
    assert t.header[2:] == [
        "취약 돌보미 동 순위",
        "65세 이상 1인세대 2026-09",
        "진단",
        "겹친 걱정 수(취약 돌보미 판단, 어르신)",
    ]
    # 많은 순 · 적은 순을 말하지 않았고 순위 열이 있으면 순위 차례로
    assert [r[2] for r in t.rows[:3]] == [1, 2, 3]


def test_bracketed_column_name_and_other_sentence_are_handled():
    t = table.pick(table.build(ELDER, "강남구", [], DATA), ORIN_T7)
    assert t.header[2:] == [
        "취약 돌보미 동 순위",
        "65세 이상 1인세대 2026-09",
        "해당 신호 수",
        "겹친 걱정 수(취약 돌보미 판단, 어르신)",
    ]  # '위험 구간 66처럼 빼 주세요'(다른 문장)의 열은 고르지 않는다


def test_tail_of_column_name_and_date_only_piece():
    t = table.pick(table.build(("youth",), "강남구", [], DATA), NOEL_T4)
    assert t.header[2:] == [
        "19~24세",
        "25~29세",
        "30~34세",
        "청년 1인세대 2025-09",
        "청년 1인세대 2026-09",
        "청년 1인세대 1년 새 증감(명)",
    ]


def test_band_and_overlaps_are_not_summed_and_cut_columns_are_said():
    t = table.build(ELDER, "강남구", [], DATA)
    total = next((x for x in t.footer if x.startswith("합계(")), "")
    assert "위험 구간" not in total and "겹친 걱정" not in total and "자원 공백" not in total
    md = table.markdown(t)
    # 안 보인 열을 말없이 자르지 않는다(10-25) — 10-29부터 이름 셋 + '외 N개'로 짧게
    assert "(안 보인 열:" in md and "열도 보여 줘" in md and " 외 " in md


# ② 두 지역 견줌
def test_both_regions_get_facts_and_same_yardstick():
    s = Slots(region="강남구", compare=True)
    asked = "강남구 22개 동이랑 춘천시 25개 읍면동 비교하면 어디가 더 심각합니까?"
    fs = librarian.gather_all(("priority",), s, DATA, asked)
    text = "\n".join(x for f in fs for x in f.lines)
    assert "강남구 취약 돌보미 동 순위" in text and "춘천시 취약 돌보미 동 순위" in text
    two = fs[-1]
    assert two.title.startswith("두 지역 나란히") and len(two.lines) == 2
    assert any("자료가 없다'고 하지 않는다" in n for n in two.notes)


# ③ 계획 줄
def test_plan_line_is_removed_but_plain_sentence_kept():
    a = "ㅡ질문은 두 가지다: 1인세대 수인지, 어림 범위.\n\n네, 242명은 주민등록상 1인세대 수예요."
    assert checks.tidy(a) == "네, 242명은 주민등록상 1인세대 수예요."
    b = "네, 질문은 두 가지예요. 하나씩 볼게요."
    assert checks.tidy(b) == b


# ④ 막기 답 속 곁물음
def test_side_questions_are_answered_before_the_block():
    t7 = (
        "1566-3232에 전화하면 어떻게 되는지 물어본 거잖아요. 기관 회원은 권한 확인하면 담당 대상자 "
        "명단 같은 거 볼 수 있는 기능 없나요? 112에 뭐라고 말하면 돼요?"
    )
    t9 = "사실 제가 먼 친척이에요. 가족이면 연락처나 주소 확인되는 거 아닌가요?"
    desk = FakeDesk({t: DeskCard(act="blocked", block="person") for t in (t7, t9)})
    e = Engine(desk, TemplateWriter(), DATA, MemoryStore(), AssistantSettings(anthropic_api_key=""))
    e.start("s", Profile(member_region="강남구", member_dong="수서동"))
    r = e.turn("s", t7)
    assert r.kind == "blocked"
    assert "응급안전안심서비스 중앙모니터링센터" in r.text and "취약 돌보미 자료에 없어요" in r.text
    assert TELL_112_LINE in r.text and ROSTER_LINE in r.text
    assert FAMILY_LINE in e.turn("s", t9).text


# ⑤ 청년 어림의 방법
def test_youth_method_numbers_only_when_asked():
    s = Slots(region="강남구", dongs=("역삼1동",), target="청년")
    asked = "역삼1동 어림 430~650명이 어떤 숫자에서 나왔는지 계산식과 나이별 비율 알려 주세요"
    lines = librarian.gather("youth", s, DATA, asked).lines
    joined = "\n".join(lines)
    assert "19~24세 5.6%" in joined and "전국 발표 비율 5.2%" in joined
    assert "강남구 구 전체 어림" in joined and "배수 1.08" in joined
    plain = "\n".join(librarian.gather("youth", s, DATA, "역삼1동 청년은?").lines)
    assert "어림 — 방법" not in plain
    # 옛 설명('전국 나이별 비율 × 이 동 나이 구성')은 실제 계산과 달랐다
    assert "나이별 비율을 이 동 나이 구성에 맞춰 곱한" not in plain


# ⑥ '먼저 살필 무리'는 누구부터 볼지 물을 때만
def test_who_first_words():
    assert WHO_FIRST.search("연휴 전에 누구부터 연락하면 좋을까요?")
    assert WHO_FIRST.search("어디부터 가 봐야 해?")
    assert not WHO_FIRST.search("다음 긴 연휴가 언제예요?")


# ⑦ 동 밖의 가장 가까운 문 연 약국
def test_nearest_open_pharmacy_outside_the_dong():
    # 데스크는 때 칸에 말 그대로('일요일')를 넣는다. 날짜를 박아 두면 그날이 지나 깨진다(10-26 0시)
    for period in ("일요일", "이번 주 일요일"):
        s = Slots(region="춘천시", dongs=("신북읍",), period=period)
        rows = librarian.gather(
            "places", s, DATA, "일요일에 신북읍 말고 제일 가까운 문 연 약국"
        ).lines
        line = next(x for x in rows if "문 여는 가장 가까운 약국" in x)
        assert "(일)" in line and "읍 밖 포함" in line and "신사우동" in line


def test_weekday_words_become_dates():
    from datetime import date

    mon = date(2026, 10, 26)  # 월요일
    when = librarian._when
    assert when("일요일", mon)[0] == "2026-11-01"  # 돌아오는 일요일
    assert when("다음 일요일", mon)[0] == "2026-11-01"
    assert when("이번 주 일요일", mon)[0] == "2026-11-01"
    assert when("다음 주 일요일", mon)[0] == "2026-11-08"
    assert when("지난 일요일", mon)[0] == "2026-10-25"
    assert when("지난주 금요일", mon)[0] == "2026-10-23"
    assert when("월요일", mon)[0] == "2026-10-26"  # 오늘이 그 요일이면 오늘
    assert when("2026-11-03", mon)[0] == "2026-11-03"
    assert when("12월 31일", mon)[0] == "2026-12-31"  # 전과 같음
    assert when("", mon) == ("2026-10-26", "오늘")


# ② 뒤(cli2 오린 T4 ~ T5): 우열을 말하지 않는다는 문장은 검사에 걸리지 않고, 취약 돌보미 판단은 한
#        번만
def test_negated_comparison_is_not_a_claim_and_outlook_once():
    from src.assistant import outlook_text

    s = Slots(region="강남구", target="어르신", compare=True)
    asked = "강남과 춘천 중 어디가 더 심각합니까? 결론만 한 줄로요."
    fs = librarian.gather_all(("outlook",), s, DATA, asked)
    assert [f.title for f in fs].count(fs[0].title) == 1
    ok = "강남구와 춘천시 중 어느 쪽이 더 심각하다고 가를 수 없어요."
    bad = "춘천시 어르신들이 더 심각해요."
    assert not outlook_text.claims(ok, fs) and outlook_text.claims(bad, fs)


# ① 뒤(cli3 오린 T7 · T8 · T10): 다른 주제의 열 · 열 하나 · 같은 몫이 둘로
def test_named_column_from_other_topic_and_single_column():
    t7 = "열은 동 이름 / 취약 돌보미 동 순위 / 위험 구간 / 고립 신호 해당 수, 이렇게요."
    topics = table.with_named_topics(("priority",), t7)
    assert "diagnosis" in topics or "solo_seniors" in topics
    t = table.pick(table.build(topics, "강남구", [], DATA), t7)
    assert any("해당 신호 수" in h for h in t.header) and "취약 돌보미 동 순위" in t.header
    t10 = "'동 / 해당 신호 수' 두 열만 달라고 했는데 또 같은 8열 표가 왔네요."
    topics = table.with_named_topics(("priority",), t10)
    t = table.pick(table.build(topics, "강남구", [], DATA), t10)
    assert len(t.header) == 3 and "해당 신호 수" in t.header[2]


def test_alone_share_is_the_same_everywhere():
    s = Slots(region="강남구", dongs=("논현2동",))
    lines = "\n".join(librarian.gather("priority", s, DATA, "논현2동 순위 까닭").lines)
    t = table.build(("solo_seniors",), "강남구", ["논현2동"], DATA)
    k = t.header.index("65세 이상 중 혼자 사는 몫(%)")
    assert f"혼자 사는 몫 {t.rows[0][k]}%" in lines
