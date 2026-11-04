"""변수 3개 시험(10-29 새벽, 팀장 '한 번의 테스트에 3개의 변수를 쑤시듯이')에서 찾아 고친 것.

1판 120건 중 bad 31(심사 뒤 원문 확인) — 여러 가지를 한 번에 묻는 말 · 다루지 않는 지역을 함께 물은
말 · 앞 답의 'N위' · 엑셀 '보내 주세요' · 줄 세우기와 동을 함께 물은 말.
"""

from src.assistant import librarian as L
from src.assistant.data_source import JsonDongData
from src.assistant.engine import ranks_in
from src.assistant.policy import (
    TABLE_FILE,
    desk_sanity,
    dongs_in_text,
    out_of_area_note,
    part_topics,
    preflight,
)
from src.assistant.slots import DeskCard, Slots
from src.assistant.state import Profile, apply_card, new_state

DATA = JsonDongData()


def test_excel_send_is_a_file_ask():
    # c01_052 '엑셀 파일로 보내 주시기 바랍니다'
    assert TABLE_FILE.search("동별로 정리하여 엑셀 파일로 보내 주시기 바랍니다")
    assert not TABLE_FILE.search("엑셀로 열어 보면 깨져요")


def test_rank_keeps_one_topic_per_target():
    st = new_state(Profile(member_region="강남구"))
    card = DeskCard(act="ask", topics=("solo_seniors", "youth", "priority"), rank=True)
    plan = preflight(apply_card(st, card, "고립 어르신과 고립 청년 자료를 동별로"), card, DATA)
    assert plan.topics[:3] == ("solo_seniors", "youth", "priority")


def test_rank_with_named_dong_also_gives_that_dong():
    # c01_032 '압구정동 경로당 몇 개임? 거기 포함해서 강남구에서 경로당 많은 동 상위 3곳도'
    f = L.gather("senior_hall", Slots(region="강남구", dongs=("압구정동",), rank=True), DATA)
    text = "\n".join(f.lines)
    halls = len(DATA.places("압구정동")["halls"]["list"])
    assert "[강남구 압구정동]" in text and f"경로당 {halls}곳" in text


def test_part_topics_fill_missing_topics():
    # c01_039 '일원본동 고립 어르신 1년 새 늘었어 줄었어? … 주민센터 신청창구 전화번호도'
    card = DeskCard(act="ask", topics=("places",))
    said = "일원본동 고립 어르신 1년 새 늘었어 줄었어? 그리고 주민센터 신청창구 전화번호도 같이"
    got = part_topics(card, said)
    assert "solo_seniors" in got.topics and "support" in got.topics
    # 한 마디뿐이면 그대로 · 자기소개의 주민센터는 주제가 아니다
    assert part_topics(card, "수서동 약국 어디예요").topics == ("places",)
    intro = "강남구 주민센터 복지 담당자입니다. 수서동 약국 어디예요?"
    assert "support" not in part_topics(card, intro).topics


def test_other_place_does_not_hide_our_dong():
    # c01_016 · c01_023 · c01_037: 다루지 않는 지역이 섞이면 우리 동까지 못 읽고 그 부분을 말없이 뺌
    assert dongs_in_text("수서동 경로당이랑 부산 경로당도 알려줘") == ["수서동"]
    assert dongs_in_text("부산 서면 쪽은요?") == []
    note = out_of_area_note("수서동 경로당이랑 원주 경로당도 알려줘")
    assert "원주" in note and "다루지 않는 지역" in note
    card = DeskCard(act="ask", topics=("senior_hall",))
    got, _ = desk_sanity(card, "수서동 경로당이랑 부산 경로당 몇 개야")
    assert got.dong_mentions == ("수서동",)


