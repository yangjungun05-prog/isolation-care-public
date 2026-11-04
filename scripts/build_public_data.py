"""공개 자료 원본에서 data/derived_public/ 를 만든다. 원본은 저장소에 넣지 않고 경로를 받는다.

    uv run python scripts/build_public_data.py "<나우캐스트 지표 데이터.csv>"

나우캐스트 신용카드 이용금액(공공데이터포털 15120835, 이용허락범위 제한 없음)의 주 단위 값을
대시보드가 읽는 날짜 표 모양으로 펼친다.
- 한 주의 값을 그 주 7일(토 ~ 금)에 똑같이 넣는다. 날짜별 자료가 아니다
- 나이 × 업종을 함께 본 줄이 없어 나이 줄(60대 · 70대 이상)만 쓴다. 곱해서 어림하면 흔들림이 커져
  아무 일 없는 줄의 16%에서 울렸다(2026-11-04 시험)
- n · amount 는 건수 · 금액이 아니라 수준을 1000 배 한 값이다
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "derived_public"
REGION = {"11010": "11230", "32020": "32010"}
AGE = {"60": "60대", "70": "70대 이상"}
START = "2023-01-01"


def main(path: str) -> None:
    keep = []
    types = {"지역공통코드식별자": str, "다른공통코드식별자": str}
    for chunk in pd.read_csv(path, encoding="cp949", chunksize=500_000, dtype=types):
        hit = chunk["지표구성식별자"].isin([11]) & chunk["지역공통코드식별자"].isin(REGION)
        keep.append(chunk[hit])
    d = pd.concat(keep)
    d["week"] = pd.to_datetime(d["날짜"])
    d = d[d["week"] >= START]
    d["level"] = 1 + d["자료값"]
    d["code"] = d["다른공통코드식별자"].fillna("").astype(str).str.lstrip("0")
    rows = []
    for rg, sgg in REGION.items():
        part = d[d["지역공통코드식별자"] == rg]
        ages = part[part["지표구성식별자"] == 11]
        for code, name in AGE.items():
            est = ages[ages["code"] == code].set_index("week")["level"].dropna()
            for wk, v in est.items():
                for k in range(7):
                    rows.append((sgg, wk - pd.Timedelta(days=k), name, "전체", "all", v * 1000))
    t = pd.DataFrame(
        rows, columns=["sgg_cd", "day", "age_group", "industry_group", "time_band", "n"]
    )
    t["n"] = np.round(t["n"]).astype(int)
    t["amount"] = t["n"]
    t = t.sort_values(["sgg_cd", "age_group", "industry_group", "day"])
    t["day"] = t["day"].dt.strftime("%Y-%m-%d")
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "card_pay_day.csv", index=False)
    print(len(t), t["day"].min(), t["day"].max())


if __name__ == "__main__":
    main(sys.argv[1])
