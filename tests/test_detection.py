"""규칙 성능 재기 — 줄어듦을 심으면 찾아내고, 안 심으면 조용한가."""

import pandas as pd
import pytest

from src.dashboard import cards, detection, grades


@pytest.fixture
def fake_card(tmp_path, monkeypatch):
    # 【기능】 가짜 카드 표 — 두 시군구 · 나이 넷 · 업종 셋. 요일마다 건수가 정해져 흔들림 없음
    days = pd.date_range("2025-07-01", "2025-12-31")
    rows = [
        pd.DataFrame(
            {"day": days, "sgg_cd": sgg, "age_group": age, "n": 100 + 10 * days.dayofweek}
        ).assign(industry_group=group)
        for sgg in grades.SGG.values()
        for age in ["60대", "70대 이상"]
        for group in grades.LIFE
    ]
    pd.concat(rows).to_csv(tmp_path / "card_pay_day.csv", index=False)
    monkeypatch.setattr(cards, "DERIVED", tmp_path)
    for f in (grades.card, grades.daily, grades.series):
        f.cache_clear()
    yield
    for f in (grades.card, grades.daily, grades.series):
        f.cache_clear()


def test_plant_cuts_and_scales(fake_card):
    x = grades.daily("강남구", "70대 이상", "전체")
    y = detection.plant(x, "2025-12-10", 7, 0.4)
    assert y.index[-1] == pd.Timestamp("2025-12-10") and len(y) == len(x[:"2025-12-10"])
    assert (y.iloc[-7:] == x[:"2025-12-10"].iloc[-7:] * 0.4).all()
    assert (y.iloc[:-7] == x[:"2025-12-10"].iloc[:-7]).all()
    # 원본은 그대로(daily 는 기억해 둔 값을 돌려준다)
    assert grades.daily("강남구", "70대 이상", "전체").equals(x)


def test_detection_table(fake_card):
    ends = ["2025-11-26", "2025-12-03", "2025-12-10"]
    t = detection.detection_table(ends, factors=(1.0, 0.4), days_list=(7, 14)).set_index(
        ["줄어듦", "며칠"]
    )
    assert t.loc[("0%", 7), "건수"] == 4 * 3
    # 대조 — 안 심으면 잘못 울림 0(흔들림 없는 가짜 표)
    assert t.loc[("0%", 7), "관심 이상"] == 0
    # 60% 를 7일은 한 주뿐이라 평상(4주 중 2주부터), 14일이면 모두 경고 이상
    assert t.loc[("60%", 7), "관심 이상"] == 0
    assert t.loc[("60%", 14), "경고 이상"] == 1
