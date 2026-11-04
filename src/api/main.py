"""취약 돌보미 — 화면(web/) + 대시보드 · 시뮬레이션 API.

화면 구성은 스토리보드 v1.3(비서 · 대시보드 · 시뮬레이션)을 따른다.

    uv run uvicorn src.api.main:app --port 8000
    → http://127.0.0.1:8000

- GET /api/meta                         지역 · 기준일 · 비서 주소
- GET /api/board?region=강남구           대시보드 홈(DSH-100) · 동 목록(103) · 줄어든 사람들(103G)
- GET /api/geo?region=강남구             지도(DSH-101) 동 경계
- GET /api/chart?region=&age=&group=    예상한 값과 실제 값(DSH-104)
- GET /api/dongs/{dong_cd}              동별 칸(DSH-105 · 105B) — 등급 · 이유 · 기관 · 1억 효과
- GET /api/simulation/demo              시뮬레이션 결과 예시(역삼1동, SIM-104 · 106)
- /api/auth/*                           회원가입 · 로그인 · 아이디/비밀번호 찾기(src/auth, 10-25).
                                        위의 API 는 모두 로그인한 회원만 — 아니면 401

【판단】 비서(src/api/assistant.py)는 따로 띄운다(키가 필요하다) — 비서 메뉴가 그 주소를 연다
"""

import json
import os
import time
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.auth.routes import require_member
from src.auth.routes import router as auth_router
from src.dashboard import cards, detection, grades
from src.simulation import engine, text
from src.simulation import graph as sim_graph

WEB = Path(__file__).parents[2] / "web"
# 【판단】 비서 시험 화면 주소 — 팀장 README 의 기본 포트(8010). 그 포트를 다른 프로그램이 쓰면
#   ASSISTANT_URL=http://127.0.0.1:8020 처럼 환경변수로 바꾼다
ASSISTANT_URL = os.environ.get("ASSISTANT_URL", "http://127.0.0.1:8010")

app = FastAPI(title="취약 돌보미")
# 【판단】 10-25 팀장 "시뮬레이션이나 이런것들 로그인해야지만 가능하게"
#        → /api/auth/*(로그인 · 가입 · 찾기)만 그냥 열고,
#        대시보드 · 시뮬레이션 API 는 모두 로그인한 회원만(LOGIN)
app.include_router(auth_router)
LOGIN = [Depends(require_member)]


def _region_rows(region: str):
    t, _ = cards.dong_cards()
    part = t[t["region"] == region]
    if part.empty:
        raise HTTPException(404, f"지역 없음: {region}")
    return part


def _merge_grade(card_grade: str | None, skt_grade: str | None) -> str | None:
    # 【기능】 카드 추정 등급과 SKT 경보 중 더 높은 쪽
    found = [g for g in (card_grade, skt_grade) if g in grades.GRADES]
    return min(found, key=grades.GRADES.index) if found else None


def _ref(ref: str | None) -> date | None:
    # 【기능】 화면이 고른 기준일(YYYY-MM-DD) → date. 안 고르면 자료 마지막 날,
    #   카드 자료가 없으면 None
    # 【판단】 고를 수 있는 범위(grades.ref_range) 밖이면 422 — 평소선이 없는 날을 판정하지 않게
    rng = grades.ref_range()
    if rng is None:
        return None
    if not ref:
        return rng[1]
    try:
        d = date.fromisoformat(ref)
    except ValueError:
        raise HTTPException(422, {"problems": [f"기준일 모양이 아니에요: {ref}"]}) from None
    if not rng[0] <= d <= rng[1]:
        raise HTTPException(
            422, {"problems": [f"기준일은 {rng[0]} ~ {rng[1]} 사이에서 골라 주세요."]}
        )
    return d


def _skt(part, ref: date) -> dict:
    # 【기능】 동마다 SKT 경보 (등급, 까닭) — 기준일이 든 달의 값
    # 【판단】 달 표(dong_alert_month.csv)가 없으면 동 카드의 경보(마지막 달)를 그대로 쓴다
    months = cards.alert_month()
    if months is None:
        return {
            r["dong"]: (cards.summary(r)["alert_grade"], r.get("alert_why"))
            for _, r in part.iterrows()
        }
    month = months.get(ref.year * 100 + ref.month, {})
    return {r["dong"]: month.get(r["dong_cd"], (None, None)) for _, r in part.iterrows()}


