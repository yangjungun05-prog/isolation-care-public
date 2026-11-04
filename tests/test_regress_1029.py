"""회귀 59af237(10-28 밤)에서 새로 틀린 세 턴을 원인 쪽에서 고친 것(10-29).

- long_100 T22 '강남 평균보다 넓어요 좁아요?': '지역만 말하면 지역 전체' 규칙이 견줄 기준으로 말한
  지역까지 지역 전체로 봐 앞 동(수서동) 칸을 비움
- chuncheon_youth_60 T21 '후평삼동은요?': 번호를 글자로 쓴 동을 코드가 못 읽어, 데스크가 빠뜨리자
  앞 동(효자2동)이 남음
- rules_v6_16 T3 '기초수급 받는 독거 어르신 많은 동': 계산이 수급자 지표를 썼는데 데스크 주제에
  수급이 없어 '춘천 수급자는 나이 · 혼자로 못 나눈다' 밝힘이 빠짐
"""

from src.assistant import query as Q
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.policy import desk_sanity, dongs_in_text
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter


class FakePlanner:
    def __init__(self, plan):
        self.p = plan

    def plan(self, question, region, context=""):
        return self.p


def test_spelled_number_dongs_are_read():
    assert dongs_in_text("후평삼동은요?") == ["후평3동"]
    assert dongs_in_text("대치사동 독거노인") == ["대치4동"]
    assert dongs_in_text("역삼이동이랑 삼성일동 견줘 줘") == ["역삼2동", "삼성1동"]
    # 번호 없는 진짜 동 이름은 그대로(석사동 · 신사동을 석4동 · 신4동으로 읽지 않는다)
    assert dongs_in_text("석사동은?") == ["석사동"]
    assert dongs_in_text("신사동 경로당") == ["신사동"]
    card = DeskCard(act="ask", topics=("housing",))
    got, _ = desk_sanity(card, "후평삼동은요?")
    assert got.dong_op == "set" and got.dong_mentions == ("후평3동",)


def test_region_as_comparison_base_keeps_dong():
    card = DeskCard(act="ask", topics=("senior_hall",))
    for said in (
        "강남 평균보다 넓어요 좁아요?",
        "강남구 평균 대비 많은 편이에요?",
        "춘천 전체에 비해 어때요?",
        "강남구 평균이랑 비교하면요?",
    ):
        got, _ = desk_sanity(card, said)
        assert got.dong_op == "keep", said
    # 지역 자체를 물으면 지역 전체(10-28 밤 규칙 그대로)
    solo = DeskCard(act="ask", topics=("solo_seniors",), region_op="set", region="강남구")
    got, _ = desk_sanity(solo, "강남구 독거 어르신은 몇 명쯤이에요?")
    assert got.dong_op == "clear"


def test_calc_using_livelihood_metric_gets_its_note(tmp_path):
    ask = "기초수급 받는 독거 어르신 많은 동 알려줘"
    # 데스크는 주제를 혼자 사는 어르신만 적었다(수급 없음)
    card = DeskCard(
        act="ask",
        topics=("solo_seniors",),
        region_op="set",
        region="춘천시",
        target_op="set",
        target="어르신",
        alone_op="set",
        alone=True,
        rank=True,
        calc=True,
    )
    plan = Q.Plan(
        region="춘천시",
        conds=(Q.Cond(metric="solo65", op="많음"), Q.Cond(metric="livelihood", op="많음")),
        mode="많이 맞는 순",
    )
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(
        FakeDesk({ask: card}),
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        s,
        planner=FakePlanner(plan),
    )
    e.start("x", Profile(member_region="춘천시"))
    r = e.turn("x", ask)
    assert any(f.title == "여러 조건 계산" for f in r.facts)
    assert "춘천 기초생활수급자 숫자는 나이 · 혼자 사는지로 나눠 볼 수 없어서" in r.text


