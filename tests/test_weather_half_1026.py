"""하반기 · 상반기는 코드가 기간으로 정하고, 되감기 때 오늘 뒤 관측은 자른다(weather_16 T13)."""

from datetime import date

from src.assistant.data_source import JsonDongData
from src.assistant.librarian import _half_span, _kind_days

INFO = JsonDongData().weather()


def test_half_without_year_is_the_latest_one_that_has_started():
    assert _half_span("하반기", date(2026, 10, 26))[:2] == (date(2026, 7, 1), date(2026, 10, 26))
    assert _half_span("하반기", date(2026, 3, 5))[:2] == (date(2025, 7, 1), date(2025, 12, 31))
    assert _half_span("작년 상반기", date(2026, 10, 26))[2] == "2025년 상반기"
    assert _half_span("2025년 하반기", date(2026, 10, 26))[2] == "2025년 하반기"
    assert _half_span("겨울", date(2026, 10, 26)) is None


def test_rewound_today_cuts_later_observations():
    line = _kind_days("춘천시", INFO, "폭설", date(2025, 12, 31))
    assert "2026" not in line


def test_half_line_counts_only_that_half():
    today = date(2025, 12, 31)
    line = _kind_days("춘천시", INFO, "폭설", today, _half_span("하반기", today))
    assert line.startswith("춘천시 2025년 하반기(2025-07-01 ~ 2025-12-31)")


def test_half_before_observations_says_no_data_not_zero():
    today = date(2026, 10, 26)
    line = _kind_days("춘천시", INFO, "폭설", today, _half_span("작년 상반기", today))
    assert "관측 자료가 없음" in line and "0일" not in line


def test_month_and_season_spans():
    from src.assistant.librarian import _span

    today = date(2026, 10, 26)
    assert _span("지난 12월", today)[:2] == (date(2025, 12, 1), date(2025, 12, 31))
    assert _span("12월 4일", today) is None  # 날은 _when 이 읽는다
    assert _span("작년 여름", today)[2] == "2025년 여름"
    assert _span("지난 겨울", today)[:2] == (date(2025, 12, 1), date(2026, 2, 28))


def test_span_line_names_the_extreme_day_even_without_threshold():
    from src.assistant.librarian import _span

    today = date(2026, 10, 26)
    line = _kind_days("강남구", INFO, "한파", today, _span("지난 12월", today))
    assert "이 기간 가장 낮은 날은 12-" in line
