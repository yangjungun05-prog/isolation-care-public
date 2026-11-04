"""대시보드 등급(공개판: 나우캐스트 주 값을 7일로 펼쳐 넣음)

- 줄(series) = 시군구 × 나이(80대 이상 · 70대 · 60대) × 업종 묶음(의료 · 장보기 · 음식·카페)
- 예상한 값 = 지난 4주 같은 요일의 가운데값(공휴일 · 많이 낮은 날은 빼고 — 32단계와 다른 점)
- 예상 범위 = 예상한 값 × (공휴일이 아닌 날의 실제 ÷ 예상) 분위수 — 진한 띠 80%, 옅은 띠 95%
- '평소보다 크게 적은 날' = 공휴일이 아닌 날, 실제 결제 건수가 옅은 띠(95%) 아래

등급(DSH-100H, 문구는 RULE): 위험 = 경고가 연휴가 끝나고 1주가 지나도 이어짐 ·
경고 = 최근 2주 중 절반 넘는 날 평소의 절반도 안 됨 · 주의 = 최근 7일 중 크게 적은 날 3일 이상 ·
관심 = 2일 · 평상 = 그 밖
【판단】 문구에는 늘 주어(무엇의 결제 건수)와 비교 대상(평소 건수)을 넣는다 — "절반도 안 됨"만으로는
       무엇의 절반인지 알 수 없다(10/23 사용자 지적)
【판단】 카드는 시군구 자료다 → 동 등급은 "그 나이 인구 비율이 높은 동"에 나눠 붙인 추정이다
"""

import json
from datetime import date, timedelta
from functools import lru_cache
from typing import cast

import holidays
import numpy as np
import pandas as pd

from src.dashboard import cards
from src.dashboard.cards import ROOT

PUBLIC = ROOT / "data" / "public"
SGG = {"강남구": "11230", "춘천시": "32010"}
AGES = {"70대 이상": ["70대 이상"], "60대": ["60대"]}
LIFE = ["전체"]
GRADES = ["위험", "경고", "주의", "관심", "평상"]
RULE = {
    "위험": "경고가 연휴가 끝나고 1주가 지나도 이어져요",
    "경고": "최근 2주 중 절반 넘게, 카드 이용 수준이 평소의 절반도 안 됐어요",
    "주의": "최근 4주 중 3주 이상, 카드 이용 수준이 평소보다 크게 낮았어요",
    "관심": "최근 4주 중 2주, 카드 이용 수준이 평소보다 크게 낮았어요",
    "평상": "카드 이용 수준이 평소 범위 안이에요",
}


@lru_cache(maxsize=1)
def card() -> pd.DataFrame | None:
    # 【기능】 나우캐스트를 펼친 카드 표(scripts/build_public_data.py). 없으면 None
    # 【판단】 cards.DERIVED 를 부를 때마다 읽는다 — 시험에서 폴더를 바꿔 끼울 수 있게
    path = cards.DERIVED / "card_pay_day.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["day"], dtype={"sgg_cd": str})


# 【판단】 범위(분위수)는 마지막 28일을 빼고 잰다 — 지금 판정할 날이 범위를 넓히지 않게
CALIB_GAP = 28


@lru_cache(maxsize=64)
def daily(region: str, age: str, group: str) -> pd.Series:
    # 【기능】 줄 하나(시군구 × 나이 × 업종 묶음)의 날마다 결제 건수 — 빈 날은 0
    # 【판단】 "60대 이상" · "전체" 는 그래프의 [전체] 탭(DSH-104 ①) — 줄 아홉을 합친 것
    d = card()
    if d is None:
        raise FileNotFoundError("카드 결제 표가 없어요 — 노트북 02 의 31단계")
    ages = AGES.get(age) or [a for v in AGES.values() for a in v]
    groups = [group] if group in LIFE else LIFE
    part = d[(d["sgg_cd"] == SGG[region]) & d["age_group"].isin(ages)]
    n = pd.Series(part[part["industry_group"].isin(groups)].groupby("day")["n"].sum())
    return n.asfreq("D", fill_value=0)


@lru_cache(maxsize=64)
def series(region: str, age: str, group: str) -> pd.DataFrame:
    # 【기능】 줄 하나의 날마다 실제 · 예상 · 범위 · 많이 낮음
    return build(daily(region, age, group))