def test_calc_about_few_dongs_keeps_their_shelf_facts(tmp_path):
    # 10-29 브라우저 시험(퇴계동 다음 턴): '거기는 춘천 평균보다 몇 배? 그리고 1년 전보다는?'
    #       — 계산이 평균 견줌만 하고 서가를 빼 '1년 전 자료가 없다'(2023년 2,310명이 있음)
    ask = "퇴계동 수급자는 춘천 평균보다 몇 배예요? 그리고 1년 전보다는 늘었어요?"
    card = DeskCard(
        act="ask",
        topics=("livelihood",),
        region_op="set",
        region="춘천시",
        dong_op="set",
        dong_mentions=("퇴계동",),
        calc=True,
    )
    plan = Q.Plan(region="춘천시", dongs=("퇴계동",), show=(Q.Ref(metric="livelihood"),))
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(
        FakeDesk({ask: card}),
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        s,
        planner=FakePlanner(plan),
    )
    e.start("x", Profile(member_region="춘천시"))
    r = e.turn("x", ask)
    assert any(f.title == "여러 조건 계산" for f in r.facts)
    prev = JsonDongData().dong("퇴계동")["livelihood"]["prev"]
    seen = [c for f in r.facts for c in f.compares if c[0] == "기초생활수급자"]
    assert seen and seen[0][1] == prev


def test_metric_topics_cover_calc_metrics():
    from src.assistant.engine import metric_topics

    refs = [Q.Ref(metric=m) for m in ("livelihood_per100", "solo65_rise", "halls", "v_bus")]
    assert metric_topics(refs) == ["livelihood", "solo_seniors", "senior_hall"]


def _rank_engine(tmp_path, table, plan=None):
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    kw = {"planner": FakePlanner(plan)} if plan else {}
    e = Engine(FakeDesk(table), TemplateWriter(), JsonDongData(), MemoryStore(), s, **kw)
    e.start("x", Profile(member_region="강남구"))
    return e


def test_nth_rank_dong_after_priority_turn(tmp_path):
    # 10-29 회귀 long_100 T18: 먼저 볼 동을 본 다음 '3위 동은 상황이 어때요?'
    t1, t2 = "강남에서 먼저 볼 동 알려줘", "3위 동은 상황이 어때요?"
    table = {
        t1: DeskCard(act="ask", topics=("priority",), region_op="set", region="강남구"),
        t2: DeskCard(act="ask", topics=("dong_overview",)),
    }
    e = _rank_engine(tmp_path, table)
    e.turn("x", t1)
    r = e.turn("x", t2)
    third = JsonDongData().ranked("강남구")[2][1]
    assert r.state.slots.dongs == (third,)


def test_nth_rank_dong_after_calc_is_calc_result(tmp_path):
    t1 = "강남구에서 혼자 사는 어르신 많고 경로당 적은 동"
    t2 = "2위 동은 상황이 어때요?"
    table = {
        t1: DeskCard(act="ask", topics=("solo_seniors",), region_op="set", region="강남구"),
        t2: DeskCard(act="ask", topics=("dong_overview",)),
    }
    plan = Q.Plan(
        region="강남구",
        conds=(Q.Cond(metric="solo65", op="많음"), Q.Cond(metric="halls", op="적음")),
    )
    e = _rank_engine(tmp_path, table, plan)
    r1 = e.turn("x", t1)
    assert any(f.title == "여러 조건 계산" for f in r1.facts)
    e.planner.p = Q.Plan(need="바로")
    r2 = e.turn("x", t2)
    assert r2.state.slots.dongs == (r1.state.last_calc[1],)


def test_meaning_question_adds_sources():
    # 10-29 회귀 춘천 청년 T22: 뜻 묻기에 갈 곳 목록만
    card = DeskCard(act="ask", topics=("places",))
    for said in (
        "거기 갈 곳이 적다던데 무슨 말이에요?",
        "계단 집이 뜻이 뭐예요?",
        "진단 높음은 어떤 의미인가요?",
    ):
        got, _ = desk_sanity(card, said)
        assert got.topics[0] == "sources", said
    got, _ = desk_sanity(card, "112에 신고할 때 무슨 말을 해야 해요?")
    assert "sources" not in got.topics


