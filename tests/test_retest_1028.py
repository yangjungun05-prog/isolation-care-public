"""페르소나 재심사(10-28 저녁)에서 찾아 고친 것.

- p06_b(기자) '강남구 독거노인 고독사 위험군이 전체 몇 명': 데스크만 계산이라 보고 되묻기를
  건너뛰었는데 계획기가 계산이 아니라고 봐 자료 0줄 → 빈 답 · 영어 답 · '자료에 없다'(거짓)
- q01_b: 동 하나짜리 표의 '많은 순: 1위 역삼1동'을 받아 '증감률 1위'(22곳 중 6위)
- q04_b: '많은 순 22위'를 '22위(적은 순)'로 옮김 · '문제없는 표현입니까?'에 '네, … 맞지 않아요'
- q05_a: 계획 AI의 '엑셀 파일 자체는 만들지 않는다'가 답으로 샘 · 뒤 계산이 앞 계산 기준을 덮어씀
- q05_b: '22개 동의 평균보다 높음'을 지역 전체 값(20.1%)으로 셈(9곳) — 물은 것은 동 평균(8곳)
"""

import re

from src.assistant import checks, pii
from src.assistant import query as Q
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import EMPTY_ANSWER, Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

WHOLE = "강남구 독거노인 고독사 위험군이 전체 몇 명쯤 되는지 한 번에 말씀해 주실 수 있을까요?"
NEAR = "가까운 갈 곳 좀 알려 주세요"


class FakePlanner:
    def __init__(self, plan):
        self.p = plan

    def plan(self, question, region, context=""):
        return self.p


def _engine(tmp_path, table, plan):
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    p = FakePlanner(plan)
    e = Engine(FakeDesk(table), TemplateWriter(), JsonDongData(), MemoryStore(), s, planner=p)
    e.start("x", Profile(member_region="강남구"))
    return e, p


def test_region_total_when_desk_alone_called_it_calc(tmp_path):
    card = DeskCard(
        act="ask", topics=("solo_seniors",), region_op="set", region="강남구", calc=True
    )
    e, _ = _engine(tmp_path, {WHOLE: card}, Q.Plan(need="바로"))
    r = e.turn("x", WHOLE)
    assert r.kind == "answer"
    text = "\n".join(x for f in r.facts for x in f.lines)
    data = JsonDongData()
    total = sum(data.dong(n)["solo65"]["2026-09"] for n in data.region_dongs("강남구"))
    assert f"합계: {total:,}명" in text  # 22곳을 코드가 더한 값
    # '고독사 위험군' 무리 수는 자료에 없다고 먼저 밝히게
    assert any("고독사 위험군" in n for f in r.facts for n in f.notes)


def test_lone_concept_without_rank_topic_still_asks_dong(tmp_path):
    card = DeskCard(act="ask", topics=("places",), calc=True)
    e, _ = _engine(tmp_path, {NEAR: card}, Q.Plan(need="바로"))
    r = e.turn("x", NEAR)
    assert r.kind == "ask_slot" and "어느 동" in r.text


def test_empty_answer_gets_a_sentence():
    assert EMPTY_ANSWER.startswith("그 질문에 맞는 자료를 찾지 못했어요")


def test_english_answer_is_a_problem():
    eng = "I'm sorry, but I can't provide that. The reference data does not contain figures."
    assert checks.not_korean(eng)
    assert "한국어 아님" in checks.problems(eng, "", [])
    assert not checks.not_korean("수서동 상황 PDF를 만들었어요. 강남구 기준 2026-09 판이에요.")


