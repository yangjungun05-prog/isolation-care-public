"""API 길 회귀(10-27 multi_hard_8 api9)에서 찾은 둘.

- H7: 글쓴이 안내('[알아들은 것]이 있으면 답을 …로 시작한다')를 말로 풀어 답 첫 줄에 냄
- H5: 읍 · 면을 먼저 거른 뒤 마을 조건에 맞는 곳이 0곳인데 첫 문장에 '많은 곳은 동면과 동내면'
"""

import json
from pathlib import Path

from src.assistant import checks
from src.assistant import query as Q
from src.assistant.data_source import JsonDongData

DATA = JsonDongData()
PEOPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "public" / "people.json").read_text(
        encoding="utf-8"
    )
)["dongs"]

LEAK = (
    '[알아들은 것] 항목이 있으므로 "강남구 동 중 위험 구간이 5인 동만 골라, '
    "경로당 수가 적은 순으로 "
    '3곳으로 알아들었어요."로 시작한다.\n\n그중 위 3곳은 다음과 같아요.\n· 논현1동: 4곳'
)


def test_leaked_start_instruction_keeps_only_the_quoted_line():
    out = checks.tidy(LEAK)
    assert out.startswith("강남구 동 중 위험 구간이 5인 동만 골라")
    assert "시작한다" not in out and "항목이 있으므로" not in out
    assert "논현1동: 4곳" in out


def test_ordinary_sentences_with_start_word_stay():
    for s in (
        "올해 사업은 1월로 시작해요.",
        "수서동은 2,543명이에요. 이 숫자로 시작한다면 좋아요.",
    ):
        assert checks.tidy(s) == s


def test_village_zero_match_says_towns_only_met_first_condition():
    plan = Q.Plan(
        region="춘천시",
        kind="읍면만",
        conds=(
            Q.Cond(metric="solo65", op="많음"),
            Q.Cond(metric="v_bus", op="이하", value=0),  # 하루 0번 이하 — 맞는 마을이 없다
        ),
    )
    res = Q.run(plan, DATA, PEOPLE)
    assert res.matched == []
    concl = [x for x in res.lines if x.startswith("[결론]")]
    assert concl and "조건을 모두 맞는 마을은 없음" in concl[0]
    assert "앞 조건(읍 · 면)만" in concl[0]


def test_health_facility_words_add_places():
    """qbank P2-26: '4. 가까운 보건지소'에 데스크가 갈 곳을 빠뜨림 → 코드가 더한다."""
    from src.assistant import policy
    from src.assistant.slots import DeskCard

    card = DeskCard(act="ask", topics=("dong_overview", "solo_seniors", "bus"))
    text = (
        "1. 동면이 춘천에서 어떤 편인지 2. 80세 이상 혼자 사는 분 3. 버스 드문 마을 "
        "4. 가까운 보건지소"
    )
    assert "places" in policy.rescue_topics(card, text).topics
    for t in ("북산면 보건지소 전화 알려 줘", "근처 병원 어디야", "보건소 어디 있어?"):
        assert "places" in policy.rescue_topics(DeskCard(act="ask", topics=("youth",)), t).topics
    # 보건 시설 말이 없으면 더하지 않는다
    plain = policy.rescue_topics(DeskCard(act="ask", topics=("youth",)), "효자2동 청년은?")
    assert plain.topics == ("youth",)


def test_excel_format_needs_table_words_in_this_message():
    """qbank P2-26: 앞 턴 'csv로'에 끌려 표 말이 없는 번호 질문에도 엑셀 칸 → 답으로 되돌린다."""
    from src.assistant import policy
    from src.assistant.slots import DeskCard

    card = DeskCard(act="ask", topics=("solo_seniors",), fmt="엑셀")
    fixed, _ = policy.desk_sanity(card, "1. 동면이 춘천에서 어떤 편인지 2. 80세 이상 혼자 사는 분")
    assert fixed.fmt == "답"
    kept, _ = policy.desk_sanity(card, "동별 65세 이상 1인세대를 엑셀로 받을 수 있어요?")
    assert kept.fmt == "엑셀"


def test_rescued_fourth_topic_survives_preflight():
    """qbank P2-26(api11): 데스크 주제 셋 + 코드가 더한 갈 곳 → 이륙 전 체크에서 잘리지 않는다."""
    from src.assistant import policy
    from src.assistant.data_source import JsonDongData
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile, apply_card, new_state

    text = "1. 동면이 어떤 편인지 2. 80세 이상 혼자 사는 분 3. 버스 드문 마을 4. 가까운 보건지소"
    card = DeskCard(
        act="ask",
        topics=("dong_overview", "solo_seniors", "bus"),
        dong_op="set",
        dong_mentions=("동면",),
    )
    card, _ = policy.desk_sanity(card, text)
    assert card.topics[-1] == "places"
    st = new_state(Profile(member_region="춘천시"))
    plan = policy.preflight(apply_card(st, card, text), card, JsonDongData())
    assert plan.kind == "answer" and "places" in plan.topics


def test_short_answer_skips_carried_facts_when_own_facts_exist():
    """qbank P2-08(API): 검사에 걸린 기본 답에 앞 턴의 다른 동 자료 줄이 나가던 것."""
    from src.assistant.librarian import Facts
    from src.assistant.writer import short_answer

    own = Facts(title="혼자 사는 어르신", lines=["[강남구 수서동]", "65세 이상 1인세대 2,543명"])
    carry = Facts(title="앞서 답할 때 본 자료(다시 확인용)", lines=["[강남구 세곡동]", "1,873명"])
    out = short_answer([own, carry], "수서동 혼자 사는 어르신 표로")
    assert "2,543명" in out and "세곡동" not in out and "다시 확인용" not in out
    # 이번 답의 자료가 없으면 앞 자료라도 보인다
    assert "1,873명" in short_answer([carry], "아까 그 숫자")