def test_inner_division_of_work_sentence_is_dropped():
    from src.assistant import checks

    said = (
        "개포3동과 효자2동의 65세 이상 1인세대와 1년 새 증감은 아래와 같아요. "
        "표는 제가 드리지 않고 코드가 아래에 붙입니다.\n\n개포3동은 1,262명이에요."
    )
    got = checks.tidy(said)
    assert "코드가" not in got and "제가 드리지" not in got
    assert got.startswith("개포3동과 효자2동의") and got.endswith("1,262명이에요.")
    # 숫자 출처를 밝히는 표 바닥 줄은 그대로
    foot = "합계(22곳, 코드가 더함): 65세 이상 1인세대 2026-09 19,769"
    assert checks.tidy(foot) == foot


def test_two_region_table_keeps_both_dongs(tmp_path):
    ask = "제 담당 개포3동이랑 효자2동, 65세 이상 혼자 사는 분 수를 표로 나란히 비교해 주세요"
    card = DeskCard(
        act="ask",
        topics=("solo_seniors",),
        dong_op="set",
        dong_mentions=("개포3동", "효자2동"),
        compare=True,
    )
    e = _rank_engine(tmp_path, {ask: card})
    r = e.turn("x", ask)
    assert "개포3동" in r.text and "효자2동" in r.text
    rows = [ln for ln in r.text.splitlines() if ln.startswith("|")]
    assert any("효자2동" in ln for ln in rows) and any("개포3동" in ln for ln in rows)


def test_modifier_words_are_not_names():
    from src.assistant import pii

    # 10-29 브라우저 시험: '오래된 집이'의 '오래된'을 이름으로 가림
    for said in (
        "계단만 있는 오래된 집이 많음은 무슨 말이에요?",
        "지원이 필요할 집이 어디예요?",
        "새로 지어질 집에 들어갈 분",
    ):
        assert pii.mask(said)[1] == [], said
    # 진짜 이름은 그대로 가린다
    assert pii.mask("이민수 주소 알려줘")[1] == ["이름"]
    assert pii.mask("김하은 할머니 건강 어때요?")[1] == ["이름"]


def test_person_part_is_blocked_rest_is_answered(tmp_path):
    from src.assistant import pii
    from src.assistant.policy import PERSON_PART, person_free_rest

    said = "302호 김순자 할머니 연락처 알려 주시고, 개포3동 노인맞춤돌봄 수행기관도 알려 주세요"
    masked = pii.mask(said)[0]
    rest = person_free_rest(masked)
    assert rest == "개포3동 노인맞춤돌봄 수행기관도 알려 주세요"
    # 개인 질문뿐이면 나누지 않는다
    assert person_free_rest(pii.mask("김순자 할머니 연락처랑 주소 알려 주세요")[0]) == ""
    assert person_free_rest(pii.mask("김순자 할머니 연락처 알려 주시고, 그분 건강은요?")[0]) == ""
    table = {
        masked: DeskCard(act="blocked", block="person"),
        rest: DeskCard(act="ask", topics=("support",), dong_op="set", dong_mentions=("개포3동",)),
    }
    e = _rank_engine(tmp_path, table)
    r = e.turn("x", said)
    assert r.kind == "answer"
    assert r.text.startswith(PERSON_PART.strip())
    assert "02-557-8091" in r.text  # 강남구노인통합지원센터(places.json 강남 care)
    assert "김순자" not in r.text and "302" not in r.text
    # 기억에는 개인 마디가 남지 않는다
    assert all("김순자" not in t.user for t in r.state.recent)


def test_person_block_suggestion_uses_named_dong():
    card = DeskCard(act="blocked", block="person")
    got, _ = desk_sanity(card, "[이름] 할머니 연락처 알려 주세요, 개포3동에 사세요")
    assert got.dong_mentions == ("개포3동",)


