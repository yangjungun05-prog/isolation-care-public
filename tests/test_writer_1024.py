"""10-24 CLI 시험지에서 찾은 글쓴이 문제."""

from src.assistant import checks


def test_yes_then_no_on_leading_question():
    # outlook_chuncheon T13: 단정이 깔린 물음에 '네,'로 시작해 부정 → 동의로 읽힘
    q = "청년들 은둔하는 건 다 게임 때문이잖아요 그쵸?"
    assert checks.yes_then_no("네, 게임 때문인지는 이 자료로 확인할 수 없어요. 자료에는 …", q)
    assert not checks.yes_then_no("게임 때문인지는 이 자료로 확인할 수 없어요.", q)
    assert not checks.yes_then_no("아니요, 게임 때문이라고 확인되지 않아요.", q)


def test_yes_then_no_leaves_right_yes_alone():
    # '알 수 없는 거죠?'에는 '네, 알 수 없어요'가 맞는 답
    assert not checks.yes_then_no("네, 이 자료로는 알 수 없어요.", "최근 피해는 알 수 없는 거죠?")
    # 단정이 없는 물음은 보지 않는다(경로당 '네, 3곳이고 급식소는 없어요')
    assert not checks.yes_then_no("네, 경로당은 3곳이고 급식소는 없어요.", "수서동 경로당 있어요?")
    # 첫 문장만 본다 — 뒤 문장의 '없어요'는 동의 뒤 덧붙임이 아니다
    a = "네, 수서동은 취약 돌보미 동 순위 3위예요. 다만 고독사 자료는 없어요."
    assert not checks.yes_then_no(a, "수서동이 순위 높잖아요?")
