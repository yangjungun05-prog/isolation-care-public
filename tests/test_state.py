from src.assistant.slots import AgeRange, DeskCard
from src.assistant.state import Profile, apply_card, new_state


def card(**kw) -> DeskCard:
    return DeskCard(act="ask", **kw)


def test_member_region_is_default():
    st = new_state(Profile(member_region="춘천시", member_dong="효자2동"))
    assert st.slots.region == "춘천시" and st.slots.dongs == ("효자2동",)


def test_dong_set_resolves_typo_and_fixes_region():
    st = new_state(Profile(member_region="춘천시"))
    out = apply_card(st, card(topics=("youth",), dong_op="set", dong_mentions=("tntjehd",)))
    assert out.state.slots.dongs == ("수서동",)
    assert out.state.slots.region == "강남구"  # 동을 정하면 지역도 맞춘다


def test_unknown_dong_keeps_old_and_reports():
    st = apply_card(new_state(), card(dong_op="set", dong_mentions=("수서동",))).state
    out = apply_card(st, card(dong_op="set", dong_mentions=("판교동",)))
    assert out.state.slots.dongs == ("수서동",)
    assert out.unknown_dongs and out.unknown_dongs[0][0] == "판교동"


def test_target_change_clears_ages_unless_said_now():
    st = apply_card(
        new_state(), card(target_op="set", target="어르신", ages_op="set", age_lo=80, age_hi=-1)
    ).state
    assert st.slots.ages == AgeRange(lo=80, hi=None)
    st2 = apply_card(st, card(target_op="set", target="청년")).state
    assert st2.slots.ages is None  # 어르신 80세 → 청년이면 지움
    st3 = apply_card(
        st, card(target_op="set", target="청년", ages_op="set", age_lo=25, age_hi=29)
    ).state
    assert st3.slots.ages == AgeRange(lo=25, hi=29)  # 이번 말에서 말한 나이는 둔다


def test_keep_is_default_and_clear_works():
    st = apply_card(new_state(), card(dong_op="set", dong_mentions=("북산면",))).state
    st = apply_card(st, card(topics=("youth",))).state
    assert st.slots.dongs == ("북산면",)
    st = apply_card(st, card(dong_op="clear")).state
    assert st.slots.dongs == ()


def test_topic_inherited_and_period_cleared_on_topic_change():
    st = apply_card(
        new_state(), card(topics=("solo_seniors",), period_op="set", period="2024년부터")
    ).state
    assert st.topics == ("solo_seniors",) and st.slots.period == "2024년부터"
    st = apply_card(st, card(target_op="set", target="청년")).state  # 주제 생략 → 잇는다
    assert st.topics == ("solo_seniors",) and st.slots.period == "2024년부터"
    st = apply_card(st, card(topics=("housing",))).state  # 주제가 바뀌면 때를 지운다
    assert st.slots.period is None


def test_turn_scoped_slots_reset():
    st = apply_card(new_state(), card(compare=True, fmt="PDF")).state
    st = apply_card(st, card()).state
    assert st.slots.compare is False and st.slots.fmt == "답"


def test_bad_age_rejected_and_swapped():
    st = apply_card(new_state(), card(ages_op="set", age_lo=300, age_hi=-1)).state
    assert st.slots.ages is None
    st = apply_card(new_state(), card(ages_op="set", age_lo=40, age_hi=20)).state
    assert st.slots.ages == AgeRange(lo=20, hi=40)


def test_two_regions_clear_region():
    st = apply_card(new_state(), card(dong_op="set", dong_mentions=("수서동", "북산면"))).state
    assert set(st.slots.dongs) == {"수서동", "북산면"} and st.slots.region is None


def test_other_city_dong_is_not_mapped_to_ours():
    # 【기능】 성남 판교동이 춘천 교동으로 바뀌면 엉뚱한 숫자를 답한다(10-12 밤에 찾은 버그)
    out = apply_card(new_state(), card(dong_op="set", dong_mentions=("판교동",)))
    assert out.state.slots.dongs == () and out.unknown_dongs


def test_typo_guess_is_reported():
    out = apply_card(new_state(), card(dong_op="set", dong_mentions=("사음서음동",)))
    assert out.state.slots.dongs == ("삼성1동", "삼성2동")
    assert out.guessed == [("사음서음동", "삼성1동·삼성2동")]


def test_region_switch_drops_dongs_of_other_region():
    st = apply_card(new_state(), card(dong_op="set", dong_mentions=("효자2동",))).state
    st = apply_card(st, card(region_op="set", region="강남구")).state
    assert st.slots.region == "강남구" and st.slots.dongs == ()