def test_top_n_without_metric_words_edits_previous_table(tmp_path):
    # 10-29 회귀 table_noel_10 T7: 계산으로 보면 표 다듬기를 막던 규칙이 '위에서 다섯 곳만'까지 막음
    t1 = "강남구 22개 동 혼자 사는 어르신 수 표로 많은 순으로 보여 주세요"
    t2 = "위에서 다섯 곳만 보여 줘"
    table = {
        t1: DeskCard(
            act="ask", topics=("solo_seniors",), region_op="set", region="강남구", rank=True
        ),
        t2: DeskCard(act="ask", topics=("solo_seniors",), calc=True),
    }
    e = _rank_engine(tmp_path, table, Q.Plan(need="바로"))
    r1 = e.turn("x", t1)
    assert sum(ln.startswith("|") for ln in r1.text.splitlines()) > 10
    r2 = e.turn("x", t2)
    rows = [ln for ln in r2.text.splitlines() if ln.startswith("|")]
    assert len(rows) == 2 + 5  # 머리 · 구분 줄 + 5곳


def test_two_region_dongs_skip_calc_and_table_keeps_both(tmp_path):
    # 10-29 브라우저 시험 2차: 데스크가 줄 세우기 · 계산을 켜자 춘천 위 5곳 표가 나감
    ask = "제 담당 개포3동이랑 효자2동, 65세 이상 혼자 사는 분 수를 표로 나란히 비교해 주세요"
    card = DeskCard(
        act="ask",
        topics=("solo_seniors",),
        dong_op="set",
        dong_mentions=("개포3동", "효자2동"),
        rank=True,
        calc=True,
    )
    plan = Q.Plan(region="춘천시", sort=Q.Ref(metric="solo65"), limit=5)
    e = _rank_engine(tmp_path, {ask: card}, plan)
    r = e.turn("x", ask)
    assert not any(f.title == "여러 조건 계산" for f in r.facts)
    rows = [ln for ln in r.text.splitlines() if ln.startswith("|")]
    names = [ln.split("|")[1].strip() for ln in rows[2:]]
    assert sorted(names) == ["개포3동", "효자2동"]


def test_restate_drops_output_form_and_file_denial_is_a_problem():
    from src.assistant import checks

    said = (
        "강남구 22개 동의 청년 1인세대와 은둔 청년 어림을 본다. "
        "엑셀 파일 형식 내보내기는 이 계획에 없어 표로 보인다."
    )
    assert Q.clean_restate(said) == "강남구 22개 동의 청년 1인세대와 은둔 청년 어림을 본다."
    have = "표 파일(엑셀 · CSV)을 만들어 이 답과 함께 건넸다."
    bad = "엑셀 파일 형식으로 내보내는 기능이 이 계획에는 없어서 표로만 보여 드릴 수 있어요."
    assert checks.file_denial(bad, have)
    assert not checks.file_denial(bad, "파일 말 없음")
    assert not checks.file_denial("엑셀 파일에 22개 동이 모두 들어 있어요.", have)


def test_more_than_four_dongs_get_summary_lines():
    # 10-29 회귀 summary_recall_24 T23 · T24: 여섯 동 정리에 '한 번에 4곳까지만',
    #       제일 많은 곳도 틀림
    from src.assistant import librarian as L
    from src.assistant.slots import Slots

    six = ("역삼1동", "개포3동", "대치2동", "세곡동", "수서동", "일원1동")
    f = L.gather("solo_seniors", Slots(region="강남구", dongs=six), JsonDongData())
    text = "\n".join(f.lines)
    data = JsonDongData()
    for n in six:
        assert f"{data.dong(n)['solo65']['2026-09']:,}명" in text, n
    assert not any("4곳까지 보여" in x for x in f.notes)
    total = sum(data.dong(n)["solo65"]["2026-09"] for n in six)
    assert f"65세 이상 1인세대 {total:,}명" in text


def test_empty_houses_line_also_in_housing():
    # 10-29 회귀 춘천 청년 T27 '남산면은 빈집이 몇 채예요?'를 사는 집 주제로 받자 '빈집 수는 없다'
    from src.assistant import librarian as L
    from src.assistant.slots import Slots

    data = JsonDongData()
    n = data.dong("남산면")["empty_houses"]["n"]
    for topic in ("housing", "livelihood"):
        f = L.gather(topic, Slots(region="춘천시", dongs=("남산면",)), data)
        assert any(f"빈집: {n}채" in x for x in f.lines), topic


