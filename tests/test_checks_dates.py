"""답 검문소: 사실 묶음에 없는 날짜(해 · 월 · 일 조합, 10-15)."""

from src.assistant import checks


def test_checker_catches_a_date_with_the_wrong_year():
    # 10-15 카드 [어느 동부터 볼지 묻기]: 사실 묶음은 2025-07-16인데 글쓴이가 다른 줄
    # (서울시 독거노인 2023년 → 2025년)의 해를 붙여 '2023년 7월 16일 자료는 없어요'라고 했다.
    # 2023은 사실 묶음에 있는 숫자라 숫자 검사로는 못 잡는다 — 해 · 월 · 일 조합으로 본다
    src = (
        "강남구 2025-07-16(7월 16일) 관측: 비 73.1mm\n서울시 독거노인 현황: 2023년 → 2025년 늘었음"
    )
    bad = "2023년 7월 16일 자료는 없어요. 강남구 비는 73.1mm예요."
    assert any("날짜" in p for p in checks.problems(bad, src, []))
    good = "2025년 7월 16일 강남구 비는 73.1mm예요. 서울시 독거노인은 2023년보다 늘었어요."
    assert not any("날짜" in p for p in checks.problems(good, src, []))
    plain = "7월 16일 강남구 비는 73.1mm예요."  # 해를 말하지 않으면 그대로 둔다
    assert not any("날짜" in p for p in checks.problems(plain, src, []))
