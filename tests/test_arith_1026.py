"""사용자가 적은 셈(10-26 페르소나 c01 · c04)."""

from src.assistant import arith


def test_sums_and_division():
    assert arith.lines("2,543명 + 1,285명 + 1,262명 = 5,090명 맞나요") == [
        "[사용자가 적은 셈] 2,543명 + 1,285명 + 1,262명 = 5,090"
    ]
    assert arith.lines("45.6÷8.1 해보면")[0].endswith("= 5.63")
    assert "약 20.1%" in arith.lines("19,769÷98,431은?")[0]
    assert arith.evaluate("2 + 3 × 4") == 14


def test_not_dates_or_ranges():
    assert arith.lines("2026-09 기준 250~260명, 10/26 회의") == []
    assert arith.evaluate("5 ÷ 0") is None
