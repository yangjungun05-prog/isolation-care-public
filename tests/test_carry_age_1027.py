"""앞 턴의 '그중에 80세 이상만'이 다음 질문에 남던 것(10-27 qbank P1-03, API).

'우리 동에 혼자 사는 어르신 몇 분?' → '그중에 80세 이상만 따로' → '작년이랑 비교해서 혼자 사는
어르신이 늘었어요?'에 데스크는 나이 칸을 '그대로'로 냈고, 코드는 주제 · 대상이 같아 80세를 남겨
'80세 이상은 작년 수가 없어 알 수 없어요'로 시작했다.
대상을 통째로 다시 말하고(혼자 사는 어르신) 나이 · '그중' 같은 말이 없으면 좁힌 나이를 푼다.
"""

from src.assistant.slots import AgeRange, DeskCard
from src.assistant.state import Profile, Standing, apply_card, new_state


def _after_80() -> object:
    st = new_state(Profile(member_region="강남구", member_dong="수서동"))
    slots = st.slots.model_copy(
        update={"dongs": ("수서동",), "region": "강남구", "ages": AgeRange(lo=80)}
    )
    return st.model_copy(update={"slots": slots, "topics": ("solo_seniors",)})


KEEP = DeskCard(act="ask", topics=("solo_seniors",))


def test_restating_whole_group_drops_narrowed_age():
    out = apply_card(_after_80(), KEEP, "작년이랑 비교해서 혼자 사는 어르신이 늘었어요, 줄었어요?")
    assert out.state.slots.ages is None


def test_follow_up_without_group_word_keeps_age():
    for text in ("그럼 여자는요?", "작년보다 늘었어요?", "그중에 기초수급은?"):
        assert apply_card(_after_80(), KEEP, text).state.slots.ages == AgeRange(lo=80), text


def test_group_word_with_back_reference_or_age_keeps_age():
    for text in ("그중 혼자 사는 어르신 중에 여자는?", "혼자 사는 80세 이상 어르신은 늘었어?"):
        assert apply_card(_after_80(), KEEP, text).state.slots.ages == AgeRange(lo=80), text


def test_standing_rule_survives():
    st = _after_80()
    st = st.model_copy(update={"standing": (Standing(target="어르신", ages=AgeRange(lo=80)),)})
    out = apply_card(st, KEEP, "혼자 사는 어르신 늘었어요?")
    assert out.state.slots.ages == AgeRange(lo=80)


def test_which_dong_question_drops_carried_dong_for_priority():
    """qbank P1-19(api9): 계산 길이 그 판만 실패하면 앞 턴 북산면 하나만 보고 '순서는 못 만든다'."""
    from src.assistant import policy

    st = new_state(Profile(member_region="춘천시"))
    st = st.model_copy(update={"slots": st.slots.model_copy(update={"dongs": ("북산면",)})})
    text = "독거노인 1,000명당 공공 자원이 적은 동은 어디예요?"
    card, _ = policy.desk_sanity(DeskCard(act="ask", topics=("priority",)), text)
    assert card.dong_op == "clear"
    assert apply_card(st, card, text).state.slots.dongs == ()
    # '그 중에'처럼 앞 동들을 가리키면 넓히지 않는다
    kept, _ = policy.desk_sanity(
        DeskCard(act="ask", topics=("priority",)), "그 중에 자원이 적은 동은 어디예요?"
    )
    assert kept.dong_op == "keep"


def test_single_plain_question_is_not_sent_to_calc_by_ai_flag_alone():
    """long_100 T46(api13): '청년 몇 명이에요?'에 AI 표시(calc)만으로 계산 길 → 앞 5곳을 합침."""
    from src.assistant import router

    card = DeskCard(act="ask", topics=("youth",), calc=True)
    assert router.decide("청년 몇 명이에요?", card).route != "깊은 고민"
    # 계산 · 묶기 · 줄 세우기 말이 있으면 AI 표시를 믿는다
    for text in ("청년 다 합치면 몇 명이에요?", "청년 많은 동 순서대로", "그중에 청년은 몇 명?"):
        assert router.decide(text, card, has_prev_calc=True).route == "깊은 고민", text


