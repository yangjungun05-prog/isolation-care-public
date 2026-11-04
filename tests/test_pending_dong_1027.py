"""되묻기('어느 동을 볼까요?')에 동만 답하면 코드가 되묻던 주제로 잇는다(10-27 desk_correct_18).

데스크(Haiku)는 '대치4동요' · '개포3동 말고요, 개포4동이요'에 주제가 없다며 act=unclear 를
내기도 한다(-pending 6문제 중 5개가 3/3 unclear). 빈 칸이 무엇인지는 코드가 아니까 되묻기 답은
코드가 잇는다.
"""

from src.assistant.data_source import JsonDongData
from src.assistant.policy import preflight
from src.assistant.slots import DeskCard
from src.assistant.state import Profile, apply_card, new_state

DATA = JsonDongData()
ASK = (
    "어느 동을 볼까요? 강남구에서는 예를 들어 수서동, 개포3동, 세곡동처럼 동 이름으로 말씀해 주세요"
)


def _pending_state(topics=()):
    st = new_state(Profile(member_region="강남구"))
    return st.model_copy(
        update={
            "topics": tuple(topics),
            "pending": "dong",
            "pending_topics": ("solo_seniors",),
            "last_question": ASK,
        }
    )


def test_unclear_card_with_dong_answers_pending_question():
    st = _pending_state()
    card = DeskCard(
        act="unclear", restate="대치4동을 보려 한다", dong_op="set", dong_mentions=("대치4동",)
    )
    applied = apply_card(st, card, "대치4동요")
    plan = preflight(applied, card, DATA)
    assert plan.kind == "answer" and plan.topics == ("solo_seniors",)
    assert applied.state.slots.dongs == ("대치4동",)


def test_correction_while_pending_uses_new_dong():
    st = _pending_state()
    card = DeskCard(
        act="unclear", restate="개포4동을 보려 한다", dong_op="set", dong_mentions=("개포4동",)
    )
    applied = apply_card(st, card, "개포3동 말고요, 개포4동이요")
    plan = preflight(applied, card, DATA)
    assert plan.kind == "answer" and applied.state.slots.dongs == ("개포4동",)


def test_bare_dong_without_pending_answers_dong_overview():
    """10-27 '싹 다 고치자': 앞 맥락 없이 동만 말해도 그 동의 상황 한눈에로(전에는 unclear)."""
    st = new_state(Profile(member_region="강남구"))
    card = DeskCard(act="unclear", restate="대치4동", dong_op="set", dong_mentions=("대치4동",))
    plan = preflight(apply_card(st, card, "대치4동요"), card, DATA)
    assert plan.kind == "answer" and plan.topics == ("dong_overview",)


def test_correction_keeps_previous_topic():
    st = new_state(Profile(member_region="강남구"))
    st = st.model_copy(
        update={
            "topics": ("youth",),
            "slots": st.slots.model_copy(update={"dongs": ("역삼1동",), "region": "강남구"}),
        }
    )
    card = DeskCard(act="unclear", restate="역삼2동", dong_op="set", dong_mentions=("역삼2동",))
    applied = apply_card(st, card, "역삼1동 아닌 역삼2동 얘기야")
    plan = preflight(applied, card, DATA)
    assert plan.kind == "answer" and plan.topics == ("youth",)
    assert applied.state.slots.dongs == ("역삼2동",)


def test_unclear_without_dong_stays_unclear():
    st = new_state(Profile(member_region="강남구"))
    card = DeskCard(act="unclear", restate="음")
    assert preflight(apply_card(st, card, "음..."), card, DATA).kind == "unclear"


def test_unclear_while_pending_but_no_dong_stays_unclear():
    st = _pending_state()
    card = DeskCard(act="unclear", restate="모르겠다")
    plan = preflight(apply_card(st, card, "음..."), card, DATA)
    assert plan.kind == "unclear"