def _graded(part, ref) -> tuple[dict, dict, dict]:
    # 【기능】 기준일 ref 의 동 등급(카드 추정 + SKT 경보 중 높은 쪽)과 이유, 그리고 걸린 신호
    # 【판단】 이번 주 · 지난주 · 4주 흐름 · 몇 주째를 모두 이 함수 하나로 센다 — 서로 다른 셈을
    #   견주면 ▲▼ 가 거짓으로 뜬다. SKT 경보는 달 자료(12월)라 같은 달 안에서는 같은 값이다
    b = grades.board(part["region"].iloc[0], part["dong"].tolist(), ref)
    assert b is not None  # 카드 자료가 있을 때만 부른다
    skt = _skt(part, ref)
    grade, why, signals = {}, {}, {}
    for d, g in b["dong_grade"].items():
        merged = _merge_grade(g, skt[d][0])
        grade[d] = merged
        # 【기능】 관심 이상으로 켜진 신호 — 카드 · SKT 둘 다면 같은 등급 안에서 먼저 간다
        signals[d] = [
            name
            for name, sg in (("카드", g), ("SKT", skt[d][0]))
            if sg in grades.GRADES and sg != "평상"
        ]
        if merged == g and b["dong_why"][d]:
            why[d] = {**b["dong_why"][d], "rule": grades.RULE[g], "source": "카드"}
        elif merged not in (None, "평상"):
            why[d] = {
                "rule": skt[d][1] if isinstance(skt[d][1], str) else "SKT 유동 경보",
                "source": "SKT",
            }
        else:
            why[d] = None
    return grade, why, signals


def _visit_order(rows: list[dict]) -> None:
    # 【기능】 방문 순서(1, 2, 3 …) — 등급이 높은 동 먼저, 같은 등급 안에서는
    #   ① 걸린 신호가 많은 동(카드 + SKT) ② 그 등급이 오래 이어진 동(몇 주째)
    #   ③ 고립 위험 바탕 인원(est_n)이 많은 동 순. 평상 · 등급 없음은 순서를 매기지 않는다
    # 【판단】 등급은 '얼마나 줄었나', 순서는 '어디부터 갈까' — 같은 등급 동들은 같은 구 단위
    #   카드 줄을 나눠 받아 카드만으로는 차이가 없으므로, 동마다 값이 다른 것으로 가른다(10-27)
    graded = [r for r in rows if r["grade"] in grades.GRADES and r["grade"] != "평상"]
    graded.sort(
        key=lambda r: (
            grades.GRADES.index(r["grade"]),
            -len(r["signals"]),
            -(r["weeks"] or 0),
            -(r["est_n"] or 0),
        )
    )
    for r in rows:
        r["visit_rank"] = None
    for i, r in enumerate(graded, 1):
        r["visit_rank"] = i


def _priority(row: dict) -> float:
    # 【기능】 동 우선순위 점수 — 등급이 높을수록, 혼자 사는 80세 이상이 많을수록, 고립자 중
    #   기초수급 몫이 클수록 앞
    # 【판단】 등급이 첫째 기준(곱하기 1,000,000), 같은 등급 안에서 인원 × (1 + 수급 몫)
    rank = len(grades.GRADES) - grades.GRADES.index(row["grade"]) if row["grade"] else 0
    vuln = (row["solo80"] or 0) * (1 + (row["who_basic"] or 0) / 100)
    return rank * 1_000_000 + vuln


@app.get("/api/meta", dependencies=LOGIN)
def meta() -> dict:
    t, has_contest = cards.dong_cards()
    regions = [r for r in ["강남구", "춘천시"] if r in set(t["region"])]
    ref = grades.ref_date()
    rng = grades.ref_range()
    return {
        "regions": regions,
        "has_contest_data": has_contest,
        "ref_date": ref.isoformat() if ref else None,
        "ref_min": rng[0].isoformat() if rng else None,
        "assistant_url": ASSISTANT_URL,
    }


