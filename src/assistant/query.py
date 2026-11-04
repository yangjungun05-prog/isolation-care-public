"""여러 조건 계산(10-26) — 조건이 여럿 겹치거나, 동들을 묶어 평균 · 합계 · 1,000명당 · 기준 맞추기를
바라는 질문을 정해진 지표 목록의 '계산 계획'으로 바꾸고, 계산은 전부 코드가 한다.

【판단】 10-26 팀장 "변수가 서너개이상 겹치는 에이전트 질문용 시제품" → "사용자가 데이터들을 읽고
       해당하는 데이터들을 한데 묶어서 무언가의 결과를 바랄 때가 많을 거란 말이야 … 진짜 사용자가
       말해 볼 만한 실무적인 일들을 예측해 봐야 해" — 고칠 때 5단계로
  1) 판단: 지금 줄 세우기(librarian._rank_by)는 지표 하나만 받는다. 조건이 여럿이면 나머지는
     '이 자료로 나눠 볼 수 없어서 빼고'로 빠지거나 '어느 동을 볼까요?'로 되묻는다
     (multi_16: 엔진 9/16)
  2) 남들: 정해진 지표 · 연산만 쓰게 한 의미 층이 SQL을 바로 짜게 하는 것보다 정확했다
     (Sequeda 외 2023 arXiv 2311.07509: 16% → 54%, dbt Labs 2026 업체 자료: 90.0% → 98.2%).
     표 질문은 AI가 머리로 계산하지 않고 코드가 계산한다(SemEval-2025 Task 8 표 질문 참가 팀들)
  3) 환경: 우리 표는 동 47곳 × 지표 서른몇 개로 작고 정해져 있다 → AI가 쓴 코드를 돌리지 않고
     지표 목록 · 연산 여덟 가지 · 계산 방식 셋(JSON)만 고르게 한다
  4) 실무에서 바라는 계산은 지난 페르소나 대화 1,933건(고유 말)에서 골랐다(BISU evals/results
     personas_*): 비율 · 1,000명당(535) · 순위 · 우선(533) · 앞말 참조(357) · 비교(259) · 증감(178)
     · 기준 맞추기 · 배분(106). 예: 공모 기준 가~사에 동마다 무엇이 맞나 · '구 평균보다 높음'
     · 3개 동 묶기(p06 harben) · '80세 이상 남성 독거노인이 다른 동보다 많은 동'(p15 astin)
"""

from __future__ import annotations

import math
import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.assistant import dongname
from src.assistant.data_source import DongData

Region = Literal["강남구", "춘천시"]
Op = Literal["많음", "적음", "이상", "이하", "있음", "없음", "평균보다 높음", "평균보다 낮음"]
Mode = Literal["모두", "많이 맞는 순", "동마다 표"]
Agg = Literal["합계", "평균", "범위"]
BOTH: tuple[str, ...] = ("강남구", "춘천시")
OPS: tuple[str, ...] = Op.__args__  # type: ignore[attr-defined]
LOW_OPS = ("적음", "이하", "없음", "평균보다 낮음")


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    unit: str
    get: Callable[[dict, dict, dict], float | None]  # (동 자료, 시설 자료, 사람 자료)
    regions: tuple[str, ...] = BOTH
    words: str = ""  # 데스크가 고를 때 볼 말(사용자가 이렇게 부르면 이 지표)
    pct: bool = False  # 0 ~ 1 몫을 %로 보인다
    # 【기능】 비율 지표의 '지역 전체 값' = 분자 합 ÷ 분모 합(동 비율의 평균과 다르다)
    num: str | None = None
    den: str | None = None
    factor: float = 1.0
    count: bool = True  # 동끼리 더해도 뜻이 있는 수(사람 · 가구 · 곳 · 채)
    note: str = ""  # 자료가 일부 동에만 있는 따위
    level: str = "동"  # '마을' = 춘천 읍 · 면의 법정 리마다 값(10-27, run_villages)


def _n(x) -> float | None:
    return None if x is None else float(x)


def _len(x) -> float | None:
    return None if x is None else float(len(x))


def _shop(p: dict, kind: str) -> float | None:
    return _n(((p.get("shops") or {}).get(kind) or {}).get("n"))


def _pharmacy_km(p: dict) -> float | None:
    row = (p.get("shops") or {}).get("약국") or {}
    if row.get("n"):
        return 0.0
    return _n((row.get("nearest") or {}).get("km"))


def _homebound(d: dict, end: str = "") -> float | None:
    h = (d.get("youth") or {}).get("homebound") or {}
    if "lo" not in h:
        return None
    return float(h[end]) if end else (h["lo"] + h["hi"]) / 2


def _seoul_sex(d: dict, key: str) -> float | None:
    return _n(((d.get("seoul_lonely_sex") or {}).get("2025") or {}).get(key))


def _kind(d: dict, key: str) -> float | None:
    return _n(((d.get("seoul_lonely_kind") or {}).get("2025") or {}).get(key))


def _lonely_all(d: dict) -> float | None:
    k = (d.get("seoul_lonely_kind") or {}).get("2025") or {}
    return float(sum(k.values())) if k else None


def _lonely_rise2(d: dict) -> float | None:
    s = d.get("seoul_lonely") or {}
    return _n(s["2025"] - s["2023"]) if "2025" in s and "2023" in s else None


def _rise(h: dict, now: str, prev: str) -> float | None:
    return _n(h[now] - h[prev]) if h.get(prev) is not None and h.get(now) is not None else None


def _ratio(a: float | None, b: float | None, f: float = 1.0) -> float | None:
    return None if a is None or not b else a / b * f


