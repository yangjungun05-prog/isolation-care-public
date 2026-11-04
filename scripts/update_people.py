"""동마다 사람 수 새로 만들기 — 행정안전부 주민등록(공공데이터포털 15097972 · 15097973,
이용허락범위 제한 없음).

    uv run python scripts/update_people.py <내려받은 폴더> 2026-09-30
    → data/public/people.json (그 달 + 1년 전 같은 달)

【정함 10-16 팀장】 자료는 2026 최신 판("1,2,3,4 ㄱㄱ"). '오늘 챙길 일' 카드가 먼저 읽는다
       (80세 이상 혼자 사시는 분 · 65세 이상 혼자 사시는 분 1년 새). 챗봇은 그 뒤에 옮긴다
【기능】 받는 파일(공공데이터포털 자료 화면 [다운로드], 과거 판은 '주기성 과거 데이터'):
       - 행안부_행정동_성별연령별_주민등록1인세대수_YYYYMMDD.csv (그 달 · 1년 전 같은 달)
       - 행안부_행정동_성별연령별_주민등록인구수_YYYYMMDD.csv (그 달)
       칸: 행정기관코드 · 기준연월 · 시도명 · 시군구명 · 읍면동명 · 계 · 남자 · 여자 · 0세남자 …
       110세이상 여자
【판단】 동은 시군구명 + 읍면동명으로 찾는다(dong_profiles.json 의 47곳). 하나라도 없으면 멈춘다
       (행정동이 바뀌었으면 사람이 확인해야 한다)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "public" / "people.json"
PROFILES = ROOT / "data" / "public" / "dong_profiles.json"
SOURCE = (
    "행정안전부 주민등록 1인세대 · 인구(공공데이터포털 15097973 · 15097972, 이용허락범위 제한 없음)"
)
AGE = re.compile(r"^(\d+)세")


def _rows(path: Path) -> dict[tuple[str, str], dict]:
    with path.open(encoding="cp949") as f:
        return {(r["시군구명"], r["읍면동명"]): r for r in csv.DictReader(f)}


def _n(v: str) -> int:
    return int(str(v).replace(",", "").strip() or 0)


def _ages(row: dict, lo: int, hi: int = 999) -> int:
    total = 0
    for col, v in row.items():
        m = AGE.match(col or "")
        if m and lo <= int(m.group(1)) <= hi:
            total += _n(v)
    return total


def build(folder: Path, basis: str) -> dict:
    d = dt.date.fromisoformat(basis)
    prev = d.replace(year=d.year - 1)
    tag, ptag = d.strftime("%Y%m%d"), prev.strftime("%Y%m%d")
    solo = _rows(folder / f"행안부_행정동_성별연령별_주민등록1인세대수_{tag}.csv")
    solo_prev = _rows(folder / f"행안부_행정동_성별연령별_주민등록1인세대수_{ptag}.csv")
    pop = _rows(folder / f"행안부_행정동_성별연령별_주민등록인구수_{tag}.csv")
    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    dongs = {}
    missing = []
    for name, p in profiles["dongs"].items():
        key = (p["region"], name)
        if key not in solo or key not in solo_prev or key not in pop:
            missing.append(f"{p['region']} {name}")
            continue
        dongs[name] = {
            "region": p["region"],
            "solo65": _ages(solo[key], 65),
            "solo65_prev": _ages(solo_prev[key], 65),
            "solo80": _ages(solo[key], 80),
            "residents": _n(pop[key]["계"]),
            "pop65": _ages(pop[key], 65),
            "pop80": _ages(pop[key], 80),
            # 【정함 10-19 팀장】 청년 카드는 19 ~ 34세("청년 카드 기준 19세 ~ 34세로 두자")
            "solo_youth": _ages(solo[key], 19, 34),
            "solo_youth_prev": _ages(solo_prev[key], 19, 34),
            "pop_youth": _ages(pop[key], 19, 34),
        }
    if missing:
        raise SystemExit("주민등록 파일에 없는 동: " + ", ".join(missing))
    return {
        "built": dt.date.today().isoformat(),
        "basis": basis,
        "prev": prev.isoformat(),
        "source": SOURCE,
        "dongs": dongs,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    data = build(Path(sys.argv[1]), sys.argv[2])
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    s80 = sum(v["solo80"] for v in data["dongs"].values())
    print(f"{OUT}: 동 {len(data['dongs'])}곳, 기준 {data['basis']}, 80세 이상 1인세대 합 {s80:,}명")