def test_nth_follows_ranking_shown_in_last_answer():
    # c01_028 · c01_102: '그 순위 3위 동'을 취약 돌보미 3위(논현2동)로 잡음
    last = (
        "강남구 80세 이상 1인세대 많은 동: 1위 수서동 595명 · 2위 세곡동 592명 · 3위 압구정동 333명"
    )
    assert ranks_in(last)[3] == "압구정동"
    assert ranks_in("· 일원1동: 1,285명(22곳 중 3위)\n· 논현1동: 891명(22곳 중 7위)") == {
        3: "일원1동",
        7: "논현1동",
    }


def test_claim_notes_catch_wrong_user_numbers_and_ranks():
    # c01_018 '우리동 1인세대 어르신 300명이라고 하셨죠?'(707명)
    # c01_053 '3위동이라던데 맞나'(16위)
    from src.assistant import checks

    facts = "[강남구 대치2동]\n- 65세 이상 1인세대: 642명 → 707명"
    got = checks.claim_notes("우리동 1인세대 어르신 300명이라고 하셨죠?", facts, ["대치2동"])
    assert got and "명 수는 [자료]에 없는 값" in got[0] and "300" not in got[0]
    assert not checks.claim_notes("707명이라고 하셨죠?", facts, ["대치2동"])
    rank = "강남구 취약 돌보미 동 순위 전체(22곳): 1위 개포3동 · 16위 도곡1동"
    got = checks.claim_notes("우리동이 3위동이라던데 맞나", rank, ["도곡1동"])
    assert got and "'네'로 시작하지" in got[0]
    assert not checks.claim_notes("16위라던데 맞나", "도곡1동 16위", ["도곡1동"])


def test_lost_contact_without_spaces_is_urgent():
    # c01_015 '이틀째 연락이안돼서 맘이 급합니다'
    from src.assistant.engine import LOST_CONTACT_SQ, URGENT_SQ

    sq = "지금담당하는한분이이틀째연락이안돼서맘이급합니다"
    assert LOST_CONTACT_SQ.search(sq) and URGENT_SQ.search(sq)
    assert not LOST_CONTACT_SQ.search("이틀째비가와서경로당몇곳인지")


def test_part_topics_read_solo_household_words():
    # c01_018: '1인세대 어르신'이 주제 단서에 없었다
    card = DeskCard(act="ask", topics=("sources",))
    got = part_topics(card, "우리동 1인세대 어르신 300명이라고 하셨죠? 그숫자 어림잡은거에요")
    assert "solo_seniors" in got.topics


def test_bus_facts_give_daily_total():
    # c01_019 · c01_078 '하루 버스 total 몇 회': 노선 하나를 합계처럼 · '합계는 자료에 없다'
    f = L.gather("bus", Slots(region="춘천시", dongs=("사북면",)), DATA)
    text = "\n".join(f.lines)
    b = DATA.bus("사북면")
    total = sum(r["per_day"] for r in b["routes"] if r["per_day"] is not None)
    assert f"하루 횟수를 더하면 약 {total}번" in text


def test_nth_town_by_metric_and_mixed_sex_note(tmp_path):
    # c01_038 '춘천 읍면 중에 고립 어르신 많은 순위 3위 동네' → 읍 · 면만 줄 세운 3위
    from src.assistant import query as Q
    from src.assistant.config import AssistantSettings
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import Engine
    from src.assistant.policy import disclose
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    said = "춘천 읍면 중에 고립 어르신 많은 순위 3위 동네 버스 몇 번 다녀?"
    card = DeskCard(act="ask", topics=("solo_seniors", "bus"), region_op="set", region="춘천시")
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({said: card}), TemplateWriter(), DATA, MemoryStore(), s)
    e.start("x", Profile(member_region="강남구", member_dong="개포2동"))
    r = e.turn("x", said)
    order = Q.run(Q.Plan(region="춘천시", sort=Q.Ref(metric="solo65"), limit=25), DATA).matched
    towns = [d for d in order if d.endswith(("읍", "면"))]
    assert r.state.slots.dongs == (towns[2],)
    # c01_051 두 지역 동의 할머니 → 지역마다 밝힘
    note = disclose(
        DeskCard(), Slots(dongs=("개포2동", "후평1동"), sex="여"), [], ("solo_seniors",)
    )
    assert "강남 동" in note and "춘천 동" in note