# 【판단】 이름 · 단위는 서가(librarian)가 쓰는 말과 같게 한다
#        — 같은 숫자를 다른 이름으로 부르지 않게
METRICS: tuple[Metric, ...] = (
    Metric(
        "residents", "주민", "명", lambda d, p, h: _n(h.get("residents")), words="주민 수, 인구"
    ),
    Metric(
        "pop65",
        "65세 이상 주민",
        "명",
        lambda d, p, h: _n(h.get("pop65")),
        words="노인 인구, 어르신 수",
    ),
    Metric(
        "pop80",
        "80세 이상 주민",
        "명",
        lambda d, p, h: _n(h.get("pop80")),
        words="80세 이상 어르신 수, 초고령",
    ),
    Metric(
        "solo65",
        "혼자 사는 65세 이상(주민등록 1인세대)",
        "명",
        lambda d, p, h: _n(h.get("solo65")),
        words="혼자 사는 어르신, 독거노인(춘천은 이것), 1인 가구 어르신",
    ),
    Metric(
        "solo65_rise",
        "1년 새 늘어난 혼자 사는 65세 이상(주민등록)",
        "명",
        lambda d, p, h: _rise(h, "solo65", "solo65_prev"),
        words="새로 혼자되신 분, 혼자 사는 어르신이 늘어남, 작년보다 늘어난",
        count=False,
    ),
    Metric(
        "solo80",
        "혼자 사는 80세 이상(주민등록 1인세대)",
        "명",
        lambda d, p, h: _n((d.get("solo80") or {}).get("n")),
        words="혼자 사는 80세 이상, 고령 독거, 초고령 1인 가구",
    ),
    Metric(
        "solo65_share",
        "65세 이상 주민 중 혼자 사는 몫(주민등록 1인세대 ÷ 65세 이상)",
        "%",
        lambda d, p, h: _ratio(_n(h.get("solo65")), _n(h.get("pop65"))),
        pct=True,
        num="solo65",
        den="pop65",
        count=False,
        words="혼자 사는 비율, 독거 비율, 1인 가구 비율",
    ),
    Metric(
        "lonely_total",
        "서울시 독거노인 현황 2025년",
        "명",
        lambda d, p, h: _lonely_all(d),
        regions=("강남구",),
        words="서울시 독거노인 수(강남)",
    ),
    Metric(
        "lonely_female",
        "서울시 독거노인 현황 2025년 여성",
        "명",
        lambda d, p, h: _seoul_sex(d, "여"),
        regions=("강남구",),
        words="혼자 사는 할머니(강남)",
    ),
    Metric(
        "lonely_male",
        "서울시 독거노인 현황 2025년 남성",
        "명",
        lambda d, p, h: _seoul_sex(d, "남"),
        regions=("강남구",),
        words="혼자 사는 할아버지, 남성 독거노인(강남)",
    ),
    Metric(
        "lonely80",
        "서울시 독거노인 현황 2025년 80세 이상(남녀 합)",
        "명",
        lambda d, p, h: _n(((d.get("seoul_lonely_kind") or {}).get("80+") or {}).get("2025")),
        regions=("강남구",),
        words="80세 이상 독거노인(강남, 성별은 나뉘지 않음)",
    ),
    Metric(
        "lonely_poor",
        "서울시 독거노인 현황 2025년 기초수급",
        "명",
        lambda d, p, h: _kind(d, "수급"),
        regions=("강남구",),
        words="기초수급 받는 독거노인(강남)",
    ),
    Metric(
        "lonely_outside_share",
        "서울시 독거노인 중 기초수급 · 저소득 명단 밖(일반) 몫(2025년)",
        "%",
        lambda d, p, h: _ratio(_kind(d, "일반"), _lonely_all(d)),
        regions=("강남구",),
        pct=True,
        num="lonely_general",
        den="lonely_total",
        count=False,
        words="공적 지원 밖 독거노인 비율, 사각지대 비율(강남)",
    ),
    Metric(
        "lonely_general",
        "서울시 독거노인 현황 2025년 일반(기초수급 · 저소득 아님)",
        "명",
        lambda d, p, h: _kind(d, "일반"),
        regions=("강남구",),
        words="명단 밖 독거노인 수(강남)",
    ),
    Metric(
        "lonely_rise2",
        "2년 새 늘어난 서울시 독거노인(2023 → 2025)",
        "명",
        lambda d, p, h: _lonely_rise2(d),
        regions=("강남구",),
        count=False,
        words="최근 2년 늘어난 독거노인(강남)",
    ),
    Metric(
        "livelihood",
        "기초생활수급자(2024)",
        "명",
        lambda d, p, h: _n((d.get("livelihood") or {}).get("people")),
        regions=("춘천시",),
        words="기초수급자, 수급자 수(춘천)",
    ),
    Metric(
        "livelihood_per100",
        "주민 100명당 기초생활수급자(2024)",
        "명",
        lambda d, p, h: _n((d.get("livelihood") or {}).get("per100")),
        regions=("춘천시",),
        count=False,
        words="수급자 비율(춘천)",
    ),
    Metric(
        "solo_all",
        "1인 가구(모든 나이, 춘천시 자료 2025)",
        "가구",
        lambda d, p, h: _n((d.get("solo_all") or {}).get("2025")),
        regions=("춘천시",),
        words="1인 가구 전체(춘천)",
    ),
    Metric(
        "empty_houses",
        "빈집(춘천시 빈집 현황 2025-10)",
        "채",
        lambda d, p, h: _n((d.get("empty_houses") or {}).get("n")),
        regions=("춘천시",),
        words="빈집(춘천)",
        note="춘천 25곳 중 10곳만 자료에 있음",
    ),
    Metric(
        "old_walkup",
        "30년 넘은 계단 집(승강기 없는 3~5층)",
        "가구",
        lambda d, p, h: _n((d.get("housing") or {}).get("old_walkup_units")),
        words="계단 집, 엘리베이터 없는 낡은 집, 노후 주거",
    ),
    Metric(
        "res_units",
        "주거 가구(건축물대장)",
        "가구",
        lambda d, p, h: _n((d.get("housing") or {}).get("res_units")),
        words="주거 가구 수",
    ),
    Metric(
        "old_walkup_share",
        "주거 가구 중 30년 넘은 계단 집 몫",
        "%",
        lambda d, p, h: _n((d.get("housing") or {}).get("old_walkup_share")),
        pct=True,
        num="old_walkup",
        den="res_units",
        count=False,
        words="계단 집 비율, 노후 주거 비율",
    ),
    Metric(
        "basement_old",
        "지하층이 있는 30년 넘은 저층 주거 건물",
        "채",
        lambda d, p, h: _n((d.get("housing") or {}).get("basement_old")),
        words="반지하, 지하층 집",
    ),
    Metric(
        "halls",
        "경로당 · 마을회관",
        "곳",
        lambda d, p, h: _len((p.get("halls") or {}).get("list")),
        words="경로당, 마을회관, 어르신 모이는 곳",
    ),
    Metric(
        "hall_area_per100",
        "65세 이상 100명당 경로당 면적(2022)",
        "㎡",
        lambda d, p, h: _n((d.get("senior_hall") or {}).get("per100")),
        regions=("강남구",),
        count=False,
        words="경로당 면적, 경로당 넓이(강남)",
    ),
    Metric("meals", "무료급식소", "곳", lambda d, p, h: _len(p.get("meals")), words="무료급식소"),
    Metric(
        "pharmacies",
        "약국",
        "곳",
        lambda d, p, h: _n(p["_pharmacy_n"]) if "_pharmacy_n" in p else _shop(p, "약국"),
        words="약국 수",
    ),
    Metric(
        "pharmacy_km",
        "가장 가까운 약국까지(동 안에 있으면 0)",
        "km",
        lambda d, p, h: _pharmacy_km(p),
        count=False,
        words="약국이 먼 곳, 약국까지 거리",
    ),
    Metric("clinics", "의원", "곳", lambda d, p, h: _shop(p, "의원"), words="병원, 의원 수"),
    Metric(
        "ltc_home",
        "재가 장기요양기관",
        "곳",
        lambda d, p, h: _n(((p.get("ltc") or {}).get("home") or {}).get("n")),
        words="방문요양, 재가 돌봄 기관",
    ),
    Metric(
        "ltc_res",
        "입소 요양시설",
        "곳",
        lambda d, p, h: _len((p.get("ltc") or {}).get("res")),
        words="요양원, 입소 시설",
    ),
    Metric(
        "youth",
        "청년(19~34세)",
        "명",
        lambda d, p, h: _n(h.get("pop_youth")),
        words="청년 인구",
    ),
    Metric(
        "youth_solo",
        "혼자 사는 청년(주민등록 1인세대)",
        "명",
        lambda d, p, h: _n(h.get("solo_youth")),
        words="1인 가구 청년",
    ),
    Metric(
        "youth_solo_rise",
        "1년 새 늘어난 혼자 사는 청년(주민등록, 줄었으면 음수)",
        "명",
        lambda d, p, h: _rise(h, "solo_youth", "solo_youth_prev"),
        count=False,
        words="청년 1인세대 증감, 혼자 사는 청년이 늘어난",
    ),
    Metric(
        "youth_homebound",
        "거의 집에만 있는 청년 어림(가운데값, 실제로 센 수 아님)",
        "명",
        lambda d, p, h: _homebound(d),
        words="은둔 청년, 집에만 있는 청년",
    ),
    # 10-26 페르소나 c05: 아래 · 위 값을 표로 달라고 세 번 물음
    Metric(
        "youth_homebound_lo",
        "거의 집에만 있는 청년 어림 아래 값(실제로 센 수 아님)",
        "명",
        lambda d, p, h: _homebound(d, "lo"),
        words="은둔 청년 어림 아래 값 · 하한",
    ),
    Metric(
        "youth_homebound_hi",
        "거의 집에만 있는 청년 어림 위 값(실제로 센 수 아님)",
        "명",
        lambda d, p, h: _homebound(d, "hi"),
        words="은둔 청년 어림 위 값 · 상한",
    ),
    Metric(
        "gap",
        "돌봄 자원 공백(지역 안 등수, 1에 가까울수록 65세 이상 1,000명당 자원이 적음)",
        "",
        lambda d, p, h: _n((d.get("rank") or {}).get("gap")),
        count=False,
        words="돌봄 자원이 적은 곳, 도움 거리가 적은 곳, 생활 자원 부족",
    ),
    Metric(
        "risk_band",
        "동 순위 위험 구간(5가 가장 위험)",
        "구간",
        lambda d, p, h: _n((d.get("rank") or {}).get("band")),
        count=False,
        words="위험 구간",
    ),
    Metric(
        "priority",
        "취약 돌보미 동 순위(1이 가장 먼저 볼 동)",
        "위",
        lambda d, p, h: _n((d.get("rank") or {}).get("now")),
        count=False,
        words="먼저 볼 동 순위, 취약 돌보미 순위(옛 이름 살핌 순위)",
    ),
    Metric(
        "diag",
        "진단 신호(겹친 가능성, 8가지 중)",
        "개",
        lambda d, p, h: _n((d.get("diag") or {}).get("n")),
        count=False,
        words="진단, 고립 신호가 겹친 곳",
    ),
)


# 【정함 10-27 팀장】 마을 단위 조건은 "넣기"
#        예상 질문 2-2 '춘천 읍면 중에 버스가 하루 5번 이하로 다니고 약국이 먼 마을이 있는 곳'에
#        계산 길이 없어 읍 하나의 판단 근거를 통째로 냈고, 2-8 T2에는 '마을별 약국 거리 자료는
#        없다'(있음 — focus.json 마을마다 요일별)고 했다.
#   자료: 마을 = 법정 리(focus.json, big-contest scripts/build_weather_focus.py — 행정 리는
#         법정 리로 묶음, 거리는 그 리 경로당 · 마을회관 좌표 가운데에서 직선).
#         버스 = bus.json 경로당 · 마을회관마다 가장 가까운 정류장의 가장 잦은 노선 하루 횟수
#         (TAGO 첫차 · 막차 · 배차로 어림) → 이름으로 리에 붙이고, 한 리에 여럿이면 가장 잦은 것
#         (그 마을에서 탈 수 있는 가장 잦은 버스)
def _v(key: str) -> Callable[[dict, dict, dict], float | None]:
    return lambda d, p, h: _n(d.get(key))


_VILLAGE = "춘천시 읍 · 면 마을(법정 리)마다 — 동 지역 · 강남에는 없음"
VILLAGE_METRICS: tuple[Metric, ...] = tuple(
    Metric(k, n, u, _v(f), regions=("춘천시",), words=w + f"({_VILLAGE})", count=c, level="마을")
    for k, n, u, f, c, w in (
        (
            "v_bus",
            "마을 버스 하루 횟수(마을 경로당 · 마을회관 근처 가장 잦은 노선, 어림)",
            "번",
            "bus_per_day",
            False,
            "버스가 드문 마을, 버스가 하루 몇 번 오는 마을, 대중교통이 불편한 마을",
        ),
        (
            "v_pharm",
            "평일에 문 연 약국까지 거리(마을 가운데에서 직선)",
            "km",
            "pharm_km_3",
            False,
            "약국이 먼 마을(우리 기준 5km 넘으면 멀다)",
        ),
        (
            "v_pharm_sun",
            "일요일에 문 연 약국까지 거리(마을 가운데에서 직선)",
            "km",
            "pharm_km_7",
            False,
            "일요일 · 주말에 약국이 먼 마을",
        ),
        (
            "v_clinic",
            "의원 · 보건기관까지 거리(마을 가운데에서 직선)",
            "km",
            "clinic_km",
            False,
            "병원 · 의원 · 보건지소가 먼 마을, 진료받기 먼 마을",
        ),
        (
            "v_public",
            "공공기관(행정복지센터 · 보건기관 · 노인복지관 · 병원)까지 거리",
            "km",
            "public_km",
            False,
            "공공기관이 먼 마을, 도움 받을 곳이 먼 마을",
        ),
        (
            "v_shop",
            "편의점 · 장보기까지 거리(마을 가운데에서 직선)",
            "km",
            "shop_km",
            False,
            "장보기 · 생필품 사기 먼 마을",
        ),
        ("v_homes", "마을 주거 건물", "채", "homes", True, "마을 집 수, 큰 마을 · 작은 마을"),
        (
            "v_old_homes",
            "마을 1995년 이전 주거 건물",
            "채",
            "old_homes",
            True,
            "낡은 집이 많은 마을",
        ),
        (
            "v_weak_roof",
            "마을 눈 무게에 약한 지붕 주택(슬레이트 · 함석 · 판넬 등)",
            "채",
            "weak_roof",
            True,
            "슬레이트 지붕 · 약한 지붕 집이 많은 마을",
        ),
        (
            "v_basement",
            "마을 지하층에 집이 있는 건물",
            "채",
            "basement_home",
            True,
            "지하 · 반지하 집이 있는 마을",
        ),
        ("v_steep", "마을 급경사지", "곳", "steep", True, "비탈 · 급경사지가 많은 마을"),
        ("v_landslide", "마을 산사태취약지역", "곳", "landslide", True, "산사태 걱정 마을"),
    )
)
METRICS = METRICS + VILLAGE_METRICS
BY_KEY = {m.key: m for m in METRICS}
# 【판단】 '1,000명당'의 분모로 쓸 수 있는 사람 수(그 밖은 뜻이 없다: 약국 ÷ 경로당 따위)
PER: tuple[str, ...] = ("residents", "pop65", "pop80", "solo65", "solo80", "youth")