def test_rank_direction_flip():
    facts = "[대치1동] 서울시 독거노인 현황 2025년 245명(22곳 중 많은 순 22위)"
    bad = "245명은 강남구 22곳 중 22위(적은 순)예요."
    assert checks.rank_direction_flips(bad, facts) == ["22위(적은 순)"]
    assert any(x.startswith("순위 방향 뒤집힘") for x in checks.problems(bad, facts, []))
    # 자료나 질문에 적은 순이 있으면 그 말을 따른 것
    assert not checks.rank_direction_flips(bad, facts + " 적은 순 1위 대치1동")
    assert not checks.rank_direction_flips("22곳 중 많은 순 22위로 가장 적어요.", facts)


def test_yes_then_no_on_is_it_ok_question():
    q = "의회 발언에서 '대치1동은 독거노인이 가장 적어'라고 말하면, 자료상 문제없는 표현입니까?"
    assert checks.yes_then_no("네, 대치1동이 가장 적다는 말은 자료상 맞지 않아요. 다만 …", q)
    assert not checks.yes_then_no("네, 서울시 독거노인 현황 기준으로 그렇게 말할 수 있어요.", q)


def test_planner_restate_drops_cannot_make_file():
    got = Q.clean_restate(
        "앞 결과 4곳을 표로 나란히 보여 준다. 엑셀 파일 자체는 만들지 않는다. "
        "엑셀 파일 생성은 이 도구로 할 수 없어 표 형태로만 답함."
    )
    assert got == "앞 결과 4곳을 표로 나란히 보여 준다."


def test_dong_mean_basis():
    plan = Q.Plan(region="강남구", conds=(Q.Cond(metric="solo65_share", op="평균보다 높음"),))
    data = JsonDongData()
    whole = Q.run(plan, data)
    mean = Q.run(plan.model_copy(update={"dong_mean": True}), data)
    assert len(whole.matched) == 9 and "개포4동" in whole.matched
    assert len(mean.matched) == 8 and "개포4동" not in mean.matched
    assert "동 평균" in mean.conds[0][1] and "지역 전체 값" in whole.conds[0][1]


def test_engine_uses_dong_mean_when_said(tmp_path):
    ask = "강남구 22개 동의 평균보다 혼자 사는 몫이 높은 동은?"
    plan = Q.Plan(region="강남구", conds=(Q.Cond(metric="solo65_share", op="평균보다 높음"),))
    card = DeskCard(act="ask", topics=("solo_seniors",), region_op="set", region="강남구")
    e, _ = _engine(tmp_path, {ask: card}, plan)
    r = e.turn("x", ask)
    text = "\n".join(x for f in r.facts for x in f.lines)
    assert "동 평균" in text and "모두 8곳" in text


def test_calc_log_keeps_first_calc_basis(tmp_path):
    first = "혼자 사는 몫이 높으면서 경로당 적은 동"
    second = "1,000명당 경로당 순위로 다시 봐 주세요"
    again = "처음 고른 곳은 어떤 기준이에요?"
    card = DeskCard(act="ask", topics=("solo_seniors", "senior_hall"))
    e, p = _engine(tmp_path, {first: card, second: card, again: card}, None)
    p.p = Q.Plan(
        conds=(Q.Cond(metric="solo65_share", op="많음"), Q.Cond(metric="halls", op="적음"))
    )
    e.turn("x", first)
    p.p = Q.Plan(conds=(Q.Cond(metric="halls", per="pop65", scale=1000, op="적음"),))
    e.turn("x", second)
    p.p = Q.Plan(need="바로")
    r = e.turn("x", again)
    log = next(f for f in r.facts if f.title == "이 대화의 계산 기록")
    assert len(log.lines) == 2
    assert log.lines[0].startswith("1번째 질문의 계산")
    assert "경로당 · 마을회관 적음" in log.lines[0]
    assert log.lines[1].startswith("2번째 질문의 계산")


def test_single_dong_table_has_no_rank_line(tmp_path):
    ask = "역삼1동 혼자 사는 어르신 표로 보여 줘"
    card = DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("역삼1동",))
    e, _ = _engine(tmp_path, {ask: card}, Q.Plan(need="바로"))
    r = e.turn("x", ask)
    lines = [x for f in r.facts for x in f.lines]
    assert not any(re.search(r"많은 순: 1위 역삼1동", x) for x in lines)


