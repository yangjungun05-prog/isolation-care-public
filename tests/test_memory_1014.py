"""계속 쓰는 조건 — '앞으로 ○○만'을 코드가 지킨다(문제 목록 4-3, 10-14).

【기능】 전에는 데스크(AI)가 [앞선 대화에서 확인된 사실]을 읽어야만 지켜졌다. 주제가 바뀌면 코드가
       나이 · 성별을 비우는데(멘토 10-12), 그때 계속 쓰기로 한 조건을 다시 채운다.
"""

from src.assistant.slots import AgeRange, DeskCard
from src.assistant.state import Profile, apply_card, new_state

ST = new_state(Profile(member_region="강남구"))


def _say(state, card, text):
    return apply_card(state, card, text)


def test_standing_age_survives_topic_change():
    a = _say(
        ST,
        DeskCard(act="chitchat", target_op="set", target="어르신", ages_op="set", age_lo=80),
        "참고로 저는 앞으로 80세 이상 어르신만 볼 거예요",
    )
    assert [(x.target, x.ages) for x in a.state.standing] == [("어르신", AgeRange(lo=80))]
    # 주제가 바뀌어 코드가 나이를 비울 때 계속 쓰는 조건을 다시 채운다(데스크가 나이를 안 적음)
    b = _say(
        a.state,
        DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("일원본동",)),
        "일원본동 혼자 사는 어르신 몇 명이야?",
    )
    assert b.state.slots.ages == AgeRange(lo=80) and b.standing_used
    c = _say(b.state, DeskCard(act="ask", topics=("senior_hall",)), "경로당은?")
    assert c.state.slots.ages == AgeRange(lo=80)


def test_standing_only_for_its_target_and_can_be_dropped():
    a = _say(
        ST,
        DeskCard(
            act="chitchat", target_op="set", target="청년", ages_op="set", age_lo=25, age_hi=29
        ),
        "앞으로 청년은 25~29세만 볼게요",
    )
    b = _say(
        a.state,
        DeskCard(act="ask", topics=("solo_seniors",), target_op="set", target="어르신"),
        "수서동 어르신은?",
    )
    assert b.state.slots.ages is None and not b.standing_used  # 어르신에는 안 씀
    c = _say(
        b.state, DeskCard(act="ask", topics=("youth",), target_op="set", target="청년"), "청년은?"
    )
    assert c.state.slots.ages == AgeRange(lo=25, hi=29)
    # 이번 질문에 다른 나이를 말하면 이번만 그 나이
    d = _say(
        c.state,
        DeskCard(act="ask", topics=("youth",), ages_op="set", age_lo=19, age_hi=24),
        "19~24세는?",
    )
    assert d.state.slots.ages == AgeRange(lo=19, hi=24) and len(d.state.standing) == 1
    # '앞으로 … 상관없이'면 지운다
    e = _say(
        d.state,
        DeskCard(act="chitchat", target_op="set", target="청년", ages_op="clear"),
        "앞으로 청년은 나이 상관없이 볼게요",
    )
    assert e.state.standing == ()


def test_standing_sex_rule():
    a = _say(
        ST,
        DeskCard(act="chitchat", target_op="set", target="어르신", sex_op="set", sex="여"),
        "이제부터 할머니만 볼게요",
    )
    b = _say(a.state, DeskCard(act="ask", topics=("solo_seniors",)), "개포3동은?")
    assert b.state.slots.sex == "여" and b.standing_used