class Ref(BaseModel):
    """지표 하나(1,000명당처럼 나눈 것이면 per · scale)."""

    model_config = ConfigDict(frozen=True)

    metric: str
    per: str | None = None
    scale: int | None = None

    @property
    def key(self) -> str:
        return f"{self.metric}/{self.per}@{self.scale or 1000}" if self.per else self.metric


class Cond(Ref):
    op: Op
    value: float | None = None  # '이상' · '이하'일 때만


class Plan(BaseModel):
    """질문 → 계산 계획(데스크가 채움). 숫자를 세거나 줄 세우는 일은 하지 않는다."""

    model_config = ConfigDict(frozen=True)

    region: Region | None = None
    dongs: tuple[str, ...] = ()  # 이 동들 안에서만(비면 지역 전체)
    use_prev: bool = False  # 앞 계산에서 고른 동들 안에서(엔진이 prev 로 넘김)
    # 【기능】 춘천의 읍 · 면만 또는 동만('도심 동 말고 면만', 페르소나 q11 brann)
    kind: Literal["읍면만", "동만"] | None = None
    exclude: tuple[str, ...] = ()  # 빼 달라는 동('퇴계동은 빼고')
    conds: tuple[Cond, ...] = Field(default=(), max_length=8)
    mode: Mode = "모두"
    show: tuple[Ref, ...] = ()  # 조건은 아니지만 같이 보일 지표
    agg: tuple[Agg, ...] = ()  # 고른 동들의 합계 · 평균
    sort: Ref | None = None
    order: Literal["많은 순", "적은 순"] = "많은 순"
    limit: int = Field(default=5, ge=1, le=25)
    unknown: tuple[str, ...] = ()  # 지표 목록에 없어 옮기지 못한 조건(사용자 말 그대로)
    cross: bool = False  # 사람 한 명 단위로 겹쳐 세 달라는 말(80세 이상이면서 반지하 사는 분 수)
    restate: str = ""  # 데스크가 알아들은 것(한 문장)
    # 【판단】 10-26 route_hold_32 r1: 코드 신호만으로 '깊은 고민'을 정하면 새 말에서 너무 자주
    #        켜졌다(설명 · 되짚기 말에도 지표 이름이 여럿, 18/32 — 데스크만 19/32). 코드 신호는
    #        후보만 고르고, 계산이 필요한 말인지는 계획을 짜는 AI가 정한다(아니면 지금 길)
    need: Literal["계산", "바로", "되짚기"] = "계산"
    # 【기능】 '평균보다'의 기준을 동 평균으로(사용자가 '동 평균 · 22개 동의 평균'이라고 함 —
    #        코드가 정함)
    dong_mean: bool = False

    @field_validator("sort", mode="before")
    @classmethod
    def _sort_str(cls, v):
        return {"metric": v} if isinstance(v, str) else v

    @field_validator("show", mode="before")
    @classmethod
    def _show_str(cls, v):
        return tuple({"metric": x} if isinstance(x, str) else x for x in (v or ()))


@dataclass
class Stat:
    n: int
    mean: float
    median: float
    total: float | None  # 더해도 뜻이 있는 수만
    whole: float | None  # 비율 지표의 지역 전체 값(분자 합 ÷ 분모 합)


@dataclass
class Result:
    region: str
    candidates: list[str]
    conds: list[tuple[Cond, str]]  # (조건, 사람이 읽는 기준)
    mode: str
    matched: list[str]  # '모두'면 모두 맞는 동, 나머지 방식이면 보일 동(순서대로)
    near: list[tuple[str, list[int]]]
    hits: dict[str, list[bool]]  # 동 → 조건마다 맞았나
    values: dict[str, dict[str, float | None]]  # 동 → 지표 키 → 값
    ranks: dict[str, dict[str, int]]  # 지표 키 → 동 → 많은 순 등수(같은 값 같은 등수)
    stats: dict[str, Stat]
    dropped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    table: str = ""  # 동마다 표(마크다운, 엔진이 글 아래에 붙인다)
    raw: dict = field(default_factory=dict, repr=False)  # 동 → (동 자료, 시설, 사람) — 묶음 평균용
    # 【판단】 10-26 calc_flow_8 T3: '면 중 1위'인 동내면이 '25곳 중 7위'로만 나가 글쓴이가 '가장
    #        많은 곳은 가려 드리지 못했어요'라고 썼다 → 일부만 볼 때는 그 안의 등수도 준다
    sub_ranks: dict[str, dict[str, int]] = field(default_factory=dict)
    sub_name: str = ""  # '읍 · 면 10곳' · '퇴계동을 뺀 24곳' · '고른 5곳'
    sub_low: set = field(default_factory=set)  # 그 안의 등수를 적은 순으로 센 지표 키
    refs: list = field(default_factory=list)  # 계산에 쓴 지표(말에 나온 동 줄을 덧붙일 때)


def _ref_name(r: Ref) -> str:
    m = BY_KEY[r.metric]
    if not r.per:
        return m.name
    return f"{BY_KEY[r.per].name.split('(')[0]} {(r.scale or 1000):,}명당 {m.name.split('(')[0]}"


def _ref_unit(r: Ref) -> str:
    return "" if r.per else BY_KEY[r.metric].unit


def _ref_ok(r: Ref, region: str) -> str | None:
    """이 지역에서 계산할 수 없으면 까닭(쓸 수 있으면 None)."""
    m = BY_KEY.get(r.metric)
    if m is None:
        return f"'{r.metric}'(지표 목록에 없음)"
    if region not in m.regions:
        return f"{m.name}({region}에는 자료 없음)"
    if r.per:
        if r.per not in PER:
            return f"{m.name} ÷ {r.per}(사람 수로만 나눌 수 있음)"
        if not m.count:
            return f"{m.name}(비율 · 등수라 사람 수로 나눌 수 없음)"
    return None


def _fmt(r: Ref, v: float | None) -> str:
    if v is None:
        return "자료 없음"
    m = BY_KEY[r.metric]
    if r.per:
        return f"{v:,.1f}{m.unit}"
    if m.pct:
        return f"{v:.1%}"
    if m.unit == "km":
        return f"{v:.1f}km"
    if m.key == "gap":
        return f"{v:.2f}"
    if m.unit == "㎡":
        return f"{v:,.0f}㎡"
    if abs(v - round(v)) > 1e-9:
        return f"{v:,.1f}{m.unit}"
    return f"{v:,.0f}{m.unit}"


def _third(n: int) -> int:
    return max(1, math.ceil(n / 3))


def _value(r: Ref, d: dict, p: dict, h: dict) -> float | None:
    v = BY_KEY[r.metric].get(d, p, h)
    if not r.per:
        return v
    return _ratio(v, BY_KEY[r.per].get(d, p, h), float(r.scale or 1000))


def _stat(r: Ref, vals: dict[str, float | None], raw: dict[str, dict]) -> Stat:
    have = [v for v in vals.values() if v is not None]
    m = BY_KEY[r.metric]
    total = sum(have) if (m.count and not r.per) else None
    whole = None
    if r.per or (m.num and m.den):
        num = r.metric if r.per else m.num
        den = r.per if r.per else m.den
        a = [BY_KEY[num].get(*raw[n]) for n in vals]
        b = [BY_KEY[den].get(*raw[n]) for n in vals]
        pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y]
        if pairs:
            whole = (
                sum(x for x, _ in pairs)
                / sum(y for _, y in pairs)
                * (float(r.scale or 1000) if r.per else 1.0)
            )
    return Stat(len(have), statistics.fmean(have), statistics.median(have), total, whole)


def _value_fix(c: Cond) -> Cond:
    # 비율 지표에 '30%'를 30으로 적은 경우를 0.3으로(데스크 실수를 코드가 바로잡음)
    m = BY_KEY.get(c.metric)
    if m and m.pct and not c.per and c.value is not None and c.value > 1:
        return c.model_copy(update={"value": c.value / 100})
    return c


_RI = re.compile(r"([가-힣]+?)(?:\d+(?:[,·]\d+)*)?리")


def _hub_ri(hub: str, ris: dict) -> str | None:
    """경로당 · 마을회관 이름 → 법정 리. 못 붙이면 None(시내 아파트 경로당 따위).

    '조교1리 경로당' → 조교리 · '가정1,2리 경로당' → 가정리 · '발뢰 경로당(강촌3리)' → 강촌리 ·
    '고탄늘푸른경로당' → 고탄리(행정 리는 법정 리로 묶는다 — focus.json과 같은 단위)
    """
    for m in _RI.finditer(hub):
        if (base := m.group(1) + "리") in ris:
            return base
    for ri in ris:
        if len(ri) >= 3 and hub.startswith(ri[:-1]):
            return ri
    return None


