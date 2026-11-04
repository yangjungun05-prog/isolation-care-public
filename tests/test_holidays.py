"""공휴일(src/common/holidays.py) 테스트 — 인터넷·DB 없이 돈다."""

from datetime import date

from src.common.holidays import holiday_rows, is_holiday


def test_holiday_rows():
    # 【기능】 2025·2026 공휴일이 날짜 순서로 나오고, 이름은 DB 칸(20자) 안에 들어간다
    rows = holiday_rows()
    days = [r["day"] for r in rows]
    assert days == sorted(days)
    assert all(len(r["name"]) <= 20 for r in rows)
    # 【판단】 대회 카드 자료 기간(2025 하반기)의 공휴일은 8일 — 광복절 · 개천절 · 추석 연휴 4일 ·
    #   한글날 · 성탄절
    second_half = [d for d in days if date(2025, 7, 1) <= d <= date(2025, 12, 31)]
    assert len(second_half) == 8


def test_is_holiday():
    # 【기능】 대체공휴일은 True, 평일과 그냥 주말은 False
    assert is_holiday(date(2025, 10, 8))
    assert is_holiday(date(2025, 5, 6))
    assert not is_holiday(date(2025, 10, 10))
    assert not is_holiday(date(2025, 10, 11))