def build(x: pd.Series) -> pd.DataFrame:
    # 【기능】 날마다 결제 건수 → 예상한 값 · 범위 · 많이 낮음 · 절반도 안 됨 표
    #   (detection.py 가 결제를 일부러 줄인 가짜 줄을 넣어 규칙을 시험할 때도 쓴다)
    days = pd.DatetimeIndex(x.index)
    kr = holidays.KR(years=sorted({t.year for t in days}))
    hol = pd.Series([t.date() in kr for t in days], index=x.index)

    # 1차 — 노트북 32단계 그대로: 지난 4주 같은 요일 가운데값 → 실제 ÷ 예상 의 분위수
    first = pd.concat([x.shift(7 * k) for k in range(1, 5)], axis=1).median(axis=1)
    ratio = (x / first).where(~hol)
    # 【판단】 범위는 ① 마지막 28일 ② 평소의 절반도 안 되는 날을 빼고 잰다 — 오래 떨어진 날이
    #   섞이면 범위 아래 끝이 같이 내려가 '많이 낮음' · 경고가 다시는 안 뜬다
    calib = ratio[ratio.index <= ratio.index[-1] - pd.Timedelta(days=CALIB_GAP)]
    q = calib[calib >= 0.5].dropna().quantile([0.025, 0.10, 0.90, 0.975])

    # 2차 — 공휴일 · 많이 낮은 날은 '평소' 계산에서 예상값으로 바꿔 끼운다
    # 【판단】 안 그러면 3주 넘게 낮으면 예상선이 같이 내려가 경고 · 위험이 풀려 버린다
    vals, holi = x.to_numpy(dtype=float), hol.to_numpy()
    clean, expected = vals.copy(), np.full(len(vals), np.nan)
    for i in range(28, len(vals)):
        expected[i] = np.median(clean[i - 28 : i : 7])
        if holi[i] or vals[i] < expected[i] * q[0.025]:
            clean[i] = expected[i]

    t = pd.DataFrame({"actual": x, "expected": expected, "clean": clean, "holiday": hol})
    _bands(t, q)
    t.attrs["q"] = q.to_dict()
    return t.dropna(subset=["expected"])


def _bands(t: pd.DataFrame, q) -> None:
    # 【기능】 예상한 값 × 분위수 → 띠 넷, 그리고 '많이 낮음' · '절반도 안 됨' 표시
    for name, qq in [("lo95", 0.025), ("lo80", 0.10), ("hi80", 0.90), ("hi95", 0.975)]:
        t[name] = t["expected"] * q[qq]
    t["low"] = (t["actual"] < t["lo95"]) & ~t["holiday"]
    t["half"] = (t["actual"] < 0.5 * t["expected"]) & ~t["holiday"]


def long_breaks(holiday: pd.Series) -> list[pd.Timestamp]:
    # 【기능】 명절 · 긴 연휴가 끝난 날 목록 — 쉬는 날(공휴일 · 주말)이 3일 넘게 이어지고
    #   공휴일이 하루라도 낀 덩어리의 마지막 날
    days = pd.DatetimeIndex(holiday.index)
    off = holiday.to_numpy() | (days.dayofweek >= 5)
    ends, run, has_hol = [], 0, False
    for day, o, h in zip(days, off, holiday.to_numpy(), strict=True):
        if o:
            run, has_hol = run + 1, has_hol or bool(h)
            continue
        if run >= 3 and has_hol:
            ends.append(day - pd.Timedelta(days=1))
        run, has_hol = 0, False
    return ends


def _until(t: pd.DataFrame, end) -> pd.DataFrame:
    # 【기능】 end 날까지의 줄만 (표 모양 그대로)
    return cast(pd.DataFrame, t[pd.DatetimeIndex(t.index) <= pd.Timestamp(end)])