def village_rows(data: DongData, towns: list[str]) -> tuple[dict[str, dict], int]:
    """읍 · 면마다 마을(법정 리) 줄 — 이름은 '사북면 고탄리'.

    돌려주는 것: (줄, 리에 붙이지 못한 경로당 · 마을회관 수)
    """
    rows: dict[str, dict] = {}
    unplaced = 0
    for town in towns:
        fv = data.focus(town) if hasattr(data, "focus") else None
        ris = {v["name"]: v for v in (fv or {}).get("villages") or [] if v.get("name")}
        best: dict[str, int] = {}
        bus = data.bus(town) if hasattr(data, "bus") else None
        for h in (bus or {}).get("villages") or []:
            ri = _hub_ri(h.get("hub") or "", ris)
            if ri is None:
                unplaced += 1
            elif h.get("per_day") is not None:
                best[ri] = max(
                    best.get(ri, 0), int(h["per_day"])
                )  # 그 마을에서 탈 수 있는 가장 잦은 버스
        for name, v in ris.items():
            rows[f"{town} {name}"] = {**v, "town": town, "bus_per_day": best.get(name)}
    return rows, unplaced


class _VillageData:
    """마을 줄을 동처럼 읽히는 얇은 껍데기(run이 쓰는 네 가지만)."""

    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = rows

    def region_dongs(self, region: str) -> list[str]:
        return list(self.rows)

    def dong(self, name: str) -> dict | None:
        return self.rows.get(name)

    def places(self, name: str) -> dict:
        return {}

    def people(self) -> dict:
        return {"dongs": {}}


def _is_village(r: Ref | None) -> bool:
    m = BY_KEY.get(r.metric) if r else None
    return bool(m and m.level == "마을")


def run_villages(
    plan: Plan, data: DongData, people: dict | None = None, prev: list[str] | None = None
) -> Result:
    """마을 지표가 든 계획 — 읍면 조건으로 읍 · 면을 먼저 거른 뒤,
    그 안의 마을(법정 리)마다 계산한다.

    【판단】 계산 자체는 run을 그대로 쓴다(마을 줄을 동처럼 넣는다)
           — 연산 · 등수 · 평균 셈이 동과 같다.
           '많음 · 적음'의 3분의 1은 고른 읍 · 면 마을들 안에서 센다
    """
    town_conds = tuple(c for c in plan.conds if not _is_village(c))
    # 【판단】 10-27 village_6 c1 · qbank 2-8 c1: 읍면 지표를 '같이 보기'(show)로 달라고 했는데 마을
    #        계산이 버렸다('80세 이상 혼자 사는 분 수는 자료에 없어요' — 동면 337명이 있다) →
    #        읍 · 면 값으로 남긴다
    town_show = tuple(r for r in plan.show if not _is_village(r))
    # 앞 계산이 마을이면('그중에 슬레이트 지붕 집이 많은 마을은?') 그 마을들 안에서 —
    # 마을 이름은 '사북면 지암리' 꼴(빈칸이 있다)
    prev_v = [x for x in (prev or []) if " " in x]
    first: Result | None = None
    if plan.use_prev and prev_v:
        towns = list(dict.fromkeys(x.split()[0] for x in prev_v))
    else:
        first = run(
            plan.model_copy(
                update={
                    "conds": town_conds,
                    "show": town_show,
                    "sort": None,
                    "agg": (),
                    "mode": "모두",
                    "kind": "읍면만",
                    "limit": 25,
                    "restate": "",
                }
            ),
            data,
            people,
            [x for x in (prev or []) if " " not in x],
        )
        towns = [
            t
            for t in (first.matched if town_conds else first.candidates)
            if t.endswith(("읍", "면"))
        ]
    rows, unplaced = village_rows(data, towns)
    if plan.use_prev and prev_v:
        rows = {k: rows[k] for k in prev_v if k in rows}
    p2 = plan.model_copy(
        update={
            "dongs": (),
            "use_prev": False,
            "kind": None,
            "exclude": (),
            "conds": tuple(c for c in plan.conds if _is_village(c)),
            "show": tuple(r for r in plan.show if _is_village(r)),
            "sort": plan.sort if _is_village(plan.sort) else None,
        }
    )
    res = run(p2, _VillageData(rows), people={}, prev=None)
    n = len(rows)
    label = f"춘천시 읍 · 면 {len(towns)}곳의 마을(법정 리) {n}곳"
    tags = (
        ("[모두 맞는 동]", "[모두 맞는 마을]"),
        ("[하나만 못 맞춘 동]", "[하나만 못 맞춘 마을]"),
        ("[자료 없는 동]", "[자료 없는 마을]"),
        ("[고른 동]", "[고른 마을]"),
        ("동 평균", "마을 평균"),
    )

    def fix(x: str) -> str:
        x = x.replace(f"[여러 조건 계산] 춘천시 {n}곳", f"[여러 조건 계산] {label}")
        x = re.sub(r"춘천시 (\d+)곳", r"마을 \1곳", x)
        for a, b in tags:
            x = x.replace(a, b)
        return x

    head = [
        f"[마을 단위] {label}: {' · '.join(towns) or '맞는 읍 · 면 없음'}. "
        "거리는 그 마을 경로당 · 마을회관 자리에서 잰 직선, "
        "버스는 마을 경로당 · 마을회관 근처 정류장의 가장 잦은 노선 하루 횟수(첫차 · 막차 · "
        "배차로 어림)"
    ]
    if plan.use_prev and prev_v:
        head.append(f"[앞 결과 안에서] 앞에서 고른 마을 {len(prev_v)}곳 안에서 다시 걸렀어요")
    if first is not None and town_conds:
        head.append(
            "[읍 · 면 먼저 거름] "
            + " / ".join(s for _, s in first.conds)
            + f" → 맞는 읍 · 면 {len(towns)}곳"
        )
    if first is not None and (town_conds or town_show):
        # 읍 · 면 지표 값(조건 · 같이 보기) — '[동면] 혼자 사는 80세 이상 … 337명 …'
        cells = [
            x
            for x in first.lines
            if any(x.startswith(f"[{t}] ") for t in towns) and "가지 중" not in x
        ]
        head += [f"[읍 · 면 값] {x}" for x in cells]
    if unplaced:
        head.append(
            f"[버스를 마을에 붙이지 못한 경로당 · 마을회관] {unplaced}곳(이름으로 리를 알 수 없음)"
        )
    if first is not None:
        if first.dropped:
            head.append("[계산하지 못한 조건] " + " · ".join(first.dropped))
        head += [f"[참고] {x}" for x in first.notes]
        res.notes = first.notes + res.notes
        res.dropped = first.dropped + res.dropped
    body = [fix(x) for x in res.lines]
    # 【판단】 10-27 multi_hard H5(API): 읍 · 면을 먼저 거른 뒤 마을 조건에 맞는 곳이 0곳인데
    #        글쓴이가
    #        '… 많은 곳은 동면과 동내면입니다'로 시작하고 뒤에서 '조건을 모두 맞는 마을은 없다'고 해
    #        앞뒤가 엇갈렸다. 먼저 거른 읍 · 면은 '앞 조건만 맞은 곳'이라고 코드가 결론 줄로 밝힌다
    if towns and town_conds and not res.matched and res.mode == "모두":
        body.append(
            f"[결론] 조건을 모두 맞는 마을은 없음 — {' · '.join(towns)}은(는) 앞 조건(읍 · 면)만 "
            "맞은 곳이고, 그 마을들은 뒤 조건(마을)에 맞지 않음"
        )
    at = 1 if body and body[0].startswith("[알아들은 것]") else 0
    res.lines = body[:at] + head + body[at:]
    res.conds = [(c, fix(s)) for c, s in res.conds]
    res.table = res.table.replace("| 동 |", "| 마을 |", 1)
    return res


# 【판단】 10-28 재심사 q05_a: 계획 AI가 '[알아들은 것]'에 '엑셀 파일 자체는 만들지 않는다' ·
#        '엑셀 파일 생성은 이 도구로 할 수 없어'를 적어, 글쓴이가 '엑셀 파일은 만들 수 없어요'
#        (거짓 — 파일은 계산 뒤 코드가 만든다)로 옮겼다. 계산 밖 기능을 못 한다는 문장은 뗀다
#        10-29 브라우저 시험: '엑셀 파일 형식으로 내보내는 기능이 이 계획에는 없어서'(못 한다 꼴이
#        아니라 빠져나감) → 결과의 모양(엑셀 · 파일 · CSV · 내보내기)을 말하는 문장도 뗀다. 계획은
#        무엇을 셀지만 말하고, 파일은 코드가 만든다
_RESTATE_DROP = re.compile(
    r"만들지 않|만들 수 없|할 수 없|드릴 수 없|생성은|불가|못\s?(?:만들|드리|해|합)|따로 없|"
    r"엑셀|파일|CSV|csv|내보내|내려받|다운로드"
)


def clean_restate(text: str) -> str:
    parts = re.split(r"(?<=\.)\s+", (text or "").strip())
    return " ".join(x for x in parts if x and not _RESTATE_DROP.search(x)).strip()