def test_urgent_person_block_gives_named_dong_office(tmp_path):
    said = (
        "김말순 어르신이 이틀째 전화를 안 받으세요. 사북면에 혼자 사세요. 괜찮으신지 알 수 있나요?"
    )
    masked = said.replace("김말순", "[이름]")  # 데스크에는 가린 글이 간다
    card = DeskCard(act="blocked", block="person", urgent=True)
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({masked: card}), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    e.start("x", Profile(member_region="춘천시"))
    for _ in range(2):
        r = e.turn("x", said)
        assert r.kind == "blocked"
        assert "사북면행정복지센터" in r.text and "033-250-3609" in r.text
        assert "동 이름을 말씀해 주시면" not in r.text


def test_days_count_is_not_a_name():
    # 10-28 재심사 q06_b: '이틀째'를 이름(이씨)으로 가렸다
    assert pii.mask("엄마가 이틀째 전화를 안 받아요")[1] == []
    assert pii.mask("나흘째 소식이 없고 조만간 장보기를 도와야 해요")[1] == []
    assert pii.mask("이민수 어르신이 이틀째 안 보여요")[1] == ["이름"]


def test_complex_ask_says_no_complex_data_and_gives_dong_total(tmp_path):
    t1 = "김말순 어르신 집 주소 좀 알려 주세요"
    t2 = "개포3동 아파트 중에서 혼자 사시는 어르신이 제일 많은 단지가 어디예요?"
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({}), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    e.start("x", Profile(member_region="강남구"))
    e.turn("x", t1)  # 개인 막기 다음 턴이어도
    r = e.turn("x", t2)
    assert r.kind == "blocked"
    assert r.text.startswith("아파트 단지 · 골목처럼 동보다 작은 단위 자료는 없어")
    solo = JsonDongData().dong("개포3동")["solo65"]
    assert f"개포3동 전체로는 65세 이상 1인세대(주민등록 {max(solo)})" in r.text
    assert "한 분 한 분의 정보" not in r.text


def test_top_five_note_says_rest_exist(tmp_path):
    ask = "강남구 청년 1인세대 많은 동"
    card = DeskCard(act="ask", topics=("youth",), rank=True, region_op="set", region="강남구")
    e, _ = _engine(tmp_path, {ask: card}, Q.Plan(need="바로"))
    r = e.turn("x", ask)
    notes = [n for f in r.facts for n in f.notes]
    assert any("22곳 모두 이 값이 있다" in n for n in notes)


def test_table_edit_clauses_add_remove_move():
    from src.assistant import table, table_edit
    from src.assistant.state import TableSpec

    data = JsonDongData()
    t = table.build(("solo_seniors",), "강남구", [], data)
    h = t.header
    c25 = next(x for x in h if "1인세대 2025" in x)
    c26 = next(x for x in h if "65세 이상 1인세대 2026" in x)
    c80 = next(x for x in h if "80세" in x)
    rate = next(x for x in h if "증감률" in x)
    cap = next(x for x in h if "정원" in x)
    spec = TableSpec(region="강남구", topics=("solo_seniors",), cols=(c25, c26, c80, cap))
    # 한 말에 더하기와 빼기(q01_a T3)
    s1, notes = table_edit.apply(
        spec, h, "1년 증감률(%) 열도 추가해 주세요. 80세 이상 열은 빼 주세요.", "강남구"
    )
    assert rate in s1.cols and c80 not in s1.cols
    assert any(n.startswith("더한 열") for n in notes) and any(n.startswith("뺀 열") for n in notes)
    # 옮기기는 빼기가 아니다(q01_a T5)
    s2, _ = table_edit.apply(
        s1,
        h,
        "증감률 열을 2026-09 바로 옆으로 옮겨 주세요. 복지시설 정원 열은 빼 주세요.",
        "강남구",
    )
    assert list(s2.cols) == [c25, c26, rate]
    # 다시 넣기 · '○○ 옆에'(q01_a T6)
    s3 = s2.model_copy(update={"cols": (c25, c26)})
    s4, _ = table_edit.apply(
        s3, h, "증감률(%) 열이 빠졌어요. 2026-09 바로 옆에 다시 넣어 주세요.", "강남구"
    )
    assert list(s4.cols) == [c25, c26, rate]
    md, _, _ = table_edit.render(s2, data)
    head = md.splitlines()[0]
    assert head.index("2026-09") < head.index("증감률")