def grade_at(t: pd.DataFrame, ref: date) -> str:
    # 【기능】 기준일(ref)까지의 자료로 스토리보드 규칙 등급
    upto = _until(t, ref)

    def warn(end: pd.Timestamp) -> bool:
        win = _until(upto, end).tail(14)
        workdays = win[~win["holiday"].astype(bool)]
        return len(workdays) > 0 and float(workdays["half"].mean()) > 0.5

    last = pd.Timestamp(pd.DatetimeIndex(upto.index)[-1])
    if warn(last):
        # 【판단】 위험 = 경고가 명절 · 긴 연휴 뒤 1주가 지나도 안 풀림. 연휴 끝이 7~28일 전이고,
        #   연휴 끝 + 7일에도 경고였으면 위험. 연휴가 없으면 오래 낮아도 경고까지만
        breaks = long_breaks(cast(pd.Series, t["holiday"]))
        ends = [e for e in breaks if 7 <= (last - e).days <= 28]
        return "위험" if ends and warn(ends[-1] + pd.Timedelta(days=7)) else "경고"
    # 【판단】 공개판은 주 값을 7일로 펼친 자료라 최근 4주 중 몇 주인지 센다. 대회판 규칙(7일 중
    #   2 · 3일)이면 아무 일 없는 줄의 21%에서 울렸다. 연휴가 든 주는 낮은 날이 5 ~ 6일이라 반올림
    lows = round(int(upto.tail(28)["low"].sum()) / 7)
    return "주의" if lows >= 3 else "관심" if lows >= 2 else "평상"


@lru_cache(maxsize=1)
def people() -> dict:
    # 【기능】 팀 공개 자료 — 동마다 65세 이상 · 80세 이상 인구와 혼자 사는 분(주민등록 2026-09)
    return json.loads((PUBLIC / "people.json").read_text(encoding="utf-8"))["dongs"]


@lru_cache(maxsize=1)
def profiles() -> dict:
    # 【기능】 팀 공개 자료 — 동마다 청년(19~34세) 인구 · 1인세대 · 거의 집에만 있는 청년 어림
    #   (청년의 삶 실태조사 2024 나이별 비율 × 동 나이 구성, 비서와 같은 값)
    return json.loads((PUBLIC / "dong_profiles.json").read_text(encoding="utf-8"))["dongs"]


def youth(dong: str) -> dict | None:
    # 【기능】 동 하나의 청년 칸(DSH-105 청년) — 인구 · 1인세대 · 은둔 어림 · 연결 창구
    y = profiles().get(dong, {}).get("youth")
    if not y:
        return None
    return {**y, "desk": youth_desk()}


@lru_cache(maxsize=1)
def youth_desk() -> list[str]:
    # 【기능】 고립 · 은둔 청년 연결 창구 안내(청년ON · 행정복지센터 · 청년미래센터, 공개 자료)
    full = json.loads((PUBLIC / "places.json").read_text(encoding="utf-8"))
    return full.get("common", {}).get("youth_desk", [])


@lru_cache(maxsize=1)
def places() -> dict:
    # 【기능】 팀 공개 자료 — 동마다 경로당 · 무료급식소 · 복지관
    return json.loads((PUBLIC / "places.json").read_text(encoding="utf-8"))["dongs"]


def helpers(dong: str) -> int:
    # 【기능】 도와줄 기관 수 = 경로당 + 무료급식소 + 노인복지관
    p = places().get(dong, {})
    n = len(p.get("halls", {}).get("list", []))
    return n + len(p.get("meals", [])) + len(p.get("senior_centers", []))


def ref_date() -> date | None:
    d = card()
    return None if d is None else d["day"].max().date()


def ref_range() -> tuple[date, date] | None:
    # 【기능】 고를 수 있는 기준일의 처음 · 끝(DSH-100 기준일 고르기)
    # 【판단】 처음 = 자료 첫날 + 28일(평소선이 생기는 날) + 8주. 몇 주째를 8주까지 거슬러 세고,
    #   그 주마다 '지난주' 등급도 보므로 7주 + 1주가 더 필요하다. 그보다 앞이면 평소선이 없는
    #   날을 판정하게 된다
    d = card()
    if d is None:
        return None
    first = d["day"].min() + pd.Timedelta(days=28 + 7 * 8)
    return first.date(), d["day"].max().date()