def run(
    plan: Plan,
    data: DongData,
    people: dict | None = None,
    prev: list[str] | None = None,
) -> Result:
    """계획대로 계산한다. 값이 없는 동은 그 조건을 맞추지 못한 것으로 센다."""
    region = plan.region or "강남구"
    refs_all = list(plan.conds) + list(plan.show) + [plan.sort]
    if (
        region == "춘천시"
        and not isinstance(data, _VillageData)
        and any(map(_is_village, refs_all))
    ):
        return run_villages(plan, data, people, prev)
    if people is None:
        people = data.people().get("dongs", {})
    every = data.region_dongs(region)
    notes: list[str] = []
    want = list(plan.dongs)
    if plan.use_prev and prev:
        want = [d for d in prev if d in every] + [d for d in want if d not in prev]
    elif plan.use_prev and not prev:
        notes.append("앞에서 고른 동이 없어 지역 전체로 봤어요")
    # 【판단】 옛 이름 · 오타 · 마을은 엔진과 같은 풀이(dongname.resolve)로 받는다
    #        (10-26 공모 질문의 '일원2동'은 지금 개포3동 — 빼면 사용자가 물은 동이 사라진다)
    fixed: list[str] = []
    for d in want:
        if d in every:
            fixed.append(d)
            continue
        r = dongname.resolve(d, region)
        got = [x for x in r["dongs"] if x in every]
        if got:
            fixed += got
            if r["how"] != "목록에 있음":
                notes.append(f"'{d}'은(는) {' · '.join(got)}(으)로 봤어요({r['how']})")
        elif r["region"] and r["region"] != region:
            notes.append(f"{d}은(는) {r['region']} 동이라 {region} 계산에서 뺐어요")
        else:
            near = f", 비슷한 이름: {' · '.join(r['near'])}" if r["near"] else ""
            notes.append(f"'{d}'은(는) {region} 동 이름에서 찾지 못해 뺐어요{near}")
    want = list(dict.fromkeys(fixed))
    # 【판단】 10-26: 앞 결과 · 사용자가 말한 동은 그 차례대로('위 3곳'이 앞 답의 위 3곳이게)
    candidates = [d for d in want if d in every] if want else list(every)
    if want and not candidates:
        candidates = list(every)
    if plan.kind:
        rural = [d for d in candidates if d.endswith(("읍", "면"))]
        candidates = rural if plan.kind == "읍면만" else [d for d in candidates if d not in rural]
        if not candidates:
            notes.append(f"{region}에는 {'읍 · 면' if plan.kind == '읍면만' else '동'}이 없어요")
            candidates = list(every)
    if plan.exclude:
        gone = [d for d in candidates if d in plan.exclude]
        candidates = [d for d in candidates if d not in plan.exclude] or candidates
        if gone:
            notes.append(f"{' · '.join(gone)}은(는) 빼고 봤어요")
    conds, dropped = [], []
    for c0 in plan.conds:
        c = _value_fix(c0)
        why = _ref_ok(c, region)
        if why:
            dropped.append(why)
        elif c.op in ("이상", "이하") and c.value is None:
            dropped.append(f"{_ref_name(c)} {c.op}(기준 숫자가 없음)")
        else:
            conds.append(c)
    refs: list[Ref] = list(
        dict.fromkeys([Ref(**c.model_dump(include={"metric", "per", "scale"})) for c in conds])
    )
    for r in list(plan.show) + ([plan.sort] if plan.sort else []):
        if r is None:
            continue
        why = _ref_ok(r, region)
        if why:
            dropped.append(why)
        elif r not in refs:
            refs.append(r)
    raw = {}
    for name in every:
        p = data.places(name) or {}
        # 10-29 변수 시험 c01_099: 약국 수가 서가(국립중앙의료원 약국 정보 18곳)와 계산(상가정보
        #       16곳)에서 달라 한 답에 두 숫자가 섞였다 → 약국 정보가 있으면 계산도 그 곳 수로
        ph = data.pharmacies(name) if hasattr(data, "pharmacies") else None
        if ph and ph.get("list") is not None:
            p = {**p, "_pharmacy_n": len(ph["list"])}
        raw[name] = (data.dong(name) or {}, p, people.get(name) or {})
    values: dict[str, dict[str, float | None]] = {
        n: {r.key: _value(r, *raw[n]) for r in refs} for n in every
    }
    ranks: dict[str, dict[str, int]] = {}
    lows: dict[str, dict[str, int]] = {}
    stats: dict[str, Stat] = {}
    for r in refs:
        have = [(values[n][r.key], n) for n in every if values[n][r.key] is not None]
        # 【판단】 같은 값은 같은 등수(더 큰 값의 수 + 1) — 이름순으로 '적음'이 갈리지 않게
        ranks[r.key] = {n: 1 + sum(o > x for o, _ in have) for x, n in have}
        lows[r.key] = {n: 1 + sum(o < x for o, _ in have) for x, n in have}
        if have:
            stats[r.key] = _stat(r, {n: values[n][r.key] for n in every}, raw)
        if BY_KEY[r.metric].note:
            notes.append(f"{BY_KEY[r.metric].name}: {BY_KEY[r.metric].note}")

    def base(r: Ref) -> float | None:
        s = stats.get(r.key)
        if not s:
            return None
        # 10-28 재심사 q05_b: '22개 동의 평균보다 높음'을 비율 지표의 지역 전체 값
        #        (분자 합 ÷ 분모 합, 20.1%)으로 셈해 9곳 — 물은 것은 동 평균(20.2%, 8곳)이었다
        return s.whole if s.whole is not None and not plan.dong_mean else s.mean

    shown: list[tuple[Cond, str]] = []
    for c in conds:
        nm = _ref_name(c)
        n = len(ranks[c.key])
        if c.op == "많음":
            shown.append((c, f"{nm} 많음({region} {n}곳 중 위 {_third(n)}곳)"))
        elif c.op == "적음":
            shown.append((c, f"{nm} 적음({region} {n}곳 중 아래 {_third(n)}곳)"))
        elif c.op in ("이상", "이하"):
            shown.append((c, f"{nm} {_fmt(c, c.value)} {c.op}"))
        elif c.op in ("있음", "없음"):
            shown.append((c, f"{nm} {'1 이상' if c.op == '있음' else '0(없음)'}"))
        else:
            s = stats.get(c.key)
            whole = s is not None and s.whole is not None and not plan.dong_mean
            basis = "지역 전체 값" if whole else "동 평균"
            shown.append((c, f"{nm} {region} {basis}({_fmt(c, base(c))})보다 {c.op[-2:]}"))

    def ok(name: str, c: Cond) -> bool:
        v = values[name][c.key]
        if v is None:
            return False
        n = len(ranks[c.key])
        if c.op == "많음":
            return ranks[c.key][name] <= _third(n)
        if c.op == "적음":
            return lows[c.key][name] <= _third(n)
        if c.op == "이상":
            return v >= (c.value or 0)
        if c.op == "이하":
            return v <= (c.value or 0)
        if c.op == "있음":
            return v > 0
        if c.op == "없음":
            return v == 0
        b = base(c)
        if b is None:
            return False
        return v > b if c.op == "평균보다 높음" else v < b

    def closeness(name: str) -> float:
        # 조건들의 등수 평균(작을수록 조건에 더 맞음). 낮은 쪽 조건은 아래에서 센 등수
        rs = []
        for c in conds:
            n = len(ranks[c.key])
            rs.append(((lows if c.op in LOW_OPS else ranks)[c.key]).get(name, n + 1))
        return sum(rs) / len(rs) if rs else 0.0

    # 【판단】 10-26 예외 점검: 조건도 정렬도 없이 지표만 보여 달라면(동마다 표) 이름순이었다 →
    #        첫 지표 많은 순(값이 없는 동은 뒤로)
    key = plan.sort or (refs[0] if not conds and refs and not want else None)
    ix = {n: i for i, n in enumerate(candidates)}

    def by_sort(name: str) -> tuple:
        # 같으면 후보 차례(앞 결과 · 말한 차례, 아니면 지역 동 목록 차례)
        if key and key.key in values[name]:
            v = values[name][key.key]
            if v is None:
                return (1, 0.0, ix.get(name, 0))
            return (0, -v if (plan.sort is None or plan.order == "많은 순") else v, ix.get(name, 0))
        return (0, closeness(name), ix.get(name, 0))

    hits = {n: [ok(n, c) for c in conds] for n in candidates}
    near: list[tuple[str, list[int]]] = []
    if plan.mode == "모두":
        matched = [n for n in candidates if all(hits[n])]
        if conds:
            near = [
                (n, [i for i, h in enumerate(hits[n], 1) if not h])
                for n in candidates
                if sum(not h for h in hits[n]) == 1 and len(conds) >= 2
            ]
        matched.sort(key=by_sort)
        near.sort(key=lambda x: by_sort(x[0]))
    elif plan.mode == "많이 맞는 순":
        matched = sorted(candidates, key=lambda n: (-sum(hits[n]), by_sort(n)))
    else:
        matched = (
            sorted(candidates, key=by_sort) if (plan.sort or not plan.dongs) else list(candidates)
        )
    res = Result(
        region,
        candidates,
        shown,
        plan.mode,
        matched,
        near,
        hits,
        values,
        ranks,
        stats,
        dropped,
        notes,
        raw=raw,
        refs=refs,
    )
    if len(candidates) < len(every):
        res.sub_name = _sub_name(plan, region, candidates, every)
        for r in refs:
            hv = [(values[n][r.key], n) for n in candidates if values[n][r.key] is not None]
            low = r.key in {c.key for c in conds if c.op in LOW_OPS} or (
                plan.sort is not None and plan.sort.key == r.key and plan.order == "적은 순"
            )
            if low:
                res.sub_low.add(r.key)
            res.sub_ranks[r.key] = {
                n: 1 + sum((o < x) if low else (o > x) for o, _ in hv) for x, n in hv
            }
    res.lines = lines(res, plan, refs)
    if plan.mode != "모두" and conds:
        res.table = _table(res, plan, refs)
    elif plan.mode == "동마다 표" and refs and len(res.matched) >= 2:
        # 【판단】 10-26: 조건 없이 '동마다 열 셋으로 표'(calc_27 C09)를 바라면 값 표를
        #        코드가 만든다(없으면 글쓴이가 숫자를 옮겨 표를 다시 그린다)
        res.table = _value_table(res, plan, refs)
    return res


def _sub_name(plan: Plan, region: str, cands: list[str], every: list[str]) -> str:
    n = len(cands)
    if plan.use_prev and not plan.kind and not plan.exclude:
        return f"앞 결과 {n}곳"
    if plan.kind == "읍면만":
        return f"읍 · 면 {n}곳"
    if plan.kind == "동만":
        return f"동 지역 {n}곳"
    gone = [d for d in every if d not in cands]
    if plan.exclude and len(gone) <= 3:
        last = gone[-1][-1]
        eul = "을" if "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 else "를"
        return f"{' · '.join(gone)}{eul} 뺀 {n}곳"
    return f"고른 {n}곳"