@app.get("/api/board", dependencies=LOGIN)
def board(region: str = "강남구", ref: str | None = None) -> dict:
    # 【기능】 대시보드 홈 — ref(기준일, YYYY-MM-DD)를 주면 그날까지의 자료로 등급을 매긴다
    part = _region_rows(region)
    dongs = part["dong"].tolist()
    rng = grades.ref_range()
    day = _ref(ref)
    b = grades.board(region, dongs, day) if day else None
    # 【판단】 카드 자료가 없으면 day · b 가 None — 등급 칸만 비우고 나머지는 그대로 보낸다
    weeks = [_graded(part, day - timedelta(days=7 * k)) for k in range(8)] if day and b else []
    pp = grades.people()
    rows = []
    for _, r in part.sort_values("est_n", ascending=False).iterrows():
        s = cards.summary(r)
        d = r["dong"]
        g = weeks[0][0][d] if b else None
        # 【기능】 몇 주째 — 이번 주와 같은 등급이 지난주들로 거슬러 몇 주 이어졌나(최대 8주)
        run = 0
        for wk in weeks:
            if wk[0][d] != g:
                break
            run += 1
        s.update(
            {
                "grade": g,
                "weeks": run if b else None,
                "why": weeks[0][1][d] if b else None,
                "signals": weeks[0][2][d] if b else [],
                "solo80": pp.get(d, {}).get("solo80"),
                "youth": grades.youth(d),
                "helpers": grades.helpers(d),
                "who_basic": float(r["who_basic"])
                if "who_basic" in r and pd.notna(r["who_basic"])
                else None,
            }
        )
        s["priority"] = _priority(s)
        rows.append(s)
    _visit_order(rows)
    count = lambda wk: {g: sum(v == g for v in wk[0].values()) for g in grades.GRADES}  # noqa: E731
    # 【기능】 4주 흐름(DSH-100 ②) — 3주 전 · 2주 전 · 지난주 · 이번 주 등급별 동 수
    trend = (
        [
            {"ref": (day - timedelta(days=7 * k)).isoformat(), "counts": count(weeks[k])}
            for k in (3, 2, 1, 0)
        ]
        if day and b
        else []
    )
    return {
        "region": region,
        "ref_date": b["ref_date"] if b else None,
        "ref_min": rng[0].isoformat() if rng else None,
        "ref_max": rng[1].isoformat() if rng else None,
        "counts": trend[-1]["counts"] if b else None,
        "last_week": trend[-2]["counts"] if b else None,
        "trend": trend,
        "holidays_this_week": grades.holiday_days(day - timedelta(days=6), day)
        if day and b
        else [],
        "groups": b["groups"] if b else [],
        "rules": grades.RULE,
        "next_week": _next_week(region, dongs, part, day) if day and b else None,
        "dongs": rows,
    }


def _next_week(region: str, dongs: list[str], part, ref: date) -> dict:
    # 【기능】 다음 주 예상 — 카드 등급의 두 경우(이어짐 · 반쯤 회복)에 SKT 경보를 똑같이 얹는다
    nw = grades.next_week(region, dongs, ref)
    assert nw is not None  # 카드 자료가 있을 때만 부른다
    skt = {d: g for d, (g, _) in _skt(part, ref).items()}
    for key in ("dong_grade", "dong_grade_recover"):
        nw[key] = {d: _merge_grade(g, skt[d]) for d, g in nw[key].items()}
    both = [
        {g: sum(v == g for v in nw[key].values()) for g in grades.GRADES}
        for key in ("dong_grade", "dong_grade_recover")
    ]
    nw["counts_range"] = {g: sorted([both[0][g], both[1][g]]) for g in grades.GRADES}
    return nw


@app.get("/api/geo", dependencies=LOGIN)
def geo(region: str = "강남구") -> dict:
    # 【기능】 담당 지역의 동 경계(공개 자료, 2025-12-31 판) — dong_cd 앞 5자리로 거른다
    sgg = grades.SGG.get(region)
    if sgg is None:
        raise HTTPException(404, f"지역 없음: {region}")
    g = json.loads((grades.PUBLIC / "admdong_ver20251231.geojson").read_text(encoding="utf-8"))
    feats = [
        {
            "type": "Feature",
            "geometry": f["geometry"],
            "properties": {
                "dong_cd": f["properties"]["adm_cd"],
                "dong": f["properties"]["adm_nm"].split()[-1],
            },
        }
        for f in g["features"]
        if f["properties"]["adm_cd"].startswith(sgg)
    ]
    return {"type": "FeatureCollection", "features": feats}