def test_unclear_dialect_with_solo_words_answers_known_dong(tmp_path):
    said = (
        "140에서 180명은 머시고 어디서 어림한거유 그람 눈 오믄 80살 넘은 혼자 사는 어른신들 "
        "리별로 어디어디 사는지 알려줘유"
    )
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({}), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    e.start("x", Profile(member_region="춘천시", member_dong="북산면"))
    r = e.turn("x", said)  # 데스크는 못 알아들음(unclear)
    assert r.kind == "answer"
    assert any("북산면" in x for f in r.facts for x in f.lines)


def test_few_dongs_called_many_is_a_problem():
    facts = "\n".join(
        [
            "[강남구 대치1동]",
            "- 강남구 22곳 중 많은 순(주민등록 2026-09): 65세 이상 1인세대 22위 · 몫 22위",
            "[강남구 삼성1동]",
            "- 강남구 22곳 중 많은 순(주민등록 2026-09): 65세 이상 1인세대 20위 · 몫 15위",
            "[강남구 수서동]",
            "- 강남구 22곳 중 많은 순(주민등록 2026-09): 65세 이상 1인세대 1위 · 몫 1위",
        ]
    )
    bad = "대치1동(253명), 삼성1동(459명)은 혼자 사는 어르신이 많은 동으로, 함께 고려해야 합니다."
    assert checks.many_few_flips(bad, facts) == ["대치1동 · 삼성1동"]
    assert any(x.startswith("많고 적음 뒤집힘") for x in checks.problems(bad, facts, []))
    assert not checks.many_few_flips("대치1동 · 삼성1동은 적은 동이에요.", facts)
    assert not checks.many_few_flips("수서동은 많은 동이에요.", facts)
    assert checks.many_few_flips("수서동은 적은 편이에요.", facts) == ["수서동"]


def test_meaning_of_many_is_in_glossary():
    from src.assistant.librarian import gather
    from src.assistant.slots import Slots

    asked = "동별 자료에서 '많음'이라는 게 정확히 어떤 기준으로 나눈 건지 알려 주세요"
    f = gather("sources", Slots(region="강남구"), JsonDongData(), asked)
    assert any("말뜻 — 많음 · 적음" in x and "3분의 1" in x for x in f.lines)


def test_calc_sheet_excel_turn_gets_only_the_sheet(tmp_path):
    first = "혼자 사는 어르신 많고 경로당 적은 동"
    xls = "이 결과를 엑셀로 받을 수 있을까요? 동 이름, 1인세대 수, 경로당 수, 순위 열로요"
    table_ = {
        first: DeskCard(act="ask", topics=("solo_seniors", "senior_hall")),
        xls: DeskCard(act="ask", topics=("solo_seniors",), fmt="엑셀"),
    }
    e, p = _engine(tmp_path, table_, None)
    p.p = Q.Plan(conds=(Q.Cond(metric="solo65", op="많음"), Q.Cond(metric="halls", op="적음")))
    e.turn("x", first)
    p.p = Q.Plan(need="바로")
    r = e.turn("x", xls)
    titles = [f.title for f in r.facts]
    assert titles[0].startswith("앞 여러 조건 계산의 전체 표")
    assert not any("코드가 동 자료에서 옮김" in t for t in titles)