def _cell(res: Result, name: str, r: Ref) -> str:
    v = res.values[name].get(r.key)
    if v == 0:
        return f"{_ref_name(r)} {_fmt(r, v)}"  # 0은 등수 · 배수가 뜻이 없다(같은 0이 여럿)
    rk = res.ranks.get(r.key, {}).get(name)
    of = len(res.ranks.get(r.key, {}))
    tail = f"({of}곳 중 많은 순 {rk}위)" if rk else ""
    sub = res.sub_ranks.get(r.key, {}).get(name)
    if sub and res.sub_name:
        way = "적은" if r.key in res.sub_low else "많은"
        tail = f"({res.sub_name} 중 {way} 순 {sub}위 · {res.region} {of}곳 중 많은 순 {rk}위)"
    s = res.stats.get(r.key)
    b = s.whole if (s and s.whole is not None) else (s.mean if s else None)
    if v is not None and b:
        what = "전체 값" if s and s.whole is not None else "동 평균"
        x = v / b
        if _fmt(r, v) == _fmt(r, b) and v != b:
            # 【판단】 10-26 페르소나 c01: 역삼1동 1.9곳이 구 전체 1.9곳보다 '낮음'으로 맞았는데
            #        같아 보여 사용자가 오류로 봄 → 반올림해 같으면 소수 둘째 자리까지 함께 적는다
            tail += f", 지역 {what} {b:.2f}보다 {'낮음' if v < b else '높음'}({v:.2f})"
        # 【판단】 10-26 예외 점검: 1채 ÷ 평균 168채가 '0.0배'로 나갔다
        #        → 0.1배가 안 되면 그렇게 적는다
        tail += f", 지역 {what}의 " + ("0.1배가 안 됨" if 0 < x < 0.05 else f"{x:.1f}배")
    return f"{_ref_name(r)} {_fmt(r, v)}{tail}"


def _stat_line(res: Result, r: Ref) -> str | None:
    s = res.stats.get(r.key)
    if not s:
        return None
    parts = []
    if s.whole is not None:
        parts.append(f"지역 전체 값 {_fmt(r, s.whole)}(동 숫자를 합쳐서 나눈 값)")
    parts.append(f"동 평균 {_fmt(r, s.mean)}")
    parts.append(f"가운데값 {_fmt(r, s.median)}")
    if s.total is not None:
        parts.append(f"합계 {_fmt(r, s.total)}")
    return f"[{res.region} {s.n}곳 기준] {_ref_name(r)}: " + ", ".join(parts)


def lines(res: Result, plan: Plan, refs: list[Ref]) -> list[str]:
    """글쓴이에게 건널 사실 줄. 숫자 · 등수 · 배수는 전부 코드가 셌다."""
    out: list[str] = []
    sub = len(res.candidates) < len(set(res.candidates) | set(res.values))
    where = f"{res.region} {len(res.values)}곳"
    if sub:
        names = " · ".join(res.candidates)
        where += (
            f" 가운데 {names} 안에서"
            if len(res.candidates) <= 6 or res.sub_name.startswith("고른")
            else f" 가운데 {res.sub_name} 안에서"
        )
    if restate := clean_restate(plan.restate):
        out.append(f"[알아들은 것] {restate}")
    if res.conds:
        out.append(
            f"[여러 조건 계산] {where}, 조건 {len(res.conds)}가지(계산 방식: {res.mode}): "
            + " / ".join(f"{i}) {s}" for i, (_, s) in enumerate(res.conds, 1))
        )
    else:
        out.append(f"[여러 조건 계산] {where}(조건 없음, 계산 방식: {res.mode})")
    for r in refs:
        if line := _stat_line(res, r):
            out.append(line)
    top = res.matched[: shown_limit(res, plan)]
    blank = [n for n in top if refs and all(res.values[n].get(r.key) is None for r in refs)]
    if res.mode == "모두":
        if res.conds and res.matched:
            # 10-27 village_6 c2 T3: '10곳(위 5곳만)'을 글쓴이가 '5곳'으로 읽음 → 뜻을 풀어 적는다
            more = f" — 그중 위 {len(top)}곳만 적음" if len(res.matched) > len(top) else ""
            out.append(f"[모두 맞는 동] 모두 {len(res.matched)}곳{more}: " + " · ".join(top))
        elif res.conds:
            out.append("[모두 맞는 동] 없음")
        else:
            out.append(f"[고른 동] {' · '.join(n for n in top if n not in blank)}")
    elif res.conds:
        for name in top:
            n_hit = sum(res.hits[name])
            ok = [str(i) for i, h in enumerate(res.hits[name], 1) if h]
            out.append(
                f"[{name}] 조건 {len(res.conds)}가지 중 {n_hit}가지 맞음"
                + (f"({', '.join(ok)}번)" if ok else "")
            )
    for name in top:
        if name in blank:
            continue
        cells = ", ".join(_cell(res, name, r) for r in refs)
        if cells:
            out.append(f"[{name}] {cells}")
    if blank:
        # 【판단】 10-26 예외 점검: 춘천 빈집(25곳 중 10곳만)을 25곳 줄 세우면 '자료 없음' 줄이 15개
        out.append(f"[자료 없는 동] {len(blank)}곳: " + " · ".join(blank))
    if plan.agg and top:
        for r in refs:
            vals = [res.values[n][r.key] for n in top if res.values[n][r.key] is not None]
            if not vals:
                continue
            m = BY_KEY[r.metric]
            if "합계" in plan.agg and m.count and not r.per:
                out.append(f"[고른 {len(vals)}곳 합계] {_ref_name(r)} {_fmt(r, sum(vals))}")
            if "평균" in plan.agg:
                pooled = _pooled(res, r, [n for n in top if res.values[n][r.key] is not None])
                if pooled is not None:
                    # 비율 · N명당은 동 값을 평균 내지 않고 숫자를 합쳐서 나눈다
                    # (지역 전체 값과 같은 셈)
                    out.append(
                        f"[고른 {len(vals)}곳 평균] {_ref_name(r)} {_fmt(r, pooled)}"
                        "(고른 동 숫자를 합쳐서 나눈 값)"
                    )
                else:
                    mean = _fmt(r, statistics.fmean(vals))
                    out.append(f"[고른 {len(vals)}곳 평균] {_ref_name(r)} {mean}")
    if "범위" in plan.agg:
        for r in refs:
            have = [(res.values[n][r.key], n) for n in res.candidates]
            have = [(v, n) for v, n in have if v is not None]
            if len(have) < 2:
                continue
            (hv, hn), (lv, ln) = max(have), min(have)
            times = f", {hn} 값은 {ln} 값의 {hv / lv:.1f}배" if lv > 0 else ""
            out.append(
                f"[범위] {_ref_name(r)}: 가장 높은 {hn} {_fmt(r, hv)}, "
                f"가장 낮은 {ln} {_fmt(r, lv)}{times}"
            )
    # 【정함 10-27 팀장】 묻는 것만 — 모두 맞는 동이 있으면 '하나만 못 맞춘 동'은 넘기지 않는다
    #        (multi_16 e1: G3 · G4 · G6 · C5에서 정답 뒤에 묻지 않은 5곳.
    #        글쓴이 안내는 '없을 때만'이었다)
    if res.near and not res.matched:
        out.append(
            "[하나만 못 맞춘 동] "
            + " · ".join(
                f"{n}({', '.join(str(i) for i in miss)}번 조건)"
                for n, miss in res.near[: plan.limit]
            )
        )
    if res.dropped:
        out.append("[계산하지 못한 조건] " + " · ".join(res.dropped))
    if plan.unknown:
        out.append("[자료 목록에 없는 조건] " + " · ".join(plan.unknown))
        out += unknown_hints(plan.unknown)
    if plan.cross:
        out.append(
            "[사람 단위로 겹쳐 세기] 자료가 동 단위 합계라 "
            "'두 조건에 모두 해당하는 사람 수'는 셀 수 "
            "없음(예: 80세 이상이면서 반지하에 사는 분 수). 조건마다 동 숫자를 따로 보임"
        )
    out += [f"[참고] {x}" for x in res.notes]
    # 【판단】 10-26 페르소나 c01 3판 T3: 계산 줄에 기준 달 · 출처가 없어 '기준 연월과 출처는 자료에
    #        적혀 있지 않다'고 답함 → 주민등록 지표를 썼으면 판과 출처를 한 줄로(판은 basis가 읽음)
    #        10-26 예상 질문 2-14: 경로당 수에 넓이 자료의 날짜(2022-11-22)가 붙음 → 경로당 수도
    for key in dict.fromkeys("reg" if r.metric in REG_METRICS else r.metric for r in refs):
        if basis := metric_basis(key, res.region):
            out.append(basis)
    return out


def metric_basis(key: str, region: str) -> str | None:
    """지표의 출처 · 기준 한 줄([기준] …). 모르는 지표는 None."""
    if key in REG_METRICS or key == "reg":
        from src.assistant import basis as B

        b = B.data_basis()
        return (
            f"[기준] 주민등록 인구 · 1인세대 {b['주민등록 1인세대']} 판"
            f"(1년 새 증감은 {b['주민등록 1인세대 1년 전']} 판과 견줌), "
            "출처 행정안전부 주민등록 인구통계"
        )
    if key == "halls":
        from src.assistant.librarian import HALL_RANK_NAME

        if region in HALL_RANK_NAME:
            return f"[기준] {region} 경로당 · 마을회관 수: {HALL_RANK_NAME[region]}"
    return None


def shown_limit(res: Result, plan: Plan) -> int:
    """보일 동 수. 개수를 말하지 않았고(기본 5) 모두 맞는 동이 8곳 이하면 다 보인다.

    【판단】 10-26 calc_flow_8 을 쓰며: '그 중에 약국 없는 데는?'이 6곳인데 5곳만 나가면
           사용자가 하나를 놓친다. 8곳이 넘으면 위 5곳과 '몇 곳(위 5곳만)'을 알린다
    """
    if res.mode == "모두" and res.conds and plan.limit == 5 and len(res.matched) <= 8:
        return len(res.matched)
    return plan.limit


def focus_lines(res: Result, plan: Plan, names: list[str]) -> list[str]:
    """말에 나온 동이 보인 동에 없으면 그 동의 값 줄(조건 몇 번을 맞췄는지와 함께)."""
    shown = set(res.matched[: shown_limit(res, plan)])
    out = []
    for n in names:
        if n in shown or n not in res.values:
            continue
        cells = ", ".join(_cell(res, n, r) for r in res.refs)
        hit = res.hits.get(n)
        mark = ""
        if hit is not None and res.conds:
            ok = [str(i) for i, h in enumerate(hit, 1) if h]
            mark = f"조건 {len(res.conds)}가지 중 {sum(hit)}가지 맞음" + (
                f"({', '.join(ok)}번) · " if ok else " · "
            )
        elif res.conds:
            mark = "고른 범위 밖 · "
        out.append(f"[말씀하신 동 {n}] {mark}{cells}")
    return out