def test_short_spelled_number_dong_resolves():
    # c01_017 '개포삼 주민센터 복지 신청창구 전화번호'
    from src.assistant import dongname

    assert dongname.resolve("개포삼")["dongs"] == ["개포3동"]
    assert dongname.resolve("석사")["dongs"] == ["석사동"]


def test_past_year_gangnam_solo_adds_seoul_yearly(tmp_path):
    # c01_085 '논현1동 2020년 기준 고립 어르신'(서울시 현황에 2020년 606명)
    st = new_state(Profile(member_region="강남구"))
    card = DeskCard(
        act="ask",
        topics=("solo_seniors",),
        dong_op="set",
        dong_mentions=("논현1동",),
        period_op="set",
        period="2020년",
    )
    plan = preflight(apply_card(st, card, "논현1동 2020년 기준 고립 어르신은 몇 분"), card, DATA)
    assert "seoul_lonely" in plan.topics


def test_hall_sum_uses_latest_counts():
    # c01_097 '개포1 · 2 · 3동 경로당 total 최신 기준'(글쓴이가 2022년 곳 수로 13을 더함)
    names = ("개포1동", "개포2동", "개포3동")
    f = L.gather("senior_hall", Slots(region="강남구", dongs=names), DATA)
    total = sum(len(DATA.places(n)["halls"]["list"]) for n in names)
    assert any(f"경로당 · 마을회관 {total}곳" in x and "합계" in x for x in f.lines)


def test_lost_contact_with_data_ask_answers_both(tmp_path):
    # c01_110 '대치2동 기초수급자 몇명이에여? 거기 수급자 한분이 며칠째 연락이 안되서 맘이 급한데
    #       일단 숫자부터' → 안부 확인 안내 + 자료 답
    from src.assistant.config import AssistantSettings
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import URGENT_NOTE, Engine
    from src.assistant.policy import person_free_rest
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    said = "대치2동 기초수급자 몇명이에여? 거기 수급자 한분이 며칠째 연락이 안되서 맘이 급한데"
    rest = person_free_rest(said)
    assert rest == "대치2동 기초수급자 몇명이에여"
    table = {
        said: DeskCard(act="blocked", block="emergency", urgent=True),
        rest: DeskCard(
            act="ask", topics=("livelihood",), dong_op="set", dong_mentions=("대치2동",)
        ),
    }
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk(table), TemplateWriter(), DATA, MemoryStore(), s)
    e.start("x", Profile(member_region="강남구"))
    r = e.turn("x", said)
    assert r.text.startswith(URGENT_NOTE) and r.kind == "answer"
    # 목숨이 걸린 말은 위기 안내만
    bad = "대치2동 수급자 몇 명이에요? 한 분이 쓰러져 계신 것 같아요"
    e2 = Engine(
        FakeDesk({bad: DeskCard(act="blocked", block="emergency", urgent=True)}),
        TemplateWriter(),
        DATA,
        MemoryStore(),
        s,
    )
    e2.start("y", Profile(member_region="강남구"))
    assert e2.turn("y", bad).kind == "blocked"


def test_both_regions_rank_answers_each_region(tmp_path):
    # c01_025 '강남구와 춘천시 각각에서 … 먼저 살펴봐야 할 순서대로'에 '어느 지역?'만 되물음
    from src.assistant.config import AssistantSettings
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import Engine
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    said = "강남구와 춘천시 각각에서 혼자 사시는 어르신이 많은 동을 순서대로 알려 주세요"
    card = DeskCard(act="ask", topics=("solo_seniors",), rank=True)
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({said: card}), TemplateWriter(), DATA, MemoryStore(), s)
    e.start("x", Profile(member_region="강남구", member_dong="대치2동"))
    e.store.save("x", e.store.load("x").model_copy(update={"slots": Slots()}))
    r = e.turn("x", said)
    text = "\n".join(x for f in r.facts for x in f.lines)
    assert r.kind == "answer" and "강남구 65세 이상" in text and "춘천시 65세 이상" in text