def test_inner_marks_are_stripped_and_doc_download_note():
    from src.assistant.engine import DOC_DOWNLOAD_NOTE

    got = checks.tidy(
        "문서는 [직전 답]의 요약과 같고, 그 요약은 자료의 F1~F5와 맞아요. 순위(F2-F3) 7위예요."
    )
    assert got == "문서는 앞 답의 요약과 같고, 그 요약은 자료와 맞아요. 순위 7위예요."
    assert "PDF 내려받기" in DOC_DOWNLOAD_NOTE and "만들 수 없다" in DOC_DOWNLOAD_NOTE


def test_crisis_words_keep_care_line_after_emergency_repeats(tmp_path):
    from src.assistant.policy import CARE

    em = DeskCard(act="blocked", block="emergency", urgent=True)
    t1 = "이웃 할머니가 쓰러져 계신 것 같아요 문을 두드려도 대답이 없어요"
    t2 = "119 불렀는데 아직 안 와요 쓰러져 계신 것 같아요"
    t3 = "네 지금 119에 다시 전화할게요. 근데 저 진짜 너무 지쳐서요... 다 그만두고 싶다니까요"
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(
        FakeDesk({t1: em, t2: em, t3: em}), TemplateWriter(), JsonDongData(), MemoryStore(), s
    )
    e.start("x", Profile(member_region="강남구", member_dong="개포3동"))
    e.turn("x", t1)
    e.turn("x", t2)
    r = e.turn("x", t3)
    assert r.kind == "blocked"
    assert CARE in r.text  # 위급 되풀이 문장으로 바뀐 뒤에도 위기 상담 번호


def test_complex_answer_has_its_fact_line(tmp_path):
    t = "개포3동 아파트 중에서 혼자 사시는 어르신이 제일 많은 단지가 어디예요?"
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({}), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    e.start("x", Profile(member_region="강남구"))
    r = e.turn("x", t)
    solo = JsonDongData().dong("개포3동")["solo65"]
    assert r.facts and f"{solo[max(solo)]:,}명" in r.facts[0].lines[0]


def test_dong_level_count_with_worry_is_answered_not_blocked():
    from src.assistant.policy import desk_sanity

    blocked = DeskCard(act="blocked", block="person", urgent=True)
    for said in (
        "지금 밤 11시인데 혼자 사시는 할머니 한 분이 전화를 안 받으세요. "
        "일단 개포3동 혼자 사는 어르신 현황 좀 알려주세요",
        "아니 명단 말고요... 개포3동에 혼자 사는 어르신이 대략 몇 분인지요",
    ):
        card, _ = desk_sanity(blocked, said)
        assert card.act == "ask" and card.topics == ("solo_seniors",), said
    for said in (
        "개포3동 혼자 사는 할머니 주소 좀 알려 주세요",
        "개포3동 혼자 사는 어르신 명단 주세요",
    ):
        assert desk_sanity(blocked, said)[0].act == "blocked", said


def test_blocked_reply_keeps_code_lines_as_facts(tmp_path):
    said = (
        "김말순 어르신이 이틀째 전화를 안 받으세요. 사북면에 혼자 사세요. 괜찮으신지 알 수 있나요?"
    )
    masked = said.replace("김말순", "[이름]")
    card = DeskCard(act="blocked", block="person", urgent=True)
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({masked: card}), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    e.start("x", Profile(member_region="춘천시"))
    r = e.turn("x", said)
    lines = [x for f in r.facts for x in f.lines]
    assert any("033-250-3609" in x for x in lines)


def test_tired_forms_are_distress():
    from src.assistant.engine import SELF_DISTRESS
    from src.assistant.policy import DISTRESS

    assert DISTRESS.search("하... 저도 진짜 지치네요.") and SELF_DISTRESS.search(
        "저도 진짜 지치네요"
    )
    assert not DISTRESS.search("지치지 않게 천천히 보세요")


