"""조건 창고 — 한 동의 어르신 · 청년이 요즘 어떻게 지낼지를 여러 겹의 조건으로 판단한다.

【정함 10-20 팀장】 "수서동의 노인분들이 잘 지내니? 라는 대답에 단순히 '잘지내요!' 같은 식의
       단답보다는 … 무언가 근거가 있어야해" · "변수통제를 철저히해서 최소 5겹 이상으로 변수
       통제를 해서 감싸서 대답하게" · "최신자료들을 창고에 저장해두고 … 그 질문에 대해서 최신
       자료들을 바탕으로 자체적으로 고려해서 답이 나왔으면" · "조건A = 지붕이 많음 조건 B =
       엘리베이터가 없음 조건 C = 노인분들이 많은 곳임 등등. 이런식으로 조건들을 좌르륵 나열"

【기능】 네 단계(모두 코드, 같은 자료면 같은 판단)
  1. 겹(layer) 여덟 — 사람 · 집 · 동네 · 안전망 · 지난 날씨 · 앞으로 날씨 · 달력 · 땅
  2. 조건(Cond) — 겹마다 공개 자료의 가장 새 판(data/public, 자동 받기가 바꿈)에서 계산.
     값 · 같은 지역 동들 가운데 자리 · 해당 여부. 해당 = 같은 지역 동들 가운데 위쪽 3분의 1
     (많을수록 걱정인 값), 또는 아래 정한 기준을 넘음
  3. 겹침(Pattern) — 겹침마다 정한 조건 무리(GROUPS)가 모두 맞고 그 조건들이 서로 다른 겹
     3개 이상일 때만 선다. 겹침의 뜻
     문장은 이 파일에 적은 것만 쓴다(AI가 원인을 지어내지 않게)
  4. 판단 — 선 겹침 수로 한 줄
  AI(글쓴이)는 이 묶음을 읽기 쉬운 말로 옮기기만 한다(writer.OUTLOOK_SYSTEM).

【판단】 기준값(위쪽 3분의 1 · 약국 5km · 공공기관 1km · 7일 · 사흘 · 10명)은 Claude 판단
       (10-20 팀장이 맡김). 카드(today.py)와 같은 기준을 쓴다
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.assistant.data_source import DongData

LAYERS = ("사람", "집", "동네", "안전망", "지난 날씨", "앞으로 날씨", "달력", "땅")
YOUTH_LAYERS = ("사람", "어림", "집", "동네", "지난 날씨", "앞으로 날씨", "달력")
# 【판단】 10-20 알림 피로 조사(lab/night_1020/how_often.py): 이레로 보면 여름 · 겨울 내내
#        날씨 겹침이
#        섰다(춘천 읍면은 본 날의 79%). 지난 날씨는 궂은 날 바로 뒤 사흘만 본다
PAST_DAYS = 3  # 지난 날씨는 어제까지 사흘
AHEAD = 2  # 앞으로 날씨는 오늘 · 내일 · 모레(기상청 단기예보)
HOLIDAY_LEAD = 7  # 긴 연휴가 이레 안에 오면
FAR_PHARM_KM = 5.0  # 카드와 같음(10-16 팀장 '약국으로부터 5KM 이상')
FAR_PUBLIC_KM = 1.0  # 카드와 같음(10-19 팀장이 맡김 → 1km)
NEAR_WALK_KM = 1.0  # 동 지역 약국 · 의원이 이보다 멀면 걸어가기 먼 편
MIN_PEOPLE = 10  # 이보다 적은 집단은 비율로 견주지 않는다(작은 수는 흔들림이 큼)
MIN_YOUTH = 30
STALE_DAYS = 3  # 관측 자료가 이만큼 넘게 늦으면 밝힌다
# 【판단】 10-20 페르소나 o02(구청 팀장): "위쪽 3분의 1이면 어느 구든 항상 걸리는 동 나오는 거
#        아냐?" — 맞다. 같은 지역 안 상대 기준은 늘 3분의 1을 고른다. 그래서 날씨 · 연휴 · 쉬는 날
#        같은 절대 계기가 든 겹침(지금 닥친 걱정)과 상대 조건만으로 선 겹침(평소 구조 걱정)을
#        나눠 말한다
# 【판단】 10-20 알림 피로 조사: 쉬는 날(주말)까지 넣자 읍면은 거의 늘 '지금 닥친 걱정'이었다.
#        지금 닥친 걱정 = 앞으로 사흘 궂은 날씨 · 이레 안 긴 연휴. 지난 사흘 궂은 날씨만이면
#        '지난 궂은 날씨 뒤 걱정'. 주말은 조건으로만 쓴다
NOW_KEYS = {"ahead", "holiday"}
AFTER_KEYS = {"past"}
MAX_DONGS = 3  # 한 번에 판단하는 동(대상 둘이면 조건표 여섯)
KIND_WORD = {"폭우": "비", "한파": "추위", "폭설": "눈", "폭염": "더위"}


@dataclass(eq=False)
class Cond:
    key: str
    layer: str
    label: str  # '80세 이상 혼자 사시는 분이 많음'
    value: str  # '595명(80세 이상 주민 961명 중 62%)'
    place: str = ""  # '강남 22곳 중 2번째로 높음'
    hit: bool = False
    okay: str = ""  # 해당하지 않을 때 쓸 말('약국이 가까움')
    letter: str = ""
    kinds: list[str] = field(default_factory=list)  # 날씨 조건: 넘은 기준 종류
    piece: str = ""  # 겹침의 뜻에 쓸 말(비우면 PIECE[key])

    def line(self) -> str:
        head = f"조건 {self.letter}: " if self.letter else ""
        place = f", {self.place}" if self.place else ""
        return f"{head}{self.label}({self.value}{place}) [{self.layer}]"


@dataclass(eq=False)
class Pattern:
    key: str
    title: str
    meaning: str
    conds: list[Cond]

    def layers(self) -> set[str]:
        return {c.layer for c in self.conds}

    @property
    def now(self) -> bool:
        """지금 닥친 걱정 — 앞으로 사흘 궂은 날씨 · 이레 안 긴 연휴가 든 겹침."""
        return any(c.key in NOW_KEYS for c in self.conds)

    @property
    def after(self) -> bool:
        """지난 궂은 날씨 뒤 걱정 — 지난 사흘 궂은 날씨가 들고 지금 닥친 계기는 없는 겹침."""
        return not self.now and any(c.key in AFTER_KEYS for c in self.conds)

    @property
    def kind(self) -> str:
        if self.now:
            return "지금 닥친 걱정"
        return "지난 궂은 날씨 뒤 걱정" if self.after else "평소 구조 걱정"


@dataclass
class Sheet:
    name: str
    region: str
    target: str  # 어르신 · 청년
    unit: str  # 동 · 면
    conds: list[Cond] = field(default_factory=list)
    patterns: list[Pattern] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # 확인하지 못한 겹(까닭)
    notes: list[str] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    today: date = field(default_factory=date.today)
    rewind: bool = False  # 지난 날을 오늘로 본다(앞으로 날씨는 그날 뒤 관측)
    # 사용자가 지난 날을 말했는가('7월 16일 폭우 때 …'). 되감기(.env AS_OF)만이면 말은 '오늘'
    dated: bool = False

    @property
    def hits(self) -> list[Cond]:
        return [c for c in self.conds if c.hit]

    def get(self, key: str) -> Cond | None:
        return next((c for c in self.conds if c.key == key), None)

    def on(self, *keys: str) -> list[Cond]:
        return [c for k in keys if (c := self.get(k)) and c.hit]

    def verdict(self) -> str:
        when = f"{self.today.isoformat()} 기준 " if self.dated else ""
        who = f"{when}{self.region} {self.name} {self.target}"
        if self.patterns:
            parts = []
            for kind in ("지금 닥친 걱정", "지난 궂은 날씨 뒤 걱정", "평소 구조 걱정"):
                got = [p.title for p in self.patterns if p.kind == kind]
                if got:
                    parts.append(f"{kind} {len(got)}가지({' / '.join(got)})")
            return f"{who} 취약 돌보미 판단: 겹친 걱정 {len(self.patterns)}가지. " + " · ".join(
                parts
            )
        if self.hits:
            return (
                f"{who} 취약 돌보미 판단: 겹친 걱정(정한 모양의 조건 무리가 함께 해당)은 없음. "
                f"따로따로 해당하는 조건 {len(self.hits)}가지"
            )
        return f"{who} 취약 돌보미 판단: 같은 지역 동들과 견줘 두드러지게 해당하는 조건이 없음"


# ── 같은 지역 안의 자리 ──


def _third(n: int) -> int:
    return max(1, math.ceil(n / 3))


def _place(
    region: str, name: str, values: dict[str, float | None], high_bad: bool = True
) -> tuple[int, int] | None:
    """(자리, 몇 곳 중). 1 = 걱정 쪽으로 가장 큼. 값이 없는 동은 빼고 센다."""
    have = {n: v for n, v in values.items() if v is not None}
    if name not in have:
        return None
    order = sorted(have, key=lambda n: (-have[n] if high_bad else have[n], n))
    return order.index(name) + 1, len(order)


def _place_text(region: str, pos: tuple[int, int] | None, word: str) -> str:
    if not pos:
        return ""
    short = {"강남구": "강남", "춘천시": "춘천"}.get(region, region)
    r, n = pos
    return f"{short} {n}곳 중 {r}번째로 {word}" if r > 1 else f"{short} {n}곳 중 가장 {word}"


def _mean(region: str, values: dict[str, float | None]) -> str:
    """지역 평균(몫) — 자리만으로는 얼마나 큰지 모른다(10-20 페르소나 o02: 상대 기준)."""
    xs = [v for v in values.values() if v is not None]
    if not xs:
        return ""
    short = {"강남구": "강남", "춘천시": "춘천"}.get(region, region)
    return f", {short} 평균 {round(sum(xs) / len(xs) * 100)}%"


def _top(pos: tuple[int, int] | None) -> bool:
    return bool(pos) and pos[0] <= _third(pos[1])


def _pct(a: float, b: float) -> int:
    return round(a / b * 100) if b else 0


# ── 자료 꺼내기 ──


def _people_row(data: DongData, name: str) -> dict:
    p = data.people() or {}
    return (p.get("dongs") or {}).get(name) or {}


def _focus_rows(data: DongData, name: str) -> tuple[str, list[dict]]:
    get = getattr(data, "focus", None)
    fv = (get(name) if get else None) or {}
    if not fv:
        return "", []
    return fv.get("unit", "동"), fv.get("villages") or [fv]


def _sum(rows: list[dict], key: str) -> float:
    return sum(r.get(key) or 0 for r in rows)


_CACHE: dict[tuple, dict[str, float | None]] = {}


class _Region:
    """지역 안 동마다 값 — 자리를 매길 때 쓴다(한 번만 계산)."""

    def __init__(self, data: DongData, region: str) -> None:
        self.names = data.region_dongs(region)
        self.data = data
        self.cache: dict[str, dict[str, float | None]] = {}

    def values(self, key: str, fn) -> dict[str, float | None]:
        # 【판단】 자리 매기기는 지역 동 모두의 값이 필요해 조건표마다 다시 세면 지역 카드 하나에
        #        1초가 넘었다(10-20). 자료 판(사람 · 날씨 · 건물 묶음의 객체)이 같으면 다시 쓴다
        token = (id(self.data.people()), id(self.data.weather()), tuple(self.names), key)
        hit = _CACHE.get(token)
        if hit is None:
            if len(_CACHE) > 4096:
                _CACHE.clear()
            hit = _CACHE[token] = {n: fn(n) for n in self.names}
        return hit


# ── 날씨 · 달력 ──


def _thresholds(data: DongData) -> dict:
    return (data.weather() or {}).get("thresholds") or {}


def _over(row: dict, th: tuple) -> bool:
    col, op, v, _unit = th
    x = row.get(col)
    return x is not None and (x >= v if op == ">=" else x <= v)


def _observed(data: DongData, region: str) -> dict[str, dict]:
    return (((data.weather() or {}).get("regions") or {}).get(region) or {}).get("days") or {}


def _long_holiday(data: DongData, today: date) -> tuple[date, int, list[str]] | None:
    """이레 안에 시작하는 3일 이상 연휴(공휴일이 하나라도 낀). 카드와 같은 기준."""
    hol = data.holidays()
    work = lambda x: x.weekday() < 5 and x.isoformat() not in hol  # noqa: E731
    x = today
    end = today + timedelta(days=HOLIDAY_LEAD + 10)
    while x <= end:
        if not work(x) and (x == today or work(x - timedelta(days=1))):
            run = []
            y = x
            while not work(y):
                run.append(y)
                y += timedelta(days=1)
            names = [hol[d.isoformat()] for d in run if d.isoformat() in hol]
            if len(run) >= 3 and names and x <= today + timedelta(days=HOLIDAY_LEAD):
                return x, len(run), list(dict.fromkeys(names))
            x = y
        x += timedelta(days=1)
    return None


def _holiday_runs(data: DongData, start: date, end: date) -> list[tuple[date, int, list[str]]]:
    """start ~ end 사이에 시작하는 3일 이상 연휴(공휴일이 하나라도 낀) — (첫날, 날 수, 이름)."""
    hol = data.holidays()
    work = lambda x: x.weekday() < 5 and x.isoformat() not in hol  # noqa: E731
    out = []
    x = start
    while x <= end:
        if not work(x) and work(x - timedelta(days=1)):
            run, y = [], x
            while not work(y):
                run.append(y)
                y += timedelta(days=1)
            names = [hol[d.isoformat()] for d in run if d.isoformat() in hol]
            if len(run) >= 3 and names:
                out.append((x, len(run), list(dict.fromkeys(names))))
            x = y
        x += timedelta(days=1)
    return out


def _near_holidays(data: DongData, today: date) -> str:
    """【판단】 10-20 페르소나 o03 r6 '추석이 곧 아닌가요? 달력이 틀린 건 아닌지': 2026 추석
    (9월 24일 ~)은 지났는데 '7일 안에 없음'만 있어 달력이 맞는지 답하지 못했다
    → 지난 60일 안의 긴 연휴(세 개까지)와 다음 긴 연휴를 함께 적는다."""
    past = _holiday_runs(data, today - timedelta(days=60), today - timedelta(days=1))
    ahead = _holiday_runs(data, today + timedelta(days=1), today + timedelta(days=400))
    bits = [
        f"지난 긴 연휴 {x.year}년 {x.month}월 {x.day}일부터 {n}일({', '.join(names)})"
        for x, n, names in past[-3:]
    ]
    # 10-20 페르소나 f01 r9 T7: 다음 하나만 적혀 '설 연휴는 자료에 없다' → 셋까지, 달력 범위도
    for i, (x, n, names) in enumerate(ahead[:3]):
        word = "다음 긴 연휴" if i == 0 else "그다음"
        bits.append(f"{word} {x.year}년 {x.month}월 {x.day}일부터 {n}일({', '.join(names)})")
    years = sorted({k[:4] for k in data.holidays()})
    if years:
        bits.append(f"달력(공휴일) 자료는 {years[0]} ~ {years[-1]}년")
    return " · ".join(bits)


# ── 어르신 조건 ──


def _elder_conds(sheet: Sheet, data: DongData, reg: _Region, wx_days: dict | None) -> None:
    name, region = sheet.name, sheet.region
    d = data.dong(name) or {}
    pe = _people_row(data, name)
    add = sheet.conds.append

    # 사람
    def solo80(n: str) -> float | None:
        r = _people_row(data, n)
        return (
            r["solo80"] / r["pop80"]
            if r.get("pop80") and r.get("solo80", 0) >= MIN_PEOPLE
            else None
        )

    if pe.get("solo80") is not None and pe.get("pop80"):
        pos = _place(region, name, reg.values("solo80", solo80))
        add(
            Cond(
                "solo80",
                "사람",
                "80세 이상 혼자 사시는 분이 많음",
                f"{pe['solo80']:,}명, 80세 이상 주민 {pe['pop80']:,}명 중 "
                f"{_pct(pe['solo80'], pe['pop80'])}%",
                _place_text(region, pos, "높음") + _mean(region, reg.values("solo80", solo80)),
                _top(pos),
                okay=f"80세 이상 혼자 사시는 분 몫은 높은 편이 아님({pe['solo80']:,}명)",
            )
        )

    def share65(n: str) -> float | None:
        r = _people_row(data, n)
        return (
            r["solo65"] / r["pop65"]
            if r.get("pop65") and r.get("solo65", 0) >= MIN_PEOPLE
            else None
        )

    if pe.get("solo65") is not None and pe.get("pop65"):
        pos = _place(region, name, reg.values("share65", share65))
        add(
            Cond(
                "solo65",
                "사람",
                "65세 이상 중 혼자 사시는 분 몫이 큼",
                f"{pe['solo65']:,}명, 65세 이상 주민 {pe['pop65']:,}명 중 "
                f"{_pct(pe['solo65'], pe['pop65'])}%",
                _place_text(region, pos, "높음") + _mean(region, reg.values("share65", share65)),
                _top(pos),
                okay="65세 이상 중 혼자 사시는 분 몫은 지역 안에서 높은 편이 아님",
            )
        )

    def rise(n: str) -> float | None:
        r = _people_row(data, n)
        a, b = r.get("solo65_prev"), r.get("solo65")
        return (b - a) / a if a and b is not None and a >= MIN_PEOPLE else None

    if pe.get("solo65_prev"):
        a, b = pe["solo65_prev"], pe["solo65"]
        pos = _place(region, name, reg.values("rise", rise))
        p = data.people() or {}
        word = "늘어남" if b > a else "줄어듦" if b < a else "같음"
        add(
            Cond(
                "rise",
                "사람",
                "혼자 사시는 65세 이상이 1년 새 많이 늘어남",
                f"{a:,}명 → {b:,}명, {abs(b - a):,}명 {word}"
                f"({str(p.get('prev', ''))[:7]} → {str(p.get('basis', ''))[:7]})",
                _place_text(region, pos, "많이 늚") if b > a else "",
                b > a and _top(pos),
                okay=f"혼자 사시는 65세 이상이 1년 새 바뀐 폭은 지역 안에서 큰 편이 아님"
                f"({a:,}명 → {b:,}명)",
            )
        )

    def aged(n: str) -> float | None:
        r = _people_row(data, n)
        return r["pop80"] / r["residents"] if r.get("residents") and r.get("pop80") else None

    if pe.get("residents") and pe.get("pop80"):
        pos = _place(region, name, reg.values("aged", aged))
        add(
            Cond(
                "aged",
                "사람",
                "주민 가운데 80세 이상이 많음",
                f"주민 {pe['residents']:,}명 중 80세 이상 {pe['pop80']:,}명, "
                f"{_pct(pe['pop80'], pe['residents'])}%",
                _place_text(region, pos, "높음") + _mean(region, reg.values("aged", aged)),
                _top(pos),
                okay="주민 가운데 80세 이상 몫은 지역 안에서 높은 편이 아님",
            )
        )
    s80 = d.get("solo80") or {}
    if s80.get("care_cap") and pe.get("solo80") and s80["care_cap"] >= pe["solo80"] * 0.3:
        sheet.notes.append(
            f"이 동에는 요양시설 정원 {s80['care_cap']:,}명이 있어 80세 이상 1인세대 수에 "
            "시설에 사시는 분이 섞였을 수 있음"
        )

    # 집 · 땅
    unit, rows = _focus_rows(data, name)
    if rows:
        need, got = _sum(rows, "basement_lots_need"), _sum(rows, "basement_lots_fetched")
        exact = need and got >= 0.9 * need

        def base(n: str) -> float | None:
            _u, rs = _focus_rows(data, n)
            if not rs:
                return None
            ok = _sum(rs, "basement_lots_need") and _sum(rs, "basement_lots_fetched") >= 0.9 * _sum(
                rs, "basement_lots_need"
            )
            return _sum(rs, "basement_home") if ok else _sum(rs, "basement_old")

        v = _sum(rows, "basement_home") if exact else _sum(rows, "basement_old")
        pos = _place(region, name, reg.values("basement", base))
        what = "지하층에 집이 있는 건물" if exact else "반지하가 있을 수 있는 옛 저층 건물(어림)"
        add(
            Cond(
                "basement",
                "집",
                f"{what}이 많음",
                f"{int(v):,}채",
                _place_text(region, pos, "많음"),
                v > 0 and _top(pos),
                okay=f"{what}은 지역 안에서 많은 편이 아님({int(v):,}채)",
            )
        )

        def roof(n: str) -> float | None:
            _u, rs = _focus_rows(data, n)
            return _sum(rs, "weak_roof") if rs else None

        v = _sum(rows, "weak_roof")
        pos = _place(region, name, reg.values("roof", roof))
        add(
            Cond(
                "roof",
                "집",
                "눈 무게에 약한 지붕(슬레이트 · 함석 · 판넬) 집이 많음",
                f"{int(v):,}채",
                _place_text(region, pos, "많음"),
                v > 0 and _top(pos),
                okay=f"눈 무게에 약한 지붕 집은 많은 편이 아님({int(v):,}채)",
            )
        )

        def slope(n: str) -> float | None:
            _u, rs = _focus_rows(data, n)
            return _sum(rs, "landslide") + _sum(rs, "steep") if rs else None

        ls, st = int(_sum(rows, "landslide")), int(_sum(rows, "steep"))
        pos = _place(region, name, reg.values("slope", slope))
        # 【판단】 10-20 새벽: 수서동(산사태취약지역 0곳 · 급경사지 9곳)에 '비탈 ·
        #        산사태취약지역에서 흙이 무너질 수 있고'가 나가 산사태취약지역이 있는 듯
        #        읽혔다 — 0곳인 쪽은 말에서 뺀다
        piece = (
            "급경사지(비탈)" if not ls else "산사태취약지역" if not st else "비탈 · 산사태취약지역"
        )
        add(
            Cond(
                "slope",
                "땅",
                f"{'산사태취약지역 · 급경사지(비탈)' if ls and st else piece}가 많음",
                f"산사태취약지역 {ls}곳 · 급경사지 {st}곳",
                _place_text(region, pos, "많음"),
                (ls + st) > 0 and _top(pos),
                okay="산사태취약지역 · 급경사지는 많은 편이 아님",
                piece=piece,
            )
        )
        years = sorted({y for r in rows for y in str(r.get("flood_years") or "").split(",") if y})
        if region == "강남구":
            sites = int(_sum(rows, "flood_sites"))

            def flood(n: str) -> float | None:
                _u, rs = _focus_rows(data, n)
                return _sum(rs, "flood_sites") if rs else None

            pos = _place(region, name, reg.values("flood", flood))
            span = f", {years[0]} ~ {years[-1]}년" if years else ""
            add(
                Cond(
                    "flood",
                    "땅",
                    "침수 흔적이 많이 나옴",
                    f"서울시 침수흔적도의 흔적 {sites:,}곳{span}",
                    _place_text(region, pos, "많음"),
                    sites > 0 and _top(pos),
                    okay="침수 흔적은 많은 편이 아님",
                )
            )
    else:
        sheet.missing.append("집 · 땅(이 동의 건축물 · 지형 자료가 없음)")
    h = d.get("housing") or {}
    if h.get("old_walkup_units") is not None and h.get("res_units"):

        def walk(n: str) -> float | None:
            hh = (data.dong(n) or {}).get("housing") or {}
            return hh.get("old_walkup_share")

        pos = _place(region, name, reg.values("walkup", walk))
        add(
            Cond(
                "walkup",
                "집",
                "30년 넘은 계단 집(승강기 없는 3~5층)이 많음",
                f"{h['old_walkup_units']:,}가구, 주거 {h['res_units']:,}가구 중 "
                f"{_pct(h['old_walkup_units'], h['res_units'])}%",
                _place_text(region, pos, "높음"),
                h["old_walkup_units"] > 0 and _top(pos),
                okay="승강기 없는 오래된 계단 집은 많은 편이 아님",
            )
        )

    # 동네
    p = data.places(name) or {}
    if rows:
        if unit == "면":
            placed = [r for r in rows if r.get("halls") and r.get("pharm_km_3") is not None]
            far = [r for r in placed if r["pharm_km_3"] > FAR_PHARM_KM]
            add(
                Cond(
                    "pharmacy",
                    "동네",
                    f"평일에 문 연 약국이 {FAR_PHARM_KM:g}km 넘게 먼 마을이 많음",
                    f"경로당 있는 마을 {len(placed)}곳 중 {len(far)}곳",
                    "",
                    bool(placed) and len(far) * 3 >= len(placed),
                    okay="마을 대부분에서 문 연 약국이 멀지 않음",
                )
            )
            pub = [r for r in rows if r.get("halls") and r.get("public_km") is not None]
            pfar = [r for r in pub if r["public_km"] > FAR_PUBLIC_KM]
            add(
                Cond(
                    "public",
                    "동네",
                    "공공기관(행정복지센터 · 보건기관 · 노인복지관 · 병원)이 "
                    f"{FAR_PUBLIC_KM:g}km 넘게 먼 마을이 많음",
                    f"경로당 있는 마을 {len(pub)}곳 중 {len(pfar)}곳",
                    "",
                    bool(pub) and len(pfar) * 2 >= len(pub),
                    okay="공공기관이 먼 마을은 많지 않음",
                )
            )
        else:
            km = rows[0].get("pharm_km_3")
            if km is not None:
                add(
                    Cond(
                        "pharmacy",
                        "동네",
                        "평일에 문 연 약국까지 걸어가기 먼 편",
                        f"경로당들 가운데에서 직선 {km:g}km",
                        "",
                        km > NEAR_WALK_KM,
                        okay=f"평일에 문 연 약국이 가까움(직선 {km:g}km)",
                    )
                )
    halls = len(((p.get("halls") or {}).get("list")) or [])
    if pe.get("pop65"):

        def per100(n: str) -> float | None:
            r = _people_row(data, n)
            pp = data.places(n) or {}
            hh = len(((pp.get("halls") or {}).get("list")) or [])
            return hh / r["pop65"] * 1000 if r.get("pop65") else None

        pos = _place(region, name, reg.values("halls", per100), high_bad=False)
        add(
            Cond(
                "halls",
                "동네",
                "어르신 수에 비해 경로당 · 마을회관이 적음",
                f"{halls}곳, 65세 이상 1,000명당 {halls / pe['pop65'] * 1000:.1f}곳",
                _place_text(region, pos, "적음"),
                _top(pos),
                okay=f"어르신 수에 비해 경로당 · 마을회관이 적은 편은 아님({halls}곳)",
            )
        )
    # 【판단】 10-20: 무료급식소(전국무료급식소 표준데이터, places.json)는 있었지만
    #        판단에 쓰지 않았다.
    #        연휴에는 급식소도 쉬고, 더위에는 쉴 곳이 되므로 동네 겹의 조건으로 둔다
    if "meals" in p:
        meals = p.get("meals") or []
        ne = (p.get("nearest") or {}).get("meals") or {}
        far = f", 가장 가까운 {ne['name']}({ne['dong']}) 직선 {ne['km']}km" if ne else ""
        add(
            Cond(
                "meals",
                "동네",
                "동 안에 무료급식소가 없음",
                f"0곳{far}" if not meals else f"{len(meals)}곳",
                "",
                not meals,
                okay=f"동 안에 무료급식소 {len(meals)}곳",
            )
        )
    clinic = (p.get("shops") or {}).get("의원") or {}
    if clinic:
        ne = clinic.get("nearest") or {}
        add(
            Cond(
                "clinic",
                "동네",
                "동 안에 의원이 없음",
                f"가장 가까운 의원 {ne['name']}({ne['dong']}) 직선 {ne['km']}km" if ne else "0곳",
                "",
                clinic.get("n") == 0,
                okay=f"동 안에 의원 {clinic.get('n', 0)}곳",
            )
        )
    b = data.bus(name) or {}
    if b:
        low = b.get("low_freq") or []
        add(
            Cond(
                "bus",
                "동네",
                "하루 3번 이하 다니는 버스 노선이 지나감(어림)",
                " · ".join(low[:3]) if low else "없음",
                "",
                bool(low),
                okay="하루 3번 이하 다니는 마을버스는 지나지 않음",
            )
        )

    # 안전망
    home = (p.get("ltc") or {}).get("home") or {}
    if p.get("ltc") is not None:
        add(
            Cond(
                "homecare",
                "안전망",
                "동 안에 집으로 오는 돌봄 기관(재가 장기요양기관)이 없음",
                f"{home.get('n', 0)}곳",
                "",
                home.get("n", 0) == 0,
                okay=f"동 안에 재가 장기요양기관 {home.get('n', 0)}곳",
            )
        )
    lv = d.get("livelihood")
    if lv:
        add(
            Cond(
                "poverty",
                "안전망",
                "기초생활수급자 몫이 춘천 평균보다 높음",
                f"{lv['people']:,}명, 주민 100명당 {lv['per100']}명"
                f"(춘천 평균 {lv['city_per100']}명, {lv['year']}년)",
                f"춘천 {lv['of']}곳 중 {lv['rank']}번째로 높음",
                lv["per100"] > lv["city_per100"],
                okay=f"기초생활수급자 몫이 춘천 평균보다 높지 않음(100명당 {lv['per100']}명)",
            )
        )
    kind = ((d.get("seoul_lonely_kind") or {}).get("2025")) or {}
    if kind:

        def gshare(n: str) -> float | None:
            k = ((data.dong(n) or {}).get("seoul_lonely_kind") or {}).get("2025") or {}
            t = sum(k.values())
            return k.get("수급", 0) / t if t else None

        t = sum(kind.values())
        pos = _place(region, name, reg.values("gshare", gshare))
        add(
            Cond(
                "poverty",
                "안전망",
                "독거노인 가운데 기초생활수급권자 몫이 큼",
                f"서울시 독거노인 {t:,}명 중 수급권자 {kind.get('수급', 0):,}명, "
                f"{_pct(kind.get('수급', 0), t)}%(2025)",
                _place_text(region, pos, "높음"),
                _top(pos),
                okay="독거노인 가운데 수급권자 몫은 높은 편이 아님",
            )
        )
    sig = [s for s in ((d.get("diag") or {}).get("signals") or []) if "외출" in s]
    if region == "강남구":
        add(
            Cond(
                "outing",
                "안전망",
                "외출 · 연락이 모두 적은 어르신 몫이 큼",
                _outing(sig[0])[0] if sig else "해당 신호 없음",
                _outing(sig[0])[1] if sig else "",
                bool(sig),
                okay="외출 · 연락이 모두 적은 어르신 몫은 두드러지지 않음",
            )
        )

    _weather_conds(sheet, data, wx_days, elder=True)
    _calendar_conds(sheet, data, rows, unit)


def _outing(signal: str) -> tuple[str, str]:
    """'외출·연락이 모두 적은 어르신 2.5%(4위)' → ('2.5%, 서울시 시민생활 데이터',
    '강남 22곳 중 4번째로 높음')."""
    m = re.search(r"([\d.]+%)\((\d+)위\)", signal)
    if not m:
        return f"{signal}, 서울시 시민생활 데이터", ""
    r = int(m.group(2))
    place = "강남 22곳 중 가장 높음" if r == 1 else f"강남 22곳 중 {r}번째로 높음"
    return f"{m.group(1)}, 서울시 시민생활 데이터", place


def _weather_conds(sheet: Sheet, data: DongData, wx_days: dict | None, elder: bool) -> None:
    th = _thresholds(data)
    today, rewind, dated = sheet.today, sheet.rewind, sheet.dated
    obs = _observed(data, sheet.region)
    if not obs or not th:
        sheet.missing.append("지난 날씨(관측 자료가 없음)")
    else:
        last = max(obs)
        if (today - date.fromisoformat(last)).days > STALE_DAYS:
            sheet.notes.append(f"관측 자료가 {last}까지라 그 뒤 날씨는 빠짐")
        days = [(today - timedelta(days=i)).isoformat() for i in range(1, PAST_DAYS + 1)]
        rows = [(x, obs[x]) for x in days if x in obs]
        hit = [
            (kind, x, r)
            for kind, t in th.items()
            for x, r in rows
            if _over(r, t) and (elder or kind == "폭우")
        ]
        rain = sum(r.get("rain") or 0 for _x, r in rows)
        low = min((r["tmin"] for _x, r in rows if r.get("tmin") is not None), default=None)
        station = (((data.weather() or {}).get("regions") or {}).get(sheet.region) or {}).get(
            "station", ""
        )
        if hit:
            kinds = list(dict.fromkeys(k for k, _x, _r in hit))
            detail = " · ".join(
                f"{KIND_WORD[k]} 기준 넘은 날 {sum(1 for kk, _x, _r in hit if kk == k)}일"
                for k in kinds
            )
        else:
            detail = "기준을 넘은 날 없음"
        add_low = f", 가장 낮은 기온 {low:g}℃" if low is not None else ""
        # 【판단】 10-20 새벽: 관측 일자료는 하루 늦게 들어와(자료 받기 12:30) 아침에는 어제 관측이
        #        없다. 빠진 날을 밝힌다(카드의 '관측 자료는 ~까지'와 같은 사실)
        lack = [x for x in days if x not in obs]
        if lack and rows:
            add_low += ", " + " · ".join(f"{int(x[5:7])}월 {int(x[8:])}일" for x in lack)
            add_low += " 관측은 아직 없음"
        sheet.conds.append(
            Cond(
                "past",
                "지난 날씨",
                f"{'그날 앞' if dated else '지난'} {PAST_DAYS}일 궂은 날씨가 있었음",
                f"{station} 관측, {detail}, 비 합계 {rain:g}mm{add_low}",
                "",
                bool(hit),
                okay=f"{'그날 앞' if dated else '지난'} {PAST_DAYS}일은 "
                "궂은 날씨 기준을 넘은 날이 없음",
            )
        )
        sheet.conds[-1].kinds = [k for k, _x, _r in hit]
    if wx_days is None:
        sheet.missing.append("앞으로 날씨(기상청 예보를 받지 못함)")
        return
    window = [(today + timedelta(days=i)).isoformat() for i in range(AHEAD + 1)]
    hit = []
    for kind, t in th.items():
        if not elder and kind != "폭우":
            continue
        for x in window:
            r = wx_days.get(x)
            if r and _over(r, t):
                col, _op, _v, unit = t
                hit.append((kind, x, r[col], unit))
    if hit:
        detail = " · ".join(f"{x[5:]} {KIND_WORD[k]} {v:g}{u}" for k, x, v, u in hit[:4])
    else:
        detail = "기준을 넘는 날 없음"
    # 10-20 페르소나 h01 r4: 예보를 받았는데 글쓴이가 '오늘 날씨 예보는 자료에 없어요'
    #        → 값을 적어 둔다
    seen = []
    for x in window:
        r = wx_days.get(x) or {}
        if r.get("tmin") is not None or r.get("tmax") is not None:
            seen.append(
                f"{int(x[5:7])}/{int(x[8:])} 최저 {r.get('tmin', '?')}℃ · "
                f"최고 {r.get('tmax', '?')}℃"
                f" · 비 {r.get('rain') or 0:g}mm"
            )
    if seen:
        detail += "(" + " / ".join(seen) + ")"
    src = f"{today.isoformat()} 뒤 관측" if rewind else "기상청 단기예보"
    start = "그날부터" if dated else "오늘부터"
    sheet.conds.append(
        Cond(
            "ahead",
            "앞으로 날씨",
            f"{start} 사흘 안에 궂은 날씨가 옴",
            f"{src}, {detail}",
            "",
            bool(hit),
            okay=f"{start} 사흘 안에는 궂은 날씨 기준을 넘는 날이 없음",
        )
    )
    sheet.conds[-1].kinds = [k for k, *_ in hit]


def _calendar_conds(sheet: Sheet, data: DongData, rows: list[dict], unit: str) -> None:
    today = sheet.today
    hol = data.holidays()
    years = {int(k[:4]) for k in hol}
    if today.year not in years:
        sheet.missing.append(f"달력({today.year}년 공휴일 자료가 아직 없음)")
        return
    lh = _long_holiday(data, today)
    # 【판단】 10-20 페르소나 f01 r8: '해당하지 않음' 말(okay)에는 지난 · 다음 연휴가 없어
    #        '10월 20일 뒤 연휴 날짜는 자료에 없다'고 세 번 답했다(특일 자료는 2026년까지 있다)
    near = "" if lh else _near_holidays(data, today)
    sheet.conds.append(
        Cond(
            "holiday",
            "달력",
            f"{HOLIDAY_LEAD}일 안에 긴 연휴가 시작함",
            f"{lh[0].month}월 {lh[0].day}일부터 {lh[1]}일({', '.join(lh[2])})"
            if lh
            else "없음" + (f" — {near}" if near else ""),
            "",
            bool(lh),
            okay=f"{HOLIDAY_LEAD}일 안에 긴 연휴는 없음" + (f"({near})" if near else ""),
        )
    )
    off = today.weekday() >= 5 or today.isoformat() in hol
    if off and unit == "면" and rows:
        k = 8 if today.isoformat() in hol else today.weekday() + 1
        placed = [r for r in rows if r.get("halls") and r.get(f"pharm_km_{k}") is not None]
        far = [r for r in placed if r[f"pharm_km_{k}"] > FAR_PHARM_KM]
        word = "공휴일" if k == 8 else "주말"
        sheet.conds.append(
            Cond(
                "dayoff",
                "달력",
                f"오늘은 {word}이라 문 연 약국이 더 멂",
                f"오늘 문 연 약국이 {FAR_PHARM_KM:g}km 넘게 먼 마을 {len(far)}곳"
                f"(경로당 있는 마을 {len(placed)}곳 중)",
                "",
                bool(far),
                okay=f"오늘은 {word}지만 문 연 약국이 먼 마을은 없음",
            )
        )


# ── 청년 조건 ──


def _youth_conds(sheet: Sheet, data: DongData, reg: _Region, wx_days: dict | None) -> None:
    name, region = sheet.name, sheet.region
    pe = _people_row(data, name)
    d = data.dong(name) or {}
    pop = pe.get("pop_youth")
    if not pop:
        sheet.missing.append("사람(청년 주민 자료가 없음)")
        return
    if pop < MIN_YOUTH:
        sheet.notes.append(
            f"청년(19 ~ 34세)이 {pop:,}명뿐이라 다른 동과 비율로 견주지 않음(작은 수는 흔들림이 큼)"
        )

    def share(n: str) -> float | None:
        r = _people_row(data, n)
        return r["solo_youth"] / r["pop_youth"] if (r.get("pop_youth") or 0) >= MIN_YOUTH else None

    pos = _place(region, name, reg.values("yshare", share)) if pop >= MIN_YOUTH else None
    sheet.conds.append(
        Cond(
            "yshare",
            "사람",
            "청년 가운데 혼자 사는 몫이 큼",
            f"혼자 사는 청년(19 ~ 34세 1인 세대) {pe['solo_youth']:,}명, 청년 주민 {pop:,}명 중 "
            f"{_pct(pe['solo_youth'], pop)}%",
            _place_text(region, pos, "높음"),
            _top(pos),
            okay=f"청년 가운데 혼자 사는 몫은 높은 편이 아님({_pct(pe['solo_youth'], pop)}%)",
        )
    )

    def yrise(n: str) -> float | None:
        r = _people_row(data, n)
        a = r.get("solo_youth_prev")
        return (r["solo_youth"] - a) / a if a and a >= MIN_PEOPLE else None

    a, b = pe.get("solo_youth_prev"), pe.get("solo_youth")
    if a is not None:
        p = data.people() or {}
        pos = _place(region, name, reg.values("yrise", yrise))
        word = "늘어남" if b > a else "줄어듦" if b < a else "같음"
        sheet.conds.append(
            Cond(
                "yrise",
                "사람",
                "혼자 사는 청년이 1년 새 많이 늘어남",
                f"{a:,}명 → {b:,}명, {abs(b - a):,}명 {word}"
                f"({str(p.get('prev', ''))[:7]} → {str(p.get('basis', ''))[:7]})",
                _place_text(region, pos, "많이 늚") if b > a else "",
                b > a and a >= MIN_PEOPLE and _top(pos),
                okay=f"혼자 사는 청년이 1년 새 바뀐 폭은 지역 안에서 큰 편이 아님"
                f"({a:,}명 → {b:,}명)",
            )
        )
    hb = (d.get("youth") or {}).get("homebound") or {}
    if hb:
        if hb.get("under10"):
            val = "10명 미만"
            per = None
        else:
            val = (
                f"약 {hb['lo']:,} ~ {hb['hi']:,}명, "
                f"청년 100명당 {hb['per100_lo']} ~ {hb['per100_hi']}명"
            )
            per = hb["per100_hi"]

        def hper(n: str) -> float | None:
            h2 = ((data.dong(n) or {}).get("youth") or {}).get("homebound") or {}
            return None if not h2 or h2.get("under10") else h2.get("per100_hi")

        pos = _place(region, name, reg.values("homebound", hper)) if per is not None else None
        sheet.conds.append(
            Cond(
                "homebound",
                "어림",
                "거의 집에만 있는 청년이 많을 수 있음(어림)",
                f"{val}. 전국 조사의 나이별 비율을 이 동 나이 구성에 맞춘 어림, "
                "실제로 센 수가 아님",
                _place_text(region, pos, "높음"),
                _top(pos),
                # 10-20 페르소나 f01 r4: '괜찮은 쪽'에 두면 현장을 모르는 사람이 안심한다
                #        → 토를 단다
                okay="거의 집에만 있는 청년 어림은 두드러지지 않음(전국 비율을 이 동 나이 "
                "구성에 곱한 "
                "값이라 이 동네에 은둔 청년이 적다는 뜻은 아님)",
            )
        )
    unit, rows = _focus_rows(data, name)
    if rows:
        # 【판단】 어르신 조건표와 같은 셈(층별개요를 90% 넘게 받은 동은 지하층 집, 아니면 표제부의
        #        '반지하가 있을 수 있는 옛 저층 건물' 어림). 10-20 r0: 강남 청년 조건표가 이 겹을
        #        빠뜨려 다섯 겹만 봤다
        need, got = _sum(rows, "basement_lots_need"), _sum(rows, "basement_lots_fetched")
        exact = bool(need) and got >= 0.9 * need
        v = int(_sum(rows, "basement_home") if exact else _sum(rows, "basement_old"))

        def yb(n: str) -> float | None:
            _u, rs = _focus_rows(data, n)
            if not rs:
                return None
            nd = _sum(rs, "basement_lots_need")
            ok = nd and _sum(rs, "basement_lots_fetched") >= 0.9 * nd
            return _sum(rs, "basement_home") if ok else _sum(rs, "basement_old")

        pos = _place(region, name, reg.values("basement", yb))
        what = "지하층에 집이 있는 건물" if exact else "반지하가 있을 수 있는 옛 저층 건물(어림)"
        sheet.conds.append(
            Cond(
                "basement",
                "집",
                f"{what}이 많음(나이를 가리지 않은 동 전체)",
                f"{v:,}채",
                _place_text(region, pos, "많음"),
                v > 0 and _top(pos),
                okay=f"{what}은 많은 편이 아님({v:,}채)",
            )
        )
    b = data.bus(name) or {}
    if b:
        low = b.get("low_freq") or []
        sheet.conds.append(
            Cond(
                "bus",
                "동네",
                "하루 3번 이하 다니는 버스 노선이 지나감(일 · 학교 · 상담 다니기 불편, 어림)",
                " · ".join(low[:3]) if low else "없음",
                "",
                bool(low),
                okay="하루 3번 이하 다니는 마을버스는 지나지 않음",
            )
        )
    _weather_conds(sheet, data, wx_days, elder=False)
    _calendar_conds(sheet, data, [], "")


# ── 겹침 ──


def _kinds(sheet: Sheet, key: str) -> set[str]:
    c = sheet.get(key)
    return set(c.kinds) if c and c.hit else set()


def _weather_hit(sheet: Sheet, kinds: set[str]) -> list[Cond]:
    out = []
    for key in ("past", "ahead"):
        if _kinds(sheet, key) & kinds:
            out.append(sheet.get(key))
    return [c for c in out if c]


def _pick(*groups: list[Cond]) -> list[Cond] | None:
    """무리마다 하나 이상 해당해야 선다. 겹(layer)이 3개 이상이어야 선다."""
    if not all(groups):
        return None
    conds = list(dict.fromkeys(c for g in groups for c in g))
    return conds if len({c.layer for c in conds}) >= 3 else None


# 【판단】 겹침의 뜻은 실제로 해당한 조건만으로 만든다(10-20 첫 판: 수서동에 계단 집이 0인데
#        '계단 집 · 비탈 · 약한 지붕이 바깥 출입을 막을 수 있고'가 나가 계단 집이 있는 듯 읽혔다)
PIECE = {
    "walkup": "승강기 없는 계단 집",
    "roof": "눈 무게에 약한 지붕 집",
    "slope": "비탈 · 산사태취약지역",
    "basement": "지하층 집",
    "flood": "전에 물에 잠긴 흔적이 있는 곳",
    "pharmacy": "약국",
    "public": "공공기관",
    "clinic": "의원",
    "bus": "드문 버스",
    "dayoff": "오늘이 쉬는 날",
    "holiday": "다가오는 긴 연휴",
    "halls": "어르신 수에 비해 적은 경로당 · 마을회관",
    "meals": "동 안에 없는 무료급식소",
    "homecare": "동 안에 없는 재가 돌봄 기관",
    "poverty": "형편이 어려운 분이 많음",
    "outing": "외출 · 연락이 적은 어르신이 많음",
    "solo80": "혼자 사시는 80세 이상 어르신",
    "aged": "80세 이상 어르신",
    "solo65": "혼자 사시는 어르신",
    "rise": "새로 혼자되신 분",
    "yshare": "혼자 사는 청년",
    "yrise": "새로 혼자 살게 된 청년",
    "homebound": "거의 집에만 있는 청년(어림)",
}


def _names(conds: list[Cond], *keys: str) -> str:
    got = [c.piece or PIECE[c.key] for c in conds if c.key in keys]
    return " · ".join(dict.fromkeys(got))


def _who(conds: list[Cond]) -> str:
    return _names(conds, "solo80") or _names(conds, "aged", "solo65") or "어르신"


def _m_cold(c: list[Cond]) -> str:
    return (
        f"영하의 추위나 눈이 오면 {_names(c, 'walkup', 'roof', 'slope')} 때문에 바깥 출입이 "
        f"어려워질 수 있고, {_who(c)}은 며칠씩 집 안에만 계실 수 있어요"
    )


def _m_rain(c: list[Cond]) -> str:
    bits = []
    if any(x.key == "basement" for x in c):
        bits.append("지하층 집에 물이 들 수 있고")
    if any(x.key == "flood" for x in c):
        bits.append("전에 물에 잠긴 적이 있는 곳이 다시 잠길 수 있고")
    if any(x.key == "slope" for x in c):
        bits.append(f"{_names(c, 'slope')}에서 흙이 무너질 수 있고")
    return f"큰비가 오면 {' '.join(bits)}, {_who(c)}은 스스로 피하기 어려울 수 있어요"


def _m_heat(c: list[Cond]) -> str:
    return (
        f"무더위에는 시원한 곳에서 쉬어야 하는데 {_names(c, 'halls', 'meals')} 사정까지 겹쳐, "
        f"{_who(c)}은 더운 집에 머물 수 있어요"
    )


def _m_access(c: list[Cond]) -> str:
    far = _names(c, "pharmacy", "public", "clinic")
    when = _names(c, "bus", "dayoff", "holiday")
    return (
        f"{far}이 멀고 {when}까지 겹치면, 차가 없는 {_who(c)}은 약을 타거나 진료를 받으러 "
        "나가기 어려울 수 있어요"
    )


def _m_newalone(c: list[Cond]) -> str:
    weak = _names(c, "halls", "homecare", "poverty", "outing")
    return (
        f"혼자 사시는 분이 1년 새 많이 늘었는데 {weak}까지 겹쳐, 새로 혼자되신 분이 이어질 곳을 "
        "찾기 어려울 수 있어요"
    )


def _m_isolation(c: list[Cond]) -> str:
    return (
        "외출 · 연락이 모두 적은 어르신이 많은 동에 혼자 사시는 분 몫까지 크고 경로당 · 마을회관이 "
        "적어, 바깥과 이어지는 끈이 약한 분이 있을 수 있어요"
    )


def _m_holiday(c: list[Cond]) -> str:
    return (
        "긴 연휴에는 병원 · 약국 · 경로당 · 돌봄 기관이 쉬는 곳이 많은데 "
        f"{_names(c, 'homecare', 'pharmacy', 'clinic', 'meals')} 사정까지 겹쳐, "
        f"{_who(c)}은 며칠 동안 "
        "도움 없이 지내실 수 있어요"
    )


def _m_poor(c: list[Cond]) -> str:
    return (
        f"형편이 어려운 분이 많고 {_who(c)} 몫이 큰 곳에 {_names(c, 'walkup', 'roof', 'basement')}"
        "이 많아, 궂은 날씨에 집을 고치거나 피하기 어려울 수 있어요"
    )


def _m_yholiday(c: list[Cond]) -> str:
    return (
        "긴 연휴에는 일 · 학교 같은 바깥 일정이 끊겨, 혼자 사는 청년 가운데 거의 집에만 있는 "
        "청년은 며칠 동안 아무와도 만나지 않을 수 있어요"
    )


def _m_yrain(c: list[Cond]) -> str:
    return (
        "큰비가 오면 지하층 집에 물이 들 수 있어요. 지하층 집에 사는 사람의 나이는 이 자료에 없어 "
        "동 전체로 보고, 혼자 사는 청년 몫이 큰 동이라 함께 봐요"
    )


def _m_ycut(c: list[Cond]) -> str:
    return (
        "혼자 사는 청년이 많은데 버스가 드물면 일 · 학교 · 상담에 다니기 어려워 바깥과 멀어질 수 "
        "있어요(버스 횟수는 어림)"
    )


# 【판단】 10-20 페르소나 o01(도청 점검) r8: 북산면 조건이 사람 · 땅 · 동네 · 안전망 네 겹에
#        있는데 '겹친 걱정 없음'이라 '서로 다른 겹 3가지 이상이면 겹친 걱정'이라는 설명과
#        앞뒤가 맞지 않았다. 실제 규칙은 겹침마다 정한 조건 무리가 있고 무리마다 하나 이상
#        해당하며 그 조건들이 서로 다른 겹 3가지 이상일 때다(북산면 '약 · 진료'는 약국 ·
#        버스가 둘 다 동네 겹이라 2겹).
#        무리를 표 하나로 두고, 서는 규칙(_rule)과 서지 않은 까닭(misses)이 같은 표를 본다
GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "cold": (("날씨", "한파", "폭설"), ("walkup", "roof", "slope"), ("solo80", "aged")),
    "rain": (("날씨", "폭우"), ("basement", "flood", "slope"), ("solo65", "solo80")),
    "heat": (("날씨", "폭염"), ("halls", "meals"), ("solo80", "aged")),
    "access": (("pharmacy", "public", "clinic"), ("bus", "dayoff", "holiday"), ("solo80", "aged")),
    "newalone": (("rise",), ("halls",), ("homecare", "poverty", "outing")),
    "isolation": (("outing",), ("solo65", "solo80"), ("halls",)),
    "holiday": (
        ("holiday",),
        ("solo80", "aged"),
        ("homecare", "pharmacy", "clinic", "meals"),
    ),
    "poor": (("poverty",), ("solo65", "solo80"), ("walkup", "roof", "basement")),
    # 【판단】 10-20 페르소나 f01 r4: 어림(전국 비율 × 나이 구성)이 필수라 혼자 사는 청년이 춘천
    #        2위이고 1년 새 101명 는 효자2동이 연휴에 서지 않았다 → 세 번째 무리를 어림 ·
    #        지하층 집 ·
    #        드문 버스로 넓힘(미정: 겹침 목록은 Claude 판단, big-contest docs/미정.md)
    "yholiday": (("holiday",), ("yshare",), ("yrise", "homebound", "basement", "bus")),
    "yrain": (("날씨", "폭우"), ("basement",), ("yshare",)),
    "ycut": (("yrise", "yshare"), ("bus",), ("homebound",)),
}
WEATHER_GROUP = {"한파": "한파", "폭설": "눈", "폭우": "큰비", "폭염": "폭염"}


def _groups(s: Sheet, key: str) -> list[list[Cond]]:
    return [_weather_hit(s, set(g[1:])) if g[0] == "날씨" else s.on(*g) for g in GROUPS[key]]


def _rule(key: str):
    return lambda s: _pick(*_groups(s, key))


COL_WORD = {
    "rain": "하루 비",
    "tmin": "아침 최저기온",
    "tmax": "낮 최고기온",
    "snow": "새로 쌓인 눈",
}


def _md(x: date) -> str:
    return f"{x.month}월 {x.day}일"


def _group_word(g: tuple[str, ...], s: Sheet | None = None, th: dict | None = None) -> str:
    """무리를 말로. 날씨 무리는 기준값과 날짜까지(10-20 페르소나 o01 r2: '궂은 비 무리가 비었다'더니
    '궂은 비 기준은 자료에 없다' — 기준과 날짜를 적어 둔다)."""
    if g[0] != "날씨":
        return " · ".join(PIECE.get(k, k) for k in g)
    words = []
    for k in g[1:]:
        t = (th or {}).get(k)
        if t:
            col, op, v, unit = t
            words.append(f"{COL_WORD.get(col, col)} {v:g}{unit} {'이상' if op == '>=' else '이하'}")
        else:
            words.append(WEATHER_GROUP[k])
    if s is None:
        return "지난 · 앞으로 사흘 " + " 또는 ".join(words)
    t0 = s.today
    past = f"{_md(t0 - timedelta(days=PAST_DAYS))} ~ {_md(t0 - timedelta(days=1))}"
    ahead = f"{_md(t0)} ~ {_md(t0 + timedelta(days=AHEAD))}"
    return f"지난 사흘({past}) · 앞으로 사흘({ahead}) 가운데 하루라도 " + " 또는 ".join(words)


ELDER_PATTERNS = (
    ("cold", "추위 · 눈에 집 밖으로 나오기 어려움", _rule("cold"), _m_cold),
    ("rain", "큰비에 집이 잠기거나 무너질 수 있음", _rule("rain"), _m_rain),
    ("heat", "더위에 쉴 곳이 부족함", _rule("heat"), _m_heat),
    ("access", "약 · 진료를 구하기 어려움", _rule("access"), _m_access),
    ("newalone", "새로 혼자되신 분이 늘었는데 기댈 곳이 적음", _rule("newalone"), _m_newalone),
    ("isolation", "밖에 덜 나오고 연락이 적은 분이 많음", _rule("isolation"), _m_isolation),
    ("holiday", "연휴에 도움이 끊기기 쉬움", _rule("holiday"), _m_holiday),
    ("poor", "형편이 어려운 분이 많은 곳에 낡은 집", _rule("poor"), _m_poor),
)

YOUTH_PATTERNS = (
    ("yholiday", "연휴에 혼자 보내는 청년", _rule("yholiday"), _m_yholiday),
    ("yrain", "큰비에 지하층 집", _rule("yrain"), _m_yrain),
    ("ycut", "혼자 사는 청년이 많은데 다니기 불편함", _rule("ycut"), _m_ycut),
)


def misses(s: Sheet, data: DongData | None = None) -> list[str]:
    """서지 않은 겹침마다 까닭 — 빈 무리, 또는 무리는 다 맞았지만 겹이 3가지가 안 됨."""
    th = _thresholds(data) if data is not None else {}
    pats = YOUTH_PATTERNS if s.target == "청년" else ELDER_PATTERNS
    fired = {p.key for p in s.patterns}
    out = []
    for key, title, _r, _m in pats:
        if key in fired:
            continue
        gs = _groups(s, key)
        words = [_group_word(g, s, th) for g in GROUPS[key]]
        empty = [w for w, g in zip(words, gs, strict=True) if not g]
        if empty:
            out.append(
                f"서지 않은 겹침 '{title}': 무리 {len(words)}개({' / '.join(words)}) 중 "
                f"해당 조건이 없는 무리 — {' / '.join(empty)}"
            )
        else:
            layers = list(dict.fromkeys(c.layer for g in gs for c in g))
            out.append(
                f"서지 않은 겹침 '{title}': 무리 {len(words)}개 모두 해당했지만 그 조건들의 겹이 "
                f"{len(layers)}가지({' · '.join(layers)})라 3가지에 못 미침"
            )
    return out


# ── 만들기 ──


def clock(as_of: date | None = None) -> tuple[date, bool]:
    """(그날, 되감기인가). as_of 가 없으면 비서의 오늘(librarian._today, .env AS_OF 되감기 포함)."""
    from src.assistant import forecast as fc
    from src.assistant import librarian as L

    if as_of is None:
        return L._today()
    return as_of, as_of < fc.today_kst()


def _forecast(
    data: DongData, region: str, names: list[str], as_of: date | None = None
) -> dict[str, dict] | None:
    """동마다 오늘 ~ 모레 예보({동: {날짜: 값}}). 되감기면 관측을 예보처럼. 못 받으면 None."""
    from src.assistant import forecast as fc
    from src.assistant import librarian as L

    today, rewind = clock(as_of)
    if rewind:
        obs = _observed(data, region)
        days = {
            (today + timedelta(days=i)).isoformat(): obs[(today + timedelta(days=i)).isoformat()]
            for i in range(AHEAD + 1)
            if (today + timedelta(days=i)).isoformat() in obs
        }
        return {n: days for n in names} if days else None
    grids = data.grids(region)
    use = {n: grids[n] for n in names if n in grids}
    if not use:
        return None
    try:
        by_dong, _issued = L._wx().forecast(use)
    except fc.ForecastError:
        return None
    return by_dong


def sheet(
    name: str,
    target: str,
    data: DongData,
    forecasts: dict | None = None,
    as_of: date | None = None,
) -> Sheet | None:
    """한 동 · 한 대상(어르신 · 청년)의 조건표. forecasts 를 주면 예보를 다시 받지 않는다."""
    d = data.dong(name)
    if d is None:
        return None
    region = d["region"]
    unit, _rows = _focus_rows(data, name)
    s = Sheet(name, region, target, unit or ("면" if name.endswith(("면", "읍")) else "동"))
    s.today, s.rewind = clock(as_of)
    s.dated = as_of is not None and s.rewind
    reg = _Region(data, region)
    if forecasts is None:
        forecasts = _forecast(data, region, [name], as_of) or {}
        fc_ok = bool(forecasts)
    else:
        fc_ok = name in forecasts
    wx_days = forecasts.get(name) if fc_ok else None
    if target == "청년":
        _youth_conds(s, data, reg, wx_days)
        patterns, layers = YOUTH_PATTERNS, YOUTH_LAYERS
    else:
        _elder_conds(s, data, reg, wx_days)
        patterns, layers = ELDER_PATTERNS, LAYERS
    for key, title, rule, meaning in patterns:
        got = rule(s)
        if got:
            s.patterns.append(Pattern(key, title, meaning(got), got))
    # 【판단】 앞으로 사흘 날씨가 든 겹침을 먼저 둔다('이번 주에 제일 걱정되는 게?'의 답)
    s.patterns.sort(key=lambda p: not any(c.key == "ahead" for c in p.conds))
    # 글자는 해당 조건부터(겹침에 든 것 먼저), 그다음 해당하지 않는 조건
    used = [c for p in s.patterns for c in p.conds]
    order = list(dict.fromkeys(used + s.hits))
    for i, c in enumerate(order):
        c.letter = chr(ord("A") + i)
    s.checked = [x for x in layers if any(c.layer == x for c in s.conds)]
    return s


def facts_lines(s: Sheet) -> list[str]:
    """사실 묶음에 넣을 줄(글쓴이 · 코드 기본 답이 같이 쓴다). 줄표를 쓰지 않는다."""
    out = [s.verdict()]
    out.append(
        f"살펴본 겹 {len(s.checked)}가지: {' · '.join(s.checked)}"
        + (f". 확인하지 못한 겹: {' / '.join(s.missing)}" if s.missing else "")
    )
    lettered = sorted((c for c in s.conds if c.letter), key=lambda c: c.letter)
    out += [f"해당 {c.line()}" for c in lettered]
    for i, p in enumerate(s.patterns, 1):
        letters = "·".join(sorted(c.letter for c in p.conds))
        soon = ", 앞으로 사흘 날씨와 겹침" if any(c.key == "ahead" for c in p.conds) else ""
        soon = f", {p.kind}{soon}"
        out.append(
            f"겹침 {i}: {p.title}(조건 {letters}, 겹 {len(p.layers())}가지에 걸침{soon}). "
            f"뜻: {p.meaning}"
        )
    # 【판단】 10-26 예상 질문 2-16 '내일모레 한파 특보가 예고됐고 …': 앞으로 사흘 예보가 해당하지
    #        않으면 '괜찮은 쪽' 앞 다섯 줄에서 잘리고 값(예보 기온)도 빠져 글쓴이가 '예보는 자료에
    #        없다'고 했다 → 날씨 · 달력 줄은 지역 판단(region_lines)처럼 값과 함께 늘 준다
    weather = ("past", "ahead", "holiday")
    for key in weather:
        c = s.get(key)
        if c and not c.hit and c.okay:
            val = "" if c.value.startswith("없음") else f"({c.value})"
            out.append(f"날씨 · 달력(해당하지 않음): {c.okay}{val}")
    fine = [c.okay for c in s.conds if not c.hit and c.okay and c.key not in weather]
    if fine:
        out.append("해당하지 않는 조건(괜찮은 쪽): " + " / ".join(fine[:5]))
    return out


def region_lines(region: str, target: str, data: DongData, as_of: date | None = None) -> list[str]:
    """지역 전체 — 동마다 조건표를 만들어 겹친 걱정이 많은 동과 지역 날씨 · 달력을 준다."""
    names = data.region_dongs(region)
    forecasts = _forecast(data, region, names, as_of)
    sheets = [s for n in names if (s := sheet(n, target, data, forecasts or {}, as_of))]
    if not sheets:
        return []
    with_p = sorted(
        (s for s in sheets if s.patterns), key=lambda s: (-len(s.patterns), -len(s.hits), s.name)
    )
    now_n = sum(1 for s in with_p if any(p.now for p in s.patterns))
    after_n = sum(
        1 for s in with_p if not any(p.now for p in s.patterns) and any(p.after for p in s.patterns)
    )
    out = [
        f"{region} {target} 취약 돌보미 판단: {len(sheets)}곳 중 겹친 걱정이 하나라도 있는 동 "
        f"{len(with_p)}곳(지금 닥친 걱정이 있는 동 {now_n}곳 · "
        f"지난 궂은 날씨 뒤 걱정 {after_n}곳 · "
        f"평소 구조 걱정만 있는 동 {len(with_p) - now_n - after_n}곳). 취약 돌보미 동 순위와는 다른 것"  # noqa: E501
    ]
    # 【판단】 10-20 페르소나 o02: '1위 개포3동은 왜 겹친 걱정 목록에 없어?' — 다른 기준임을 숫자로
    ranked = data.ranked(region) if target == "어르신" else []
    if ranked:
        first = next((s for s in sheets if s.name == ranked[0][1]), None)
        if first is not None:
            out.append(
                f"취약 돌보미 동 순위 1위 {first.name}: 겹친 걱정 {len(first.patterns)}가지"
                "(순위는 혼자 사는 어르신 몫 · 외출 · 갈 곳으로 매기고, "
                "취약 돌보미 판단은 여러 겹 조건의 겹침이라 다를 수 있음)"
            )
    # 【판단】 10-20 페르소나 o02: '8곳이라며? 아래엔 5곳만 나오네'(위 다섯만 줬다) → 겹친 동은
    #        모두 이름과 가짓수로 한 줄, 자세한 줄은 위 다섯
    if with_p:
        out.append(
            f"겹친 걱정이 있는 동 {len(with_p)}곳(가짓수): "
            + " · ".join(f"{s.name} {len(s.patterns)}가지" for s in with_p)
        )
    for s in with_p[:5]:
        out.append(
            f"{s.name}: 겹친 걱정 {len(s.patterns)}가지({' / '.join(p.title for p in s.patterns)})"
        )
    counts: dict[str, int] = {}
    for s in sheets:
        for p in s.patterns:
            counts[p.title] = counts.get(p.title, 0) + 1
    if counts:
        out.append(
            "지역에서 많이 선 겹침: "
            + " · ".join(f"{t} {n}곳" for t, n in sorted(counts.items(), key=lambda x: -x[1]))
        )
    first = sheets[0]
    for key in ("past", "ahead", "holiday"):
        c = first.get(key)
        if c:
            # 10-26 예상 질문 2-2: 연휴가 없을 때 okay 에 가까운 연휴가 이미 들어 있는데 값('없음 —
            #        …')을 또 붙여 같은 연휴 목록이 한 줄에 두 번 나갔다
            val = "" if c.value.startswith("없음") else f"({c.value})"
            out.append(f"{c.label if c.hit else c.okay}{val} [{c.layer}, 지역 공통]")
    if not forecasts:
        out.append("앞으로 날씨: 기상청 예보를 받지 못해 겹침 판단에서 뺐음")
    return out


def region_top(region: str, target: str, data: DongData, as_of: date | None = None) -> list[str]:
    """겹친 걱정이 많은 동(region_lines 와 같은 순서)."""
    names = data.region_dongs(region)
    forecasts = _forecast(data, region, names, as_of)
    sheets = [s for n in names if (s := sheet(n, target, data, forecasts or {}, as_of))]
    ranked = sorted(
        (s for s in sheets if s.patterns), key=lambda s: (-len(s.patterns), -len(s.hits), s.name)
    )
    return [s.name for s in ranked]


# 【판단】 10-20 페르소나 o02 r6: '상대 기준이면 22곳 중 7 ~ 8곳은 늘 걸리는 거 아냐?' · '논현1동
#        4가지 중 어떤 게 상대 기준이야?'에 '상대 기준이 아니다 → 섞여 있다 → 확인되지 않는다 →
#        3가지가 상대 기준 → 근거 없음'으로 다섯 번 바뀌었다(조건마다 기준 종류가 자료에 없었다).
#        정한 기준(늘 같은 잣대)인 조건을 코드가 정해 두고, 물으면 겹침마다 나눠 준다
FIXED = frozenset(
    {
        "pharmacy",
        "public",
        "meals",
        "clinic",
        "bus",
        "homecare",
        "past",
        "ahead",
        "holiday",
        "dayoff",
    }
)
BASIS_LINE = (
    "조건의 기준 종류: 정한 기준(늘 같은 잣대)인 조건은 약국 · 공공기관 거리, 동 안에 무료급식소 · "
    "의원 · 재가 돌봄 기관이 없음, 하루 3번 이하 버스, 지난 · 앞으로 사흘 궂은 날씨, "
    "긴 연휴 · 쉬는 날. "
    "나머지(사람 · 집 · 땅 · 경로당 · 수급 · 외출)는 같은 지역 동들 가운데 위쪽 3분의 1(올림 — "
    f"강남 22곳 중 {_third(22)}번째까지 · 춘천 25곳 중 {_third(25)}번째까지)에 들면 "
    "해당(상대 기준). "
    "지역 평균은 얼마나 큰지 보라고 적어 두는 참고 값이지 해당 여부의 기준이 아님. "
    "겹침은 정한 무리 조건이 서로 다른 겹 3가지 이상에서 함께 해당할 때라 상대 기준 조건만으로도 "
    "설 수 있음"
)


def basis_lines(name: str, target: str, data: DongData, as_of: date | None = None) -> list[str]:
    """그 동 겹침마다 정한 기준 · 상대 기준 조건을 나눈 줄(BASIS_LINE 위 판단)."""
    s = sheet(name, target, data, as_of=as_of)
    if s is None:
        return []
    if not s.patterns:
        return [f"{s.region} {name} {target}: 겹친 걱정 없음"]
    # 묻는 말('4가지 중 어떤 게 상대 기준?')에 바로 맞는 요약 줄을 코드가 센다(재생: 글쓴이가
    # 겹침마다의 조건 수를 더하다 '5개 중 4개' · '나머지 열 개'처럼 틀리게 셈)
    with_fixed = [p.title for p in s.patterns if any(c.key in FIXED for c in p.conds)]
    only_rel = [p.title for p in s.patterns if not any(c.key in FIXED for c in p.conds)]
    out = [
        f"{s.region} {name} {target} 겹친 걱정 {len(s.patterns)}가지 중 정한 기준 조건이 든 것 "
        f"{len(with_fixed)}가지({' / '.join(with_fixed) or '없음'}), 상대 기준 조건만으로 선 것 "
        f"{len(only_rel)}가지({' / '.join(only_rel) or '없음'})"
    ]
    for p in s.patterns:
        fixed = [c.label for c in p.conds if c.key in FIXED]
        rel = [c.label for c in p.conds if c.key not in FIXED]
        out.append(
            f"{s.region} {name} {target} 겹침 '{p.title}'의 조건 — 정한 기준 {len(fixed)}개"
            f"({' · '.join(fixed) or '없음'}) / 상대 기준 {len(rel)}개({' · '.join(rel) or '없음'})"
        )
    return out


def kind_counts(region: str, target: str, data: DongData, as_of: date | None = None) -> dict:
    """지역에서 '지금 닥친 걱정' · '지난 궂은 날씨 뒤 걱정'이 있는 동 수(region_lines 와 같은 셈).

    두 지역을 같은 잣대(정한 기준값)로 견줄 때 쓴다(10-20 페르소나 o06 r5 재생: 글쓴이가 강남
    '지난 궂은 날씨 뒤 걱정 8곳'을 '두 곳 모두 0곳'으로 썼다 — 숫자 0곳이 다른 줄에 있어 검사를
    지났다). 지역마다 따로 적은 줄을 준다
    """
    names = data.region_dongs(region)
    forecasts = _forecast(data, region, names, as_of)
    sheets = [s for n in names if (s := sheet(n, target, data, forecasts or {}, as_of))]
    now = sum(1 for s in sheets if any(p.now for p in s.patterns))
    after = sum(
        1 for s in sheets if not any(p.now for p in s.patterns) and any(p.after for p in s.patterns)
    )
    return {"now": now, "after": after, "of": len(sheets)}


OVERLAP_RULE = (
    "겹친 걱정은 미리 정한 모양(어르신 8가지 · 청년 3가지)마다 필요한 조건 무리가 정해져 있고, "
    "무리마다 하나 이상 해당하며 그 조건들이 서로 다른 겹(사람 · 집 · 동네 같은 자료 묶음) "
    "3가지 이상에 걸칠 때만 섬(예: '큰비에 집이 잠기거나 무너질 수 있음' = 큰비 + 지하층 · "
    "침수 흔적 · 비탈 가운데 하나 + 혼자 사시는 분이 많음). 겹친 걱정 1가지 = 그런 모양 하나가 "
    "선 것이라 한 동에 1가지만 있어도 '겹친 걱정이 있는 동'. '겹 3가지'는 한 겹친 걱정 안의 "
    "조건들이 걸친 자료 묶음 수이지 겹친 걱정의 개수가 아님. 조건이 여러 겹에 따로 해당해도 "
    "어느 모양에도 맞지 않으면 겹친 걱정이 아님"
)

# 【판단】 10-20 페르소나 o02: '세 겹 이상이라 한 기준은 뭐야?'에 글쓴이가 '정의가 없다'고 했다
#        (기준이 [참고]에만 있었다) → 판단의 기준을 사실 줄로 준다
RULE_LINE = (
    "판단 기준: 조건마다 같은 지역 동들 가운데 위쪽 3분의 1이거나 정한 기준"
    "(약국 5km · 공공기관 1km · "
    "날씨는 카드와 같은 기준값)을 넘으면 '해당'. "
    + OVERLAP_RULE
    + ". 같은 지역 안 상대 기준이라 위쪽 3분의 1은 어느 지역에나 있어서, "
    "앞으로 사흘 궂은 날씨 · 이레 안 긴 연휴가 든 것은 '지금 닥친 걱정', "
    "지난 사흘 궂은 날씨만 든 것은 '지난 궂은 날씨 뒤 걱정', "
    "상대 조건만으로 선 것은 '평소 구조 걱정'으로 나눔. "
    "취약 돌보미 동 순위(먼저 볼 동을 매기는 v2)와는 다른 것"
)

NOTES = (
    "해당 = 같은 지역 동들 가운데 위쪽 3분의 1이거나 정한 기준(약국 5km · 공공기관 1km 등)을 넘음",
    OVERLAP_RULE + ". 뜻 문장은 취약 돌보미가 미리 정해 둔 것",
    "모든 값은 동(읍면동) 단위 공개 자료라 한 분 한 분의 사정은 이 자료로 알 수 없음",
)