def test_year_said_goes_to_period_and_heard_dup_and_negated_contact():
    from src.assistant.engine import HEARD_AGAIN, LOST_CONTACT_SQ

    # c01_088 '춘천시 전체의 2020년 기준 65세 이상 1인세대'
    card = DeskCard(act="ask", topics=("solo_seniors",))
    got, _ = desk_sanity(card, "춘천시 전체의 2020년 기준 65세 이상 1인세대가 몇 세대인지")
    assert got.period == "2020년"
    # c01_006: 글쓴이가 다시 쓴 '○○로 알아들었어요'(앞에 자음 하나)
    body = "ㅇ일원본동으로 알아들었어요. 아니면 말씀해 주세요.\n\n571명은 14%예요."
    assert HEARD_AGAIN.sub("", body).strip() == "571명은 14%예요."
    # c01_000 '며칠째 연락이 되지 않아'
    assert LOST_CONTACT_SQ.search("관내수급자한분이며칠째연락이되지않아걱정이되는데")


def test_rest_parts_split_person_intro_and_data():
    # 2판 문장 점검: '어르신이'를 걱정 단서로 넣으면 자료 마디를 빼고 인사 · 개인 마디를 남겼다
    from src.assistant import pii
    from src.assistant.policy import person_free_rest

    said = (
        "논현1동 주민센터 복지 담당자입니다. 논현1동 관내 반지하 주택에 거주하는 고립 어르신이 "
        "총 몇 분인지 숫자 하나로 회신해 주시기 바랍니다. 아울러 해당 어르신들의 성함, 호수, "
        "전화번호도 함께 알려 주시면 방문 일정 수립에 활용하겠습니다."
    )
    assert person_free_rest(pii.mask(said)[0]).startswith("논현1동 관내 반지하")
    plain = "안녕하십니까. 주민센터 복지 담당자입니다. 우리 동 고립 어르신이 몇 명인지 숫자만"
    assert person_free_rest(plain) == ""
    worry = "대치2동 지원 기관 전화번호 알려 주세요? 혼자 사시는 할머니가 3일째 연락이 안돼요"
    assert person_free_rest(worry) == "대치2동 지원 기관 전화번호 알려 주세요"


def test_claim_with_dialect_and_about():
    # c01_101 '1인세대 고립 어르신이 어림잡아 380명쯤 된다 캤는데'(어림 420 ~ 450 · 1인세대 571)
    from src.assistant import checks

    facts = (
        "[강남구 일원본동]\n- 65세 이상 1인세대: 528명 → 571명\n"
        "- 실제로 혼자 사는 어림 약 420~450명"
    )
    said = "아까 일원본동 1인세대 고립 어르신이 어림잡아 380명쯤 된다 캤는데"
    assert checks.claim_notes(said, facts, ["일원본동"])
    assert not checks.claim_notes("571명이라 했는데 맞아요?", facts, ["일원본동"])


def test_pharmacy_count_same_in_calc_and_shelf():
    # c01_099 '약국 16곳 · 18곳'이 한 답에 — 계산(상가정보)과 서가(약국 정보)의 출처가 달랐다
    from src.assistant import query as Q

    n = len(DATA.pharmacies("일원본동")["list"])
    r = Q.run(
        Q.Plan(region="강남구", dongs=("일원본동",), show=(Q.Ref(metric="pharmacies"),)), DATA
    )
    assert any(f"[일원본동] 약국 {n}곳" in x for x in r.lines)
    f = L.gather("places", Slots(region="강남구", dongs=("일원본동",)), DATA, "약국 몇 곳")
    assert any(f"약국 {n}곳" in x for x in f.lines)