@app.get("/api/chart", dependencies=LOGIN)
def chart(
    region: str = "강남구", age: str = "70대 이상", group: str = "전체", ref: str | None = None
) -> list[dict]:
    if grades.card() is None:
        raise HTTPException(404, "카드 결제 자료가 없어요")
    whole = age == "60대 이상" and group == "전체"
    if not whole and (age not in grades.AGES or group not in grades.LIFE):
        raise HTTPException(404, f"없는 묶음: {age} · {group}")
    return grades.chart(region, age, group, end=_ref(ref))


@app.get("/api/dongs/{dong_cd}", dependencies=LOGIN)
def dong(dong_cd: str, ref: str | None = None) -> dict:
    t, _ = cards.dong_cards()
    hit = t[t["dong_cd"] == dong_cd]
    if hit.empty:
        raise HTTPException(404, f"동 없음: {dong_cd}")
    out = cards.detail(hit.iloc[0])
    b = board(out["region"], ref)
    mine = next(x for x in b["dongs"] if x["dong_cd"] == dong_cd)
    why = mine["why"]
    # 【기능】 근거 세 줄(DSH-102) — 카드 줄 때문에 오른 등급일 때만 그 줄로 잰다
    ev = None
    day = _ref(ref)
    if day and why and why.get("source") == "카드":
        ev = grades.evidence(out["region"], why["age"], why["group"], day)
    nw = b["next_week"]
    out.update(
        {
            "grade": mine["grade"],
            "weeks": mine["weeks"],
            "solo80": mine["solo80"],
            "helpers": mine["helpers"],
            "youth": mine["youth"],
            "why": why,
            "evidence": ev,
            "next_grade": nw["dong_grade"].get(out["dong"]) if nw else None,
            "next_grade_recover": nw["dong_grade_recover"].get(out["dong"]) if nw else None,
        }
    )
    return out


@app.get("/api/detection", dependencies=LOGIN)
def detection_rates() -> list[dict]:
    # 【기능】 규칙 성능(DSH-100H 도움말) — 줄어듦을 심었을 때 찾아낸 몫 · 안 심었을 때 잘못 울린 몫
    if grades.card() is None:
        raise HTTPException(404, "카드 결제 자료가 없어요")
    return _detection_cached()


@lru_cache(maxsize=1)
def _detection_cached() -> list[dict]:
    # 【판단】 줄 18개 × 기준일 11개 × 경우 8개 — 5초쯤 걸려 한 번만 계산해 기억한다
    ref = grades.ref_date()
    assert ref is not None
    ends = pd.date_range(end=pd.Timestamp(ref), periods=22, freq="7D")
    return detection.detection_table([d.strftime("%Y-%m-%d") for d in ends]).to_dict("records")


@app.get("/api/simulation/demo", dependencies=LOGIN)
def simulation_demo() -> dict:
    demo = cards.sim_demo()
    if demo is None:
        raise HTTPException(404, "시뮬레이션 요약 파일이 없어요")
    return demo


class SimInput(BaseModel):
    # 【기능】 시뮬레이션 입력 칸(SIM-100) — 돈은 1년 만원, overrides 는 [고치기]로 정한 값
    region: str = "강남구"
    dongs: list[str]
    who: str = "80세 이상 혼자 사는 분"
    kind: str = "찾아가서 살피기(방문)"
    money: float | None = None
    years: int = Field(2, ge=1, le=3)
    order: str = "무작위"
    compare: str = "모델 위험 순"
    overrides: dict[str, float] = {}


class ReverseInput(BaseModel):
    region: str = "강남구"
    dongs: list[str]
    who: str = "80세 이상 혼자 사는 분"
    kind: str = "찾아가서 살피기(방문)"
    goal: float = Field(gt=0)
    years: int = Field(2, ge=1, le=3)
    order: str = "무작위"
    overrides: dict[str, float] = {}


# 【판단】 돈 칸이 비면 전국 방문 · 안부 사업 22건의 가운데 값(지방재정365 2025, SIM-105)
MONEY_MEDIAN = 800


