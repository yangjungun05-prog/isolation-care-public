"""규칙 성능 재기 — 결제가 줄어든 가짜 줄을 심어 등급 규칙이 찾아내는지 잰다(만약에 ③ · S3).

정답(실제로 고립이 시작된 사람)이 없어서, 줄어듦을 일부러 심고 되찾는 비율을 센다.
"""

import pandas as pd

from src.dashboard import grades


def plant(x: pd.Series, end: str, days: int, factor: float) -> pd.Series:
    # 【기능】 날마다 결제 x 를 end 날까지 자르고, 마지막 days 일에 factor 를 곱한 가짜 줄
    # 【판단】 end 에서 자른다 — 그날 아침 06:00 에 계산한다고 치면 그 뒤 자료는 아직 없다
    cut = x[x.index <= pd.Timestamp(end)].astype(float).copy()
    cut.iloc[-days:] *= factor
    return cut


# 【기능】 시험할 줄 18개 — 시군구 2 × 나이 3 × 업종 묶음 3
LINES = [(r, a, g) for r in grades.SGG for a in grades.AGES for g in grades.LIFE]


def at_least(got: pd.Series, level: str) -> float:
    # 【기능】 등급 목록 중 level 이상(더 높은 등급 포함)인 몫. GRADES 는 위험 → 평상 순서
    rank = got.map(grades.GRADES.index)
    return round(float((rank <= grades.GRADES.index(level)).mean()), 3)


def detection_table(
    ends: list[str], factors=(1.0, 0.9, 0.8, 0.7, 0.6, 0.4), days_list=(28,)
) -> pd.DataFrame:
    # 【기능】 줄 18개 × 기준일마다 줄어듦을 심고 등급을 매겨, 몇 % 를 찾아냈는지 표로
    # 【판단】 factor 1.0 = 아무것도 안 심음 → 여기서 뜬 등급은 전부 '잘못 울림'(대조군)
    rows = []
    for days in days_list:
        for factor in factors:
            got = []
            for region, age, group in LINES:
                x = grades.daily(region, age, group)
                for end in ends:
                    t = grades.build(plant(x, end, days, factor))
                    got.append(grades.grade_at(t, pd.Timestamp(end).date()))
            g = pd.Series(got)
            rows.append(
                {
                    "줄어듦": f"{round((1 - factor) * 100)}%",
                    "며칠": days,
                    "건수": len(g),
                    "관심 이상": at_least(g, "관심"),
                    "주의 이상": at_least(g, "주의"),
                    "경고 이상": at_least(g, "경고"),
                }
            )
    return pd.DataFrame(rows)