REG_METRICS = {
    "residents",
    "pop65",
    "pop80",
    "solo65",
    "solo65_rise",
    "solo80",
    "solo65_share",
    "youth",
    "youth_solo",
    "youth_solo_rise",
}


def _pooled(res: Result, r: Ref, names: list[str]) -> float | None:
    """고른 동들의 비율 · N명당을 숫자를 합쳐서 나눈 값(비율 지표가 아니면 None)."""
    m = BY_KEY[r.metric]
    if not (r.per or (m.num and m.den)) or not names or not res.raw:
        return None
    return _stat(r, {n: res.values[n][r.key] for n in names}, res.raw).whole


# 【판단】 10-26 예외 점검: 계산 도구 지표 목록에 없어도 다른 서가에 있는 자료가 있다(버스 · 날씨 ·
#        기관 연락처). '자료 없음'으로 끝내지 않게 어디서 볼 수 있는지 사실 줄로 건넨다
_ELSEWHERE = (
    (
        re.compile(r"버스|정류장|배차|교통"),
        "[다른 곳에 있는 자료] 버스 횟수 · 정류장 거리는 춘천 읍면마다 따로 볼 수 있음"
        "(이 계산 도구의 지표는 아님)",
    ),
    (
        re.compile(r"날씨|한파|폭염|특보|예보|기온|폭설|호우"),
        "[다른 곳에 있는 자료] 날씨 예보 · 특보는 동 상황 · 오늘 챙길 일에서 따로 봄"
        "(이 계산 도구의 지표는 아님)",
    ),
    (
        re.compile(r"전화|연락처|창구|신청"),
        "[다른 곳에 있는 자료] 지원 기관 연락처 · 신청 창구는 지원 기관 안내에서 따로 봄",
    ),
    (re.compile(r"우울|소득|질병|치매|장애|자살"), "[취약 돌보미에 없는 자료] {u}"),
)


def unknown_hints(unknown: tuple[str, ...]) -> list[str]:
    """목록 밖 조건마다 다른 서가에 있는지 · 아예 없는지 한 줄씩."""
    out: list[str] = []
    for u in unknown:
        for rx, hint in _ELSEWHERE:
            line = hint.format(u=u)
            if rx.search(u) and line not in out:
                out.append(line)
    return out


def _table(res: Result, plan: Plan, refs: list[Ref]) -> str:
    """동마다 조건에 맞았나 표(○ · ×와 값)."""
    head = ["동"] + [f"{i}) {_ref_name(c)}" for i, (c, _) in enumerate(res.conds, 1)] + ["맞은 수"]
    rows = []
    for name in res.matched[: shown_limit(res, plan)]:
        cells = [name]
        for i, (c, _) in enumerate(res.conds):
            mark = "○" if res.hits[name][i] else "×"
            cells.append(f"{mark} {_fmt(c, res.values[name].get(c.key))}")
        cells.append(f"{sum(res.hits[name])}/{len(res.conds)}")
        rows.append(cells)
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(md)


def sheet(res: Result) -> tuple[tuple[str, ...], ...]:
    """계산 결과 전체 표(머리 줄 + 후보 동 모두) — 엑셀로 줄 때 쓴다(10-28 p09_c).

    【판단】 10-28 페르소나 p09_c(데이터 담당): 여러 조건 계산 뒤 '엑셀로'를 세 번 말했는데 파일은
           2곳 → 8곳 → 1곳(그때 동 칸)으로 바뀌고 조건 열이 없었다. 채팅 표는 보인 곳만이라
           파일은 후보 동 모두 · 조건마다 ○ × 와 값 · 맞은 수로 코드가 만든다
    """
    if res.conds:
        head = ["동"] + [f"{i}) {_ref_name(c)}" for i, (c, _) in enumerate(res.conds, 1)]
        head.append("맞은 수")
        order = {n: i for i, n in enumerate(res.matched)}
        names = sorted(
            res.candidates,
            key=lambda n: (-sum(res.hits.get(n, [])), order.get(n, len(order)), n),
        )
        rows = []
        for name in names:
            cells = [name]
            for i, (c, _) in enumerate(res.conds):
                hit = (res.hits.get(name) or [False] * len(res.conds))[i]
                cells.append(f"{'○' if hit else '×'} {_fmt(c, res.values[name].get(c.key))}")
            cells.append(f"{sum(res.hits.get(name, []))}/{len(res.conds)}")
            rows.append(tuple(cells))
    else:
        refs = list(res.refs)
        head = ["동"] + [_ref_name(r) for r in refs]
        order = {n: i for i, n in enumerate(res.matched)}
        names = sorted(res.candidates, key=lambda n: (order.get(n, len(order)), n))
        rows = [tuple([n] + [_fmt(r, res.values[n].get(r.key)) for r in refs]) for n in names]
    return (tuple(head), *rows)


def _value_table(res: Result, plan: Plan, refs: list[Ref]) -> str:
    """동마다 지표 값 표(조건 없이 나란히 보기)."""
    head = ["동"] + [_ref_name(r) for r in refs]
    md = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for name in res.matched[: shown_limit(res, plan)]:
        cells = [name] + [_fmt(r, res.values[name].get(r.key)) for r in refs]
        md.append("| " + " | ".join(cells) + " |")
    return "\n".join(md)


# ── 질문 → 계산 계획(지표 목록 안에서만 고름) ──


def _nullable_enum(values: list[str]) -> dict:
    """값 목록 중 하나 또는 null.

    【판단】 10-27 village_6(API 길 첫 실측): `{"type": ["string", "null"], "enum": [..., null]}`
           꼴을 API의 strict 도구 검사가 400('Enum value … does not match declared type')으로 거절해
           계획기가 한 번도 돌지 못하고 엔진이 '계산 아님'으로 넘어갔다(CLI 길의 --json-schema는
           이 검사를 하지 않아 10-24 ~ 10-27 아침까지 드러나지 않음). anyOf 꼴은 통과한다
    """
    return {"anyOf": [{"type": "string", "enum": list(values)}, {"type": "null"}]}


def _ref_schema() -> dict:
    keys = [m.key for m in METRICS]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["metric", "per", "scale"],
        "properties": {
            "metric": {"type": "string", "enum": keys},
            "per": _nullable_enum(list(PER)),
            "scale": {"type": ["integer", "null"]},
        },
    }


def plan_schema() -> dict:
    """데스크(LLM)가 채울 JSON 모양 — 지표 · 연산 · 방식은 목록 안에서만."""
    cond = _ref_schema()
    cond = {
        **cond,
        "required": ["metric", "per", "scale", "op", "value"],
        "properties": {
            **cond["properties"],
            "op": {"type": "string", "enum": list(OPS)},
            "value": {"type": ["number", "null"]},
        },
    }
    props = {
        "restate": {"type": "string"},
        "need": {"type": "string", "enum": ["계산", "바로", "되짚기"]},
        "region": _nullable_enum(["강남구", "춘천시"]),
        "dongs": {"type": "array", "items": {"type": "string"}},
        "use_prev": {"type": "boolean"},
        "kind": _nullable_enum(["읍면만", "동만"]),
        "exclude": {"type": "array", "items": {"type": "string"}},
        "conds": {"type": "array", "items": cond},
        "mode": {"type": "string", "enum": list(Mode.__args__)},  # type: ignore[attr-defined]
        "show": {"type": "array", "items": _ref_schema()},
        "agg": {"type": "array", "items": {"type": "string", "enum": ["합계", "평균", "범위"]}},
        "sort": {"anyOf": [_ref_schema(), {"type": "null"}]},
        "order": {"type": "string", "enum": ["많은 순", "적은 순"]},
        "limit": {"type": "integer"},
        "unknown": {"type": "array", "items": {"type": "string"}},
        "cross": {"type": "boolean"},
    }
    # 【판단】 strict 도구는 모든 칸이 required 여야 한다
    #        — 칸을 더할 때 빠뜨리지 않게 칸 목록에서 만든다
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(props),
        "properties": props,
    }


def metric_list() -> str:
    """지시문에 넣는 지표 목록(키 · 이름 · 단위 · 있는 지역 · 이렇게 부르면)."""
    rows = []
    for m in METRICS:
        where = "두 지역" if m.regions == BOTH else m.regions[0] + "만"
        rows.append(f"- {m.key}: {m.name} ({m.unit or '값'}, {where}) — {m.words}")
    return "\n".join(rows)


