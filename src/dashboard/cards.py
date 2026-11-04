"""화면이 읽을 동 카드 · 시뮬레이션 요약 — 노트북 02(19 · 41단계)가 만든 파일을 읽는다.

- 동 카드: data/derived_public/dong_card.csv, 없으면 data/processed/dong_base_2025.csv
- 시뮬레이션 요약: 공개판에는 없다(None)

【판단】 DB 대신 파일을 읽는다 — 원래 대회판 구조를 유지. 값은서만 쓰기 때문
"""

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parents[2]
DERIVED = ROOT / "data" / "derived_public"
PROCESSED = ROOT / "data" / "processed"

# 【판단】 dong_cd 8자리 앞 5자리 = 경계 파일의 시군구 (11230 강남 · 32010 춘천)
REGION_OF = {"11230": "강남구", "32010": "춘천시"}


def _parse(cell: object) -> object:
    # 【기능】 CSV 에 JSON 글자로 들어 있는 칸(standout · detail)을 파이썬 값으로
    return json.loads(cell) if isinstance(cell, str) and cell[:1] in "[{" else None


@lru_cache(maxsize=1)
def dong_cards() -> tuple[pd.DataFrame, bool]:
    # 【기능】 동 카드 표와 "대회 자료가 섞였나"를 돌려준다. 한 번 읽으면 기억해 둔다
    derived = DERIVED / "dong_card.csv"
    path = derived if derived.exists() else PROCESSED / "dong_base_2025.csv"
    t = pd.read_csv(path, dtype={"dong_cd": str}, encoding="utf-8-sig")
    t["region"] = t["dong_cd"].str[:5].map(REGION_OF)
    for col in ("standout", "detail"):
        t[col] = t[col].map(_parse)
    # 【판단】 공개판 dong_card.csv 는 공개 자료와 합계표로만 만들었다 → 대회 자료 표시는 늘 거짓
    return t, False


@lru_cache(maxsize=1)
def alert_month() -> dict[int, dict[str, tuple[str | None, str | None]]] | None:
    # 【기능】 SKT 동 경보를 달마다 — {202510: {dong_cd: (등급, 까닭 문장)}}. 파일이 없으면 None
    # 【판단】 동 카드(dong_card.csv)의 경보는 마지막 달(12월) 하나뿐이다. 기준일을 고르면 그 달의
    #   경보를 써야 한다 — 10월을 보는데 12월 경보가 섞이면 안 된다(10-27)
    path = DERIVED / "dong_alert_month.csv"
    if not path.exists():
        return None
    t = pd.read_csv(path, dtype={"dong_cd": str}, encoding="utf-8-sig")
    out: dict[int, dict[str, tuple[str | None, str | None]]] = {}
    for _, r in t.iterrows():
        grade = r["grade"] if isinstance(r["grade"], str) else None
        why = r["why"] if isinstance(r["why"], str) and grade not in (None, "평상") else None
        out.setdefault(int(r["month"]), {})[r["dong_cd"]] = (grade, why)
    return out


def summary(row: pd.Series) -> dict:
    # 【기능】 동 목록 한 줄 — 지도 · 목록에 쓰는 칸만
    def num(col: str) -> float | None:
        v = row.get(col)
        return None if v is None or pd.isna(v) else float(v)

    return {
        "dong_cd": row["dong_cd"],
        "dong": row["dong"],
        "region": row["region"],
        "adult": int(row["adult"]),
        "rate": float(row["rate"]),
        "est_n": int(row["est_n"]),
        "alert_grade": row.get("alert_grade") if isinstance(row.get("alert_grade"), str) else None,
        "visit_fewer_random": num("visit_fewer_random"),
        "visit_fewer_upper": num("visit_fewer_upper"),
    }


def detail(row: pd.Series) -> dict:
    # 【기능】 동 상세 — 목록 칸 + 누가 · 두드러진 이유 · 세부 이유 13개 · 경보 문장
    out = summary(row)
    out.update(
        {
            "who": {
                "75세 이상": row["who_75"],
                "혼자 삶": row["who_alone"],
                "기초수급": row["who_basic"],
            },
            "standout": [
                {
                    "group": s[0].split("|")[0],
                    "reason": s[0].split("|")[1],
                    "pct": s[1],
                    "lift": s[2],
                }
                for s in (row["standout"] or [])
            ],
            "detail": [
                {"group": k.split("|")[0], "reason": k.split("|")[1], "pct": v[0], "lift": v[1]}
                for k, v in (row["detail"] or {}).items()
            ],
            # 【판단】 30단계는 모든 동에 문장을 만든다 → 경보가 걸린 동(평상이 아님)만 보인다
            "alert_why": row.get("alert_why")
            if isinstance(row.get("alert_why"), str) and row.get("alert_grade") != "평상"
            else None,
        }
    )
    return out


def sim_demo() -> dict | None:
    # 【기능】 역삼1동 시뮬레이션 요약(41단계) — 노트북이 새로 만든 것(derived)이 먼저,
    #   없으면 git 에 올린 예시(processed). 둘 다 없으면 None
    # 【판단】 이 파일은 결과 합계(줄어든 인원 · 범위 · 흔드는 값)뿐이라 git 에 올린다 — 응답자 줄 ·
    #   대회 자료는 없다. 재료가 없는 팀원 컴퓨터에서도 시뮬레이션 화면이 예시로 돈다
    for path in (DERIVED / "sim_demo_yeoksam1.json", PROCESSED / "sim_demo_yeoksam1.json"):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None