def _sim_check(region: str, dongs: list[str], who: str, kind: str, order: str) -> list[str]:
    # 【기능】 입력 검사(SIM-100E2) — 담당 지역 밖 동 · 모르는 대상 · 종류 · 순서. 동 이름 → dong_cd
    if engine.inputs.load() is None:
        raise HTTPException(404, "시뮬레이션 재료가 없어요")
    part = _region_rows(region)
    code = dict(zip(part["dong"], part["dong_cd"], strict=True))
    outside = [d for d in dongs if d not in code and d not in code.values()]
    problems = [f"{d}은(는) 담당 지역({region})이 아닙니다." for d in outside]
    if not dongs:
        problems.append("동을 하나 이상 고르세요.")
    if who not in engine.WHO:
        problems.append(f"모르는 대상: {who}")
    if kind not in engine.KINDS:
        problems.append(f"모르는 정책 종류: {kind}")
    if order not in ("무작위", "모델 위험 순", "고립자 먼저", engine.APPLY):
        problems.append(f"모르는 순서: {order}")
    elif order == engine.APPLY and who != engine.YOUTH:
        problems.append(
            f"'{engine.APPLY}'는 청년 대상에서만 고를 수 있어요(근거가 청년 사업 실적)."
        )
    if problems:
        raise HTTPException(422, {"problems": problems})
    return [code.get(d, d) for d in dongs]


@app.post("/api/simulation/run", dependencies=LOGIN)
def simulation_run(x: SimInput) -> dict:
    # 【기능】 입력대로 다시 계산(SIM-104 ~ 107) — 이 안 · 비교 안 · 보수적 경우 · 흔드는 값
    started = time.time()
    cds = _sim_check(x.region, x.dongs, x.who, x.kind, x.order)
    money = x.money if x.money else MONEY_MEDIAN
    over = {k: v for k, v in x.overrides.items() if k in ("base_stay", "nnt", "cost")}
    # 【판단】 청년은 은둔을 고르게 뿌려 모델 점수가 은둔을 못 가른다(점수 평균 은둔 0.068 · 아님
    #   0.067, 역삼1동 10-29) → 비교 안의 기본 '모델 위험 순'을 '알려서 신청받기'로 바꾼다
    youth_compare = x.who == engine.YOUTH and x.compare == "모델 위험 순"
    compare = engine.APPLY if youth_compare else x.compare
    # 【판단】 10-26 계산 순서 · 갈림길(대상 0명 · 설명글 숫자 검사)은 LangGraph 그래프가 맡는다
    #   (src/simulation/graph.py). 여기는 입력 검사와 HTTP 응답만
    request = {**x.model_dump(), "money": money, "money_filled": not x.money, "dong_cds": cds}
    out = sim_graph.run(
        request, cds, x.who, x.kind, money * 10_000, x.years, x.order, compare, over
    )
    if out is None:
        raise HTTPException(
            422, {"problems": ["고른 조건에 맞는 분이 0명입니다. 대상이나 동을 넓혀 주세요."]}
        )
    return {**out, "seconds": round(time.time() - started, 2)}


class ReadInput(BaseModel):
    text: str
    form: dict


@app.post("/api/simulation/read", dependencies=LOGIN)
def simulation_read(x: ReadInput) -> dict:
    # 【기능】 설명글 읽기(SIM-102 · 103) — [실행] 전에 칸과 글이 다른지 묻는다
    return text.read_text(x.text, x.form)


@app.post("/api/simulation/reverse", dependencies=LOGIN)
def simulation_reverse(x: ReverseInput) -> dict:
    # 【기능】 거꾸로 계산(SIM-108) — 목표 인원을 줄이는 1년 최소 금액
    cds = _sim_check(x.region, x.dongs, x.who, x.kind, x.order)
    over = {k: v for k, v in x.overrides.items() if k in ("base_stay", "nnt", "cost")}
    r = engine.reverse(cds, x.who, x.kind, x.goal, x.years, x.order, overrides=over)
    if r is None:
        raise HTTPException(422, {"problems": ["고른 조건에 맞는 분이 0명입니다."]})
    return {**r, "goal": x.goal}


# 【판단】 API 를 먼저 등록하고 화면은 맨 끝에 — "/" 가 위 경로들을 가로채지 않게
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
