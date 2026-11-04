"""긍정 · 부정 · 머뭇 칸 대조(10-26). AI를 부르지 않는다."""

from src.assistant.polarity import cues, reconcile
from src.assistant.slots import DeskCard


def card(pos=(), neg=(), uns=()):
    return DeskCard(
        act="ask",
        topics=("solo_seniors",),
        dong_op="set" if pos else "keep",
        dong_mentions=tuple(pos),
        dong_not=tuple(neg),
        dong_unsure=tuple(uns),
    )


def test_cues_only_right_after_name():
    assert cues("대치4동이 아니라 대치1동", "대치4동") == "not"
    assert cues("수서동은 빼고 세곡동", "수서동") == "not"
    assert cues("수서동 어르신 아니라 청년이요", "수서동") == ""  # 대상에 걸린 부정
    assert cues("도곡1동인가.. 아니 도곡2동", "도곡1동") == "unsure"
    assert cues("대치4동보다 수서동이 더 많아?", "대치4동") == ""  # 견줌
    assert cues("대치4동보다는.. 글쎄 역삼1동", "대치4동") == "unsure"


def test_ai_kept_negated_dong_code_moves_it():
    c, note = reconcile(card(pos=("대치4동", "대치1동")), "대치4동 말고 대치1동 청년")
    assert c.dong_mentions == ("대치1동",) and c.dong_not == ("대치4동",)
    assert "아니라고 하셔서" in note


def test_ai_invented_negative_is_dropped():
    c, _ = reconcile(card(pos=("수서동",), neg=("세곡동",)), "수서동 혼자 사는 어르신")
    assert c.dong_not == () and c.dong_mentions == ("수서동",)


def test_ai_dropped_unsure_dong_is_noted():
    say = "세곡동일지도 모르겠는데 일단 수서동 혼자 사는 어르신"
    c, note = reconcile(card(pos=("수서동",)), say)
    assert c.dong_mentions == ("수서동",) and c.dong_unsure == ("세곡동",)
    assert "분명하지 않아" in note


def test_omission_without_cue_is_left_to_ai():
    c, note = reconcile(card(pos=("일원1동",)), "일원본동은 아까 봤고 일원1동은?")
    assert c.dong_mentions == ("일원1동",) and c.dong_not == () and note == ""


def test_ai_used_old_dong_not_in_words_code_takes_the_said_one():
    # 10-26 예상 질문 2-26: AI가 앞 동(신북읍)을 적고 말에 나온 동면을 빠뜨림
    c, _ = reconcile(
        card(pos=("신북읍",)), "1. 동면이 춘천에서 어떤 편인지 2. 80세 이상 혼자 사는 분"
    )
    assert c.dong_mentions == ("동면",)


def test_pointing_words_keep_the_ai_dong():
    # '거기'처럼 앞 동을 가리키면 말에 없어도 AI가 적은 동을 그대로
    c, _ = reconcile(card(pos=("신북읍",)), "거기랑 동면 견줘 줘")
    assert "신북읍" in c.dong_mentions


def test_old_dong_dropped_when_both_listed_and_restate_follows_words():
    # q2: AI가 앞 동 신북읍과 말한 동면을 둘 다 적고 다시 쓴 질문도 신북읍 → 원문으로
    text = "1. 동면이 춘천에서 어떤 편인지 2. 80세 이상 혼자 사는 분"
    c, _ = reconcile(card(pos=("신북읍", "동면")), text)
    assert c.dong_mentions == ("동면",) and c.restate == text


def test_compare_keeps_current_dong():
    # '○○이랑 비교하면?'은 지금 칸의 동도 같이(데스크 지시문)
    c, _ = reconcile(card(pos=("세곡동", "수서동")), "수서동이랑 비교하면?")
    assert set(c.dong_mentions) == {"세곡동", "수서동"}


def test_ai_left_dongs_empty_code_takes_the_said_one():
    # q3 2-26: AI가 동 칸을 비워 앞 동이 남음 → 말에 나온 동면
    text = "1. 동면이 춘천에서 어떤 편인지 2. 80세 이상 혼자 사는 분"
    c, _ = reconcile(card(), text)
    assert c.dong_mentions == ("동면",) and c.dong_op == "set"


def test_rank_question_with_example_dong_is_left_alone():
    # '수서동처럼 … 많은 동'은 줄 세우기라 동 칸에 넣지 않는다
    c, _ = reconcile(
        card().model_copy(update={"rank": True}), "수서동처럼 혼자 사는 어르신 많은 동 어디야"
    )
    assert c.dong_mentions == ()


def test_stale_restate_with_old_dong_falls_back_to_words():
    # q4 2-26: 칸은 동면인데 다시 쓴 질문이 신북읍 → 원문으로
    text = "1. 동면이 춘천에서 어떤 편인지 4. 가까운 보건지소"
    c0 = card(pos=("동면",)).model_copy(update={"restate": "신북읍의 가까운 보건지소를 알려 달라"})
    c, _ = reconcile(c0, text)
    assert c.restate == text and c.dong_mentions == ("동면",)


def test_restate_kept_when_pointing_back():
    c0 = card(pos=("동면",)).model_copy(update={"restate": "신북읍과 동면을 견줘 달라"})
    c, _ = reconcile(c0, "거기랑 동면 견줘 줘")
    assert c.restate == "신북읍과 동면을 견줘 달라"


def test_follow_up_without_dong_keeps_restate_with_current_dong():
    # '청년은?'은 다시 쓴 질문이 지금 동(수서동)을 채우는 것이 맞다
    c0 = card().model_copy(update={"restate": "수서동의 청년 상황을 알려 달라"})
    c, _ = reconcile(c0, "청년은?")
    assert c.restate == "수서동의 청년 상황을 알려 달라"