def test_restate_with_dongs_not_in_slots_falls_back_to_text():
    # 10-29 회귀 summary_recall_24 T22: 다시 쓴 질문의 동(개포3동)이 코드가 꺼낸 동과 어긋남
    from src.assistant.policy import restate_or_text

    text = "처음에 물어본 세 동 혼자 사는 어르신 숫자 다시 알려줘"
    restate = "강남구 세곡동 · 역삼1동 · 개포3동의 혼자 사는 어르신 숫자를 다시 알려 달라"
    slots = ("세곡동", "수서동", "역삼1동")
    assert restate_or_text(restate, text, "강남구", False, slots) == text
    ok = "강남구 세곡동 · 수서동 · 역삼1동의 혼자 사는 어르신 숫자를 다시 알려 달라"
    assert restate_or_text(ok, text, "강남구", False, slots) == ok


def test_my_dong_follows_desk_restate():
    # 10-29 회귀 춘천 청년 T57: 다시 쓴 질문은 효자2동, 동 칸은 앞 턴 소양동 그대로
    card = DeskCard(
        act="ask",
        topics=("dong_overview",),
        restate="내 담당 동(앞서 말한 효자2동 행정복지센터 담당 기준)의 상황을 한눈에 정리해 달라",
    )
    got, _ = desk_sanity(card, "마지막으로 우리 동 한눈에 정리")
    assert got.dong_op == "set" and got.dong_mentions == ("효자2동",)
    # 가리키는 말이 없으면 그대로
    got, _ = desk_sanity(card, "마지막으로 한눈에 정리")
    assert got.dong_op == "keep"


def test_table_answer_drops_repeated_row_bullets(tmp_path):
    # 10-29 팀장 '개포3동 … 1,287명이에요 <- 이렇게 설명은 괜찮은데 그 아래 … 너무 길어'
    from src.assistant.engine import drop_row_bullets

    body = (
        "개포3동 65세 이상 1인세대는 1,262명이고, 효자2동은 1,287명이에요.\n\n"
        "· 개포3동: 1,262명(2025-09 1,198명에서 64명 늘었음, 5%)\n"
        "· 효자2동: 1,287명(2025-09 1,233명에서 54명 늘었음, 4%)\n\n"
        "1인세대 수는 주민등록 기준이에요."
    )
    got = drop_row_bullets(body, ["개포3동", "효자2동"])
    assert got == (
        "개포3동 65세 이상 1인세대는 1,262명이고, 효자2동은 1,287명이에요.\n\n"
        "1인세대 수는 주민등록 기준이에요."
    )
    # 표에 없는 동 · 목록이 아닌 줄은 그대로
    assert drop_row_bullets("· 수서동: 2,543명", ["개포3동"]) == "· 수서동: 2,543명"


def test_table_place_sentence_is_dropped():
    from src.assistant import checks

    got = checks.tidy("표는 아래에 붙습니다. 개포3동은 1,262명이에요.")
    assert got == "개포3동은 1,262명이에요."
    keep = "아래 표와 같이 개포3동이 1,262명이에요."
    assert checks.tidy(keep) == keep


def test_region_youth_has_totals():
    # 10-29 변수 시험 c99_001 '춘천시 … 거의 집에만 있는 애들 어림 몇 명이야?'에 지역 전체 수가 없음
    from src.assistant import librarian as L
    from src.assistant.slots import Slots

    data = JsonDongData()
    f = L.gather("youth", Slots(region="춘천시", rank=True), data)
    text = "\n".join(f.lines)
    x = data.youth_method()["regions"]["춘천시"]
    assert f"약 {x['lo']:,}~{x['hi']:,}명" in text
    total = sum((data.dong(n)["youth"] or {}).get("solo", 0) for n in data.region_dongs("춘천시"))
    assert f"합계: {total:,}명" in text
