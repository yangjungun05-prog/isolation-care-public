"""오늘 챙길 일 — 회원 담당 지역 기준 카드(비서 설계 v3 4절, 10-14 · 10-15 고침).

계기(궂은 날씨 · 폭염 · 긴 연휴 · 월초) → 담당 지역의 상태 → 출처 · 단추.
AI를 쓰지 않는다. 날씨 기록 · 공휴일 · 동 자료를 코드가 읽어 만든다(빠르고 돈이 들지 않음).

【정함 10-19 팀장】 할 일은 적지 않는다 — "카드 할 일은 적어두지마. 그냥 전체적인 status
       (상태)만 보여줘. 그래서 알아서 찾아가라고 해야지. 우리는 그냥 정보 제공하는 사람들이야".
       '(쉼터로 여는지 확인)' 같은 지시 꼬리도 뺐다.
【정함 10-19 팀장】 "해당하는 동 안에 있는 마을들 중에서 취약점이 눈에 보이는게 있으면 거기를
       적어줘" — 읍면 카드는 그 줄에서 두드러진 마을(리) 이름을 세 곳까지 적는다.
【정함 10-19 팀장】 카드 기한 문구('오늘(월) 오후 6시까지')는 뺀다("카드 기한 문구 <- 빼줘").
【정함 10-19 팀장】 담당 동을 여러 곳 고를 수 있다("선택할 수 있게 하자") — 고른 동들만
       구 담당처럼 합계로 본다(Who.member_dongs).
【정함 10-19 팀장】 청년 카드는 19 ~ 34세(youth_cards). 노인 카드와 따로 낸다.
【정함 10-20 팀장이 맡김】 "카드가 완전히 완성되었으면 … 뭐가 중요하고 뭐를 더 추가하고 …
       예외처리들도 모두" → ① 카드마다 '취약 돌보미 판단' 한 줄(챗봇과 같은 조건 창고 conditions.py
       —
       카드와 챗봇이 같은 판단을 말한다) ② 단추는 챗봇에 판단 질문을 보낸다 ③ 자료가 없는 날
       (관측 전 · 예보 밖 · 공휴일 자료 밖)은 '없다'고 밝힌다(data_notes)

【정함 10-12 팀장】 카드는 회원 담당 지역 기준("그 동은 폭우가 와요").
       먼저 볼 동 목록(순위)은 카드에 넣지 않는다 — 구 전체 담당이면 '어느 동부터 볼지 묻기'
       단추로 챗봇에 넘긴다.
【정함 10-19 팀장이 맡김】 구 전체 · 여러 동 카드 모양("이것도 바꿔보자" → "너한테 맡길게 전부"):
       합계만 쓰던 줄마다 값이 큰 동 세 곳의 이름을 붙이고(읍면 카드의 마을 이름처럼),
       날씨 예보 카드는 기준을 넘는 동 이름과 값을 적는다. 순위가 아니라 그 줄의 값이다.
【판단】 계기 기준값은 big-contest `src/bigcon/today.py`(09-27~)와 같다.
       기준값은 날씨 자료(weather.json thresholds)에서 읽는다. 우리 기준값으로 걸지 기상청 특보로
       걸지는 미정(기획설계 v2의 질문, big-contest docs/미정.md)이라 기준값을 그대로 둔다.
【정함 10-16 팀장】 비서의 '오늘'은 진짜 오늘. 날씨 카드는 기상청 특보가 나오면 특보로,
       없으면 동마다 단기예보가 우리 기준값을 넘을 때 선다(forecast.py, 동 격자 grids.json).
       지난 날짜를 주면 그날까지의 관측을 예보처럼 되짚는다
       (10-14 ~ 10-15의 방식, 시험 · 시연 되감기용). 카드에 밝힌다.
【정함 10-16 팀장】 카드는 간단하게 — 제목 · 둘째 줄(언제 몰리나 · 확률) · 안내 줄 · 먼저 볼
       곳(세 줄까지) ·
       출처(접힘) · 단추. 예시 10장(big-contest outputs/card_examples_1016)을 보고 "응"
       (10-19 할 일 칸을 뺌)
【판단】 믿을 만한 정도 딱지는 붙이지 않고 출처만 둔다(10-12 팀장: 답에는 딱지 없음.
       카드는 설계 v3 4절 제안 — 결정 대기). 출처는 카드에 실제로 쓴 줄의 자료만(10-15)
【판단】 카드 번호는 팀 ERD todo_card.card_id 규칙 '지역-종류-계기 첫날'(시군구 코드-종류-날짜).
       같은 계기는 동 담당 · 구 담당 모두 같은 카드이고, [했어요]는 회원마다 따로(todo_done)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

from src.assistant import basis as B
from src.assistant import forecast as fc
from src.assistant.data_source import DongData

LOOKAHEAD = 2  # 오늘 + 이틀
MERGE_GAP = 3  # 같은 종류가 사흘 안에 다시 오면 같은 카드
MAX_CARDS = 3  # 하루 최대 장수(09-27 팀장)
LEAD_HOLIDAY = 7  # 긴 연휴 1주 전부터
DOW = "월화수목금토일"
GROUP = {"폭우": "궂은 날씨", "한파": "궂은 날씨", "폭설": "궂은 날씨", "폭염": "폭염"}
# 【정함 10-20 팀장이 맡김 · 판단】 궂은 날씨 '뒤' 카드. 10-20(화) 서울 관측소에 10-18(일)
#        비 51.4mm가 왔는데 카드는 '사흘 안에 궂은 날씨가 없습니다'만 말했다(챗봇은 같은 날
#        '지난 궂은 날씨 뒤 걱정'을 말함). 큰비 · 눈은 그친 뒤에도 남는 것(잠긴 지하층 · 무른
#        비탈 · 빙판 · 쌓인 눈)이 있어 그친 다음 날부터 사흘(conditions.PAST_DAYS, 챗봇과 같은
#        날들) 동안 '폭우 뒤' · '폭설 뒤' 카드를 세운다. 한파 · 폭염은 그치면 남는 것이 적어
#        세우지 않는다(챗봇 조건표에는 든다). 같은 종류의 앞 카드(특보 · 예보 · 되짚기)가
#        서 있으면 세우지 않는다(그 카드가 말한다). 앞을 보는 날씨 카드 다음, 긴 연휴 앞에 둔다
AFTER = {"폭우": "폭우 뒤", "폭설": "폭설 뒤"}
BASE = {v: k for k, v in AFTER.items()}
AFTER_DAYS = 3
ORDER = {
    "폭우": 0, "한파": 0, "폭설": 0, "폭염": 1, "폭우 뒤": 1.5, "폭설 뒤": 1.5, "긴 연휴": 2,
    "월초 점검": 4,
}  # fmt: skip
COL_WORD = {"폭우": "비", "한파": "최저기온", "폭설": "새로 쌓인 눈", "폭염": "최고기온"}
# 【판단】 춘천 관측소 일자료에는 적설이 없어 '비 1mm 이상 · 최고 1도 이하'인 날을 눈 1cm로
#        어림했다(weather.json notes). 카드에 관측이 아니라 어림이라고 밝힌다
SNOW_ESTIMATED = {"춘천시"}

SOURCES = {
    "날씨": "기상청 ASOS 일자료(공공누리 1유형)",
    "예보": fc.SOURCE_FCST,
    "특보": fc.SOURCE_WRN,
    "연휴": "한국천문연구원 특일 정보(이용허락범위 제한 없음)",
    "사람": "행정안전부 주민등록 1인세대",
    "정원": "노인복지시설 정원(국민건강보험공단 장기요양기관 · 시설 표준데이터)",
    "서울": "서울시 독거노인 현황(공공누리 1유형)",
    "수급": "춘천시 기초생활보장 수급권자",
    "집": "국토교통부 건축물대장",
    "경로당": "서울시 경로당 현황 · 전국마을회관및경로당 표준데이터",
    "급식": "전국무료급식소 표준데이터",
    "약국": "소상공인시장진흥공단 상가(상권)정보(이용허락범위 제한 없음)",
    "보건": "건강보험심사평가원 병의원 현황(공공누리 1유형)",
    "버스": "국토교통부 TAGO 버스노선정보 · 춘천시 버스정류장 노선정보",
    "지하층": "국토교통부 건축물대장 층별개요(이용허락범위 제한 없음)",
    "산사태": "강원특별자치도 산사태취약지역 현황 2026-04-01(이용허락범위 제한 없음)",
    "급경사지": "행정안전부 급경사지 현황 2026-06-30(이용허락범위 제한 없음)",
    "침수": "서울시 침수흔적도 2010 ~ 2025(공공누리 1유형)",
    "약국시간": "국립중앙의료원 전국 약국 정보 · 요일별 운영 시간(이용허락범위 제한 없음)",
    "공공기관": "춘천시 행정복지센터 · 노인복지관(이용허락범위 제한 없음) · "
    "서울시 강남구 사회복지시설 목록(공공누리 1유형) · 심평원 병의원 현황(공공누리 1유형)",
}
# 경로당은 지역마다 자료가 다르다(places.json: 강남 서울시 2025-06 · 춘천 표준데이터)
HALL_SOURCE = {
    "강남구": "서울시 경로당 현황 2025-06(공공누리 1유형)",
    "춘천시": "전국마을회관및경로당 표준데이터",
}

EMPTY_HEAD = (
    "오늘부터 사흘 안에 궂은 날씨 · 긴 연휴 · 월초 점검이 없고, 지난 사흘 큰비 · 눈도 없었습니다. "
    "궁금한 것을 물어보세요."
)

# 【정함 10-16 팀장】 카드는 간단하게("카드가 그리 복잡할 이유까지는 없을것같긴한데",
#        예시 10장을 보고 "응").
#        '먼저 볼 곳'은 그 종류에 맞는 줄 두 개까지 + 80세 이상 혼자 사시는 분 한 줄.
#        서울시 독거노인 줄은 카드에서 뺀다(세는 방식이 달라 주민등록 숫자와 헷갈림 —
#        챗봇에서 설명과 함께)
# 【정함 10-16 팀장】 날씨마다 변수를 따로 — "비가 오면 … 반지하 + 지하에 살고 있는
#        사람들", "눈이나 우박이 오면 해당 온도가 너무 낮거나 혹은 집의 형태가 눈에 잘
#        막히는(물리적으로) 곳". 자료는 focus.json(10-18, 지하층 집 · 침수 흔적 · 산사태 ·
#        급경사지 · 약한 지붕 · 그날 문 연 약국).
# 【판단】 어느 줄을 앞에 둘지 · 약한 지붕(슬레이트 · 함석 · 판넬 · 초가)의 범위 · 약국 5km는
#        Claude 판단(팀장 확인 전, big-contest docs/미정.md 10-16 '먼저 볼 곳의 기준').
# 【정함 10-19 팀장】 읍면 카드는 두드러진 마을(리) 이름을 적는다(VILLAGE_MAX곳까지, 값이 큰 순).
# 【판단】 집이 MIN_HOMES채가 안 되는 마을은 이름을 쓰지 않는다(10-16 팀장 '인구가 한두 명이면
#        의미가 없을 것 같다'. 리별 인구 자료가 없어 집 수로 거름 — 미정)
FOCUS = {
    "폭우": ("basement_home", "flood", "basement", "slope", "pharmacy", "bus", "health"),
    "한파": ("halls", "livelihood", "pharm_far", "weak_roof", "pharmacy", "bus", "walkup"),
    "폭설": ("walkup", "weak_roof", "steep", "pharm_far", "bus", "pharmacy"),
    "폭염": ("halls", "walkup", "pharmacy"),
    "긴 연휴": ("meals", "livelihood", "health", "pharmacy"),
    "월초 점검": ("trend",),
}
# 면(읍면)은 순서가 다르다 — 산비탈 · 약국 · 버스가 먼저(10-16 예시 2 · 5 · 8을 날씨마다로)
FOCUS_MYEON = {
    "폭우": ("slope", "basement_home", "basement", "pharmacy", "bus", "health"),
    "한파": ("pharm_far", "livelihood", "pharmacy", "bus", "halls"),
    "폭설": ("pharm_far", "weak_roof", "steep", "bus", "pharmacy", "walkup"),
    "폭염": ("pharmacy", "bus", "halls"),
    "긴 연휴": ("health", "pharmacy", "meals", "livelihood"),
    "월초 점검": ("trend",),
}
FAR_KM = 5  # 그날 문 연 약국이 이보다 먼 마을(10-16 팀장 '약국으로부터 거리가 5KM이상 된 곳')
# 【정함 10-19 팀장】 공공기관은 5km가 너무 길다("1km만 해도 괜찮을거라 … 네가 판단해서").
# 【판단】 1km(직선). 경로당 · 마을회관 가운데에서 직선 1km면 길로는 더 멀어 어르신 걸음으로
#        20 ~ 30분이다. 춘천 읍면 마을 72곳 중 48곳이 넘어 카드는 가장 먼 세 곳의 이름을 붙인다.
#        동 지역은 동 하나에 가운데 한 점이라 걸음 거리로 읽기 어려워 마을(리)만 센다
PUBLIC_KM = 1
COVER = 0.9  # 층별개요를 받은 몫이 이만큼 넘어야 '지하층에 집' 줄을 쓴다(아니면 표제부 어림 줄)
FOCUS_MAX = 2
VILLAGE_MAX = 3
MIN_HOMES = 20
# 【판단】 '많이 늘어난 곳'은 1년 새 이만큼 넘게 는 동만(10-19: '대치1동 +1명'이 나와서)
MIN_UP = 10
# 강남은 경로당만, 춘천은 경로당 · 마을회관(10-16: 강남 카드에 '마을회관'이 나왔다)
HALL_WORD = {"강남구": "경로당", "춘천시": "경로당 · 마을회관"}
FAC_MIX = 0.3  # 요양시설 정원이 80세 이상 혼자 사시는 분의 30% 이상이면 섞였을 수 있다고 밝힌다


class Member(Protocol):
    """카드를 받을 회원의 담당 지역(팀 ERD member_region). 챗봇의 Profile 도 같은 칸을 갖는다."""

    member_region: str | None
    member_dong: str | None


@dataclass
class Who:
    """카드만 쓸 때의 담당 지역(10-16: 카드를 챗봇과 떼어 팀 저장소로 옮김).

    member_dongs = 담당 동 여러 곳(팀 ERD member_region 여러 줄, 10-19 팀장). 한 곳이면
    member_dong 과 같다.
    """

    member_region: str | None = None
    member_dong: str | None = None
    member_dongs: list[str] = field(default_factory=list)


def _picked(profile: Member) -> list[str]:
    many = list(dict.fromkeys(getattr(profile, "member_dongs", None) or []))
    if many:
        return many
    return [profile.member_dong] if profile.member_dong else []


class _Some:
    """고른 동 여러 곳만 보이는 자료 창구 — 구 담당 카드의 셈을 그 동들에만 쓴다."""

    def __init__(self, data: DongData, names: list[str]):
        self._data, self._names = data, names

    def region_dongs(self, region: str) -> list[str]:
        return [n for n in self._data.region_dongs(region) if n in self._names]

    def grids(self, region: str) -> dict:
        return {n: g for n, g in self._data.grids(region).items() if n in self._names}

    def picked(self) -> list[str]:
        return list(self._names)

    def __getattr__(self, name: str):
        return getattr(self._data, name)


@dataclass
class Card:
    id: str  # 팀 ERD todo_card.card_id — 시군구 코드-종류-계기 첫날
    kind: str  # 폭우 · 한파 · 폭설 · 폭염 · 긴 연휴 · 월초 점검
    group: str
    label: str  # '폭우 알림'
    sgg_cd: str
    where: str  # '강남구 수서동' · '강남구'
    title: str  # '비 18일 52mm'
    sub: str  # 둘째 줄 — '15~17시에 가장 셈 · 비 올 확률 90%'
    note: str  # 작은 글씨 — '강남구 수서동 · 기상청 예보 10월 16일 14시 발표(바뀔 수 있음)'
    why: str  # 근거 문장(출처를 펼치면)
    rule: str = ""  # 이 카드가 선 기준(팀 ERD todo_rule.threshold)
    start: str = ""  # 계기 첫날(정렬용)
    days: list[str] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)  # 먼저 볼 곳(세 줄까지)
    sources: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    asks: dict[str, str] = field(default_factory=dict)  # 단추 → 챗봇에 보낼 질문
    targets: list[dict] = field(default_factory=list)  # 팀 ERD todo_target — 담당 동
    judge: str = ""  # 취약 돌보미 판단 한 줄(conditions.py, 챗봇과 같은 판단)


def _d(x: date) -> str:
    return f"{x.month}월 {x.day}일({DOW[x.weekday()]})"


def _area(dong: str | None) -> str:
    return "면" if dong and dong.endswith(("면", "읍")) else "동"


def _workday(x: date, hol: dict[str, str]) -> bool:
    return x.weekday() < 5 and x.isoformat() not in hol


def _episodes(days: dict[str, dict], col: str, op: str, v: float) -> list[list[date]]:
    hit = sorted(
        date.fromisoformat(k)
        for k, r in days.items()
        if r.get(col) is not None and (r[col] >= v if op == ">=" else r[col] <= v)
    )
    out: list[list[date]] = []
    for x in hit:
        if out and (x - out[-1][-1]).days <= MERGE_GAP:
            out[-1].append(x)
        else:
            out.append([x])
    return out


Line = tuple[str, tuple[str, ...]]  # (문장, 그 문장이 쓴 출처 이름들 — SOURCES 의 키)


def _more(n: int) -> str:
    return f"{n:,}명 늘어남" if n > 0 else f"{-n:,}명 줄어듦" if n < 0 else "그대로"


def _ym(iso: str) -> str:
    return iso[:7]


def _people(data: DongData, name: str) -> dict:
    """동의 사람 수 — 2026 최신 판(people.json)이 있으면 그것, 없으면 동 자료(dong_profiles)."""
    p = data.people() or {}
    row = (p.get("dongs") or {}).get(name)
    if row:
        return {
            "solo80": row["solo80"],
            "solo65": row["solo65"],
            "solo65_prev": row["solo65_prev"],
            "basis": _ym(p["basis"]),
            "prev": _ym(p["prev"]),
        }
    d = data.dong(name) or {}
    s65 = d.get("solo65") or {}
    pm = B.months(s65) or (None, None)
    return {
        "solo80": (d.get("solo80") or {}).get("n"),
        "solo65": s65.get(pm[1]) if pm[1] else None,
        "solo65_prev": s65.get(pm[0]) if pm[0] else None,
        "basis": pm[1] or B.reg(),
        "prev": pm[0] or B.reg_prev(),
    }


def _day_code(day: date | None, hol: dict[str, str]) -> int | None:
    """focus.json 약국 칸의 요일 번호(1 월 … 7 일, 8 공휴일)."""
    if day is None:
        return None
    return 8 if day.isoformat() in hol else day.isoweekday()


def _fv(data: DongData, name: str) -> dict:
    get = getattr(data, "focus", None)
    return (get(name) if get else None) or {}


def _rows(fv: dict) -> list[dict]:
    """동이면 그 동 한 줄, 면이면 마을(리)마다."""
    return fv.get("villages") or ([fv] if fv else [])


def _top(villages: list[dict], value, unit: str) -> str:
    """두드러진 마을(리) 이름 — 값이 큰 순 VILLAGE_MAX곳, 집이 MIN_HOMES채 넘는 마을만.

    예: '청평리 32곳 · 추곡리 20곳 · 조교리 15곳'. 없으면 빈 글.
    """
    hit = [
        (value(r), r["name"])
        for r in villages
        if r.get("name") and (r.get("homes") or 0) >= MIN_HOMES and (value(r) or 0) > 0
    ]
    hit.sort(key=lambda t: (-t[0], t[1]))
    return " · ".join(f"{name} {v:,g}{unit}" for v, name in hit[:VILLAGE_MAX])


def _top_dongs(
    pairs: list[tuple[str, float]], unit: str, plus: bool = False, floor: float = 0
) -> str:
    """두드러진 동 이름 — 값이 큰 순 VILLAGE_MAX곳(구 · 여러 동 담당 카드).

    예: '논현1동 610채 · 역삼2동 540채 · 대치4동 400채'. 없으면 빈 글.
    """
    hit = sorted(
        ((v, n) for n, v in pairs if (v or 0) > 0 and v >= floor), key=lambda t: (-t[0], t[1])
    )
    return " · ".join(f"{n} {'+' if plus else ''}{v:,g}{unit}" for v, n in hit[:VILLAGE_MAX])


def _weather_facts(
    names: list[str], data: DongData, day: date | None, region: str | None
) -> dict[str, Line]:
    """날씨마다 먼저 볼 곳 줄(10-18, focus.json). region 이 있으면 구 · 여러 동 합계.

    【정함 10-19 팀장이 맡김】 구 · 여러 동 담당 카드도 읍면 카드의 마을 이름처럼 줄마다 값이 큰
           동 세 곳의 이름을 붙인다("너한테 맡길게 전부"). 순위(먼저 볼 동)가 아니라 그 줄의 값이
           큰 곳이다 — 순위는 여전히 챗봇에서(10-12 팀장)
    """
    fvs = [_fv(data, n) for n in names]
    rows = [r for fv in fvs for r in _rows(fv)]
    if not rows:
        return {}
    out: dict[str, Line] = {}
    tot = lambda k: sum(r.get(k) or 0 for r in rows)  # noqa: E731
    villages = [] if region else [r for fv in fvs for r in fv.get("villages") or []]
    owner = {id(r): n for n, fv in zip(names, fvs, strict=True) for r in _rows(fv)}

    def per_dong(value, among: list[dict] | None = None) -> list[tuple[str, float]]:
        sums: dict[str, float] = {}
        for r in rows if among is None else among:
            sums[owner[id(r)]] = sums.get(owner[id(r)], 0) + (value(r) or 0)
        return list(sums.items())

    def top(value, unit: str, among: list[dict] | None = None) -> str:
        """마을(읍면 한 곳 담당) 또는 동(구 · 여러 동 담당) 이름."""
        if region:
            return _top_dongs(per_dong(value, among), unit)
        pool = villages if among is None else [r for r in among if r in villages]
        return _top(pool, value, unit)

    def named(head: str, value, unit: str) -> str:
        t = top(value, unit)
        if region and t:
            return f"{head}, 많은 곳 {t}"
        return f"{head}, {t}" if t else head

    need, got = tot("basement_lots_need"), tot("basement_lots_fetched")
    if need and got >= COVER * need and tot("basement_home"):
        out["basement_home"] = (
            named(
                f"지하층에 집이 있는 건물 {'합계 ' if region else ''}{tot('basement_home'):,}채",
                lambda r: r.get("basement_home"),
                "채",
            ),
            ("지하층",),
        )
    years = sorted({y for r in rows for y in str(r.get("flood_years") or "").split(",") if y})
    if years:
        if region:
            hit = sum(1 for fv in fvs if any(r.get("flood_sites") for r in _rows(fv)))
            t = top(lambda r: r.get("flood_sites"), "곳")
            text = (
                f"침수 흔적이 나온 동 {hit}곳({years[0]}~{years[-1]}년"
                f"{', 흔적이 많은 곳 ' + t if t else ''})"
            )
        else:
            span = " · ".join(years) if len(years) <= 3 else f"{years[0]}~{years[-1]}년 중"
            text = (
                f"침수 흔적이 나온 해 {len(years)}번({span}{'년' if len(years) <= 3 else ''}, "
                f"흔적 {int(tot('flood_sites')):,}곳)"
            )
        out["flood"] = (text, ("침수",))
    ls, st = tot("landslide"), tot("steep")
    if ls or st:
        parts = ([f"산사태취약지역 {ls}곳"] if ls else []) + ([f"급경사지 {st}곳"] if st else [])
        keys = (("산사태",) if ls else ()) + (("급경사지",) if st else ())
        slope = lambda r: (r.get("landslide") or 0) + (r.get("steep") or 0)  # noqa: E731
        tail = ""
        if villages:
            n = sum(1 for r in villages if slope(r))
            t = top(slope, "곳")
            tail = f"(마을 {n}곳에 걸침{', 많은 곳 ' + t if t else ''})"
        elif region:
            t = top(slope, "곳")
            tail = f"(많은 곳 {t})" if t else ""
        out["slope"] = (" · ".join(parts) + tail, keys)
    if st:
        out["steep"] = (
            named(
                f"급경사지(비탈) {'합계 ' if region else ''}{st}곳", lambda r: r.get("steep"), "곳"
            ),
            ("급경사지",),
        )
    if tot("weak_roof"):
        out["weak_roof"] = (
            named(
                f"눈 무게에 약한 지붕(슬레이트 · 함석 · 판넬) 집 {'합계 ' if region else ''}"
                f"{tot('weak_roof'):,}채",
                lambda r: r.get("weak_roof"),
                "채",
            ),
            ("집",),
        )
    # 【정함 10-19 팀장】 공공기관 = 행정복지센터 · 보건지소(보건기관) · 노인복지관 · 병원
    #        ("등등을 보면 될 것 같은데"). public_km = 그중 가장 가까운 곳(focus.json).
    #        10-16 팀장 말("약국으로부터 5KM 이상 … 공공기관도 근처에 없는 곳")대로
    #        약국 줄에 붙인다. 거리는 PUBLIC_KM(10-19 팀장이 맡김), 읍면 마을(리)만 센다
    # 【판단】 구 · 여러 동 담당은 '먼 마을이 많은 읍면' 세 곳(마을 수)
    pub_rows = [r for fv in fvs if fv.get("unit") == "면" for r in fv.get("villages") or []]
    pub_placed = [r for r in pub_rows if r.get("public_km") is not None and r.get("halls")]
    pub_far = [r for r in pub_placed if r["public_km"] > PUBLIC_KM]
    far_word = "먼 마을이 많은 곳" if region else "먼 곳"
    pub_val = (lambda r: 1) if region else (lambda r: r["public_km"])  # noqa: E731
    pub_unit = "곳" if region else "km"
    pub_top = top(pub_val, pub_unit, pub_far)
    pub_text = (
        f"공공기관(행정복지센터 · 보건기관 · 노인복지관 · 병원)이 {PUBLIC_KM}km 넘게 먼 마을 "
        f"{len(pub_far)}곳(경로당 있는 마을 {len(pub_placed)}곳 중"
        f"{', ' + far_word + ' ' + pub_top if pub_top else ''})"
    )
    k = _day_code(day, data.holidays())
    if k:
        placed = [r for r in rows if r.get(f"pharm_km_{k}") is not None and r.get("halls")]
        far = [r for r in placed if r[f"pharm_km_{k}"] > FAR_KM]
        if far:
            when = "공휴일" if k == 8 else f"{DOW[k - 1]}요일"
            km = f"pharm_km_{k}"
            t = top((lambda r: 1) if region else (lambda r: r[km]), pub_unit, far)
            both = [r for r in far if r in pub_far]
            tail = ""
            if both:
                names_ = top(pub_val, pub_unit, both)
                tail = (
                    f". 그중 공공기관(행정복지센터 · 보건기관 · 노인복지관 · 병원)도 {PUBLIC_KM}km "
                    f"넘게 먼 마을 {len(both)}곳{'(' + names_ + ')' if names_ else ''}"
                )
            out["pharm_far"] = (
                f"{when}에 문 연 약국이 {FAR_KM}km 넘게 먼 마을 {len(far)}곳"
                f"(경로당 있는 마을 {len(placed)}곳 중{', ' + far_word + ' ' + t if t else ''})"
                f"{tail}",
                ("약국시간", "경로당") + (("공공기관",) if both else ()),
            )
    if pub_far and "pharm_far" not in out:
        out["pharm_far"] = (pub_text, ("공공기관",))
    return out


def _dong_facts(
    kind: str, region: str, dong: str, data: DongData, day: date | None = None
) -> dict[str, Line]:
    """그 동에서 카드에 쓸 수 있는 줄들(종류마다 FOCUS 순서로 고른다). 숫자는 자료 그대로."""
    d = data.dong(dong) or {}
    p = data.places(dong) or {}
    out: dict[str, Line] = {}
    h = d.get("housing") or {}
    if h.get("basement_old"):
        out["basement"] = (f"반지하가 있을 수 있는 옛 집 {h['basement_old']:,}채", ("집",))
    if h.get("old_walkup_units"):
        out["walkup"] = (
            f"30년 넘은 계단 집(승강기 없는 3~5층) {h['old_walkup_units']:,}가구",
            ("집",),
        )
    halls = len(((p.get("halls") or {}).get("list")) or [])
    if halls:
        out["halls"] = (f"{HALL_WORD[region]} {halls}곳", ("경로당",))
    if p.get("meals"):
        out["meals"] = (f"무료급식소 {len(p['meals'])}곳", ("급식",))
    lv = d.get("livelihood")
    if lv:
        out["livelihood"] = (
            f"기초생활수급자 {lv['people']:,}명({lv['year']}년, "
            f"주민 100명당 {lv['per100']}명 · 춘천 평균 {lv['city_per100']}명)",
            ("수급",),
        )
    if _area(dong) == "면":
        ph = (p.get("shops") or {}).get("약국") or {}
        if ph.get("n") == 0 and ph.get("nearest"):
            ne = ph["nearest"]
            out["pharmacy"] = (
                f"면 안에 약국 없음. 가장 가까운 {ne['name']}({ne['dong']}), "
                f"마을 경로당들 가운데에서 직선 {ne['km']}km",
                ("약국",),
            )
        b = data.bus(dong) or {}
        if b.get("low_freq"):
            out["bus"] = (f"하루 3번 이하 버스(어림): {', '.join(b['low_freq'][:3])}", ("버스",))
        health = [x["name"] for x in p.get("health") or []]
        if health:
            out["health"] = (f"보건지소 · 진료소: {', '.join(health[:3])}", ("보건",))
    pe = _people(data, dong)
    if pe["solo65"] and pe["solo65_prev"]:
        a, b = pe["solo65_prev"], pe["solo65"]
        out["trend"] = (
            f"65세 이상 혼자 사시는 분 {a:,}명 → {b:,}명"
            f"({pe['prev']} → {pe['basis']}, {_more(b - a)})",
            ("사람",),
        )
    out.update(_weather_facts([dong], data, day, None))
    return out


def _solo80_line(names: list[str], data: DongData, region: str | None) -> Line | None:
    """80세 이상 혼자 사시는 분 — 늘 맨 뒤 한 줄. 요양시설 정원이 크면 그 줄에 밝힌다(10-04 팀장
    '빼지 말고 표시')."""
    total, caps, basis = 0, 0, ""
    each: list[tuple[str, float]] = []
    for n in names:
        pe = _people(data, n)
        if pe["solo80"] is None:
            continue
        total += pe["solo80"]
        each.append((n, pe["solo80"]))
        caps += ((data.dong(n) or {}).get("solo80") or {}).get("care_cap") or 0
        basis = pe["basis"]
    if not total:
        return None
    keys: tuple[str, ...] = ("사람",)
    tail = ""
    if region is None and caps and caps >= total * FAC_MIX:
        tail = f", 요양시설 정원 {caps:,}명이 섞였을 수 있음"
        keys = ("사람", "정원")
    if region:
        # 【정함 10-19 팀장이 맡김】 구 · 여러 동 담당은 많은 동 세 곳의 이름도
        t = _top_dongs(each, "명")
        return (
            f"80세 이상 혼자 사시는 분 합계 {total:,}명({len(names)}곳, 주민등록 {basis})"
            f"{', 많은 곳 ' + t if t else ''}",
            keys,
        )
    return (f"80세 이상 혼자 사시는 분 {total:,}명(주민등록 {basis}{tail})", keys)


def _region_facts(
    kind: str, region: str, data: DongData, day: date | None = None
) -> dict[str, Line]:
    """구 · 시 전체(또는 고른 여러 동) — 합계와, 줄마다 값이 큰 동 세 곳(10-19 팀장이 맡김).
    먼저 볼 동의 순위는 넣지 않는다(챗봇에서, 10-12 팀장)."""
    names = data.region_dongs(region)
    rows = [data.dong(n) or {} for n in names]
    places = [data.places(n) or {} for n in names]
    out: dict[str, Line] = {}

    def total(f) -> int:
        return sum(f(r) or 0 for r in rows)

    def most(f, unit: str) -> str:
        t = _top_dongs([(n, f(r)) for n, r in zip(names, rows, strict=True)], unit)
        return f", 많은 곳 {t}" if t else ""

    def listed(hit: list[str]) -> str:
        more = len(hit) - VILLAGE_MAX
        return " · ".join(hit[:VILLAGE_MAX]) + (f" 외 {more}곳" if more > 0 else "")

    old = lambda r: (r.get("housing") or {}).get("basement_old")  # noqa: E731
    n = total(old)
    if n:
        out["basement"] = (f"반지하가 있을 수 있는 옛 집 합계 {n:,}채{most(old, '채')}", ("집",))
    walk = lambda r: (r.get("housing") or {}).get("old_walkup_units")  # noqa: E731
    n = total(walk)
    if n:
        out["walkup"] = (
            f"30년 넘은 계단 집(승강기 없는 3~5층) 합계 {n:,}가구{most(walk, '가구')}",
            ("집",),
        )
    n = sum(len(((p.get("halls") or {}).get("list")) or []) for p in places)
    if n:
        out["halls"] = (f"{HALL_WORD[region]} {n:,}곳", ("경로당",))
    n = sum(len(p.get("meals") or []) for p in places)
    if n:
        out["meals"] = (f"무료급식소 {n}곳", ("급식",))
    lv = [r["livelihood"] for r in rows if r.get("livelihood")]
    if lv:
        out["livelihood"] = (
            f"기초생활수급자 합계 {sum(x['people'] for x in lv):,}명({lv[0]['year']}년)",
            ("수급",),
        )
    myeon = [n for n in names if _area(n) == "면"]
    if myeon:
        no_ph = [
            n
            for n in myeon
            if (((data.places(n) or {}).get("shops") or {}).get("약국") or {}).get("n") == 0
        ]
        low = [n for n in myeon if (data.bus(n) or {}).get("low_freq")]
        out["pharmacy"] = (
            f"읍면 {len(myeon)}곳 중 약국이 없는 곳 {len(no_ph)}곳"
            + (f"({listed(no_ph)})" if no_ph else ""),
            ("약국",),
        )
        out["bus"] = (
            f"하루 3번 이하 버스가 다니는 읍면 {len(low)}곳"
            f"(어림{', ' + listed(low) if low else ''})",
            ("버스",),
        )
    pes = [_people(data, n) for n in names]
    if all(pe["solo65"] and pe["solo65_prev"] for pe in pes):
        a = sum(pe["solo65_prev"] for pe in pes)
        b = sum(pe["solo65"] for pe in pes)
        up = _top_dongs(
            [(n, pe["solo65"] - pe["solo65_prev"]) for n, pe in zip(names, pes, strict=True)],
            "명",
            plus=True,
            floor=MIN_UP,
        )
        out["trend"] = (
            f"65세 이상 혼자 사시는 분 합계 {a:,}명 → {b:,}명"
            f"({pes[0]['prev']} → {pes[0]['basis']}, {_more(b - a)}"
            f"{', 많이 늘어난 곳 ' + up if up else ''})",
            ("사람",),
        )
    out.update(_weather_facts(names, data, day, region))
    return out


def _focus(
    kind: str, region: str, dong: str | None, data: DongData, day: date | None = None
) -> tuple[list[str], list[str]]:
    """(먼저 볼 곳 줄들, 그 줄들이 쓴 출처 이름들). day = 계기 첫날(그날 문 연 약국)."""
    facts = (
        _dong_facts(kind, region, dong, data, day)
        if dong
        else _region_facts(kind, region, data, day)
    )
    if "basement_home" in facts:
        facts.pop("basement", None)  # 층별개요로 센 줄이 있으면 표제부 어림 줄은 겹쳐서 뺀다
    order = FOCUS_MYEON if dong and _area(dong) == "면" else FOCUS
    lines = [facts[k] for k in order[BASE.get(kind, kind)] if k in facts][:FOCUS_MAX]
    tail = _solo80_line(
        [dong] if dong else data.region_dongs(region), data, None if dong else region
    )
    if tail:
        lines.append(tail)
    keys = list(dict.fromkeys(k for _, ks in lines for k in ks))
    names = [HALL_SOURCE.get(region, SOURCES[k]) if k == "경로당" else SOURCES[k] for k in keys]
    return [t for t, _ in lines], names


def _rule(kind: str, w: dict) -> str:
    if kind == "긴 연휴":
        return "공휴일이 낀 3일 이상 연휴, 1주 전부터"
    if kind == "월초 점검":
        return "매달 첫 근무일부터 10일까지"
    col, op, v, unit = w["thresholds"][kind]
    return f"하루 {COL_WORD[kind]} {v:g}{unit} {'이상' if op == '>=' else '이하'}, 오늘부터 사흘 안"


ASK_WORD = {
    "폭우": "비 오는데",
    "한파": "추운데",
    "폭설": "눈 오는데",
    "폭염": "더운데",
    "긴 연휴": "연휴 앞두고",
    "월초 점검": "요즘",
    "폭우 뒤": "비 온 뒤",
    "폭설 뒤": "눈 온 뒤",
}


def _asks(
    kind: str, start: date, region: str, dong: str | None, some: list[str] | None = None
) -> dict[str, str]:
    """단추를 누르면 챗봇에 보낼 질문(카드 맥락을 문장에 담는다).

    【판단】 날씨 카드는 그날을 문장에 넣는다(10-15: 날짜 없이 '폭우 때 수서동은?'을 보내자
           챗봇이 7~12월 전체 폭우 이야기를 했다. 데스크는 '7월 16일'을 날짜 칸에 적는다)
    """
    when = f"{start.month}월 {start.day}일 " if kind in GROUP else ""
    # 【정함 10-20 팀장이 맡김】 '자세히 묻기'는 챗봇의 취약 돌보미 판단(outlook)으로 — 카드의 날씨
    #        · 날을
    #        문장에 담아 그날의 조건표로 답하게 한다
    lead = f"{when}{ASK_WORD[kind]} " if kind in ASK_WORD else ""
    if dong:
        return {
            "자세히 묻기": f"{lead}{dong} 어르신들 괜찮으실까요?",
            "동 상황 문서": f"{dong} 동 상황 문서 만들어 줘",
        }
    # 뒤 카드는 날짜를 넣지 않는다 — 데스크가 그날을 '오늘'로 잡으면 그날 앞 사흘을 본다
    first = f"{when}{kind} 때 " if kind in GROUP else f"{ASK_WORD[kind]} " if kind in BASE else ""
    where = " · ".join(some) if some else region
    rank = f"{where} 중 어느 동부터" if some else f"{region} 어느 동부터"
    return {
        "어느 동부터 볼지 묻기": f"{first}{rank} 봐야 해요?",
        "취약 돌보미 판단 보기": f"{lead}{where} 어르신들 괜찮으실까요?",
    }


def _buttons(dong: str | None) -> list[str]:
    # 【정함 10-19 팀장】 "했어요 단추는 필요 없을듯 일단. 주석 처리해놔 지우진 말고" —
    #        카드에서 단추만 뺀다. 기록 API(POST /assistant/today/{card_id}/done) · done.py ·
    #        화면의 기록 창 코드는 그대로
    # if dong:
    #     return ["자세히 묻기", "동 상황 문서", "했어요"]
    # return ["어느 동부터 볼지 묻기", "했어요"]
    if dong:
        return ["자세히 묻기", "동 상황 문서"]
    return ["어느 동부터 볼지 묻기", "취약 돌보미 판단 보기"]


def _make(
    kind: str,
    start: date,
    region: str,
    dong: str | None,
    data: DongData,
    *,
    rule: str | None = None,
    trigger: list[str] | None = None,
    note: str = "",
    sub: str = "",
    focus_day: date | None = None,
    **kw,
) -> Card:
    sgg = data.region_code(region)
    some = data.picked() if isinstance(data, _Some) else []
    where = f"{region} {dong}" if dong else f"{region} {' · '.join(some)}" if some else region
    day = focus_day or (start if kind in GROUP else None)
    focus, sources = _focus(kind, region, dong, data, day)
    if trigger is None:
        trigger = [] if kind == "월초 점검" else [SOURCES["연휴" if kind == "긴 연휴" else "날씨"]]
    if rule is None:
        rule = _rule(kind, data.weather()) if kind in GROUP else _rule(kind, {})
    on = [dong] if dong else some
    return Card(
        id=f"{sgg}-{kind}-{start.isoformat()}",
        kind=kind,
        group=GROUP.get(BASE.get(kind, kind), kind),
        label=f"{kind} 알림" if kind in GROUP or kind in BASE or kind == "긴 연휴" else kind,
        sgg_cd=sgg,
        where=where,
        sub=sub,
        note=f"{where} · {note}" if note else where,
        start=start.isoformat(),
        rule=rule,
        focus=focus,
        sources=list(dict.fromkeys(trigger + sources)),
        buttons=_buttons(dong),
        asks=_asks(kind, start, region, dong, some),
        targets=[{"dong_cd": (data.dong(n) or {}).get("dong_cd", ""), "dong": n} for n in on],
        **kw,
    )


def _weather_title(
    kind: str, region: str, vals: list[tuple[date, float]], estimated: bool | None = None
) -> str:
    if kind == "폭우":
        total = sum(v for _, v in vals)
        return f"비 {'·'.join(f'{x.day}일' for x, _ in vals)} {total:,.0f}mm"
    if kind in ("한파", "폭염"):
        pick = min if kind == "한파" else max
        x, v = pick(vals, key=lambda t: t[1])
        return f"{_d(x)} {'아침 최저' if kind == '한파' else '낮 최고'} {v:.1f}℃"
    x, v = vals[0]
    if region in SNOW_ESTIMATED if estimated is None else estimated:
        return f"{_d(x)} 눈(어림)"
    return f"{_d(x)} 눈 {v:.0f}cm"


def _weather_why(kind: str, region: str, vals, days: dict, station: str) -> str:
    if kind == "폭설" and region in SNOW_ESTIMATED:
        parts = [
            f"{_d(x)} 비 {days[x.isoformat()]['rain']:.1f}mm · 최고기온 "
            f"{days[x.isoformat()]['tmax']:.1f}℃"
            for x, _ in vals
        ]
        return (
            ", ".join(parts)
            + f" — {station}에는 쌓인 눈 기록이 없어 비가 오고 최고기온이 1℃ 이하인 날을 "
            "눈 온 날로 어림(기준일까지의 관측값을 예보처럼 되짚어 봄)"
        )
    unit = {"폭우": "mm", "폭설": "cm"}.get(kind, "℃")
    why = ", ".join(f"{_d(x)} {COL_WORD[kind]} {v:.1f}{unit}" for x, v in vals)
    return why + f" — {station} 관측(기준일까지의 관측값을 예보처럼 되짚어 봄)"


def _weather_cards(d: date, region: str, dong: str | None, data: DongData) -> list[Card]:
    """지난 날 되짚기 — 그날까지의 기상청 관측을 예보처럼(시험 · 시연 되감기)."""
    w = data.weather()
    reg = (w.get("regions") or {}).get(region) or {}
    days = reg.get("days") or {}
    station = reg.get("station", "")
    window = [d + timedelta(days=i) for i in range(LOOKAHEAD + 1)]
    cards = []
    for kind, (col, op, v, _unit) in (w.get("thresholds") or {}).items():
        for ep in _episodes(days, col, op, v):
            if not (ep[0] - timedelta(days=LOOKAHEAD) <= d <= ep[-1]):
                continue
            hit = [x for x in window if x in ep]
            if not hit:
                continue
            vals = [(x, float(days[x.isoformat()][col])) for x in hit]
            cards.append(
                _make(
                    kind,
                    ep[0],
                    region,
                    dong,
                    data,
                    note=f"{station} 관측(지난 날을 되짚음)",
                    title=_weather_title(kind, region, vals),
                    why=_weather_why(kind, region, vals, days, station),
                    days=[x.isoformat() for x in hit],
                )
            )
    return cards


def _after_cards(
    d: date, region: str, dong: str | None, data: DongData, found: list[Card]
) -> list[Card]:
    """큰비 · 눈이 그친 다음 날부터 사흘 — 관측(AFTER 위 판단).

    앞 카드(특보 · 예보 · 되짚기)가 같은 종류면 세우지 않는다."""
    w = data.weather() or {}
    reg = (w.get("regions") or {}).get(region) or {}
    days = reg.get("days") or {}
    station = reg.get("station", "")
    have = {c.kind for c in found}
    seen = [date.fromisoformat(k) for k in days if date.fromisoformat(k) < d]
    last = max(seen) if seen else None
    out = []
    for kind, after in AFTER.items():
        t = (w.get("thresholds") or {}).get(kind)
        if not t or kind in have:
            continue
        col, op, v, unit = t
        eps = [
            ep
            for ep in _episodes(days, col, op, v)
            if ep[-1] < d <= ep[-1] + timedelta(days=AFTER_DAYS)
        ]
        if not eps:
            continue
        ep = eps[-1]
        vals = [(x, float(days[x.isoformat()][col])) for x in ep]
        gap = (d - ep[-1]).days
        if kind == "폭설" and region in SNOW_ESTIMATED:
            seen_text = ", ".join(
                f"{_d(x)} 비 {days[x.isoformat()]['rain']:.1f}mm · 최고기온 "
                f"{days[x.isoformat()]['tmax']:.1f}℃(눈 온 날로 어림)"
                for x in ep
            )
        else:
            seen_text = ", ".join(f"{_d(x)} {COL_WORD[kind]} {val:.1f}{unit}" for x, val in vals)
        # 관측은 하루 늦게 들어온다 — 어제 관측이 아직 없으면 밝힌다('그친 지 이틀'이 틀릴 수 있음)
        lag = f"관측 자료는 {_d(last)}까지" if last and last < d - timedelta(days=1) else ""
        out.append(
            _make(
                after,
                ep[0],
                region,
                dong,
                data,
                rule=f"하루 {COL_WORD[kind]} {v:g}{unit} 이상이 온 뒤 {AFTER_DAYS}일"
                "(관측, 같은 날씨의 앞 카드가 없을 때)",
                note=f"{station} 관측",
                title=f"{_weather_title(kind, region, vals)} · 그친 지 {gap}일",
                sub=lag,
                why=f"{station} 관측: {seen_text}. 그친 다음 날부터 {AFTER_DAYS}일 동안 보여 줘요",
                days=[x.isoformat() for x in ep],
                focus_day=d,
            )
        )
    return out


def _hm(stamp: str) -> str:
    """'2026-10-16 14:00' → '10월 16일 14시'."""
    try:
        t = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except ValueError:
        return stamp
    return f"{t.month}월 {t.day}일 {t.hour}시" + (f" {t.minute}분" if t.minute else "")


def _warning_cards(d: date, region: str, dong: str | None, data: DongData, w: dict) -> list[Card]:
    """【정함 10-16 팀장】 특보가 나오면 특보로 — 발효 중인 특보와 예비특보(카드 종류 넷만)."""
    now: dict[str, list[str]] = {}
    soon: dict[str, list[str]] = {}
    for head, kind in w["now"]:
        if kind:
            now.setdefault(kind, []).append(head)
    for text, kind in w["soon"]:
        if kind:
            soon.setdefault(kind, []).append(text)
    out = []
    for kind in [k for k in GROUP if k in now or k in soon]:
        if kind in now:
            title = f"{' · '.join(dict.fromkeys(now[kind]))} 발효 중"
            sub = f"{w['area']}에 걸림"
            why = f"기상청 특보: {' · '.join(now[kind])}({w['area']})"
        else:
            title = f"{kind} 예비특보"
            sub = soon[kind][0]
            why = f"기상청 예비특보: {soon[kind][0]}"
        out.append(
            _make(
                kind,
                d,
                region,
                dong,
                data,
                rule="기상청 특보(발효 중 · 예비특보)가 이 지역에 걸리면",
                trigger=[SOURCES["특보"]],
                note=f"기상청 특보 {_hm(w['issued'])} 현황",
                title=title,
                sub=sub,
                why=f"{why}. {_hm(w['issued'])} 특보 현황",
                days=[d.isoformat()],
            )
        )
    return out


def _peak_text(kind: str, row: dict) -> str:
    """'15~17시에 가장 셈 · 비 올 확률 90%' — 비 · 눈만(예보 시각 그대로)."""
    parts = []
    pk = row.get("rain_peak" if kind == "폭우" else "snow_peak")
    if pk:
        parts.append(f"{pk[0]}시에 가장 셈" if pk[0] == pk[1] else f"{pk[0]}~{pk[1]}시에 가장 셈")
    if row.get("pop") is not None:
        parts.append(f"{'비' if kind == '폭우' else '눈 · 비'} 올 확률 {row['pop']}%")
    return " · ".join(parts)


def _forecast_cards(
    d: date,
    region: str,
    dong: str | None,
    data: DongData,
    by_dong: dict[str, dict],
    issued: str,
    skip: set[str],
) -> list[Card]:
    """【정함 10-16 팀장】 특보가 없으면 동마다 단기예보가 우리 기준값을 넘을 때.

    동 담당은 그 동 격자, 구 · 시 담당은 동마다 보고 가장 센 값과 넘은 동 수
    (동 이름은 쓰지 않음).
    """
    w = data.weather()
    window = [d + timedelta(days=i) for i in range(LOOKAHEAD + 1)]
    names = [dong] if dong else list(by_dong)
    of = len(data.region_dongs(region))
    out = []
    for kind, (col, op, v, unit) in (w.get("thresholds") or {}).items():
        if kind in skip:
            continue
        worst: dict[str, dict] = {}
        over: dict[str, int] = {}
        who: dict[str, list[tuple[str, float]]] = {}  # 그날 기준을 넘은 동과 값
        for n in names:
            for day, row in (by_dong.get(n) or {}).items():
                x = row.get(col)
                if x is None:
                    continue
                cur = worst.get(day)
                if cur is None or (x > cur[col] if op == ">=" else x < cur[col]):
                    worst[day] = row
                if x >= v if op == ">=" else x <= v:
                    over[day] = over.get(day, 0) + 1
                    who.setdefault(day, []).append((n, float(x)))
        for ep in _episodes(worst, col, op, v):
            hit = [x for x in window if x in ep]
            if not hit or not (ep[0] - timedelta(days=LOOKAHEAD) <= d <= ep[-1]):
                continue
            vals = [(x, float(worst[x.isoformat()][col])) for x in hit]
            word = COL_WORD[kind]
            first = worst[hit[0].isoformat()]
            sub = _peak_text(kind, first) if kind in ("폭우", "폭설") else ""
            if dong:
                parts = [f"{_d(x)} {word} {val:.1f}{unit}" for x, val in vals]
                grid = f"{dong} 경로당 · 마을회관 가운데 격자"
            else:
                # 【정함 10-19 팀장이 맡김】 구 · 여러 동 담당은 기준을 넘는 동 이름과 값도
                #        (센 쪽부터 세 곳, 한파는 낮은 쪽부터)
                got = who.get(hit[0].isoformat(), [])
                got.sort(key=lambda t: -t[1] if op == ">=" else t[1])
                shown = " · ".join(f"{n} {x:.1f}{unit}" for n, x in got[:VILLAGE_MAX])
                rest = len(got) - VILLAGE_MAX
                count = f"{of}곳 중 {over.get(hit[0].isoformat(), 0)}곳이 기준을 넘음"
                if shown:
                    count += f"({shown}{f' 외 {rest}곳' if rest > 0 else ''})"
                sub = f"{sub} · {count}" if sub else count
                parts = [
                    f"{_d(x)} {word} {'최대' if op == '>=' else '최저'} {val:.1f}{unit}"
                    f"({of}곳 중 {over.get(x.isoformat(), 0)}곳이 기준을 넘음)"
                    for x, val in vals
                ]
                grid = "동마다 경로당 · 마을회관 가운데 격자"
            out.append(
                _make(
                    kind,
                    ep[0],
                    region,
                    dong,
                    data,
                    rule=f"{_rule(kind, w)}(기상청 단기예보, 특보가 없을 때)",
                    trigger=[SOURCES["예보"]],
                    note=f"기상청 예보 {_hm(issued)} 발표(바뀔 수 있음)",
                    title=_weather_title(kind, region, vals, estimated=False),
                    sub=sub,
                    why=", ".join(parts) + f" — 기상청 단기예보({_hm(issued)} 발표, {grid})",
                    days=[x.isoformat() for x in hit],
                )
            )
    return out


def _live_weather(
    d: date, region: str, dong: str | None, data: DongData, wx
) -> tuple[list[Card], dict]:
    """진짜 오늘의 날씨 카드와 화면에 적을 날씨 정보. 기상청을 못 받아도 다른 카드는 낸다."""
    info: dict = {
        "mode": "예보",
        "forecast_issued": None,
        "warning_issued": None,
        "other_warnings": [],
        "warnings_here": [],
        "missing": [],
        "error": None,
    }
    out: list[Card] = []
    errors = []
    try:
        w = wx.warnings(region)
        info["warning_issued"] = w["issued"]
        info["other_warnings"] = [h for h, k in w["now"] if not k]
        info["warnings_here"] = [h for h, _ in w["now"]] + [t for t, _ in w["soon"]]
        out += _warning_cards(d, region, dong, data, w)
    except fc.ForecastError as e:
        errors.append(str(e))
    grids = data.grids(region)
    if dong:
        grids = {dong: grids[dong]} if dong in grids else {}
    try:
        if not grids:
            raise fc.ForecastError(f"{dong or region}의 예보 격자가 없음")
        by_dong, issued = wx.forecast(grids)
        info["forecast_issued"] = issued
        info["by_dong"] = by_dong  # 취약 돌보미 판단(_judge)이 같은 예보를 쓴다(응답에는 넣지 않음)
        info["missing"] = [n for n in grids if n not in by_dong]
        if info["missing"]:
            errors.append(f"예보를 못 받은 곳 {len(info['missing'])}곳")
        out += _forecast_cards(d, region, dong, data, by_dong, issued, {c.kind for c in out})
    except fc.ForecastError as e:
        errors.append(str(e))
    if errors:
        info["error"] = weather_error(errors)
    return out, info


def weather_error(errors: list[str]) -> str:
    """화면에 보일 날씨 오류 — 같은 말은 한 번, 설정 이름(키 이름)은 쓰는 사람에게 보이지 않게.

    【판단】 10-28 사이트 점검: 키가 없으면 특보 · 예보 두 곳이 같은 말을 내 '공공데이터포털
           키(DATA_GO_KR_SERVICE_KEY)가 없음'이 두 번 붙어 쓰는 사람에게 보였다
    """
    out = []
    for e in errors:
        if "KEY" in e or "키" in e:
            e = "기상청 자료 연결 설정이 아직 안 돼 있어요(관리자 확인 필요)"
        out.append(e)
    return " · ".join(dict.fromkeys(out))


_LIVE: fc.Live | None = None


def live() -> fc.Live:
    """예보 · 특보를 받는 곳 하나(한 시간 · 10분 동안은 받은 것을 다시 쓴다)."""
    global _LIVE
    if _LIVE is None:
        _LIVE = fc.Live()
    return _LIVE


def _holiday_cards(d: date, region: str, dong: str | None, data: DongData) -> list[Card]:
    hol = data.holidays()
    span = [d - timedelta(days=15) + timedelta(days=i) for i in range(60)]
    runs: list[list[date]] = [[]]
    for y in span:
        if _workday(y, hol):
            runs.append([])
        else:
            runs[-1].append(y)
    out = []
    for run in runs:
        if len(run) < 3 or not any(y.isoformat() in hol for y in run):
            continue
        start = run[0]
        if not (start - timedelta(days=LEAD_HOLIDAY) <= d < start):
            continue
        names = list(dict.fromkeys(hol[y.isoformat()] for y in run if y.isoformat() in hol))
        span_text = f"{_d(start)}~{_d(run[-1])} {len(run)}일 연휴({', '.join(names)})"
        out.append(
            _make(
                "긴 연휴",
                start,
                region,
                dong,
                data,
                title=f"{_d(start)}부터 {len(run)}일간",
                sub=span_text,
                why=f"{span_text}. 병원 · 약국 · 경로당이 쉬는 곳이 많아요",
                days=[y.isoformat() for y in run],
            )
        )
    return out


def _monthly_card(d: date, region: str, dong: str | None, data: DongData) -> list[Card]:
    hol = data.holidays()
    first = date(d.year, d.month, 1)
    while not _workday(first, hol):
        first += timedelta(days=1)
    if not (first <= d <= date(d.year, d.month, 10)):
        return []
    return [
        _make(
            "월초 점검",
            first,
            region,
            dong,
            data,
            title=f"{d.month}월 점검",
            sub="이번 달 담당 지역 자료를 확인해 보세요",
            why=f"{d.month}월 첫 근무일이에요. 이번 달 담당 지역 자료를 확인해 보세요",
        )
    ]


YOUTH_SOURCES = {
    "청년": "행정안전부 주민등록 1인세대 · 인구(19 ~ 34세)",
    "어림": "청년의 삶 실태조사 2024(국무조정실, 전국 조사)의 나이별 비율로 어림",
    "창구": "보건복지부 보도자료 2026-03-25(공공누리 1유형)",
}
# 【판단】 10-20 팀장이 맡김('카드 … 뭐를 더 추가하고'): 청년 카드에는 고립 · 은둔 청년을 이을 곳을
#        한 줄 적는다. 할 일이 아니라 정보다(노인 카드도 보건지소 · 경로당 같은 곳을 적는다).
#        내용은 places.json common.youth_desk(보건복지부 보도자료)와 같다
YOUTH_DESK_LINE = "고립 · 은둔 청년(19 ~ 34세)을 이을 곳: 온라인 '청년ON' · 읍면동 행정복지센터"


def _youth_lines(names: list[str], data: DongData, many: bool) -> tuple[list[str], list[str]]:
    """청년 카드의 상태 줄 — 19 ~ 34세(10-19 팀장). many = 구 · 여러 동 합계."""
    p = data.people() or {}
    rows = [(p.get("dongs") or {}).get(n) or {} for n in names]
    if not rows or any(r.get("solo_youth") is None for r in rows):
        return [], []
    a = sum(r["solo_youth_prev"] for r in rows)
    b = sum(r["solo_youth"] for r in rows)
    pop = sum(r["pop_youth"] for r in rows)
    head = "합계 " if many else ""
    # 【정함 10-19 팀장이 맡김】 '얼마나 늘면' 카드를 따로 세우지 않는다 — 주민등록은 달마다 한 번
    #        바뀌어 날마다 같은 숫자의 카드가 된다. 대신 구 · 여러 동 카드에 1년 새 많이 늘어난
    #        동 세 곳을 적는다
    up = (
        _top_dongs(
            [(n, r["solo_youth"] - r["solo_youth_prev"]) for n, r in zip(names, rows, strict=True)],
            "명",
            plus=True,
            floor=MIN_UP,
        )
        if many
        else ""
    )
    lines = [
        f"혼자 사는 청년(19 ~ 34세 1인 세대) {head}{a:,}명 → {b:,}명"
        f"({_ym(p['prev'])} → {_ym(p['basis'])}, {_more(b - a)}"
        f"{', 많이 늘어난 곳 ' + up if up else ''})",
        f"청년(19 ~ 34세) 주민 {head}{pop:,}명, 100명 중 {round(b / pop * 100) if pop else 0}명이"
        " 혼자 삶",
    ]
    keys = ["청년"]
    hb = [((data.dong(n) or {}).get("youth") or {}).get("homebound") for n in names]
    if all(hb):
        # 아주 작은 곳은 자료가 '10명 미만'만 준다(합계에서는 0 ~ 9명으로 셈)
        lo = sum(0 if h.get("under10") else h["lo"] for h in hb)
        hi = sum(9 if h.get("under10") else h["hi"] for h in hb)
        size = "10명 미만" if hi < 10 else f"약 {lo:,} ~ {hi:,}명"
        lines.append(f"거의 집에만 있는 청년 {head}{size}(어림, 실제로 센 수가 아님)")
        keys.append("어림")
    lines.append(YOUTH_DESK_LINE)
    keys.append("창구")
    return lines, [YOUTH_SOURCES[k] for k in keys]


def _youth_cards(
    elder: list[Card], d: date, region: str, dong: str | None, data: DongData
) -> list[Card]:
    """【정함 10-19 팀장】 청년 카드(19 ~ 34세, "노인이랑 다르게"). 날씨는 보지 않고
    긴 연휴 · 월초에 그 지역 청년의 상태를 건넨다.

    【정함 10-19 팀장이 맡김】 계기는 긴 연휴 · 월초 둘. '얼마나 늘면' 카드는 따로 세우지 않고
           구 · 여러 동 카드에 1년 새 많이 늘어난 동을 적는다(_youth_lines)
    """
    some = data.picked() if isinstance(data, _Some) else []
    names = [dong] if dong else data.region_dongs(region)
    lines, sources = _youth_lines(names, data, not dong)
    if not lines:
        return []
    out = []
    for c in elder:
        if c.kind not in ("긴 연휴", "월초 점검"):
            continue
        start = date.fromisoformat(c.start)
        title = c.title if c.kind == "긴 연휴" else f"{start.month}월 청년 현황"
        lead = ASK_WORD.get(c.kind, "요즘")
        if dong:
            # 【정함 10-19 팀장이 맡김】 청년 문서를 따로 두지 않는다 — 동 상황 문서에 이미
            #        '청년' 절이 있다(doc.py: 어르신 / 청년 / 사는 곳과 갈 곳 / 현장에서 확인할 것)
            asks = {
                "자세히 묻기": f"{lead} {dong} 청년들 괜찮을까요?",
                "동 상황 문서": f"{dong} 동 상황 문서 만들어 줘",
            }
        else:
            where = " · ".join(some) + " 중" if some else region
            asks = {
                "혼자 사는 청년 많은 동 묻기": f"{where} 혼자 사는 청년 많은 동은?",
                "취약 돌보미 판단 보기": f"{lead} {' · '.join(some) or region} 청년들 괜찮을까요?",
            }
        out.append(
            Card(
                id=f"{c.sgg_cd}-청년-{c.kind}-{c.start}",
                kind=c.kind,
                group="청년",
                label=f"청년 · {c.label}",
                sgg_cd=c.sgg_cd,
                where=c.where,
                title=title,
                sub=c.sub if c.kind == "긴 연휴" else "이번 달 담당 지역 청년 자료예요",
                note=c.where,
                why=c.why
                if c.kind == "긴 연휴"
                else "매달 첫 근무일부터 10일까지, 1년 전 같은 달과 견줌",
                rule=c.rule,
                start=c.start,
                days=c.days,
                focus=lines,
                sources=list(
                    dict.fromkeys(([SOURCES["연휴"]] if c.kind == "긴 연휴" else []) + sources)
                ),
                buttons=list(asks),
                asks=asks,
                targets=c.targets,
            )
        )
    return out


def suggest(region: str, dong: str | None) -> list[str]:
    """카드 아래 추천 질문(스토리보드 CHT-100 ④ — 누르면 바로 보낸다). 노인 · 청년 둘 다."""
    if dong:
        return [
            f"{dong} 혼자 사시는 어르신 몇 명이에요?",
            f"{dong} 근처 약국은?",
            f"{dong} 청년은 몇 명이에요?",
        ]
    short = region.removesuffix("구").removesuffix("시")
    return [
        f"{short} 어디부터 가야 해?",
        f"{region} 혼자 사는 청년 많은 동은?",
        f"{region} 경로당 많은 동은?",
    ]


KIND_PATTERN = {
    "폭우": "rain",
    "한파": "cold",
    "폭설": "cold",
    "폭염": "heat",
    "긴 연휴": "holiday",
    "폭우 뒤": "rain",
    "폭설 뒤": "cold",
}
YOUTH_PATTERN = {"긴 연휴": "yholiday"}


def _judge(
    found: list[Card],
    target: str,
    d: date,
    today_: date,
    region: str,
    dong: str | None,
    data: DongData,
    forecasts: dict | None,
) -> None:
    """카드마다 취약 돌보미 판단 한 줄 — 챗봇과 같은 조건 창고(conditions.py).

    【판단】 날씨 · 연휴 카드는 그 계기에 맞는 겹침(폭우 → 큰비, 한파 · 폭설 → 추위 · 눈,
           폭염 → 더위, 긴 연휴 → 연휴)이 섰는지, 월초 점검은 겹친 걱정 전부.
           구 · 여러 동 담당은 그 겹침이 선 동 수와 많은 곳.
           순위(먼저 볼 동)와는 다른 것이라 그 말은 쓰지 않는다.
           자리(몇 곳 중 몇 번째)는 지역 전체로 매긴다(고른 동들끼리만 견주지 않는다)
    """
    from src.assistant import conditions as C

    if not found:
        return
    base = data._data if isinstance(data, _Some) else data
    names = [dong] if dong else data.region_dongs(region)
    as_of = d if d < today_ else None
    sheets = [s for n in names if (s := C.sheet(n, target, base, forecasts, as_of))]
    keys = YOUTH_PATTERN if target == "청년" else KIND_PATTERN
    for c in found:
        key = keys.get(c.kind)
        if dong:
            sh = sheets[0] if sheets else None
            if sh is None:
                continue
            if key:
                p = next((p for p in sh.patterns if p.key == key), None)
                c.judge = (
                    f"취약 돌보미 판단: {p.title}({p.kind}, 겹 {len(p.layers())}가지에 걸침)"
                    if p
                    else "취약 돌보미 판단: 이 계기와 겹친 걱정은 없음"
                )
            else:
                c.judge = (
                    f"취약 돌보미 판단: 겹친 걱정 {len(sh.patterns)}가지("
                    + " / ".join(p.title for p in sh.patterns)
                    + ")"
                    if sh.patterns
                    else "취약 돌보미 판단: 겹친 걱정은 없음"
                )
            continue
        if key:
            hit = [s for s in sheets if any(p.key == key for p in s.patterns)]
            title = next((p.title for s in hit for p in s.patterns if p.key == key), "")
            top = " · ".join(s.name for s in sorted(hit, key=lambda s: -len(s.patterns))[:3])
            c.judge = (
                f"취약 돌보미 판단: '{title}' 겹침이 선 곳 {len(names)}곳 중 {len(hit)}곳(많은 곳 {top})"  # noqa: E501
                if hit
                else f"취약 돌보미 판단: 이 계기와 겹친 걱정이 선 곳 없음({len(names)}곳)"
            )
        else:
            hit = [s for s in sheets if s.patterns]
            top = " · ".join(s.name for s in sorted(hit, key=lambda s: -len(s.patterns))[:3])
            c.judge = (
                f"취약 돌보미 판단: 겹친 걱정이 있는 곳 {len(names)}곳 중 {len(hit)}곳(많은 곳 {top})"  # noqa: E501
                if hit
                else f"취약 돌보미 판단: 겹친 걱정이 있는 곳 없음({len(names)}곳)"
            )


def _data_notes(d: date, today_: date, data: DongData) -> list[str]:
    """그날 자료가 모자라면 '없다'고 밝힌다(없는 것을 '궂은 날씨 없음'으로 읽히지 않게).

    【판단】 10-20: 2025-03-02(관측 자료 전)에 '오늘부터 사흘 안에 궂은 날씨 · 긴 연휴 · 월초 점검이
           없습니다'가 나갔다 — 날씨 관측이 없는 날이었다
    """
    out = []
    w = data.weather() or {}
    period = w.get("period") or []
    if d < today_ and period and not (period[0] <= d.isoformat() <= period[1]):
        out.append(
            f"그날은 날씨 관측 자료가 없어요(관측 {period[0]} ~ {period[1]}). "
            "날씨 카드는 세우지 못했어요"
        )
    if d > today_ + timedelta(days=LOOKAHEAD):
        out.append(
            "그날은 아직 기상청 예보가 없어요(단기예보는 오늘부터 사흘). "
            "날씨 카드는 그날이 가까워지면 나와요"
        )
    years = {int(k[:4]) for k in data.holidays()}
    need = {d.year, (d + timedelta(days=LEAD_HOLIDAY + 10)).year}
    lack = sorted(y for y in need if y not in years)
    if lack:
        out.append(
            f"{', '.join(map(str, lack))}년 공휴일 자료가 아직 없어 긴 연휴 카드를 세우지 못해요"
        )
    return out


def cards(profile: Member, data: DongData, on: str | None = None, wx=None) -> dict:
    """그날 담당 지역에 건넬 카드(최대 3장, 나머지는 제목만).

    【정함 10-16 팀장】 날짜를 안 주면 진짜 오늘 — 기상청 특보 · 단기예보로 선다(wx, 기본 live()).
    지난 날짜를 주면 그날까지의 관측을 예보처럼 되짚는다(시험 · 시연 되감기, weather.json).
    """
    region = profile.member_region
    # 【판단】 그 지역에 없는 동 이름은 버린다(API는 400으로 막고, 여기서는 지역 카드로 돌아감)
    known = set(data.region_dongs(region)) if region else set()
    picked = [n for n in _picked(profile) if n in known]
    dong = picked[0] if len(picked) == 1 else None
    if len(picked) > 1:
        data = _Some(data, picked)
    today_ = fc.today_kst()
    d = date.fromisoformat(on) if on else today_
    if not region:
        return {
            "date": d.isoformat(),
            "headline": "",
            "cards": [],
            "youth_cards": [],
            "more": [],
            "suggest": [],
            "notice": "담당 지역을 정하시면 그 지역에 맞춘 오늘 챙길 일을 보여 드려요.",
            "data_notes": [],
        }
    forecasts = None
    if d >= today_:
        weather, info = _live_weather(d, region, dong, data, wx or live())
        forecasts = info.pop("by_dong", None)
    else:
        weather = _weather_cards(d, region, dong, data)
        station = ((data.weather().get("regions") or {}).get(region) or {}).get("station", "")
        info = {"mode": "관측 되짚기", "station": station}
    weather += _after_cards(d, region, dong, data, weather)
    found = weather + _holiday_cards(d, region, dong, data) + _monthly_card(d, region, dong, data)
    found.sort(key=lambda c: (ORDER[c.kind], c.start))
    shown, more = found[:MAX_CARDS], found[MAX_CARDS:]
    young = _youth_cards(found, d, region, dong, data)
    _judge(shown, "어르신", d, today_, region, dong, data, forecasts)
    _judge(young, "청년", d, today_, region, dong, data, forecasts)
    notes = _data_notes(d, today_, data)
    # 【정함 스토리보드 CHT-100 · 100E】 비서가 먼저 날짜와 챙길 일 개수를 알린다
    headline = (
        f"{_d(d)}, 오늘 챙길 일이 {len(found) + len(young)}건 있습니다."
        if found or young
        else f"{_d(d)}, 오늘은 먼저 챙길 일이 없습니다."
    )
    return {
        "date": d.isoformat(),
        "date_label": _d(d),
        "where": f"{region} {' · '.join(picked)}" if picked else region,
        "headline": headline,
        "cards": [asdict(c) for c in shown],
        "youth_cards": [asdict(c) for c in young],
        "more": [{"id": c.id, "title": f"{c.label} · {c.title}"} for c in more],
        "suggest": suggest(region, dong),
        "notice": None if found else (notes[0] if notes else EMPTY_HEAD),
        "data_notes": notes,
        "weather": info,
    }


def erd_rows(card: dict, created_at: str) -> dict:
    """카드 하나를 팀 ERD 표 모양으로(todo_card 한 줄 + todo_target 줄들). 팀 DB로 옮길 때 쓴다."""
    return {
        "todo_card": {
            "card_id": card["id"],
            "kind": card["kind"],
            "sgg_cd": card["sgg_cd"],
            "title": card["title"],
            "why": card["why"],
            # 【정함 10-19 팀장】 기한은 뺐다. 팀 ERD todo_card.due(빈칸 불가)는 빈 글 —
            #        ERD는 나중에 한 번에 맞춘다(10-19 팀장 "ERD는 나중에 한번에 커버할거야")
            "due": "",
            "created_at": created_at,
            "evidence": {"rule": card["rule"], "sources": card["sources"]},
            # 【정함 10-19 팀장】 할 일은 적지 않는다. 팀 ERD todo_card.todo(빈칸 불가)는 빈 목록 —
            #        칸을 없앨지는 팀원과 정할 일(big-contest docs/미정.md)
            "todo": [],
        },
        "todo_target": [
            {
                "seq": i + 1,
                "card_id": card["id"],
                "dong_cd": t["dong_cd"],
                "note": {"focus": card["focus"]},
            }
            for i, t in enumerate(card["targets"])
        ],
    }