def test_challenge_to_previous_answer_goes_to_memory():
    """10-27 '싹 다 고치자': 앞 답을 따지거나 되묻는 말은 기억 길(hold · hold2 · route_50)."""
    from src.assistant import router

    card = DeskCard(act="ask", topics=("solo_seniors",), calc=True)
    for text in (
        "지난번엔 석사동이 후평1동보다 약국이 멀다더니 이번엔 반대잖아. 앞뒤 말이 왜 이래?",
        "방금 그 동 경로당이 2개라고 했어? 내가 잘못 들었나",
        "처음에 본 일원1동 65세 이상 혼자 사는 어르신 숫자가 몇 명이었는지 한 번만 더 알려줘",
    ):
        assert router.decide(text, card, has_prev_calc=True).route == "기억", text
    # 새 질문이 따로 붙으면 그쪽: 말뜻 · 기준 → 바로, 새 계산 말 → 계산 길
    assert (
        router.decide("말이 앞뒤가 안 맞습니다. 순위는 뭘 기준으로 매기는 겁니까?", card).route
        == "바로"
    )
    q20 = "앞서 아니라고 하셨는데, 사북면 65세 이상이면서 1인세대인 주민이 몇 명입니까?"
    assert router.decide(q20, card).route == "깊은 고민"


def test_two_regions_without_metric_is_not_calc_and_define_choice_is_direct():
    from src.assistant import router

    card = DeskCard(act="ask", topics=("outlook",), calc=True)
    assert router.decide("강남이랑 춘천 중에 어디가 더 심각한가요?", card).route != "깊은 고민"
    card2 = DeskCard(act="ask", topics=("solo_seniors",))
    text = "혼자 사는 비율이 65세 이상 중이에요 아니면 전체 주민 중이에요?"
    assert router.decide(text, card2).route == "바로"


def test_fallback_answer_uses_one_bullet_style():
    from src.assistant.librarian import Facts
    from src.assistant.writer import short_answer

    f = Facts(
        title="지원 기관 · 신청 창구",
        lines=[
            "[강남구]",
            "- 응급안전안심서비스: 동 주민센터에 신청",
            "- 안부살핌 우편서비스: 우체국",
        ],
    )
    out = short_answer([f], "응급안전안심서비스 신청은 어디서 해?")
    assert "· 응급안전안심서비스" in out and "\n- " not in out


def test_heard_sentence_josa_follows_batchim():
    from src.assistant import checks

    assert checks.tidy("춘천로 알아들었어요. 마을은 5곳이에요.").startswith("춘천으로 알아들었어요")
    assert checks.tidy("강남구로 알아들었어요.") == "강남구로 알아들었어요."  # 받침 없음
    assert checks.tidy("춘천시 읍면으로 알아들었어요.") == "춘천시 읍면으로 알아들었어요."
    assert checks.tidy("서울로 알아들었어요.") == "서울로 알아들었어요."  # ㄹ 받침


def test_restate_other_region_falls_back_to_text():
    """10-27 회귀 rules_v6_16 T3: 칸은 춘천시인데 다시 쓴 질문이 강남구를 끌어오면 원문으로."""
    from src.assistant.policy import restate_or_text

    said = "기초수급 받는 독거 어르신 많은 동 알려줘"
    bad = "강남구에서 기초생활수급을 받는 독거 어르신이 많은 동을 순서대로 알려 달라"
    assert restate_or_text(bad, said, "춘천시", False) == said
    good = "춘천시에서 기초생활수급자가 많은 동을 순서대로 알려 달라"
    assert restate_or_text(good, said, "춘천시", False) == good
    # 견주기 · 사용자가 직접 말한 지역 · 춘천 강남동은 그대로
    both = "강남구와 춘천시의 혼자 사는 어르신을 견줘 달라"
    assert restate_or_text(both, "강남이랑 견줘 줘", "춘천시", True) == both
    assert restate_or_text(bad, "강남은?", "춘천시", False) == bad
    dong = "춘천 강남동의 기초생활수급자 수를 알려 달라"
    assert restate_or_text(dong, "강남동 수급자는?", "춘천시", False) == dong
    assert restate_or_text("", said, "춘천시", False) == said
