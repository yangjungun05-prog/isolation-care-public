"""10-20 페르소나 o06(에델) r5에서 나온 셋 — 계절을 말에서 읽기 · 두 지역 우열 · 몇 턴 앞 숫자."""

from src.assistant import librarian, outlook_text
from src.assistant.data_source import JsonDongData
from src.assistant.engine import carry_facts
from src.assistant.librarian import Facts
from src.assistant.slots import Slots

DATA = JsonDongData()


def test_season_is_read_from_the_words_when_desk_left_period_empty():
    # T2: 데스크가 때 칸을 채우지 않음 → '작년 여름 기록은 자료에 없다'(관측은 2025-07부터 있음)
    s = Slots(region="춘천시", target="어르신", weather="비")
    f = librarian.gather(
        "outlook", s, DATA, "그럼 작년 여름 폭우 때 춘천에서는 어떻게 판단하셨어요?"
    )
    assert any("그 계절 비가 가장 많이 온 날" in n for n in f.notes)
    # 때 칸이 차 있으면 그 칸을 쓴다(말을 다시 읽지 않음)
    s2 = Slots(region="춘천시", target="어르신", period="7월 16일")
    f2 = librarian.gather("outlook", s2, DATA, "작년 여름 폭우 때는요?")
    assert not any("그 계절" in n for n in f2.notes)
    # 앞날의 계절은 그대로 '날짜로 읽을 수 없다'
    f3 = librarian.gather("outlook", Slots(region="춘천시"), DATA, "내년 겨울엔 어떨까요?")
    assert not any("그 계절" in n for n in f3.notes)


def test_two_regions_are_not_ranked_against_each_other():
    f = librarian.gather("outlook", Slots(region="춘천시", target="어르신", compare=True), DATA)
    assert librarian.REGION_COMPARE_LINE in f.lines
    bad = "비율로 보면 강남구 어르신들이 겹친 걱정을 더 많이 안고 있어요."
    ok = "강남구는 22곳 중 9곳, 춘천시는 25곳 중 7곳에 겹친 걱정이 있어요. 두 몫은 잣대가 달라요."
    assert outlook_text.claims(bad, [f]) and not outlook_text.claims(ok, [f])
    # 한 지역 판단에는 이 검사를 걸지 않는다('더 걱정'은 동 견줌 줄이 따로 막음)
    one = librarian.gather("outlook", Slots(region="강남구", target="어르신"), DATA)
    assert not outlook_text.claims(bad, [one])


def test_numbers_from_a_few_turns_ago_are_carried():
    # T9: T1 답의 41% · 28%를 되짚었는데 직전(T8) 답의 자료에 없어 '자료에 없다'
    t1 = (
        "견줌(겹친 걱정이 있는 동 몫): 강남구 어르신 22곳 중 9곳, 41% / "
        "춘천시 어르신 25곳 중 7곳, 28%",
    )
    t8 = ("자료: 주민등록 인구통계 — 행정안전부",)
    now = [Facts(title="자료 설명 · 출처", lines=["자료: 주민등록 인구통계 — 행정안전부"])]
    said = "처음에 강남이 41%, 춘천이 28%라고 하신 숫자 자체는 맞는 건가요?"
    c = carry_facts(
        said, "자료 설명 …", t8, now, t1, "강남구는 22곳 중 9곳(41%), 춘천시는 25곳 중 7곳(28%)"
    )
    assert c is not None and t1[0] in c.lines
    # 숫자만 맞춰도(되짚는 말이 없어도) 앞 답들의 숫자면 잇는다
    c2 = carry_facts("41%가 맞아요?", "", t8, now, t1, "(41%)")
    assert c2 is not None and t1[0] in c2.lines
    # 앞 답들과 상관없는 말이면 잇지 않는다
    assert carry_facts("북산면 버스는요?", "", t8, now, t1, "(41%)") is None


def test_same_yardstick_counts_are_written_per_region():
    # 재생: 글쓴이가 강남 '지난 궂은 날씨 뒤 걱정 8곳'을 '두 곳 모두 0곳'으로 씀
    #       → 지역마다 따로 적은 줄
    f = librarian.gather("outlook", Slots(region="춘천시", target="어르신", compare=True), DATA)
    line = next(x for x in f.lines if x.startswith("같은 잣대(정한 기준값)로 견준 것: "))
    assert "강남구 어르신은 지금 닥친 걱정이 있는 동" in line
    assert "춘천시 어르신은 지금 닥친 걱정이 있는 동" in line


def test_myeon_is_a_unit_with_numbers_and_shares_are_given():
    # o04 r5 T8 · T9: '면 단위 자료도 나오지 않아요'(틀린 말)
    # o04 r5 T4 · T5: '비율 · 65세 이상 주민 수가 없다'
    m = librarian.gather(
        "sources", Slots(region="춘천시"), DATA, asked="리 단위는 안 되고 면 단위까지만 되는 거죠?"
    )
    assert m.lines[0].startswith("말뜻 — 자료의 단위: 읍면동") and "북산면" in m.lines[0]
    f = librarian.gather("solo_seniors", Slots(region="춘천시", dongs=("사북면",)), DATA)
    assert any(x.startswith("- 65세 이상 주민 ") and "%(주민등록" in x for x in f.lines)


