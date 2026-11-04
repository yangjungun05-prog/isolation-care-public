"""답 쓰는 AI에게 보낼 자료 크기 안전장치(10-26)."""

from src.assistant import budget
from src.assistant.engine import CARRY_TITLE
from src.assistant.librarian import Facts


def test_small_is_untouched():
    f = [Facts(title="혼자 사는 어르신", lines=["수서동 2,543명"])]
    out, cut = budget.fit(f, ("수서동 몇 명?",), CARRY_TITLE)
    assert out == f and cut == 0


def test_carry_is_trimmed_first_and_answer_facts_kept():
    calc = Facts(title="여러 조건 계산", lines=[f"[동{i}] 값 {i}" * 20 for i in range(200)])
    carry = Facts(title=CARRY_TITLE, lines=["앞 답 자료 줄 " * 30 for _ in range(400)])
    out, cut = budget.fit([calc, carry], ("질문",), CARRY_TITLE, budget=60_000)
    assert cut > 0
    assert len(out[0].lines) == 200  # 이번 질문 자료는 그대로
    assert len(out[1].lines) < 400 and "줄였어요" in out[1].notes[-1]


def test_never_blocks_when_nothing_to_trim():
    big = [Facts(title=f"묶음{i}", lines=["가" * 3000] * 30) for i in range(3)]
    out, _ = budget.fit(big, ("질문",), CARRY_TITLE, budget=1000)
    assert len(out) == 3 and all(f.lines for f in out)  # 다 덜어 낼 수 없어도 보낸다