def exposure(dongs: list[str]) -> dict[str, list[str]]:
    # 【기능】 나이마다 '그 나이 인구 비율이 높은 동' 순서 — 앞 절반이 그 나이 줄의 등급을 받는다
    # 【판단】 80대 이상은 pop80, 나머지는 pop65 를 주민 수로 나눈 값
    pp = people()
    out = {}
    for age in AGES:
        key = "pop65"
        share = {d: pp[d][key] / max(pp[d]["residents"], 1) for d in dongs if d in pp}
        out[age] = sorted(share, key=lambda d: share[d], reverse=True)
    return out


def _spread(group_grade: dict, ranked: dict, dongs: list[str]) -> tuple[dict, dict]:
    # 【기능】 줄(나이 × 업종) 등급 → 동 등급과 "어느 줄 때문인가"
    dong_grade: dict[str, str] = {d: "평상" for d in dongs}
    dong_why: dict[str, dict | None] = {d: None for d in dongs}
    for (age, group), g in sorted(group_grade.items(), key=lambda kv: GRADES.index(kv[1])):
        exposed = ranked[age][: max(1, len(ranked[age]) // 2)]
        for d in exposed:
            if GRADES.index(g) < GRADES.index(dong_grade[d]):
                dong_grade[d], dong_why[d] = g, {"age": age, "group": group}
    return dong_grade, dong_why


def board(region: str, dongs: list[str], ref: date | None = None) -> dict | None:
    # 【기능】 대시보드 홈(DSH-100) · 줄어든 사람들(DSH-103G) · 동 등급(추정)과 그 이유
    if card() is None:
        return None
    ref = ref or ref_date()
    assert ref is not None  # card() 가 있으면 기준일도 있다
    ranked = exposure(dongs)
    groups, group_grade = [], {}
    for age in AGES:
        exposed = ranked[age][: max(1, len(ranked[age]) // 2)]
        for group in LIFE:
            t = series(region, age, group)
            now, before = grade_at(t, ref), grade_at(t, ref - timedelta(days=7))
            group_grade[(age, group)] = now
            groups.append(
                {
                    "age": age,
                    "group": group,
                    "grade": now,
                    "last_week": before,
                    "rule": RULE[now],
                    "dongs": ranked[age][:2],
                    "exposed": exposed,
                }
            )
    groups.sort(key=lambda g: GRADES.index(g["grade"]))
    dong_grade, dong_why = _spread(group_grade, ranked, dongs)
    counts = {g: sum(v == g for v in dong_grade.values()) for g in GRADES}
    return {
        "ref_date": ref.isoformat(),
        "counts": counts,
        "groups": groups,
        "dong_grade": dong_grade,
        "dong_why": dong_why,
    }


def evidence(region: str, age: str, group: str, ref: date) -> dict:
    # 【기능】 근거 세 줄(DSH-102) — 지난 7일 얼마나 줄었나(%) · 예상과 비교한 말 · 며칠째 낮은가
    t = series(region, age, group)
    upto = t[t.index <= pd.Timestamp(ref)]
    week = upto.tail(7)
    work = week[~week["holiday"]]
    drop = float(work["actual"].sum() / work["expected"].sum() - 1) if len(work) else 0.0
    if bool(week["low"].any()):
        label = "평소보다 크게 적음"
    elif work["actual"].sum() < work["lo80"].sum():
        label = "평소보다 조금 적음"
    else:
        label = "평소 범위 안"
    # 【판단】 며칠째 = 오늘부터 거꾸로, 진한 띠(80%) 아래인 날이 끊기지 않고 이어진 날 수.
    #   공휴일은 세지도 끊지도 않는다
    days = 0
    for _, r in upto.iloc[::-1].iterrows():
        if r["holiday"]:
            continue
        if r["actual"] >= r["lo80"]:
            break
        days += 1
    return {"age": age, "group": group, "drop_pct": round(drop * 100), "label": label, "days": days}


def next_week(region: str, dongs: list[str], ref: date | None = None) -> dict | None:
    # 【기능】 다음 주 예상(DSH-100 ③ · 101 · 104 · 105) — 다음 7일 예상선과, "이번 주 낮은 만큼이
    #   이어지면 / 반쯤 돌아오면" 두 경우의 등급
    # 【판단】 예상선은 7일 전까지의 값만 쓰므로 다음 7일도 지금 자료로 바로 나온다.
    #   실제 결제는 아직 모른다 → 등급은 가정 둘(이어짐 · 반쯤 회복)의 범위로만 말한다
    if card() is None:
        return None
    ref = ref or ref_date()
    assert ref is not None  # card() 가 있으면 기준일도 있다
    end = pd.Timestamp(ref) + pd.Timedelta(days=7)
    future = pd.date_range(pd.Timestamp(ref) + pd.Timedelta(days=1), end)
    kr = holidays.KR(years=sorted({d.year for d in future}))
    fut_hol = pd.Series([d.date() in kr for d in future], index=future)
    ranked = exposure(dongs)
    lines, grades_by = {}, {"persist": {}, "recover": {}}
    for age in AGES:
        for group in LIFE:
            t = series(region, age, group)
            past = t[t.index <= pd.Timestamp(ref)]
            q = pd.Series(t.attrs["q"])
            clean = pd.Series(past["clean"])
            exp = [
                float(
                    np.median(
                        [clean.get(d - pd.Timedelta(days=7 * k), np.nan) for k in (1, 2, 3, 4)]
                    )
                )
                for d in future
            ]
            # 지난주 같은 요일의 실제 ÷ 예상 (공휴일이었으면 1)
            ratio = []
            for d in future:
                prev = d - pd.Timedelta(days=7)
                if prev not in past.index:
                    ratio.append(1.0)
                    continue
                r = past.loc[prev]
                ok = not r["holiday"] and r["expected"] > 0
                ratio.append(float(r["actual"] / r["expected"]) if ok else 1.0)
            ratio = np.array(ratio)
            lines[f"{age}|{group}"] = [
                {
                    "day": d.strftime("%Y-%m-%d"),
                    "expected": round(e, 1),
                    "lo80": round(e * q[0.10], 1),
                    "hi80": round(e * q[0.90], 1),
                    "lo95": round(e * q[0.025], 1),
                    "hi95": round(e * q[0.975], 1),
                    "holiday": bool(h),
                }
                for d, e, h in zip(future, exp, fut_hol, strict=True)
            ]
            for case, r in [("persist", ratio), ("recover", (1 + ratio) / 2)]:
                f = pd.DataFrame(
                    {"actual": np.array(exp) * r, "expected": exp, "holiday": fut_hol.to_numpy()},
                    index=future,
                )
                _bands(f, q)
                ext = pd.concat([past.loc[:, list(f.columns)], f])
                grades_by[case][(age, group)] = grade_at(ext, ref + timedelta(days=7))
    out = {}
    for case, gg in grades_by.items():
        dg, _ = _spread(gg, ranked, dongs)
        out[case] = {
            "counts": {g: sum(v == g for v in dg.values()) for g in GRADES},
            "dong_grade": dg,
        }
    lo_hi = {g: sorted([out["persist"]["counts"][g], out["recover"]["counts"][g]]) for g in GRADES}
    return {
        "from": future[0].strftime("%Y-%m-%d"),
        "to": future[-1].strftime("%Y-%m-%d"),
        "holidays": holiday_days(future[0].date(), future[-1].date()),
        "counts_range": lo_hi,
        "dong_grade": out["persist"]["dong_grade"],
        "dong_grade_recover": out["recover"]["dong_grade"],
        "lines": lines,
    }


def chart(region: str, age: str, group: str, days: int = 56, end: date | None = None) -> list[dict]:
    # 【기능】 예상한 값과 실제 값(DSH-104) — end(기준일, 없으면 자료 마지막 날)까지 days 일
    t = series(region, age, group)
    if end is not None:
        t = _until(t, end)
    t = t.tail(days)
    out = t.reset_index(names="day")
    out["day"] = out["day"].dt.strftime("%Y-%m-%d")
    cols = ["day", "actual", "expected", "lo80", "hi80", "lo95", "hi95", "low", "holiday"]
    return pd.DataFrame(out[cols]).round(1).to_dict(orient="records")


def holiday_days(start: date, end: date) -> list[str]:
    # 【기능】 기간 안의 공휴일 이름 — 이번 주 안내(DSH-100 ③)에 쓴다
    kr = holidays.KR(years=sorted({start.year, end.year}), language="ko")
    out, d = [], start
    while d <= end:
        if d in kr:
            out.append(f"{d.month}/{d.day} {kr[d].split(';')[0]}")
        d += timedelta(days=1)
    return out