def test_generalized_rules_cover_paraphrases():
    # 10-28 밤 팀장 '하드코딩 말고' — 고칠 때 쓴 말이 아닌 다른 말투로 확인한다
    from src.assistant.engine import SELF_DISTRESS
    from src.assistant.policy import DISTRESS

    # 이름 가림: 낱말 예외 없이(사흘째 · 이번주 · 이웃이) — 진짜 이름은 그대로 가림
    for said in ("사흘째 연락이 안 돼요", "이번주 전화를 안 받으세요", "이웃이 전화를 안 받아요"):
        assert pii.mask(said)[1] == [], said
    assert pii.mask("박영희는 어디 사셔")[1] == ["이름"]
    # 위기 말: 활용형과 상관없이, 권하는 말은 아님
    for said in ("저 요즘 너무 버거워요", "저도 진짜 지치네요", "제가 좀 지쳤나 봐요"):
        assert SELF_DISTRESS.search(said), said
    assert DISTRESS.search("힘드네요 정말") and not DISTRESS.search("지치지 않게 천천히 보세요")
    # '네, … 아니에요': 물음 꼴과 상관없이 판단을 뒤집는 부정만
    assert checks.yes_then_no("네, 그 문장은 자료와 맞지 않아요.", "이 문장 기사에 넣어도 될까요?")
    assert not checks.yes_then_no("네, 경로당은 3곳이고 급식소는 없어요.", "경로당 있나요?")
    # 계획 AI의 '못 한다' 문장은 주제와 상관없이 뗌
    got = Q.clean_restate("두 조건이 모두 맞는 동을 찾는다. 지도로는 보여 드릴 수 없다.")
    assert got == "두 조건이 모두 맞는 동을 찾는다."


def test_region_only_question_uses_region_not_member_dong(tmp_path):
    # 10-28 밤 브라우저 시험(로그인 회원 · 담당 동 개포3동): '강남구 독거 어르신 … 몇 명쯤'에
    #        개포3동 숫자로 답하고 '강남구 합계는 자료에 없다'(거짓)
    from src.assistant.policy import desk_sanity

    card = DeskCard(act="ask", topics=("solo_seniors",), region_op="set", region="강남구")
    got, _ = desk_sanity(card, "강남구 독거 어르신 중에 고독사 위험군이 몇 명쯤인지 대략 숫자만요")
    assert got.dong_op == "clear" and got.rank
    # 자기 동을 가리키면 그대로
    got, _ = desk_sanity(card, "강남구 우리 동 독거 어르신은 몇 명이에요?")
    assert got.dong_op == "keep"


def test_table_edit_splits_on_comma_and_move_words():
    from src.assistant import table_edit

    assert table_edit.is_edit("늘어난 비율 칸은 2026-09 바로 다음에 오게 자리 바꿔 주세요")
    parts = [
        p for p in table_edit.CLAUSE.split("비율 칸 하나 붙여 주시고, 80세 칸은 지워 주세요") if p
    ]
    assert len(parts) >= 2


def test_dong_mean_words_and_column_edit_over_calc():
    from src.assistant.engine import DONG_MEAN

    for said in ("강남 동들 평균보다 높은", "동별 평균보다", "22개 동의 평균보다", "동 평균보다"):
        assert DONG_MEAN.search(said), said
    assert not DONG_MEAN.search("강남구 평균보다 높은")


def test_orphan_heard_sentence_is_dropped():
    assert checks.tidy("로 알아들었어요. 강남구 동 중 4곳이에요.") == "강남구 동 중 4곳이에요."
    assert checks.tidy("(퇴계동은 빼고 봤어요.)\n로 알아들었어요. 16곳이에요.").endswith(
        "\n16곳이에요."
    )
    keep = "강남구 동 중 비율이 높은 동을 찾는 것으로 알아들었어요. 4곳이에요."
    assert checks.tidy(keep) == keep