def test_top_dong_question_ranks_the_region():
    # r6 rules_v6 T16 '강남 청년 제일 많은 동은?': 앞 턴 세곡동이 남아 '세곡동만 있다'(틀린 말)
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    card, _ = desk_sanity(DeskCard(act="ask", topics=("youth",)), "강남 청년 제일 많은 동은?")
    assert card.rank
    # 동을 말했으면 줄 세우기를 켜지 않는다
    card2, _ = desk_sanity(
        DeskCard(act="ask", topics=("youth",)), "수서동은 청년이 제일 많은 곳이에요?"
    )
    assert not card2.rank


def test_status_word_after_judge_goes_to_that_topic():
    # r2 · r6 chuncheon_youth_60 T51 '교동 수급자 현황은 괜찮죠?' → 판단이 아니라 수급자 현황
    from src.assistant.slots import DeskCard
    from src.assistant.state import apply_card, new_state

    st = new_state()
    c = DeskCard(act="ask", topics=("outlook",), dong_op="set", dong_mentions=("교동",))
    out = apply_card(st, c, "교동 수급자 현황은 괜찮죠?")
    assert out.state.topics == ("livelihood",)
    out2 = apply_card(st, c, "교동 어르신들 괜찮죠?")
    assert out2.state.topics == ("outlook",)


def test_many_dong_without_top_word_also_ranks():
    # r7 rules_v6 T3 '기초수급 받는 독거 어르신 많은 동 알려줘' → '어느 동?'으로 되물음
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    card, _ = desk_sanity(
        DeskCard(act="ask", topics=("livelihood",)), "기초수급 받는 독거 어르신 많은 동 알려줘"
    )
    assert card.rank
    # 취약 돌보미 판단과 함께면 켜지 않는다(겹친 동들 가운데에서 꺼낸다)
    card2, _ = desk_sanity(
        DeskCard(act="ask", topics=("outlook", "senior_hall")),
        "걱정이 겹친 동 중에 경로당이 적은 곳은요?",
    )
    assert not card2.rank


def test_relative_or_fixed_basis_is_given_per_overlap():
    # o02 r6: '논현1동 4가지 중 어떤 게 상대 기준이야?'에 답이 다섯 번 바뀜
    #         (기준 종류가 자료에 없었음)
    from src.assistant import conditions as C

    asked = "논현1동 4가지 중에 어떤 게 상대 기준이고 어떤 게 정한 기준이야?"
    s = Slots(region="강남구", dongs=("논현1동",), target="어르신")
    f = librarian.gather("sources", s, DATA, asked)
    assert C.BASIS_LINE in f.lines[:2]  # 10-20 낮: 앞에 '한쪽으로 단정하지 않기' 줄이 하나 더
    assert any("논현1동 어르신 겹침 '" in x and "정한 기준" in x for x in f.lines)
    # 묻는 말에 바로 맞는 요약 줄(겹친 걱정 N가지 중 정한 기준이 든 것 · 상대 기준만)
    assert any("겹친 걱정" in x and "상대 기준 조건만으로 선 것" in x for x in f.lines)
    # 동이 없으면 지역에서 겹친 걱정이 많은 곳으로
    g = librarian.gather(
        "sources", Slots(region="강남구"), DATA, "상대 기준이면 무조건 걸리는 거 아냐?"
    )
    assert C.BASIS_LINE in g.lines[:2] and len(g.lines) > 2
    # 기준 종류를 묻지 않으면 붙이지 않는다
    h = librarian.gather("sources", s, DATA, "어림이 무슨 뜻이에요?")
    assert C.BASIS_LINE not in h.lines
    assert C.FIXED >= {"past", "ahead", "pharmacy", "public"}


def test_calendar_says_last_and_next_long_holidays():
    # o03 r6 '추석이 곧 아닌가요? 달력이 틀린 건 아닌지': 2026 추석은 지났다고 말할 줄이 없었음
    from datetime import date

    from src.assistant import conditions as C

    s = C.sheet("효자2동", "청년", DATA, {}, date(2026, 10, 20))
    v = s.get("holiday").value
    assert v.startswith("없음 — ") and "9월 24일부터" in v and "추석" in v and "다음 긴 연휴" in v


def test_chitchat_example_follows_the_target():
    # o03 r6: 청년 이야기 중인데 '효자2동 혼자 사는 어르신' 예
    from src.assistant.policy import preflight
    from src.assistant.slots import DeskCard
    from src.assistant.state import apply_card, new_state

    st = new_state()
    st = st.model_copy(
        update={"slots": st.slots.model_copy(update={"dongs": ("효자2동",), "target": "청년"})}
    )
    card = DeskCard(act="chitchat")
    plan = preflight(apply_card(st, card, "네 고마워요"), card, DATA)
    assert "효자2동 청년" in plan.message and "어르신" not in plan.message