PLAN_SYSTEM = """너는 복지 담당자의 질문을 '여러 조건 계산' 계획으로 옮기는 안내 데스크다.
숫자를 세거나 동을 고르지 않는다. 질문 속 조건 · 바라는 계산을 아래 목록 안에서 옮기기만 한다.

먼저 need를 정한다 — 이 말에 여러 조건 계산이 필요한가:
- 계산: 동 여럿의 값을 조건으로 거르기 · 지역 평균이나 전체와 견주기 · 합계 · 평균 ·
  1,000명당처럼 사람 수로 나누기 · 지표 둘 이상을 동마다 나란히(표) · 앞에서 고른 동들 안에서
  다시 거르기 · 두 동을 지표 여럿으로 견주어 어디가 먼저인지 · 사용자가 적은 여러 동의 숫자가
  맞는지 확인 · '면 중 · ○○ 빼고 · 도심 말고'처럼 일부만 골라 줄 세우기 · 자료에 없는 나눗셈
  (전체 주민 대비 비율처럼)을 정확히 달라는 말
- 바로: 동 하나의 자료 · 지역 전체를 지표 하나로 줄 세우기(가장 많은 동 · 위 N곳) · 말뜻 ·
  기준 · 출처 설명 · 순위와 진단 중 무엇을 쓰나 · 문서 만들기 · 날씨 · 버스 · 기관 안내 ·
  한 사람에 대한 질문
- 되짚기: 앞에서 들은 말을 확인 · 요약하거나 앞뒤가 다르다고 따지는 말(새 계산 없이 답할 수 있음)
지표 이름이 여럿 나와도 그 뜻을 묻거나 앞 답을 따지는 말이면 계산이 아니다.
춘천 읍 · 면의 마을(리)을 조건으로 거르는 말('버스가 하루 5번 이하이고 약국이 먼 마을', '약국이 먼
마을이 있는 면')은 계산이다 — 마을 지표(v_로 시작)를 쓴다.
마을 하나 · 경로당 하나 · 정류장을 묻거나,
읍 · 면 하나의 버스 · 약국을 그대로 묻는 말('북산면 버스 하루 몇 번?')은 바로다.
need가 계산이 아니면 conds · show · agg는 빈 목록, sort는 null로 둔다.

지표 목록(키: 이름 (단위, 있는 지역) — 사용자가 이렇게 부르면):
{metrics}

조건의 연산(op):
- 많음 · 적음: '많은 · 높은 · 큰' / '적은 · 낮은 · 부족한'(지역 안 위 · 아래 3분의 1)
- 평균보다 높음 · 평균보다 낮음: '평균보다 · 구 평균보다 · 시 평균보다'라고 했을 때
- 이상 · 이하: 사용자가 숫자 기준을 말했을 때만, value에 그 숫자
  ('3천 명 넘고' → 이상 3000, '5km가 넘는' → 이상 5, 비율은 0 ~ 1: '30% 이상' → 0.3)
- 있음 · 없음: '있는 · 없는'(0이냐 아니냐). 그 밖에는 value를 null로

나눈 지표(per · scale): '65세 이상 1,000명당 경로당'처럼 사람 수로 나눠 달라고 하면
metric=halls, per=pop65, scale=1000.
per에 쓸 수 있는 것: residents · pop65 · pop80 · solo65 · solo80 · youth.
그렇지 않으면 per · scale 은 null

대상 꾸밈말: '80세 이상, 여성, 혼자 사는, 기초수급, 반지하'처럼 나열 속 '혼자 사는 · 독거'가
다른 조건을 이미 독거 지표(80세 이상 독거 · 여성 독거 · 수급 독거)로 옮겼을 때 그 지표들을 꾸미는
말이면 '독거노인 전체'를 따로 조건으로 세우지 않는다(같은 말을 두 번 세지 않는다). 다른 조건이 독거
지표가 아니면(반지하만 · 경로당만) 혼자 사는 어르신 지표를 조건으로 세운다.

계산 방식(mode):
- 모두: 조건을 모두 맞는 동(기본)
- 많이 맞는 순: 공모 · 지침 기준처럼 '조건에 많이 맞을수록' · '가장 잘 맞는 동 N곳'
  · '어느 항목에 해당하는지'
- 동마다 표: 사용자가 동 몇 곳을 정해 '나란히 · 비교 · 각각' 보여 달라고 할 때(그 동들을 dongs에)

그 밖의 칸:
- restate: 알아들은 계산을 한 문장으로(꼬인 말은 가장 그럴듯하게 풀고, 어떻게 풀었는지 적는다).
  앞 결과 동 이름을 늘어놓지 않는다('앞 결과 16곳 중'처럼 수만)
- dongs: 질문이 동 몇 곳 안에서만 보라고 할 때. 동 하나가 지역에서 어느 정도인지(많은 편 · 몇 위 ·
  평균보다)를 물으면 그 동을 dongs에 넣는다(등수 · 평균은 코드가 지역 전체로 센다).
  use_prev: '그중에서 · 그 동들 중 · 위 N곳 중'처럼 앞에서 고른 동들 안에서라는 말이 있으면 true
- kind: 춘천의 '면만 · 읍면만 · 시골' → 읍면만, '도심 · 시내 동만' → 동만. exclude: '○○동은 빼고'
- show: 조건은 아니지만 같이 보여 달라는 지표. agg: '합치면 · 다 더하면' → 합계, '평균' → 평균,
  '제일 높은 동과 낮은 동 몇 배 차이 · 격차' → 범위(그 지표를 show나 sort에)
- sort: 특정 지표 순으로 줄 세워 달라고 할 때만, order: '많은 순' · '적은 순'
- limit: 'N곳'처럼 개수를 말하면 그 수, 아니면 5
- unknown: 지표 목록에 없는 조건은 지어 붙이지 말고 사용자 말 그대로
  (예: 우울감, 소득, 동 지역 · 강남의 버스 횟수, 경로당 이용자 수,
  춘천의 성별 독거노인 · 80세 이상 남성처럼 나뉘지 않은 것)
  — 다만 가까운 지표가 있으면(남녀 합 · 나이 합) 그 지표도 조건에 넣고
  unknown에는 '나뉘지 않음'을 적는다
- cross: '80세 이상이면서 반지하에 사는 분 몇 명'처럼
  한 사람이 두 조건에 함께 해당하는 수를 세 달라면 true
- region: 질문에 강남 · 춘천이 있으면 그것, 없으면 회원 담당 지역

특히:
- gap은 클수록 자원이 적다: '돌봄 · 생활 자원이 부족한 곳'은 gap 많음
- priority는 작을수록 먼저 볼 동: '먼저 볼 동 위 5곳'은 sort=priority, order=적은 순, limit=5
- 강남의 '혼자 사는 할머니 · 할아버지'는 lonely_female · lonely_male,
  '공적 지원 밖 · 사각지대 비율'은 lonely_outside_share,
  '독거노인'은 강남이면 lonely_total, 춘천이면 solo65
- '혼자 사는 비율'은 solo65_share. '늘어난'은 solo65_rise(1년) · lonely_rise2(강남 2년)
- 청년 이야기 중의 '늘어난 · 증감'은 youth_solo_rise(65세 이상 지표를 섞지 않는다)
- '그 N곳 중에 … 빼고'처럼 앞 결과와 일부만이 함께면 use_prev와 kind · exclude를 같이 쓴다
- '앞 계산 조건'이 주어지고 사용자가 같은 기준을 다시 말하면 같은 지표 · 연산으로 옮긴다
- 마을 지표(v_…)는 춘천 읍 · 면의 마을(법정 리)마다 값이다. '약국이 먼 마을'은 v_pharm 이상 5
  (우리 기준 5km — 사용자가 숫자를 말하면 그 숫자), '일요일에 약국이 먼'은 v_pharm_sun.
  '버스가 드문 마을'은 v_bus 이하 3(우리 기준 — 사용자가 '하루 5번 이하'처럼 말하면 그 숫자).
  마을 지표와 읍면 지표(solo80 따위)를 함께 쓰면 코드가 읍 · 면을 먼저 거른 뒤 그 안의 마을을 본다.
  region은 춘천시, dongs에는 읍 · 면 이름만(마을 이름은 넣지 않는다)"""


def _ref(raw: dict | None) -> Ref | None:
    if not raw or not raw.get("metric"):
        return None
    return Ref(metric=raw["metric"], per=raw.get("per"), scale=raw.get("scale"))


def plan_from(raw: dict) -> Plan:
    """데스크 JSON → Plan(모양이 틀리면 ValueError)."""
    return Plan(
        region=raw.get("region"),
        dongs=tuple(raw.get("dongs") or ()),
        use_prev=bool(raw.get("use_prev")),
        kind=raw.get("kind") or None,
        exclude=tuple(raw.get("exclude") or ()),
        conds=tuple(
            Cond(
                metric=c["metric"],
                per=c.get("per"),
                scale=c.get("scale"),
                op=c["op"],
                value=c.get("value"),
            )
            for c in raw.get("conds") or ()
        ),
        mode=raw.get("mode") or "모두",
        show=tuple(r for r in (_ref(x) for x in raw.get("show") or ()) if r),
        agg=tuple(raw.get("agg") or ()),
        sort=_ref(raw.get("sort")),
        order=raw.get("order") or "많은 순",
        limit=max(1, min(25, int(raw.get("limit") or 5))),
        unknown=tuple(raw.get("unknown") or ()),
        cross=bool(raw.get("cross")),
        restate=str(raw.get("restate") or ""),
        need=raw.get("need") or "계산",
    )


class ClaudePlanner:
    """질문 → Plan. 실패하면 None(부르는 쪽이 지금 엔진으로 넘긴다)."""

    def __init__(self, settings, usage, model: str | None = None, effort: str = "low") -> None:
        self.s = settings
        self.usage = usage
        self.model = model or settings.desk_model
        self.effort = effort

    def _kwargs(self, user: str) -> dict:
        from src.assistant import llm

        # 【판단】 10-30 팀장 '왜 오래 걸려?': 계산 계획은 지시문(지표 목록 포함 약 9천 토큰)을
        #        캐시 없이 매번 새로 읽었다 → 도구 정의 · 지시문을 1시간 캐시에(llm.CACHE_1H)
        return dict(
            model=self.model,
            max_tokens=3000,
            system=[
                {
                    "type": "text",
                    "text": PLAN_SYSTEM.format(metrics=metric_list()),
                    "cache_control": llm.CACHE_1H,
                }
            ],
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": "plan",
                    "description": "질문 속 조건 · 바라는 계산을 목록 안에서 옮긴 계획",
                    "strict": True,
                    "input_schema": plan_schema(),
                }
            ],
            tool_choice={"type": "auto"},
            output_config={"effort": self.effort},
        )

    def plan(self, question: str, member_region: str | None, context: str = "") -> Plan | None:
        from src.assistant import llm

        user = f"회원 담당 지역: {member_region or '없음'}\n"
        if context:
            user += f"앞 대화(참고): {context}\n"
        user += f"질문: {question}"
        for _ in range(2):
            r = llm.call(self.s.anthropic_api_key, self.usage, **self._kwargs(user))
            call = next((b for b in r.content if b.type == "tool_use"), None)
            if call is None:
                continue
            try:
                return plan_from(dict(call.input))
            except (ValueError, TypeError, KeyError):
                continue
        return None


def planners(s, usage) -> dict:
    """엔진에 넘길 계산 계획기 둘(Haiku · 검사에 걸릴 때 큰 모델). 설정에서 끄면 빈 dict."""
    if not s.calc_on:
        return {}
    return {
        "planner": ClaudePlanner(s, usage),
        "planner_big": ClaudePlanner(s, usage, model=s.calc_big_model, effort="medium"),
    }
