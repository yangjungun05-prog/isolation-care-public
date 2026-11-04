"""사서 — 주제 · 슬롯을 받아 자료를 꺼내고, 숫자 · 비교를 코드로 계산해 '사실 묶음'을 만든다.

【판단】 숫자 · 늘었나 줄었나 · 순위는 여기서만 만든다. 답 쓰기(AI)는 이 묶음을 옮기기만 한다.
       big-contest 동 상황 문서 47곳 시험(10-12): AI에게 계산을 맡기지 않고 미리 계산해 넘기자
       방향 반대 0건. 문장은 한 가지 뜻으로만 읽히게 쓴다
       (같은 시험에서 두 뜻으로 읽히는 문장이 틀림을 낳음).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.assistant import basis as B
from src.assistant.catalog import BY_ID, READY_IDS
from src.assistant.data_source import DongData
from src.assistant.slots import Slots

MAX_DONGS = 4
MORE_DONGS = 25  # 다섯째 동부터는 요약 줄로 — 한 지역 동 수(춘천 25곳)까지
# 【기능】 위기 상담 전화(국가 공식 번호, 24시간) — 지원 기관 서가가 늘 준다(10-15)
CRISIS_LINES = (
    "위기 상담 전화(24시간): 정신건강 위기상담 1577-0199. 생명이 위험한 급한 상황은 119 · 112"
)

# 【기능】 답에 나오는 말의 뜻. '그게 무슨 뜻이에요?'에 답할 때 쓴다(자료 설명 주제)
# 【기능】 취약 돌보미 동 순위(공개 모드) 기준 — big-contest src/bigcon/rank_v2.py 머리말
PRIORITY_BASIS = {
    "강남구": (
        "순위 기준(공개 자료): ① 혼자 사는 어르신 몫(65세 이상 1인세대 ÷ 65세 이상 주민)과 "
        "60세 이상 여성이 낮에 동네에서 보이는 정도(서울 생활인구)로 위험 구간 5개를 나누고, "
        "② 같은 구간 안에서는 동네에 있는 도움 거리(경로당 · 급식소 · 돌봄기관 · 약국 · 의원 등, "
        "65세 이상 1,000명당)가 적은 동을 앞에 둠. ③ 도움 거리 값까지 같으면 ①의 두 값을 "
        "지역 안 등수로 평균한 위험 값이 큰 동이 앞"
    ),
    "춘천시": (
        "순위 기준(공개 자료): ① 혼자 사는 어르신 몫(65세 이상 1인세대 ÷ 65세 이상 주민)으로 "
        "위험 구간 5개를 나누고, ② 같은 구간 안에서는 동네에 있는 도움 거리(경로당 · 급식소 · "
        "돌봄기관 · 약국 · 의원 등, 65세 이상 1,000명당)가 적은 동을 앞에 둠. "
        "③ 도움 거리 값까지 같으면 혼자 사는 어르신 몫이 큰 동이 앞. "
        "읍 · 면의 거리 · 버스는 순위를 매기는 값이 아니라 찾아가는 방법을 정할 때 봄"
    ),
}

# 【판단】 10-20 페르소나 o04 r5 T8 · T9: '리 단위는 안 되고 면 단위까지만 되는 거죠?'에 '면 단위
#        자료도 나오지 않아요'(틀린 말 — 북산면 숫자를 앞에서 줬다). '동 단위'라는 말만 보고 면을
#        뺐다. 단위를 사실 줄로 준다
UNIT_LINE = (
    "읍면동 — 강남구 22개 동, 춘천시 25개 읍면동(신북읍 · 동면 · 북산면 같은 "
    "읍 · 면도 동과 같은 단위라 숫자가 다 있음). 리(마을)는 사람 수가 없고 집 · 비탈 · 약국 "
    "거리처럼 일부 자료만 마을마다 있음. 통 · 반 · 아파트 단지는 자료가 없음"
)

GLOSSARY: tuple[tuple[str, str], ...] = (
    ("자료의 단위", UNIT_LINE),
    (
        "1인세대 단위",
        # 10-28 페르소나 p05_a T2: 이 줄을 보고 '1인세대 수가 곧 혼자 사는 사람 수예요'(틀림)
        "1인세대는 주민등록에 한 사람만 올라 있는 세대라 세대 수와 사람 수가 같다(취약 돌보미는 "
        "'명'으로 적는다). 다만 실제로 혼자 사는 사람 수와는 다르다 — 요양시설에 들어간 분 · "
        "주소만 둔 분도 1인세대로 잡히고, 실제로 혼자 사는 사람 수는 따로 어림한 값"
        "(실제 1인 가구 어림)을 본다",
    ),
    (
        "표 파일 받기",
        "표를 엑셀 · CSV로 달라고 하면 답 아래에 '엑셀 내려받기 · CSV 내려받기' 링크가 "
        "붙는다(화면)",
    ),
    (
        "긴 연휴 카드",
        "공휴일이 낀 3일 이상 연휴가 오면 1주 전부터 오늘 챙길 일 카드가 섬(특일 정보 2025 · 2026, "
        "한국천문연구원). 성탄절 · 새해 · 설도 3일 이상 이어지면 같은 기준",
    ),
    (
        "취약 돌보미 동 순위",
        # 10-27 밤 페르소나 s02 T7 · T8: 이 줄('외출 모습')과 춘천 순위 기준(외출 없음)이 달라
        #        춘천 담당자에게 '들어간다 · 안 들어간다'를 오갔다 → 지역마다 나눠 적는다
        "먼저 볼 동을 매긴 순서, 1위가 가장 먼저 볼 동. 강남구는 혼자 사는 어르신 몫 · "
        "낮에 동네에서 보이는 60세 이상 여성 정도(외출 모습, 서울 생활인구) · "
        "갈 곳(도움 거리)으로, 춘천시는 "
        "혼자 사는 어르신 몫 · 갈 곳(도움 거리)으로 매김. 춘천에는 "
        "생활인구 자료가 없어 외출 모습은 넣지 않음. 읍 · 면의 거리 · 버스는 순위가 아니라 "
        "찾아가는 방법을 정할 때 봄",
    ),
    (
        "다시 매긴 순위",
        "순위에 넣는 혼자 사는 분 수를 주민등록 1인세대 대신 실제 1인 가구 어림으로 "
        "바꿔 동 순위를 다시 매긴 것. "
        "주민등록이 혼자 사는 분을 실제보다 많이 · 적게 세는지 볼 수 있음",
    ),
    (
        "진단",
        "고립 가능성을 보여 주는 공개 자료 신호 몇 가지 중 몇 가지가 이 동에 해당하는지. "
        "높음 · 보통 · 낮음으로 적음. 순위와는 다른 것",
    ),
    (
        "실제로 혼자 사는 65세 이상 어림",
        "강남구 · 춘천시 전체의 실제 값(통계청 인구총조사 등록센서스, 65세 이상 1인 가구, "
        "가장 새 해)을 동마다 나눈 어림. 나누는 법은 둘이고 그 범위로 말함: ① 동의 주민등록 "
        "65세 이상 1인세대 비중대로 ② ①에 동마다 '주민등록과 실제의 차이'(2024 인구총조사 "
        "1인 가구 ÷ 2024-10 주민등록 1인세대, 모든 나이)를 곱해서. "
        "주민등록 1인세대와 세는 방식이 달라 수가 다름",
    ),
    (
        "거의 집에만 있는 청년 어림",
        "전국 조사인 청년의 삶 실태조사 2024의 나이별 비율을 "
        "이 동 청년 나이 구성에 맞춰 곱한 어림. 실제로 센 수가 아님",
    ),
    (
        "서울시 독거노인 현황",
        "서울시가 따로 세는 독거노인 수. 주민등록과 세는 방식이 달라 수가 다르고 "
        "2022년에 구 전체가 한 번에 24% 뛰었음",
    ),
    ("30년 넘은 계단 집", "건축물대장에서 승강기 없는 3~5층, 30년 넘은 주거 건물의 가구"),
    (
        "갈 곳 적음",
        "어르신 1,000명당 공공 자원(경로당 · 복지관 등)과 생활 접점(약국 · 의원 등)이 "
        "지역 안에서 적은 편이라는 신호",
    ),
    (
        "재가 장기요양기관",
        "장기요양 등급을 받은 분의 집으로 오거나(방문요양 · 방문목욕 · 방문간호) "
        "낮에 다니는(주야간보호) 돌봄을 하는 기관",
    ),
    ("입소 시설", "요양원(노인요양시설) · 노인요양공동생활가정처럼 들어가 사는 장기요양 시설"),
    ("직선거리", "지도에서 두 곳을 곧게 이은 거리. 실제 길로 가면 더 멂"),
    (
        "취약 돌보미 판단 · 조건 · 겹 · 겹침 · 겹친 걱정 · 구조 걱정 · 닥친 걱정",
        "사람 · 집 · 동네 · 안전망 · 지난 날씨 · 앞으로 날씨 · 달력 · 땅(겹)마다 공개 자료로 "
        "조건을 계산하고, 같은 지역 동들 가운데 위쪽 3분의 1이거나 정한 기준을 넘으면 '해당'. "
        "겹침마다 정한 조건 무리(예: 큰비 = 궂은 비 + 지하층 · 침수 · 비탈 + 혼자 사시는 분)가 "
        "모두 맞고 그 조건들이 서로 다른 겹 3가지 이상이면 '겹친 걱정'(겹침). 겹이 여럿이어도 "
        "정한 모양에 맞지 않으면 겹친 걱정이 아님. 먼저 볼 동 순위와는 다른 것",
    ),
    # 10-28 재심사 q05_b(노인일자리 담당) '「많음」은 어떤 기준으로 나눈 건지': 이 말뜻이 없어
    #        '많음 · 적음은 자료에 기준이 없다'(틀림)
    (
        "많음 · 적음 · 많은 편 · 적은 편 · 기준 · 컷오프",
        "같은 지역 동들 가운데 그 값의 등수가 위쪽 3분의 1(올림 — 강남 22곳 중 8번째까지 · 춘천 "
        "25곳 중 9번째까지)이면 '많음', 아래쪽 3분의 1이면 '적음'. 정해 둔 숫자(몇 명 · 몇 %) "
        "컷오프가 아니라 등수로 나눈 상대 기준이고, 평균이나 가운데값으로 나누지 않는다. 여러 조건 "
        "계산과 취약 돌보미 판단의 조건이 같은 잣대",
    ),
)


@dataclass
class Facts:
    title: str
    lines: list[str] = field(default_factory=list)
    # 【기능】 (이름, 앞, 뒤) — 답 검사에서 늘었다 · 줄었다를 반대로 쓰지 않았는지 본다
    compares: list[tuple[str, float, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # 【기능】 다룬 질문 기록에 남길 핵심 한 줄(엔진이 LogEntry.note 로 저장)
    memo: str = ""
    # 【기능】 글쓴이 지시문을 고르는 표시('outlook' = 취약 돌보미 판단, writer.OUTLOOK_SYSTEM)
    style: str = ""
    # 【기능】 앞 턴에서 짧게 달라고 했음(엔진이 표시) — 근거 꼬리를 한 줄로(outlook_text.render)
    brief: bool = False
    # 【기능】 이 세션에서 '근거 보여 줘' 안내를 이미 했음(엔진이 표시) — 다시 붙이지 않는다
    #        (10-27 밤)
    tail_shown: bool = False

    @property
    def text(self) -> str:
        return "\n".join(self.lines + self.notes)

    @property
    def status(self) -> str:
        """자료 상태 — '있음' · '일부' · '없음'(코드가 정해 글쓴이에게 넘긴다).

        【판단】 10-26 멘토 답 1: 자료가 있는지는 코드가 상태값으로 확정해 넘기고, AI에게는
               '있음이면 없다고 하지 않는다'는 규칙만 준다. 줄이 다 '자료에 없음 · 모름'이면
               없음, 몇 줄만 그러면 일부, 아니면 있음. 동 머리줄('[강남구 수서동]')은 세지 않는다
        """
        body = [ln for ln in self.lines if not _HEAD_LINE.match(ln.strip())]
        if not body:
            return "없음"
        missing = sum(1 for ln in body if MISSING_MARK.search(ln))
        if missing == len(body):
            return "없음"
        return "일부" if missing else "있음"


# 【기능】 자료 줄이 '이 자료에는 없다'고 적은 표시(Facts.status).
#        시설이 0곳인 것은 사실이라 넣지 않는다
MISSING_MARK = re.compile(r"자료에 없|자료가 없|찾지 못|담지 않|모름|아직 없음|연결 전")
_HEAD_LINE = re.compile(r"^\[[^\]]+\]$")


def trend(before: float, after: float, unit: str = "명") -> str:
    d = after - before
    if d == 0:
        return f"{before:,}{unit} → {after:,}{unit}(같음)"
    word = "늘었음" if d > 0 else "줄었음"
    pct = f", {abs(d) / before:.0%}" if before else ""
    return f"{before:,}{unit} → {after:,}{unit}({abs(d):,}{unit} {word}{pct})"


def _age_note(slots: Slots) -> str | None:
    """자료가 가진 나이 구간과 다른 구간을 물었을 때 덧붙이는 말.

    【판단】 '자료가 없어서'로 끝내지 않고, 이 자료의 구간으로 답한다고 밝힌다.
    """
    a = slots.ages
    if a is None:
        return None
    if (a.lo, a.hi) in ((65, None), (80, None), (19, 34), (19, 24), (25, 29), (30, 34)):
        return None
    return (
        "이 자료의 나이 구간은 어르신 65세 이상 · 80세 이상, "
        "청년 19~34세(19~24 · 25~29 · 30~34세)예요. "
        "그 구간으로 말씀드릴게요"
    )


BAND_WORD = {
    5: "가장 위험한 구간",
    4: "위험 높은 구간",
    3: "중간 구간",
    2: "낮은 구간",
    1: "가장 낮은 구간",
}


def _people(data: DongData, name: str) -> dict:
    """그 동의 주민등록 사람 수(people.json) — 몫을 어디서나 같은 셈으로(10-25)."""
    people = data.people() if hasattr(data, "people") else {}
    return ((people or {}).get("dongs") or {}).get(name) or {}


def _rank_why(d: dict) -> str:
    """순위의 까닭 — 위험 구간과 그 재료, 같은 구간 안의 도움 거리(동 순위 v2 그대로).

    【판단】 10-20 페르소나 f02 r4 T1 ~ T2: '왜 2위인지 한 줄씩'에 글쓴이가 순위를 되풀이하거나
           '도움 거리가 가장 적은 동'을 지어냈다(까닭 자료가 없었음). big-contest rank_v2의 구간 ·
           몫 · 자원 값을 동 자료에 실어 사서가 적는다
    """
    r = d.get("rank") or {}
    if "band" not in r:
        return ""
    # 10-28 페르소나 p05_a r2 T3: '4구간'을 '위에서 4번째'로 풀어 위험 방향을 거꾸로 말함
    #        → 5가 가장 위험한 쪽이라는 것을 줄에 적는다
    bits = [
        f"위험 구간은 5구간 중 {r['band']}구간({BAND_WORD.get(r['band'], '')}, "
        "5구간이 가장 위험하고 1구간이 가장 덜 위험)"
    ]
    why = []
    # 10-25 페르소나 cli3 오린 T8: 순위 자료의 0.205를 '20%'로, 표 · 사람 수 줄은 716 ÷ 3,486을
    #        '21%'로 적어 같은 몫이 둘로 나왔다 → 사람 수 자료가 있으면 같은 셈(반올림)으로
    p = d.get("_p") or {}
    if p.get("pop65") and p.get("solo65") is not None:
        why.append(f"65세 이상 가운데 혼자 사는 몫 {round(p['solo65'] / p['pop65'] * 100)}%")
    elif r.get("alone_sh") is not None:
        why.append(f"65세 이상 가운데 혼자 사는 몫 {r['alone_sh']:.0%}")
    if r.get("vis") is not None:
        why.append(
            f"낮에 동네에서 보이는 60세 이상 여성 정도 {r['vis']:.2f}"
            "(1이 주민 몫 그대로, 낮을수록 걱정)"
        )
    if why:
        bits[0] += " — 재료는 " + " · ".join(why)
    if r.get("gap") is not None:
        few = r["gap"] >= 0.5
        res = []
        if r.get("public_pk") is not None:
            res.append(f"경로당 · 급식소 · 돌봄기관 같은 공공 자원 {r['public_pk']:.1f}곳")
        if r.get("daily_pk") is not None:
            res.append(f"약국 · 의원 · 가게 같은 생활 접점 {r['daily_pk']:.1f}곳")
        # 10-20 페르소나 o01 r9 T6 ~ T7: '사북면이 공공 자원이 더 적은데 왜 북산면이 앞인가'
        #        — 같은 구간 안의 차례는 두 값을 각각 지역 안 등수로 매겨 평균한 '자원 공백'
        #        (rank_v2: 1 − 등수 평균, 클수록 자원이 없음)이라 한 값만 보면 달라 보인다
        bits.append(
            f"같은 구간 안에서는 자원 공백 {r['gap']:.2f}(1에 가까울수록 자원이 없음)이 "
            "큰 동이 앞. "
            f"자원 공백은 65세 이상 1,000명당 {' · '.join(res)}를 각각 지역 안 등수로 매겨 평균한 "
            f"것이라 한 값(공공 자원만)만 견주면 차례가 달라 보일 수 있음. "
            f"이 동은 자원이 {'적은' if few else '많은'} 편"
        )
    if r.get("care_why") and ("km" in r["care_why"] or "버스" in r["care_why"]):
        bits.append(f"읍 · 면은 거리 · 버스로 봄: {r['care_why']}")
    return "순위 까닭: " + ". ".join(bits)


def _rank(name: str, d: dict) -> list[str]:
    r = d["rank"]
    s = f"취약 돌보미 동 순위: {d['region']} {r['of']}곳 중 {r['now']}위(1위가 가장 먼저 볼 동)"
    if r["fix"] != r["now"]:
        more = "많이" if r["fix"] > r["now"] else "적게"
        s += (
            f". 혼자 사는 분 수를 실제 1인 가구 어림으로 바꿔 동 순위를 다시 매기면 {r['fix']}위"
            f"(주민등록이 이 동에서 혼자 사는 분을 실제보다 {more} 셈)"
        )
    else:
        # 【판단】 10-15: 같을 때도 말할 거리가 있어야 '다시 매기면 몇 위?'에 답한다
        s += f". 혼자 사는 분 수를 실제 1인 가구 어림으로 바꿔 다시 매겨도 {r['now']}위로 같음"
    why = _rank_why(d)
    return [s, why] if why else [s]


# 진단이 보는 신호 이름(big-contest diagnose_dong.OLD_CHECKS · diagnose_chuncheon.CHECKS 차례)
# — 10-20 페르소나 f01 r10 T4 ~ T6: '5가지 중 해당하지 않은 둘은 무엇인지'에 '자료에 없어요'
DIAG_SIGNALS = {
    "강남구": (
        "외출·연락이 모두 적은 어르신 · 겨울 들어 외출·연락이 적은 어르신이 더 늘어남 · "
        "아예 안 나오는 어르신 많음 · 혼자 사는 비율 · 독거노인이 기초수급·저소득 명단에 없음 · "
        "갈 곳 적음 · 독거노인 2년 새 빠르게 늘어남 · 계단만 있는 오래된 집"
    ),
    "춘천시": (
        "혼자 사는 비율 · 혼자 사는 80세 이상이 많음 · 나이 든 동네(80세 이상 주민 몫) · "
        "갈 곳이 멀거나 적음 · 버스가 드묾"
    ),
}


def _diag(d: dict) -> list[str]:
    g = d.get("diag")
    if not g:
        return []
    sig = " / ".join(g["signals"]) or "해당 없음"
    out = [
        f"진단: 고립 가능성 신호 {g['of']}가지 중 {g['n']}가지 해당(진단 {g['level']}). "
        f"해당 신호: {sig}"
    ]
    names = DIAG_SIGNALS.get(d.get("region") or "")
    if names:
        out.append(
            f"진단이 본 신호 {g['of']}가지 이름: {names}(위 '해당 신호'에 없는 것이 해당하지 않은 "
            "신호. 모두 65세 이상 어르신 기준이고 청년 지표는 없음)"
        )
    return out


def _solo(d: dict, f: Facts) -> list[str]:
    out = []
    s = d.get("solo65")
    if s:
        pm = B.months(s)
        if pm:
            a, b = s[pm[0]], s[pm[1]]
            out.append(f"65세 이상 1인세대(주민등록): {pm[0]} → {pm[1]} {trend(a, b)}")
            f.compares.append(("65세 이상 1인세대", a, b))
    s80 = d.get("solo80")
    if s80:
        out.append(f"80세 이상 1인세대(주민등록 {B.reg()}): {s80['n']:,}명")
        if s80["care_cap"]:
            out.append(f"노인복지시설 정원: {s80['care_cap']:,}명")
        if s80["fac_mix"]:
            out.append(
                "정원이 80세 이상 1인세대의 30% 이상이라 1인세대에 시설 입소자가 섞여 있을 수 있음"
            )
    e = d.get("solo65_est")
    if e:
        out.append(
            f"실제로 혼자 사는 65세 이상 어림: 약 {e['lo']:,}~{e['hi']:,}명"
            f"({d.get('region') or '구 · 시'} 전체 실제 값(인구총조사 등록센서스)을 "
            "동마다 나눈 어림, 나누는 법은 말뜻 '실제로 혼자 사는 65세 이상 어림')"
        )
    return out


def _region_rank(data: DongData, name: str, who: str) -> list[str]:
    """그 동이 지역 안에서 몇 위인지(많은 순) — 혼자 사는 수 · 몫(주민등록, people.json).

    【판단】 10-26 예상 질문 2-4 '개포3동에서 혼자 사는 어르신이랑 청년이 둘 다 많아요?': 동 하나의
           숫자만 있어 '강남구 안에서 많은 편인지 비교하지 못해요'라고 답했다. 등수는 코드가 센다
    """
    rows = (data.people() or {}).get("dongs") or {}
    me = rows.get(name) or {}
    region = me.get("region")
    if not region:
        return []
    mates = {n: r for n, r in rows.items() if r.get("region") == region}
    keys = (
        (
            ("solo65", None, "65세 이상 1인세대"),
            ("solo65", "pop65", "65세 이상 중 혼자 사는 몫"),
            ("solo80", None, "80세 이상 1인세대"),
        )
        if who == "어르신"
        else (
            ("solo_youth", None, "청년 1인세대"),
            ("solo_youth", "pop_youth", "청년 중 혼자 사는 몫"),
        )
    )
    out = []
    for num, den, word in keys:

        def val(r: dict, num: str = num, den: str | None = den) -> float | None:
            if r.get(num) is None or (den and not r.get(den)):
                return None
            return r[num] / r[den] if den else r[num]

        mine = val(me)
        vals = [v for v in (val(r) for r in mates.values()) if v is not None]
        if mine is None or len(vals) < 2:
            continue
        out.append(f"{word} {1 + sum(v > mine for v in vals)}위")
    if not out:
        return []
    return [f"{region} {len(mates)}곳 중 많은 순(주민등록 {B.reg()}): " + " · ".join(out)]


def _share(data: DongData, name: str) -> list[str]:
    """65세 · 80세 이상 주민 수와 그중 혼자 사는 몫(주민등록, people.json — 취약 돌보미 판단과 같은
    숫자).

    【판단】 10-20 페르소나 o04 r5 T4 · T5: 판단 답에서 '44%'를 보고 '사북면은 비율이 없다 ·
           65세 이상 주민 수가 자료에 없다'는 답을 받았다(현황 주제에 몫 줄이 없었음). 있는 숫자다
    """
    r = ((data.people() or {}).get("dongs") or {}).get(name) or {}
    out = []
    # 10-20 페르소나 o01 r3: '전 연령 주민 수는 자료에 없다'더니 표에는 928명 — 현황에도 준다
    if r.get("residents"):
        out.append(f"주민(모든 나이) {r['residents']:,}명(주민등록 {B.reg()})")
    # 10-20 페르소나 h02 r7: '시설 입소자를 뺀 숫자인가 · 1년 전 판도 같은 기준인가'에
    #        '자료에 없어요'
    out.append(
        "1인세대 수는 주민등록에 혼자 한 세대로 올라 있는 사람 수 그대로이고, "
        "요양시설 입소자를 따로 빼지 "
        "않음(10-04 팀장: 빼지 않고 표시만). 1년 전 판도 같은 기준(같은 나이 · 같은 셈)"
    )
    for age, solo, pop in (("65", "solo65", "pop65"), ("80", "solo80", "pop80")):
        if r.get(pop) and r.get(solo) is not None:
            out.append(
                f"{age}세 이상 주민 {r[pop]:,}명 중 혼자 사는 분(1인세대) {r[solo]:,}명, "
                f"{round(r[solo] / r[pop] * 100)}%(주민등록 {B.reg()})"
            )
    # 10-20 페르소나 o01 r8: 첫 답에서 '전체 주민 928명 중 26%'를 스스로 내놓고 뒤에 '26%는
    #        자료에 없어 확인할 수 없다' — 분모가 다른 몫도 사서가 적어 둔다
    if r.get("residents") and r.get("solo65") is not None and r.get("pop65"):
        out.append(
            f"주민(모든 나이) {r['residents']:,}명 중 65세 이상 1인세대 {r['solo65']:,}명은 "
            f"{round(r['solo65'] / r['residents'] * 100)}%(분모가 전체 주민일 때. "
            f"65세 이상 주민 중 몫 {round(r['solo65'] / r['pop65'] * 100)}%와 분모가 다름)"
        )
    return out


def _sum_halls(data: DongData, names: list[str]) -> list[str]:
    """물은 동들의 경로당 · 마을회관 수 합(가장 최근 자료) — 코드가 더한다.

    【판단】 10-29 변수 시험 c01_097 '개포1 · 2 · 3동 경로당 total 숫자 하나만, 최신 기준으로':
           글쓴이가 넓이 자료(2022, 그때 곳 수)로 3 + 6 + 4 = 13을 직접 더했다(최신 2025-06은 22)
    """
    got = [(n, data.places(n)) for n in names]
    if not all(p and (p.get("halls") or {}).get("list") is not None for _, p in got):
        return []
    total = sum(len(p["halls"]["list"]) for _, p in got)
    srcs = " · ".join(dict.fromkeys(HALL_SRC.get(p["halls"].get("src"), "") for _, p in got))
    return [
        f"[{' · '.join(names)} 합계] 경로당 · 마을회관 {total}곳"
        f"({srcs}, 가장 최근 자료, 코드가 더함)"
    ]


def _sum_rows(data: DongData, names: list[str]) -> list[str]:
    """물은 동들의 합계(주민등록) — 코드가 더한다.

    【판단】 10-20 페르소나 o01 r2: '북산면 · 사북면 합하면 695 · 1,730명 · 40.2% 맞습니까?'에
           '두 면 합계는 자료에 없어요'(글쓴이는 숫자를 만들지 않는다). 합계는 사서가 센다
    """
    rows = [((data.people() or {}).get("dongs") or {}).get(n) or {} for n in names]
    if not all(r.get("solo65") is not None and r.get("pop65") for r in rows):
        return []
    solo, pop = sum(r["solo65"] for r in rows), sum(r["pop65"] for r in rows)
    return [
        f"[{' · '.join(names)} 합계] 65세 이상 1인세대 {solo:,}명, 65세 이상 주민 {pop:,}명 중 "
        f"{round(solo / pop * 100)}%(주민등록 {B.reg()}, 코드가 더함)"
    ]


def _youth_trend(data: DongData, name: str) -> list[str]:
    """청년 1인세대 1년 새 · 청년 중 1인세대 몫(주민등록, people.json).

    【판단】 10-20 페르소나 h02(구청 청년정책) r8: '역삼1동 청년 1인세대 1년 전과 비교'에 '2025-09
           자료는 없어요'(틀린 말 — 8,229 → 7,819명). 몫은 '전체 중 혼자'의 순서로 적어 둔다
           (글쓴이가 '3,638명 중 4,736명'처럼 거꾸로 쓴 일)
    """
    r = ((data.people() or {}).get("dongs") or {}).get(name) or {}
    out = []
    a, b = r.get("solo_youth_prev"), r.get("solo_youth")
    if a is not None and b is not None:
        out.append(
            f"청년 1인세대(주민등록): {B.reg_prev()} → {B.reg()} {trend(a, b)}"
            "(두 판 모두 19~34세 · 주민등록 1인세대 그대로, 같은 기준)"
        )
    if b is not None and r.get("pop_youth"):
        out.append(
            f"청년(19~34세) 주민 {r['pop_youth']:,}명 중 1인세대 {b:,}명, "
            f"{round(b / r['pop_youth'] * 100)}%(주민등록 {B.reg()})"
        )
    return out


VILLAGE_HOME_SHOWN = 5


def _village_homes(data: DongData, name: str) -> list[str]:
    """읍면의 마을(리)별 집 — 눈 무게에 약한 지붕 · 지하층 · 오래된 집(focus.json, 건축물대장).

    【판단】 10-20 페르소나 h01(신북읍) r8: '약한 지붕 914채 어느 마을이야?'에 '마을별 채수는 확인할
           수 없어요'(틀린 말 — 마을마다 있음, 카드는 이미 마을 이름을 씀)
    """
    fv = data.focus(name) if hasattr(data, "focus") else None
    villages = (fv or {}).get("villages") or []
    if not villages:
        return []
    out = []
    for key, word in (
        ("weak_roof", "눈 무게에 약한 지붕(슬레이트 · 함석 · 판넬 · 초가) 집"),
        ("basement_old", "지하층이 있는 오래된 저층 집(어림)"),
        ("old_homes", "1995년 이전 집"),
    ):
        got = sorted(
            ((v["name"], int(v.get(key) or 0)) for v in villages if v.get(key)),
            key=lambda t: -t[1],
        )
        if got:
            shown = " · ".join(f"{n} {k:,}채" for n, k in got[:VILLAGE_HOME_SHOWN])
            rest = len(got) - VILLAGE_HOME_SHOWN
            total = sum(k for _, k in got)
            out.append(
                f"마을(리)별 {word}: {shown}{f' 외 {rest}개 마을' if rest > 0 else ''}"
                f"(건축물대장, 마을 {len(villages)}곳 중 있는 곳 {len(got)}곳) — "
                f"{name} 전체 {total:,}채(마을 합, 코드가 더함)"
            )
    return out


def _seoul(d: dict, f: Facts) -> list[str]:
    sd = d.get("seoul_lonely")
    if not sd:
        return []
    pm = B.months(d.get("solo65"))
    reg = d["solo65"][pm[1]] if pm else None
    vs = ""
    if reg is not None:
        cmp = "많음" if sd["2025"] > reg else "적음" if sd["2025"] < reg else "같음"
        vs = f"(이 동은 주민등록 {pm[1]} 65세 이상 1인세대 {reg:,}명보다 {cmp})"
    f.compares.append(("서울시 독거노인 2023 → 2025", sd["2023"], sd["2025"]))
    return [
        f"서울시 독거노인 현황: 2023년 → 2025년 {trend(sd['2023'], sd['2025'])}",
        f"서울시 현황은 세는 방식이 주민등록과 달라 사람 수가 다름{vs}. "
        "2022년에 구 전체가 한 번에 24% 뛰어 해마다 견줄 때 주의",
    ] + _seoul_kind(d, f)


def _seoul_kind(d: dict, f: Facts) -> list[str]:
    """서울시 독거노인 현황의 수급권자 · 저소득 · 일반과 80세 이상(10-14).

    【판단】 강남은 동별 기초생활수급자 전체 숫자가 없다. 서울시 현황은 독거노인을 국민기초생활보장
           수급권자 · 저소득노인 · 일반(둘 다 아님)으로 나눠 센다 — '수급권자 독거노인'이라고 이름을
           그대로 밝힌다(전체 수급자로 읽히지 않게). 늘었나 · 비율은 코드가 셈
    """
    k = d.get("seoul_lonely_kind")
    if not k:
        return []
    a, b = k["2024"], k["2025"]
    total = sum(b.values())
    f.compares.append(("수급권자 독거노인 2024 → 2025", a["수급"], b["수급"]))
    f.compares.append(("80세 이상 독거노인 2024 → 2025", k["80+"]["2024"], k["80+"]["2025"]))
    return [
        f"서울시 독거노인 2025년 {total:,}명 중 기초생활수급권자 {b['수급']:,}명 · "
        f"저소득 {b['저소득']:,}명 · 일반(수급권자 · 저소득 어디에도 없음) {b['일반']:,}명"
        f"(일반이 {round(b['일반'] / total * 100)}%)",
        f"수급권자 독거노인 2024년 → 2025년 {trend(a['수급'], b['수급'])}",
        f"2024년은 수급권자 {a['수급']:,}명 · 저소득 {a['저소득']:,}명 · 일반 {a['일반']:,}명",
        f"80세 이상 독거노인 2024년 → 2025년 {trend(k['80+']['2024'], k['80+']['2025'])}, "
        f"2025년 그중 수급권자 {k['80+']['2025_수급']:,}명",
    ]


SEX_WORD = {"여": "여성(할머니)", "남": "남성(할아버지)"}


def _seoul_sex(d: dict, slots: Slots, f: Facts) -> list[str]:
    """서울시 독거노인 현황의 남 · 여(강남만, 10-14).

    【판단】 주민등록 1인세대는 성별로 나뉘어 있지 않다. 성별을 물으면(할머니 · 할아버지)
           이 현황의 성별 숫자를 앞에 둔다. 세는 방식이 주민등록과 달라 사람 수가 다르다는 것은
           _seoul 이 밝힌다
    """
    x = d.get("seoul_lonely_sex")
    if not x or slots.sex not in SEX_WORD:
        return []
    sx = slots.sex
    other = "남" if sx == "여" else "여"
    a, b = x["2024"][sx], x["2025"][sx]
    f.compares.append((f"서울시 독거노인 {SEX_WORD[sx]} 2024 → 2025", a, b))
    return [
        f"서울시 독거노인 현황 {SEX_WORD[sx]}: 2024년 → 2025년 {trend(a, b)}"
        f"(2025년 {SEX_WORD[other]}은 {x['2025'][other]:,}명)",
        f"2025년 {SEX_WORD[sx]} 독거노인 중 기초생활수급권자 {x['2025']['수급_' + sx]:,}명",
    ]


def _residents(d: dict) -> list[str]:
    """주민 수(주민등록, big-contest build_chuncheon_local).

    10-12 청년 60턴 T40: '주민이 몇 명인데요?'에 동 상황 서가로 가서 '없다'고 했다
    (주민 수가 수급자 서가에만 있었음).

    【판단】 10-19: 주민 수는 주민등록 가장 새 판(2026-09)인데 '2024년, 수급자 자료의 주민'이라고
           적혀 있었다(수급자 해를 붙임). 판을 바로 적는다
    """
    n = d.get("residents")
    if not n:
        return []
    return [f"주민 수: {n:,}명(주민등록 {B.reg()})"]


def _youth(d: dict) -> list[str]:
    y = d.get("youth")
    if not y:
        return []
    b = y["bands"]
    out = [
        f"청년(19~34세, 주민등록 {B.reg()}): {y['total']:,}명"
        f"(19~24세 {b['19-24']:,}명 · 25~29세 {b['25-29']:,}명 · 30~34세 {b['30-34']:,}명), "
        f"그중 1인세대 {y['solo']:,}명"
    ]
    h = y.get("homebound")
    if h and h.get("under10"):
        out.append("거의 집에만 있는 청년 어림: 10명 미만")
    elif h:
        # 10-25 노엘: '전국 나이별 비율 × 이 동 나이 구성'은 실제 계산과 달랐다(바로잡음)
        out.append(
            f"거의 집에만 있는 청년 어림: 약 {h['lo']:,}~{h['hi']:,}명"
            f"(100명에 {h['per100_lo']}~{h['per100_hi']}명꼴, "
            "구 전체 어림(시도 비율 ~ 전국 비율)을 "
            "이 동의 나이 구성 · 청년 1인세대 몫으로 나눈 어림, 실제로 센 수 아님)"
        )
    return out


# 어림의 방법 · 근거를 묻는 말(10-25)
METHOD_ASK = re.compile(
    r"계산|방법|근거|출처|비율|산식|공식|어떻게 (?:냈|구했|셌|나온)|어디서 나온"
)


def _youth_method(data: DongData, regions: list[str]) -> list[str]:
    """거의 집에만 있는 청년 어림의 방법 — 실제 계산(big-contest youth.dong_estimates)에 쓴 숫자."""
    m = data.youth_method() if hasattr(data, "youth_method") else {}
    if not m:
        return []
    a = m["alone"]
    out = [
        "[거의 집에만 있는 청년 어림 — 방법(실제 계산에 쓴 숫자)]",
        "- 나이 구간별 '거의 집에만 있는 청년' 비율(전국, 청년의 삶 실태조사 2024): "
        + " · ".join(f"{k} {v}%" for k, v in m["band_rate"].items())
        + f" · 전체 {m['all_rate']}%(임신 · 출산 · 장애가 섞인 값)",
        f"- 전국 발표 비율 {m['national_rate']}%(임신 · 출산 · 장애 제외)",
    ]
    for r in regions:
        x = (m.get("regions") or {}).get(r)
        if x:
            unit = (
                "구" if r.endswith("구") else "시"
            )  # 춘천시를 '구 전체'라 했다(10-29 브라우저 시험)
            out.append(
                f"- {r} {unit} 전체 어림: 청년 {x['youth']:,}명에 "
                f"{x['sido']} 비율 {x['sido_rate_net']}%"
                f"({x['sido_rate']}%에서 임신 · 출산 · 장애 몫 {x['minus_share']}%를 뺌)을 곱하면 "
                f"약 {x['by_sido']:,}명, 전국 {m['national_rate']}%를 곱하면 "
                f"약 {x['by_national']:,}명 "
                f"→ {unit} 전체 약 {x['lo']:,}~{x['hi']:,}명"
            )
    out.append(
        "- 동마다 나누기: 동의 나이 구간별 청년 수 × 나이 구간별 비율(전체 대비) × "
        "청년 1인세대 몫 보정"
        f"(은둔 청년 중 혼자 사는 비율 {a['hidden']}% · 전체 청년 {a['all']}% → 배수 {a['factor']})"
        "을 무게로 구 전체 어림을 나눔. 실제로 센 수가 아님"
    )
    out.append(f"- 출처: {m['rate_source']} / {m['national_source']} / {m['alone_source']}")
    return out


def _housing(d: dict) -> list[str]:
    h = d.get("housing")
    if not h:
        return []
    return [
        f"주거(건축물대장): 주거 가구 {h['res_units']:,}가구, "
        f"30년 넘은 계단 집(승강기 없는 3~5층) {h['old_walkup_units']:,}가구"
        f"({h['old_walkup_share']:.0%}), "
        f"지하층이 있는 30년 넘은 저층 주거 건물 {h['basement_old']:,}채"
    ]


def _hall(d: dict, p: dict | None) -> list[str]:
    """경로당 수 · 이름(두 지역, 가장 최근 자료)과 넓이(강남구만, 2022).

    【판단】 10-13: 수는 갈 곳 서가와 같은 자료
           (강남 서울시 2025-06 · 춘천 표준데이터 2025-07)로 센다.
           넓이 자료(2022)의 곳 수가 다르면 '그때 N곳'으로 해를 밝힌다(한 사실에 두 숫자가
           해 없이 나오지 않게). 그 전에는 강남만 답하고 춘천은 '강남구 자료만 있어요'라고 했다
    """
    out = []
    if p:
        halls = p["halls"]["list"]
        kinds = Counter(h["kind"] for h in halls)
        label = " · ".join(f"{k} {v}곳" for k, v in kinds.items()) or "경로당 0곳"
        names = " · ".join(h["name"] for h in halls)
        src = HALL_SRC.get(p["halls"]["src"], "")
        out.append(f"{label}({src})" + (f": {names}" if names else ""))
    h = d.get("senior_hall")
    if h:
        out.append(
            f"경로당 넓이(강남구 경로당 현황 {h['year']}, 그때 {h['halls']}곳 기준): "
            f"{h['area']:,}㎡, 65세 이상 100명당 {h['per100']}㎡(강남 평균 {h['avg_per100']}㎡)"
        )
    elif p:
        out.append("경로당 넓이 · 정원 · 회원 수를 동마다 적은 공개 자료는 없음")
    return out


def _empty_houses(d: dict) -> list[str]:
    """빈집 줄(춘천 읍면만 동마다) — 수급 묶음과 사는 집 묶음이 함께 쓴다.

    【판단】 10-29 회귀 춘천 청년 T27 '남산면은 빈집이 몇 채예요?': 데스크가 주제를 사는 집으로
           고르자(뜻으로는 맞음) 빈집 줄이 수급 묶음에만 있어 '빈집 수는 자료에 없다'(거짓)
    """
    e = d.get("empty_houses")
    if e:
        return [f"빈집: {e['n']}채(춘천시 빈집 현황 {e['date']})"]
    if d.get("region") == "춘천시":
        # 【판단】 10-19 100턴 T30: 1위가 효자2동(동 지역)으로 바뀌자 '빈집도 있어요?'에 빈집 말이
        #        빠졌다. 춘천시 빈집 현황은 읍면만 동마다 나뉘고 시내는 법정동 이름이라 행정동으로
        #        가르지 못했다(big-contest build_chuncheon_local). 없다고만 하지 않고 까닭을 밝힌다
        return [
            "빈집: 춘천시 빈집 현황(2025-10-31)은 읍면만 동마다 나뉘어 있고, 시내(동 지역)는 "
            "법정동 이름으로 적혀 있어 이 동으로 나눠 세지 못함"
        ]
    return []


def _livelihood(d: dict, f: Facts) -> list[str]:
    out = []
    lv = d.get("livelihood")
    if lv:
        out.append(
            f"기초생활수급자: 주민 {d.get('residents', 0):,}명 중 {lv['people']:,}명"
            f"({lv['households']:,}가구, {lv['year']}년), "
            f"주민 100명당 {lv['per100']}명으로 춘천 {lv['of']}곳 중 {lv['rank']}번째"
            f"(춘천 평균 {lv['city_per100']}명, 주민은 주민등록 {B.reg()})"
        )
        if lv.get("prev") is not None:
            out.append(
                f"수급자 {lv['year'] - 1}년 → {lv['year']}년 {trend(lv['prev'], lv['people'])}"
            )
            f.compares.append(("기초생활수급자", lv["prev"], lv["people"]))
    out += _empty_houses(d)
    if not lv and d.get("seoul_lonely_kind"):
        # 【판단】 강남(10-14): 동별 전체 수급자 숫자 대신 서울시 독거노인 현황의 수급권자 독거노인
        # 【판단】 '공개 자료가 없다'고 하지 않는다 — 서울통계에 동별 수급자 표(2020~2024)가
        #        있으나 이용 조건이 적힌 곳을 못 찾아 넣지 않았다(10-14).
        #        무엇으로 대신 보여 주는지만 밝힌다
        out.append(
            "강남구는 동별 전체 수급자 숫자 대신 서울시 독거노인 현황의 "
            "'기초생활수급권자 독거노인'(혼자 사는 65세 이상 중 수급권자)으로 봄"
        )
        out += _seoul_kind(d, f)
    return out + _solo_all(d, f)


def _solo_all(d: dict, f: Facts) -> list[str]:
    sa = d.get("solo_all")
    if not sa:
        return []
    f.compares.append(("1인세대 전체", sa["from"], sa["2025"]))
    return [
        f"1인세대 전체(모든 나이, 춘천시 자료): {sa['from_year']}년 → 2025년 "
        f"{trend(sa['from'], sa['2025'], '세대')}"
    ]


def _one_dong(
    topic: str, name: str, d: dict, slots: Slots, f: Facts, p: dict | None = None
) -> list[str]:
    if topic == "dong_overview":
        rows = _residents(d) + _rank(name, d) + _diag(d)
        elder = _solo(d, f) + _seoul(d, f)[:1]
        young = _youth(d)
        rows += young + elder if slots.target == "청년" else elder + young
        return rows
    if topic == "diagnosis":
        rows = _rank(name, d) + _diag(d)
        # 【판단】 '80세 이상 어르신은 몇 명?'에 데스크가 진단을 고르기도 한다(100턴 3 · 4차 T39).
        #        나이를 물었으면 진단 답에도 그 나이의 숫자를 넣어 '없다'고 답하지 않게 한다
        if slots.ages and slots.ages.lo is not None and slots.ages.lo >= 65:
            rows += _solo(d, f)
        return rows
    if topic == "solo_seniors":
        return _seoul_sex(d, slots, f) + _solo(d, f) + _seoul(d, f) + _solo_all(d, f)
    if topic == "seoul_lonely":
        sd = d.get("seoul_lonely") or {}
        series = " · ".join(f"{y}년 {n:,}명" for y, n in sorted(sd.items()))
        rows = _seoul_sex(d, slots, f) + _seoul(d, f)
        return rows + ([f"서울시 독거노인 현황 해마다: {series}"] if series else [])
    if topic == "youth":
        return _youth(d)
    if topic == "housing":
        return _housing(d)
    if topic == "senior_hall":
        return _hall(d, p)
    if topic == "livelihood":
        return _livelihood(d, f)
    return []


RANK_UNIT = {"senior_hall": "곳", "housing": "가구"}
HALL_RANK_NAME = {
    "강남구": "경로당 수(서울시 경로당 현황 2025-06)",
    "춘천시": "경로당 · 마을회관 수(전국마을회관및경로당 표준데이터 2025-07)",
}
LIVE_RANK_NAME = {
    "강남구": "기초생활수급권자 독거노인 수(서울시 독거노인 현황 2025, 전체 수급자 아님)",
    "춘천시": "기초생활수급자 수(춘천시 기초생활보장 수급권자 현황)",
}
HALL_SRC = {
    "seoul_halls": "서울시 경로당 현황 2025-06",
    "std_halls": "전국마을회관및경로당 표준데이터 2025-07",
}
_ADDR_HEAD = re.compile(r"^(서울특별시|서울|강원특별자치도|강원도|강원)\s*(강남구|춘천시)\s*")


def _tie_example(region: str, data: DongData) -> str:
    """순위 기준 ③의 예 — 지금 자료에서 구간 · 도움 거리 값이 같은 이웃 등수 둘(없으면 빈 글).

    【판단】 10-28 밤: 새벽에 '북산면 44% 2위 · 사북면 38% 3위'를 글에 박았다 → 자료를 새로 받으면
           틀린 말이 된다. 예는 그때 자료로 만든다
    """
    rows = []
    for r, name in data.ranked(region):
        k = (data.dong(name) or {}).get("rank") or {}
        if k.get("band") is not None and k.get("gap") is not None:
            rows.append((r, name, k["band"], round(k["gap"], 2), k.get("alone_sh")))
    for a, b in zip(rows, rows[1:], strict=False):
        if a[2] == b[2] and a[3] == b[3] and a[4] is not None and b[4] is not None:
            return (
                f"(지금 자료의 예: {a[1]} · {b[1]}은 둘 다 {a[2]}구간 · "
                f"도움 거리 값 {a[3]:.2f}이라 "
                f"몫 {a[4]:.0%}인 {a[1]}이 {a[0]}위, {b[4]:.0%}인 {b[1]}이 {b[0]}위)"
            )
    return ""


def _addr(a: str) -> str:
    return _ADDR_HEAD.sub("", a or "").strip()


def _unit(name: str) -> str:
    return name[-1] if name[-1:] in "면읍" else "동"


def _with(name: str, *parts: str) -> str:
    rest = ", ".join(p for p in parts if p)
    return f"{name}({rest})" if rest else name


def _nearest(what: str, n: dict | None, unit: str) -> str:
    if not n:
        return f"{what}: {unit} 안에 없음"
    return f"{what}: {unit} 안에 없음. 가장 가까운 곳 {n['name']}({n['dong']}, 직선 {n['km']}km)"


WEEK = ("월", "화", "수", "목", "금", "토", "일")
PHARMACY_SHOWN = 8
FAR_PHARM_KM = 5.0  # 카드 · 취약 돌보미 판단과 같은 기준(10-16 팀장 '약국으로부터 5KM 이상')
# '약국 먼 데는 어디' · '약국이 멀리 있는 마을'
FAR_ASK = re.compile(r"약국[^\n]{0,6}(?:먼|멀|거리)")
WEEKDAY_ASK = re.compile(r"([월화수목금토일])요일|주말")
HOLIDAY_ASK = re.compile(r"공휴일|빨간\s?날|명절|연휴")


def _hours(h: dict) -> str:
    """요일별 운영 시간을 묶어 한 줄로 — '월~토 09:00~19:00 · 일 쉼 · 공휴일 09:00~19:30'."""
    groups: list[tuple[list[str], str]] = []
    for day in WEEK:
        v = h.get(day, "쉼")
        if groups and groups[-1][1] == v:
            groups[-1][0].append(day)
        else:
            groups.append(([day], v))
    parts = [f"{g[0]}~{g[-1]} {v}" if len(g) > 1 else f"{g[0]} {v}" for g, v in groups]
    return " · ".join(parts + [f"공휴일 {h.get('공휴일', '쉼')}"])


def _pharmacy_rows(name: str, ph: dict, slots: Slots, data: DongData, asked: str = "") -> list[str]:
    """약국 이름 · 주소 · 전화 · 그날 문 여는지(국립중앙의료원 약국 정보, 10-20).

    【판단】 10-20 페르소나 h01 '신북읍 약국 문 연 데 어디가 가까워?'에 '문 연 약국은 자료로
           확인할 수 없어요', '주소만'에 주소를 주지 않았다. 카드는 이미 요일별 운영 자료를 쓴다.
           '그날'은 때 칸이 있으면 그날, 없으면 오늘. 공휴일이면 공휴일 운영 시간을 본다
    """
    today_, _ = _today()
    day = today_
    if slots.period:
        try:
            day = date.fromisoformat(_when(slots.period, today_)[0])
        except ValueError:
            day = today_
    # 【판단】 10-27 fix_check_2 c3: '사북면에서 일요일에 약국이 먼 마을'에 때 칸이 비어
    #        오늘(화)로 보고 '일요일 기준 자료는 없다'고 했다(요일마다 있음)
    #        → 말에 요일이 있으면 다가오는 그 요일
    m = WEEKDAY_ASK.search(asked or "")
    if m and not slots.period:
        want = WEEK.index(m.group(1)) if m.group(1) else 6  # '주말'은 일요일(쉬는 약국이 더 많다)
        day = today_ + timedelta(days=(want - today_.weekday()) % 7)
    hol = data.holidays() or {}
    key = "공휴일" if day.isoformat() in hol else WEEK[day.weekday()]
    if HOLIDAY_ASK.search(asked or "") and not slots.period:
        key = "공휴일"
    when = (
        f"{day.month}월 {day.day}일({WEEK[day.weekday()]}{', 공휴일' if key == '공휴일' else ''})"
        if key != "공휴일" or day.isoformat() in hol
        else "공휴일"
    )
    meta = data.pharmacies_meta() if hasattr(data, "pharmacies_meta") else {}
    src = f"국립중앙의료원 약국 정보 {meta.get('basis') or ''}".strip()

    def one(x: dict, far: bool = False) -> str:
        now = x["hours"].get(key)
        bits = [x["addr"], x["tel"]]
        if far:
            bits.insert(0, f"{x['dong']}, 직선 {x['km']}km")
        elif x.get("km") is not None:
            # 10-20 페르소나 h01 r2: '둘 중 어디가 읍 가운데에 더 가까워?'
            # 읍 · 면은 가운데에서 잰 거리
            bits.insert(0, f"{unit} 가운데에서 직선 {x['km']}km")
        bits.append(f"{when} {now}" if now else f"{when} 쉼")
        bits.append(f"요일별 {_hours(x['hours'])}")
        return f"{x['name']}({', '.join(b for b in bits if b)})"

    rows = []
    inside = ph.get("list") or []
    unit = _unit(name)
    if inside:
        opened = [x for x in inside if x["hours"].get(key)]
        shown = sorted(inside, key=lambda x: (not x["hours"].get(key), x["name"]))
        rest = len(inside) - PHARMACY_SHOWN
        rows.append(
            f"약국 {len(inside)}곳({src}), {when}에 문 여는 곳 {len(opened)}곳: "
            + " / ".join(one(x) for x in shown[:PHARMACY_SHOWN])
            + (f" / 그 밖에 {rest}곳" if rest > 0 else "")
        )
    else:
        near = ph.get("nearest") or []
        rows.append(
            f"약국: {unit} 안에 없음({src}). 가까운 약국({unit} 경계의 가운데에서 잰 직선거리, "
            "실제 길은 더 멂): " + " / ".join(one(x, far=True) for x in near)
        )
    # 【판단】 10-25 페르소나 cli0 베리안: 동 안 약국이 그날 모두 쉬는데 '다른 동을 말해 달라'고만
    #        했다 → 그날 문 여는 가장 가까운 약국(동 밖 · 이웃 시군 포함)을 거리순으로(open_near,
    #        big-contest scripts/export_bisu_pharmacy_near.py)
    open_near = (ph.get("open_near") or {}).get(key) or []
    if open_near and not any(x["hours"].get(key) for x in inside):
        rows.append(
            f"{when}에 문 여는 가장 가까운 약국({unit} 밖 포함, {unit} 경계의 가운데에서 잰 "
            "직선거리, 실제 길은 더 멂): "
            + " / ".join(
                f"{x['name']}({x['dong']}, 직선 {x['km']}km, {x['addr']}, {x['tel']}, "
                f"{when} {x['hours']})"
                for x in open_near
            )
        )
    # 【정함 10-27 팀장】 마을 단위 "넣기" — 예상 질문 2-8 T2 '신북읍 … 약국 먼데는 어디'에
    #        '마을별 약국 거리 자료는 없다'고 했다(focus.json에 마을마다 요일별 거리가 있다).
    #        읍 · 면이면 그날 문 연 약국까지 먼 마을을 먼 순으로
    fv = data.focus(name) if hasattr(data, "focus") else None
    vs = [v for v in ((fv or {}).get("villages") or []) if v.get("name")]
    k = 8 if key == "공휴일" else WEEK.index(key) + 1
    kms = sorted(
        ((v["name"], v[f"pharm_km_{k}"]) for v in vs if v.get(f"pharm_km_{k}") is not None),
        key=lambda x: -x[1],
    )
    if kms:
        far = [x for x in kms if x[1] > FAR_PHARM_KM]
        # 10-27 c1 2-8 T2: '약국 먼데는 어디'에 이 줄을 쓰지 않고 가까운 약국만 답함 → 줄 이름을
        #        물음의 말('약국이 먼 마을')로
        rows.append(
            f"약국이 먼 마을(마을마다 {when}에 문 연 약국까지, "
            "마을 경로당 · 마을회관 자리에서 직선, 실제 길은 더 멂): "
            f"마을 {len(kms)}곳 중 {FAR_PHARM_KM:g}km 넘는 마을 {len(far)}곳"
            + ("(모두)" if far and len(far) == len(kms) else "")
            # 10-27 c4: 뒤에 적은 6곳을 글쓴이가 '10곳 중 6곳'으로 셈 → 몇 곳을 적는지 밝힌다
            + f" — 그중 먼 순 위 {len(kms[:6])}곳: "
            + " · ".join(f"{n} {km:.1f}km" for n, km in kms[:6])
        )
    rows.append("약국 운영 시간은 약국이 신고한 값이라 바뀔 수 있음(가기 전에 전화로 확인)")
    return rows


def _places(
    name: str, p: dict, d: dict, region_info: dict, f: Facts, own_pharmacy: bool = False
) -> list[str]:
    """갈 곳 — 그 동 안의 시설. 문장은 한 가지 뜻으로만 읽히게(사서 원칙).

    【판단】 10-12 페르소나: '수서동 경로당 8곳 이름 · 위치' · '퇴계동 복지관 · 어르신 모이는 곳' ·
           '북산면 버스 · 병원'을 물었는데 '연결 전'만 답했다. 동 안에 없으면 '없다'로 끝내지 않고
           가장 가까운 곳과 직선거리를 함께 건넨다(10-12 팀장: '자료가 없어서'로 끝내지 않는다).
    """
    unit = _unit(name)
    rows: list[str] = []
    halls = p["halls"]["list"]
    src = HALL_SRC.get(p["halls"]["src"], "")
    kinds = Counter(h["kind"] for h in halls)
    if halls:
        label = " · ".join(f"{k} {v}곳" for k, v in kinds.items())
        items = " / ".join(
            _with(h["name"], _addr(h.get("addr", "")), h.get("tel", "")) for h in halls
        )
        rows.append(f"{label}({src}): {items}")
    else:
        rows.append(f"경로당 · 마을회관: {unit} 안에 없음({src})")
    # 【판단】 '경로당' 서가(넓이)는 강남구 경로당 현황 2022라 수가 다를 수 있다 → 두 수를 해와 함께
    old = (d.get("senior_hall") or {}).get("halls")
    if old is not None and old != len(halls):
        rows.append(
            f"경로당 넓이를 적은 강남구 경로당 현황(2022)에는 {old}곳으로 적혀 있음(해가 다름)"
        )
    dept = region_info.get("hall_dept")
    if dept:
        rows.append(f"경로당 문의: {dept['name']} {dept['tel']}")
    sc = p.get("senior_centers") or []
    if sc:
        rows.append(
            "노인복지관: " + " / ".join(_with(c["name"], _addr(c["addr"]), c["tel"]) for c in sc)
        )
    elif "senior_centers" in p.get("nearest", {}):
        line = _nearest("노인복지관", p["nearest"]["senior_centers"], unit)
        # 10-27 밤: 강남노인종합복지관은 주소(삼성로 66)를 좌표로 못 바꿔 거리 계산에서 빠졌다
        skipped = [x["name"] for x in region_info.get("senior_centers", []) if not x.get("dong")]
        if skipped:
            line += f"({' · '.join(skipped)}은 주소를 좌표로 못 바꿔 거리 계산에서 빠짐)"
        rows.append(line)
    # 【판단】 10-27 밤 페르소나 s01 T5: 개포동 종합사회복지관 팀장에게 '동 안에 복지관이 없다'만
    #        말함 → 그 동 안 사회복지관 · 정신건강복지센터도(노인복지관과 다른 시설)
    for key, label in REGION_LISTS[:2]:
        mine = [x for x in region_info.get(key, []) if x.get("dong") == name]
        if mine:
            rows.append(
                f"{label}: "
                + " / ".join(_with(x["name"], _addr(x["addr"]), x.get("tel", "")) for x in mine)
            )
    meals = p.get("meals") or []
    if meals:
        rows.append(
            "무료급식소: "
            + " / ".join(
                _with(
                    m["name"],
                    m["days"].replace("+", "·"),
                    m["time"],
                    f"대상 {m['target']}" if m["target"] else "",
                    _addr(m["addr"]),
                    m["tel"],
                )
                for m in meals
            )
        )
    else:
        rows.append(_nearest("무료급식소", p.get("nearest", {}).get("meals"), unit))
    health = p.get("health") or []
    if health:
        rows.append(
            "보건기관: " + " / ".join(_with(h["name"], h["kind"], h["tel"]) for h in health)
        )
    else:
        rows.append(
            _nearest("보건소 · 보건지소 · 보건진료소", p.get("nearest", {}).get("health"), unit)
        )
    for kind, row in p.get("shops", {}).items():
        if kind == "약국" and own_pharmacy:
            continue  # 약국은 요일별 운영 시간이 있는 국립중앙의료원 자료로(_pharmacy_rows)
        if row["n"]:
            ex = " · ".join(row["names"])
            # 【판단】 10-15 페르소나 20b q13: '약국 여섯 곳'이라면서 이름은 다섯이라 '하나는요?'.
            #        시설 자료는 이름을 5곳까지 담는다 — 모자라면 그렇다고 밝힌다
            short = len(row["names"]) < row["n"]
            more = f", 이름은 그중 {len(row['names'])}곳만 자료에 있음" if short else ""
            rows.append(f"{kind} {row['n']}곳({ex}{more})")
        else:
            rows.append(_nearest(kind, row.get("nearest"), unit))
    # 【판단】 10-13 청년 60턴 r3 T30: '약국까지 얼마나 멀어요?'가 이 서가로 오면
    #        '거리는 자료에 없어요'라고 했다(진단 서가에만 있던 사실).
    #        같은 사실은 어느 서가로 가도 같은 문장으로 건넨다.
    #        거리가 둘이라 어디서 잰 것인지 밝힌다
    for sig in (d.get("diag") or {}).get("signals", []):
        if "약국까지" in sig:
            rows.append(f"{sig}(마을마다 가장 가까운 약국까지 잰 거리의 가운데값, 진단 신호)")
        elif "버스 노선" in sig:
            rows.append(f"{sig}(진단 신호)")
    if "가장 가까운 곳" in " ".join(rows):
        rows.append(
            f"'가장 가까운 곳' 거리는 이 {unit} 경로당들의 가운데에서 잰 직선거리(실제 길은 더 멂)"
        )
    lt = p.get("ltc") or {}
    home = lt.get("home") or {}
    if home.get("n"):
        ks = " · ".join(f"{k} {v}" for k, v in home["kinds"].items())
        orgs = " / ".join(f"{o['name']}({' · '.join(o['kinds'])})" for o in home["list"])
        rows.append(
            f"재가 장기요양기관 {home['n']}곳(하는 일별로 세면 {ks}, 한 곳이 여러 일을 하기도 함), "
            f"전부: {orgs}"
        )
    else:
        rows.append(f"재가 장기요양기관: {unit} 안에 없음")
    res = lt.get("res") or []
    if res:

        def _cap(r: dict) -> str:
            bits = [f"정원 {r['cap']:,}명"]
            if r.get("now") is not None:
                bits.append(f"현원 {r['now']:,}명")
            if r.get("wait") is not None:
                bits.append(f"대기 {r['wait']:,}명")
            return " · ".join(bits)

        rows.append(
            "입소 시설(요양원 등): "
            + " / ".join(
                _with(r["name"], r["kind"].replace("(개정법)", ""), _cap(r), r["tel"]) for r in res
            )
        )
    else:
        rows.append(f"입소 시설(요양원 등): {unit} 안에 없음")
    o = p.get("office") or {}
    if o.get("addr"):
        rows.append(_office_line("", o))
    elif o:
        rows.append(f"주민센터: {o['name']}(주소 · 전화는 이 자료에 없음)")
    shop = "의원은" if own_pharmacy else "약국 · 의원은"
    rows.append(f"장기요양기관은 건보공단 2026-10 조회, {shop} 상가정보 {B.shops()}")
    bits = [f"경로당 등 {len(halls)}곳"]
    if health:
        bits.append("보건 " + " · ".join(h["name"] for h in health))
    f.memo = (f.memo + " / " if f.memo else "") + f"{name}: " + ", ".join(bits)
    return rows


_TIMES = re.compile(r"\((\d+)회\)")


def _per_day(n: int | None) -> str:
    return f"하루 약 {n}번" if n is not None else "하루 횟수 모름"


def _bus(name: str, b: dict, info: dict, f: Facts) -> list[str]:
    """춘천 버스 — 정류장 · 노선 · 드문 버스 · 마을에서 정류장까지.

    【판단】 10-12 페르소나: '북산면 정류장 몇 개 · 하루 몇 번', '노선이 북산2 하나뿐?',
           '퇴계동 버스 어디 많이 다녀', '버스'를 물었는데 '연결 전'만 답했다.
           마을버스 하루 횟수는 TAGO 어림(공식보다 한두 번 많을 수 있음), 시내버스는 횟수를 모른다.
           모르는 것은 지어내지 않고 모른다고 적는다
    """
    unit = _unit(name)
    rows = [f"정류장 {b['stops']}곳(같은 이름의 가는 쪽 · 오는 쪽은 한 곳으로 셈)"]
    town = [r for r in b["routes"] if r["per_day"] is not None]
    city = [r for r in b["routes"] if r["per_day"] is None]
    # 【판단】 10-13 r6 T11: 합계를 주지 않으니 글쓴이가 11 + 30을 직접 더했다 → 사서가 센다
    rows.append(
        f"지나는 노선 {len(b['routes'])}개(마을버스 {len(town)}개 · 시내버스 {len(city)}개)"
    )
    if town:
        rows.append(
            f"마을버스 {len(town)}개(하루 횟수 많은 순): "
            + " / ".join(
                f"{r['no']}({_per_day(r['per_day'])}, 이 {unit} 정류장 {r['stops_here']}곳)"
                for r in town
            )
        )
        # 【판단】 10-29 변수 시험 c01_019 · c01_078 '하루 버스 total 몇 회': 노선 하나(북산1 약
        #        7번)를 합계처럼 답하거나 '합계는 자료에 없다'고 했다 — 더하기는 사서가 한다
        #        (글쓴이는 셈하지 않는다). 시내버스는 횟수를 몰라 빠진다고 함께 적는다
        total = sum(r["per_day"] for r in town)
        rows.append(
            f"이 {unit}을(를) 지나는 마을버스 {len(town)}개 노선의 하루 횟수를 더하면 약 {total}번"
            "(코드가 더함, 노선마다 어림이라 합도 어림)"
            + (f" — 시내버스 {len(city)}개는 하루 횟수를 몰라 이 합에 없음" if city else "")
        )
        # 10-20 페르소나 h01 r7 '버스 몇 시에 오는지는 결국 모른다고 함'
        #        — TAGO의 첫차 · 막차 · 갈래 출발 시각
        timed = [r for r in town if r.get("first")]
        if timed:
            # 10-20 페르소나 h01 r8 T4: 오전에 '다음 차'를 물었는데 19:25(저녁) — 지금 시각을 준다
            if (now := _clock()) is not None:
                rows.append(
                    f"지금 시각 {now}(한국 시간). '다음 차'는 이 시각 뒤 첫 출발이고, "
                    "오전 · 오후를 물으면 그 시간대의 출발 시각만"
                )
            rows.append(
                "마을버스 첫차 · 막차(TAGO, 종점 출발 기준 · 이 마을 정류장 도착 시각은 더 늦음): "
                + " / ".join(
                    f"{r['no']} 첫차 {r['first']} 막차 {r['last']}"
                    + (
                        f"(출발 {' · '.join(r['starts'])})"
                        if len(r.get("starts") or []) > 1
                        else ""
                    )
                    for r in timed
                )
            )
    if city:
        rows.append(f"시내버스 {len(city)}개(하루 횟수 모름): " + " · ".join(r["no"] for r in city))
    # 【판단】 마을버스 노선 이름은 가는 면 이름이다. 다른 면 이름 노선이 이 읍면을 지나면 밝힌다
    #        (10-15 페르소나 q06 T3: 신북읍 버스에 북산2 · 사북2가 나와 다른 면 이야기로 읽힘)
    stem = re.sub(r"(동|면|읍)$", "", name)
    others = sorted({m.group(1) for r in town if (m := re.match(r"^([가-힣]+)", r["no"]))} - {stem})
    if others:
        f.notes.append(
            f"마을버스 노선 이름은 그 노선이 가는 면 이름(예: {others[0]}…은 "
            f"{others[0] if others[0].endswith(('면', '읍')) else others[0] + '면'} 쪽). "
            f"이 {unit}을 지나 다른 면으로 가는 노선도 이 목록에 있음"
        )
    # 【판단】 원자료 계산(rural.low_freq_routes)은 드문 노선을 '면'에만 붙인다. 시내 동도 그 노선이
    #        지나가니(퇴계동에 남면2-1 하루 2번), 이 동을 지나는 노선 목록에서 바로 센다
    low = [f"{r['no']}({_per_day(r['per_day'])})" for r in town if r["per_day"] <= 3]
    rows.append(f"이 {unit}을 지나는 하루 3번 이하 마을버스: " + (" · ".join(low) or "없음"))
    if b.get("busy_stops"):
        rows.append(
            "노선이 많이 서는 정류장: "
            + " · ".join(f"{s['name']}({s['routes']}개 노선)" for s in b["busy_stops"])
        )
    v = b.get("villages") or []
    if v:
        rows.append(
            "마을(경로당 · 마을회관)에서 가장 가까운 정류장까지(직선, 먼 순): "
            + " / ".join(
                f"{x['hub']} → {x['stop']} {x['km']}km"
                + (
                    f"(그 근처 가장 잦은 노선 {x['route']}, {_per_day(x['per_day'])})"
                    if x["route"]
                    else ""
                )
                for x in v
            )
        )
    # 【판단】 10-20 페르소나 h01 r2: '버스 드문 마을 이름만'에 '노선이 다니는 마을 이름은 자료에
    #        없어요'(세 번). 마을마다 가장 가까운 정류장에 서는 가장 잦은 노선과 횟수는 있다
    #        → 그 횟수가 적은 마을부터(시내버스는 횟수를 몰라 뺌)
    known = sorted(
        (x for x in v if x.get("per_day") is not None), key=lambda x: (x["per_day"], -x["km"])
    )
    if known:
        rows.append(
            "버스가 드문 마을(마을 정류장에 서는 가장 잦은 마을버스의 하루 횟수가 적은 순, "
            "다섯 곳): "
            + " / ".join(
                f"{x['hub']}({x['stop']} {x['km']}km, {x['route']} {_per_day(x['per_day'])})"
                for x in known[:5]
            )
        )
        rare = [x["hub"] for x in known if x["per_day"] <= 3]
        rows.append("하루 3번 이하 마을버스만 서는 마을: " + (" · ".join(rare) or "없음"))
        f.notes.append(
            "마을 이름을 물으면 노선 번호가 아니라 '버스가 드문 마을' 줄의 마을(경로당) 이름으로 "
            "답한다"
        )
        # 10-20 페르소나 h01 r8 T3 ~ T7: '천전1리가 드문 마을'이라 해 놓고 '신북3은 하루 4번이라
        #        드문 편이 아니다'로 반박 → 두 기준을 밝히고, 마을을 물으면 마을 기준으로
        f.notes.append(
            "'드문 버스'는 두 기준: 노선은 하루 3번 이하, 마을은 그 마을 정류장에 서는 가장 잦은 "
            "노선의 하루 횟수가 적은 순(위 '버스가 드문 마을' 줄, 이 지역에서는 하루 4번도 "
            "드문 축). "
            "사용자가 '드문 거 맞지?'라고 물으면 마을 기준으로 '네'라고 답하고 노선 기준으로 "
            "반박하지 않는다"
        )
    allow = info.get("low_freq_all") or {}
    if allow:
        rows.append(
            "춘천에서 하루 3번 이하 마을버스가 다니는 면(노선 번호가 그 면 이름): "
            + " · ".join(
                f"{m}({', '.join(_TIMES.sub(r'(하루 약 \1번)', x) for x in r)})"
                for m, r in allow.items()
            )
        )
    rows += [f"참고: {n}" for n in info.get("notes", [])]
    bits = [f"노선 {len(b['routes'])}개"] + ([f"하루 3번 이하 {' · '.join(low)}"] if low else [])
    f.memo = (f.memo + " / " if f.memo else "") + f"{name} 버스: " + ", ".join(bits)
    return rows


REGION_LISTS = (
    ("welfare_centers", "사회복지관"),
    ("mental_health", "정신건강복지센터 · 중독관리통합지원센터"),
    ("senior_jobs", "노인일자리 지원기관"),
)


def _office_line(name: str, o: dict) -> str:
    """주민센터(행정복지센터) 한 줄 — 이름 · 주소 · 전화.

    【판단】 10-27 밤: 강남 22곳도 주소가 생겼다(강남구_동주민센터 현황, 공공데이터포털 15116896).
           그 자료에는 전화 칸이 없어 '전화는 다산콜센터 120'을 함께 적는다(10-19 팀장 '어디로
           물으면 되는지'). 춘천 행정복지센터는 전화까지 있다
    """
    kind = "주민센터" if o["name"].endswith("주민센터") else "행정복지센터"
    head = f"{name} {kind}" if name else kind
    line = f"{head}: {_with(o['name'], _addr(o['addr']), o.get('tel', ''))}"
    if not o.get("tel") and o["name"].endswith("주민센터"):
        line += "(전화는 이 자료에 없음. 서울시 다산콜센터 120으로 물으면 동 주민센터로 이어 줌)"
    return line


def _support(slots: Slots, data: DongData, f: Facts) -> None:
    """지원 기관 · 신청 창구 — 지역마다 다른 창구와 전화. 동을 말했으면 그 동 주민센터도.

    【판단】 옛 노인 비서(safety_answer) · 청년 비서(support)가
           10-07 이용 조건 점검 뒤 쓰던 사실 그대로
    """
    c = data.places_common()
    if not c:
        f.notes.append("지원 기관 자료 파일이 없어요")
        return
    first = data.dong(slots.dongs[0]) if slots.dongs else None
    region = slots.region or (first["region"] if first else "강남구")
    r = data.region_places(region)
    s, sc = r["safety"], c["safety"]
    rows: list[str] = []
    if region == "강남구":
        rows.append(
            f"응급안전안심서비스(응급 · 안부 장비: {sc['장비']}): 강남에서 혼자 사는 어르신은 "
            f"동 주민센터에 신청. 강남의 운영기관은 {s['기관']}(장애인 자립생활센터)이고, "
            "서울의 노인맞춤돌봄 수행기관은 응급안전안심을 맡지 않음"
        )
    else:
        rows.append(
            f"응급안전안심서비스(응급 · 안부 장비: {sc['장비']}): 춘천은 "
            f"{_with(s['기관'], s.get('전화', ''), s.get('주소', ''))}이 맡음. 신청: {sc['신청']}"
        )
    rows.append(f"응급안전안심 대상: {sc['대상']}")
    care = " · ".join(f"{x['기관']} {x['전화']}" for x in r["care"])
    rows.append(f"노인맞춤돌봄({c['care_what']}) 수행기관: {care}. 대상: {c['care_target']}")
    post = c["post"]
    rows.append(f"{post['이름']}: {post['내용']}. 대상: {post['대상']}. 문의: {post['문의']}")
    for hc in r.get("health_center", []):
        rows.append(f"보건소: {_with(hc['name'], _addr(hc['addr']), hc['tel'])}")
    if r.get("senior_centers"):
        rows.append(
            f"{region} 노인복지관 {len(r['senior_centers'])}곳: "
            + " / ".join(_with(x["name"], _addr(x["addr"]), x["tel"]) for x in r["senior_centers"])
        )
    # 【기능】 10-27 밤: 두 지역 사회복지관 · 정신건강복지센터, 강남 노인일자리 기관 — 고립 어르신 ·
    #        청년을 이어 줄 곳(강남은 서울시 강남구 사회복지시설 목록, 춘천은 강원도 사회복지관 ·
    #        춘천시 정신건강센터 현황). 강남 원자료는 전화 칸이 비어 이름 · 주소만
    for key, label in REGION_LISTS:
        items = r.get(key) or []
        if items:
            no_tel = (
                "" if all(x.get("tel") for x in items) else ", 전화가 안 적힌 곳은 이 자료에 없음"
            )
            rows.append(
                f"{region} {label} {len(items)}곳(이름 · 주소{no_tel}): "
                + " / ".join(_with(x["name"], _addr(x["addr"]), x.get("tel", "")) for x in items)
            )
    for name in slots.dongs[:MAX_DONGS]:
        p = data.places(name)
        o = (p or {}).get("office") or {}
        if o.get("addr"):
            rows.append(_office_line(name, o))
        elif o:
            # 10-19 팀장: 강남 동주민센터 위치는 없어도 됨. 대신 어디로 물으면 되는지(서울시 120)
            rows.append(
                f"{name} 주민센터: {o['name']}(주소 · 전화는 이 자료에 없음. "
                "서울시 다산콜센터 120으로 물으면 동 주민센터로 이어 줌)"
            )
        # 【판단】 10-20 페르소나 o02 r3: '수서명화종합사회복지관 전화번호는?'에 '자료에 없어요'
        #        (갈 곳 자료에 02-459-2696이 있다). 지원 창구를 물으면 그 동 시설 연락처도 준다
        tels = [
            _with(x["name"], x["tel"])
            for k in ("senior_centers", "meals", "health")
            for x in (p or {}).get(k) or []
            if x.get("tel")
        ]
        if tels:
            rows.append(
                f"{name} 안 복지관 · 급식소 · 보건기관 연락처: " + " / ".join(dict.fromkeys(tels))
            )
    # 10-20 페르소나 o02 r7 '오늘 밤에 신고해도 되는 거죠?'에 '절차는 자료에 없다' — 상식
    rows.append("112 · 119는 밤에도 언제든 신고할 수 있음(24시간)")
    rows.append(
        "며칠째 연락이 안 되는 혼자 사시는 어르신은 112(경찰에 안전 확인 요청) · 동 주민센터에 "
        "안부 확인을 요청하는 것이 맞음 — 일을 크게 만드는 것이 아니고, "
        "주소를 정확히 몰라도 됨(상식)"
    )
    rows.append(
        f"전화 상담: 보건복지상담센터 {c['hotline']}, "
        f"응급안전안심 중앙모니터링센터 {sc['중앙모니터링센터']}"
    )
    # 【판단】 10-15 페르소나 20b q07(정신건강복지센터 상담사): 자살 생각이 있는 분께 안내할 곳을
    #        물었는데 129만 주고 '109 · 1577-0199가 맞지 않나요?'는 범위 밖으로 냈다.
    #        생명이 걸린 안내라 국가 공식 번호를 둔다(policy.CARE 와 같은 번호)
    rows.append(CRISIS_LINES)
    # 10-28 페르소나 p02_b T4 '저는 뭘 해야 하나요'(생활지원사)에 '자료에 없다'만 두 번
    #        → 상식 한 줄
    rows.append(
        "돌봄 현장에서 어르신이 걱정될 때 실무자가 하는 일반적인 순서(상식): 소속 기관(수행기관 · "
        "복지관) 담당자에게 먼저 알리고, 동 주민센터(행정복지센터) · 보건소에 상담을 요청한다. "
        "생명이 위험해 보이면 바로 119"
    )
    # 【판단】 10-28 페르소나 p03_a T2: '역삼1동 주민센터에 신청하면 청년미래센터로
    #        연결됩니다'(단정) — 자료의 청년미래센터 시범 지역에 서울 · 강원이 적혀 있지 않다
    #        → 그 지역에 있다고 하지 않게 밝히고, 마음 건강 상담은 그 지역 정신건강복지센터로
    youth = [
        "청년 연결: " + " / ".join(c["youth_desk"]),
        f"청년미래센터가 {region}에 있는지는 이 자료에 없음(시범 지역에 서울 · 강원이 적혀 있지 "
        "않음) — 있다거나 그리로 연결된다고 말하지 않는다. 신청은 청년ON 또는 동 주민센터"
        "(행정복지센터)",
        f"마음 건강 상담이 필요하면 {region} 정신건강복지센터(지원 기관 목록의 그 줄)",
    ]
    rows = youth + rows if slots.target == "청년" else rows + youth
    f.lines.append(f"[{region}]")
    f.lines += [f"- {x}" for x in rows]
    f.memo = f"{region} 신청 창구"


# 【기능】 줄 세울 수 있는 주제 → (지표 이름, 동 자료에서 값 꺼내기). 값이 없는 동은 뺀다
#        (예: 기초생활수급자는 춘천만, 경로당은 강남만 있다)
# 【판단】 값 꺼내기는 (동 자료, 그 동 시설 자료)를 받는다 — 경로당 수는 시설 자료(10-13)
RANKABLE: dict[str, tuple[str, Callable[[dict, dict | None], float | None]]] = {
    "solo_seniors": (
        "65세 이상 1인세대(주민등록 {reg})",
        lambda d, p: _now(d.get("solo65")),
    ),
    "youth": (
        "청년(19~34세) 인구(주민등록 {reg})",
        lambda d, p: (d.get("youth") or {}).get("total"),
    ),
    # 【판단】 강남은 서울시 독거노인 현황의 수급권자 독거노인(10-14).
    #        지역마다 이름은 LIVE_RANK_NAME
    "livelihood": (
        "기초생활수급자 수",
        lambda d, p: (
            (d.get("livelihood") or {}).get("people")
            or ((d.get("seoul_lonely_kind") or {}).get("2025") or {}).get("수급")
        ),
    ),
    "senior_hall": (
        "경로당 수",
        lambda d, p: len(p["halls"]["list"]) if p else None,
    ),
    # 【기능】 10-12 재생: '계단 집 동별로 견줘 줘'에 줄 세우기가 없어 '어느 동을 볼까요?'로 빠짐
    "housing": (
        "30년 넘은 계단 집(승강기 없는 3~5층) 가구",
        lambda d, p: (d.get("housing") or {}).get("old_walkup_units"),
    ),
    "seoul_lonely": (
        "서울시 독거노인 현황 2025년",
        lambda d, p: (d.get("seoul_lonely") or {}).get("2025"),
    ),
}
RANK_SHOW = 5


def _now(values: dict | None) -> float | None:
    """{'2025-09': a, '2026-09': b} → b(가장 새 달)."""
    pm = B.months(values)
    return values[pm[1]] if pm else None


# 전부 · 아래쪽을 바라는 말('22개 동 전부' · '모두 순서대로' · '나머지는' · '가장 적은 동')
EVERY_ASK = re.compile(
    r"전부|모두|모든|전체|나머지|다\s?(?:보여|알려|줘|순서)|끝까지|꼴찌|하위|"
    r"\d+\s?(?:개\s?)?(?:동|곳)\s?(?:다|전부|모두)|(?:적은|낮은)\s?(?:곳|동|순)"
)


def _rank_by(topic: str, slots: Slots, data: DongData, f: Facts, asked: str = "") -> None:
    """지역의 동들을 한 지표로 줄 세운다(많은 순, 위 5곳).

    【판단】 10-12 팀장: "1번 3번 4번 8번 9번이 On되면 이걸로" — 주제 칸 + 줄 세우기 칸 + 지역 칸이
           켜지면 이 서가. 떠보기(10-12)에서 "기초수급 받는 독거 어르신 많은 동"에
           '어느 동을 볼까요?'만
           되물었다. 순서는 코드가 센다(AI는 옮기기만).
    """
    region = slots.region or "강남구"
    name, get = RANKABLE[topic]
    name = name.format(reg=B.reg())
    if topic == "senior_hall":
        name = HALL_RANK_NAME.get(region, name)
    if topic == "livelihood":
        name = LIVE_RANK_NAME.get(region, name)
    if topic == "solo_seniors" and slots.ages and (slots.ages.lo or 0) >= 80:
        name = f"80세 이상 1인세대(주민등록 {B.reg()})"

        def get(d: dict, p: dict | None) -> float | None:
            return (d.get("solo80") or {}).get("n")

    # 【판단】 10-26 예상 질문 1-9 '그제 비가 많이 왔는데 지하층 집이 많은 동이 어디예요?':
    #        집 주제의 줄 세우기가 계단 집 하나뿐이라 '지하층 집 많은 순서는 드릴 수 없어요'
    #        (동마다 지하층 건물 수는 있음) → 지하 · 반지하를 물으면 그 숫자로 줄 세운다
    unit = RANK_UNIT.get(topic, "명")
    if topic == "housing" and re.search(r"지하|반지하", asked or ""):
        name, unit = "지하층이 있는 30년 넘은 저층 주거 건물(어림)", "채"

        def get(d: dict, p: dict | None) -> float | None:
            return (d.get("housing") or {}).get("basement_old")

    # 【판단】 강남에서 성별을 물으면 서울시 독거노인 현황의 그 성별 숫자로 줄 세운다(10-14).
    #        춘천은 성별 숫자가 없어 그대로 두고 밝힘(policy.disclose)이 나간다
    sex = slots.sex
    if topic in ("solo_seniors", "seoul_lonely") and sex in SEX_WORD and region == "강남구":
        name = f"서울시 독거노인 현황 2025년 {SEX_WORD[sex]}"

        def get(d: dict, p: dict | None) -> float | None:
            return ((d.get("seoul_lonely_sex") or {}).get("2025") or {}).get(sex)

    rows = []
    for dong in data.region_dongs(region):
        d = data.dong(dong)
        v = get(d, data.places(dong)) if d else None
        if v is not None:
            rows.append((v, dong))
    rows.sort(key=lambda x: (-x[0], x[1]))
    if not rows:
        f.notes.append(f"{region}에는 {name} 자료가 없어요")
        return
    shown = rows[:RANK_SHOW]
    # 【판단】 10-26 웹 점검: 숫자에 단위가 없어 답 쓰는 AI가 1인세대를 '2,543가구'로 씀
    #        (세대 ≠ 가구) → 단위를 붙여 건넨다(경로당은 곳, 계단 집은 가구, 나머지는 명 —
    #        위에서 정함)
    top = " · ".join(f"{i}위 {n} {v:,}{unit}" for i, (v, n) in enumerate(shown, 1))
    f.lines.append(f"{region} {name} 많은 동(위 {len(shown)}곳, {len(rows)}곳 중): {top}")
    # 【판단】 10-12 페르소나: '구 전체 몇 명' · '22개 동 전부'에 '어느 동을 볼까요?'만 되물었다.
    #        합계와 전체 순서를 함께 건넨다(글쓴이는 물은 것만 고른다). 합계는 동 숫자를 더한 값
    total = sum(v for v, _ in rows)
    f.lines.append(f"{region} {len(rows)}곳 {name} 합계: {total:,}{unit}")
    # 【정함 10-27 팀장】 묻는 것만 — '나머지 동 순서'는 전부 · 모두 · 나머지 · 적은 쪽을 물을 때만
    #        건넨다(qbank 1-2 c1 T4 '지하층 집이 많은 동이 어디예요?'에 22곳을 다 늘어놓음)
    if len(rows) > RANK_SHOW and EVERY_ASK.search(asked or ""):
        rest = " · ".join(
            f"{i}위 {n} {v:,}{unit}" for i, (v, n) in enumerate(rows, 1) if i > RANK_SHOW
        )
        f.lines.append(f"{region} 나머지 동 순서: {rest}")
    elif len(rows) > RANK_SHOW:
        # 10-28 재심사 p01_c T4: 위 5곳만 받은 글쓴이가 '22곳 중 5곳만 자료에 있고 나머지 17개 동은
        #        자료에 없어요'(거짓 — 22곳 모두 값이 있다)
        f.notes.append(
            f"위 {RANK_SHOW}곳만 적었을 뿐 {region} {len(rows)}곳 모두 이 값이 있다. 나머지 동이 "
            "자료에 없다고 하지 않는다(나머지는 '나머지 동도 보여 줘'로 물으면 보인다)"
        )
    f.memo = f"{region} {name} 많은 순: " + " · ".join(
        f"{i}위 {n}" for i, (_, n) in enumerate(shown, 1)
    )
    # 【판단】 청년은 1인세대 · 거의 집에만 있는 청년 어림 순서도 함께 준다(10-15 페르소나 q04:
    #        '혼자 사는 청년 많은 동'에 '없어요'라고 함 — 1인세대 숫자가 있었다).
    #        글쓴이는 물은 것만 고른다
    if topic == "youth":
        f.lines += _youth_more(region, data)


def _youth_more(region: str, data: DongData) -> list[str]:
    """청년 1인세대 · 거의 집에만 있는 청년 어림이 많은 동(위 5곳).

    어림은 가운데로 줄 세우고 범위로 보인다(정확한 숫자처럼 보이지 않게).
    """
    solo, home = [], []
    for n in data.region_dongs(region):
        y = (data.dong(n) or {}).get("youth") or {}
        if y.get("solo"):
            solo.append((y["solo"], n, f"{y['solo']:,}"))
        h = y.get("homebound") or {}
        if "lo" in h:
            home.append(((h["lo"] + h["hi"]) / 2, n, f"약 {h['lo']:,}~{h['hi']:,}"))
    out = []
    for label, rows in (
        (f"청년 1인세대(주민등록 {B.reg()})", solo),
        ("거의 집에만 있는 청년 어림(실제로 센 수 아님)", home),
    ):
        rows.sort(key=lambda x: (-x[0], x[1]))
        if rows:
            top = " · ".join(f"{i}위 {n} {s}" for i, (_, n, s) in enumerate(rows[:RANK_SHOW], 1))
            out.append(f"{region} {label} 많은 동(위 {min(len(rows), RANK_SHOW)}곳): {top}")
    # 【판단】 10-29 변수 시험 c99_001 '춘천시 … 거의 집에만 있는 애들 어림 몇 명이야? 엑셀로': 위
    #        5곳만 있어 지역 전체 수를 답하지 못하고 파일만 안내했다 → 지역 전체(합계 · 어림)도
    #        준다.
    #        어림의 지역 전체는 동마다 나누기 전 값(youth_method.json, 동 값을 더한 것과 거의 같음)
    if solo:
        total = sum(v for v, _, _ in solo)
        out.append(f"{region} {len(solo)}곳 청년 1인세대(주민등록 {B.reg()}) 합계: {total:,}명")
    m = data.youth_method() if hasattr(data, "youth_method") else {}
    x = (m.get("regions") or {}).get(region)
    if x:
        out.append(
            f"{region} 전체 거의 집에만 있는 청년 어림(실제로 센 수 아님): 약 {x['lo']:,}~"
            f"{x['hi']:,}명 — 동마다 어림은 이 값을 나이 구성 · 1인세대로 나눈 것"
        )
    return out


# ── 날씨(동 상황의 조건, 10-13 팀장 결정) ──
# 【기능】 날씨 칸 → 기준(오늘 챙길 일 카드와 같은 기준) 이름
WEATHER_KIND = {"비": "폭우", "눈": "폭설", "추위": "한파", "더위": "폭염"}
_MD = re.compile(r"(\d{1,2})\s*(?:월|/|\.)\s*(\d{1,2})")
_YMD = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
# 【판단】 10-26: '일요일에 문 연 약국'의 때 칸('일요일')을 오늘로 읽었다(요일 말을 몰랐다).
#        10-25 약국 고침(open_near)은 시험한 날이 마침 일요일이라 통과했고 월요일에 깨졌다
_WD = re.compile(r"(지난\s?주|지난|다음\s?주|다음|이번\s?주|이번)?\s*([월화수목금토일])요일")
WD_NAMES = "월화수목금토일"


# 【정함 10-16 팀장】 비서의 '오늘'은 진짜 오늘. 10-19 팀장: "오늘도 진짜 오늘로 바꿔줘" —
#        챗봇 날씨도 카드처럼 오늘 · 내일 · 모레는 기상청 단기예보, 지난 날은 기상청 관측
#        (weather.json, 자동 받기가 날마다 어제까지 더함)
# 예보 · 특보를 받는 곳. 시험에서는 같은 모양의 가짜를 넣는다(없으면 카드와 같은 today.live())
WX = None
AHEAD = 2  # 단기예보는 오늘부터 사흘
# 【기능】 되감기(.env AS_OF, 카드와 같음) — 'live'가 아니라 날짜면 그날을 오늘로 보고
#        관측으로 답한다(시험 · 시연 되감기). Engine 이 설정에서 넣는다
AS_OF = "live"


HOLIDAY_ASK = re.compile(r"연휴|명절|설날|설 연휴|추석|공휴일|쉬는 날")


def calendar_facts(data: DongData) -> Facts:
    """긴 연휴 날짜(달력) — 취약 돌보미 판단 주제가 아닐 때도 연휴를 물으면 준다.

    【판단】 10-20 페르소나 f01 r9 T4 ~ T7: '다음 긴 연휴가 언제인지'를 세 번 물어야 답이 나왔고
           (청년 주제라 달력 줄이 없었음), '설 연휴는 자료에 없고 달력은 12월 25일까지'라고 했다
           (달력은 2027년까지 있고 다음 하나만 적혀 있었음)
    """
    from src.assistant import conditions as C

    today_, _ = _today()
    return Facts(title="달력(긴 연휴, 공휴일 자료)", lines=[C._near_holidays(data, today_)])


def _clock() -> str | None:
    """지금 시각 HH:MM(되감기 중이면 None — 그날의 시각은 모른다)."""
    from src.assistant import forecast as fc

    if AS_OF and AS_OF != "live":
        return None
    return fc.now_kst().strftime("%H:%M")


def _today() -> tuple[date, bool]:
    """(비서의 오늘, 되감기 중인가)."""
    from src.assistant import forecast as fc

    real = fc.today_kst()
    if AS_OF and AS_OF != "live":
        try:
            day = date.fromisoformat(AS_OF)
        except ValueError:
            return real, False
        return day, day < real
    return real, False


def _wx():
    if WX is not None:
        return WX
    from src.assistant import today

    return today.live()


_HALF = re.compile(r"(?:(\d{4})\s?년?\s?|(올해|금년|작년|지난해)\s?)?(상반기|하반기)")
# 날 없이 달만('지난 12월 · 작년 8월 · 2025년 12월' — '12월 4일'은 _when 이 날로 읽는다)
_MONTH = re.compile(r"(?:(\d{4})\s?년\s?|(올해|금년|작년|지난해|지난)\s?)?(\d{1,2})\s?월(?!\s?\d)")
_SEASONS = {"봄": (3, 5), "여름": (6, 8), "가을": (9, 11), "겨울": (12, 2)}
_SEASON = re.compile(r"(올해|금년|작년|지난해|지난|이번)?\s?(봄|여름|가을|겨울)")


def _month_end(y: int, m: int) -> date:
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def _span(period: str | None, today: date) -> tuple[date, date, str] | None:
    """때 말 → (첫날, 끝날, 부르는 말) — 반기 · 달 · 계절. 끝날은 오늘을 넘지 않는다.

    해를 말하지 않으면 시작한 것 가운데 가장 가까운 것(10월에 '12월'은 지난해 12월).
    """
    if got := _half_span(period, today):
        return got
    p = period or ""
    if m := _MONTH.search(p):
        year, which, mon = m.group(1), m.group(2), int(m.group(3))
        if not 1 <= mon <= 12:
            return None
        if year:
            y = int(year)
        elif which in ("작년", "지난해"):
            y = today.year - 1
        elif which in ("올해", "금년"):
            y = today.year
        else:
            y = today.year if mon <= today.month else today.year - 1
        first = date(y, mon, 1)
        if first > today:
            return None
        return first, min(_month_end(y, mon), today), f"{y}년 {mon}월"
    if m := _SEASON.search(p):
        which, name = m.group(1) or "", m.group(2)
        a, b = _SEASONS[name]
        y = today.year
        if which in ("작년", "지난해"):
            y -= 1
        if a > b:  # 겨울은 12월에 시작해 다음 해 2월까지 — 시작한 겨울 가운데 가장 가까운 것
            if which in ("작년", "지난해"):
                y = today.year - 1 if today.month == 12 else today.year - 2
            elif today.month < 12:
                y = today.year - 1
            first, last = date(y, 12, 1), _month_end(y + 1, b)
        else:
            if not which and date(y, a, 1) > today:
                y -= 1
            first, last = date(y, a, 1), _month_end(y, b)
        if first > today:
            return None
        return first, min(last, today), f"{first.year}년 {name}"
    return None


def _half_span(period: str | None, today: date) -> tuple[date, date, str] | None:
    """'하반기 · 작년 상반기 · 2025년 하반기' → (첫날, 끝날, '2025년 하반기').

    끝날은 오늘을 넘지 않는다.

    해를 말하지 않은 하반기는 올해 하반기가 아직 오지 않았으면(1 ~ 6월) 지난해 하반기다.
    """
    m = _HALF.search(period or "")
    if not m:
        return None
    year, which, half = m.groups()
    y = int(year) if year else today.year
    if which in ("작년", "지난해"):
        y -= 1
    elif not year and not which and half == "하반기" and today.month < 7:
        y -= 1
    first = date(y, 1 if half == "상반기" else 7, 1)
    if first > today:
        return None
    last = date(y, 6, 30) if half == "상반기" else date(y, 12, 31)
    return first, min(last, today), f"{y}년 {half}"


def _when(period: str | None, today: date) -> tuple[str, str]:
    """때 칸 → (그날 'YYYY-MM-DD', 그날을 부르는 말). 오늘이 기준(진짜 오늘)."""
    p = period or ""
    for word, n in (("모레", 2), ("내일", 1), ("어제", -1), ("그제", -2)):
        if word in p:
            return (today + timedelta(days=n)).isoformat(), word
    if m := _YMD.search(p):
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat(), p
        except ValueError:
            return today.isoformat(), "오늘"
    if m := _WD.search(p):
        # 그냥 '일요일'은 오늘부터 가장 가까운 그 요일(오늘 포함), '이번 주 · 다음 주 · 지난주'는
        # 월요일에 시작하는 주로 센다(1월 초 · 연말도 날짜 셈이라 해가 넘어가도 맞다)
        want = WD_NAMES.index(m.group(2))
        monday = today - timedelta(days=today.weekday())
        which = (m.group(1) or "").replace(" ", "")
        if which == "다음주":
            x = monday + timedelta(days=7 + want)
        elif which == "지난주":
            x = monday + timedelta(days=want - 7)
        elif which == "지난":  # 가장 가까운 지난 그 요일(오늘 빼고)
            x = today - timedelta(days=(today.weekday() - want) % 7 or 7)
        elif which.startswith("이번"):
            x = monday + timedelta(days=want)
        else:  # 그냥 · '다음 일요일' = 돌아오는 그 요일
            x = today + timedelta(days=(want - today.weekday()) % 7)
        return x.isoformat(), p
    m = _MD.search(p)
    if m:
        try:
            x = date(today.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return today.isoformat(), "오늘"
        # 【판단】 10-20: 해를 말하지 않은 날은 가까운 쪽 해로(1월 초에 '12월 4일'은 지난해 12월).
        #        반년 넘게 앞이면 지난해, 반년 넘게 뒤면 다음 해
        if (x - today).days > 183:
            x = x.replace(year=x.year - 1)
        elif (today - x).days > 183:
            x = x.replace(year=x.year + 1)
        return x.isoformat(), p
    return today.isoformat(), "오늘"


def _forecast_line(region: str, names: tuple[str, ...], data: DongData, day: str, call: str) -> str:
    """오늘 · 내일 · 모레 — 기상청 단기예보(동마다 격자, 구 · 시면 가장 센 값과 넘은 동 수)."""
    from src.assistant import forecast as fc

    grids = data.grids(region)
    mine = {n: grids[n] for n in names if n in grids}
    use = mine or grids
    try:
        by_dong, issued = _wx().forecast(use)
    except fc.ForecastError as e:
        return f"{region} {day}({call}) 기상청 예보를 받지 못함({e})"
    rows = [v[day] for v in by_dong.values() if v.get(day)]
    if not rows:
        return f"{region} {day}({call}) 예보가 아직 없음(기상청 단기예보 {issued} 발표)"

    def pick(col: str, f) -> float | None:
        xs = [r[col] for r in rows if r.get(col) is not None]
        return f(xs) if xs else None

    v = {
        "tmin": pick("tmin", min),
        "tmax": pick("tmax", max),
        "rain": pick("rain", max),
        "snow": pick("snow", max),
        "pop": pick("pop", max),
    }
    where = (
        f"{next(iter(mine))} 경로당 · 마을회관 가운데 격자"
        if len(mine) == 1
        else f"동 {len(rows)}곳 격자 중 가장 센 값"
    )
    s = (
        f"{region} {day}({call}) 기상청 단기예보({issued} 발표, {where}): "
        f"최저 {v['tmin']}℃ · 최고 {v['tmax']}℃ · 비 {v['rain']}mm · 새로 쌓인 눈 {v['snow']}cm"
        + (f" · 비 올 확률 {v['pop']}%" if v["pop"] is not None else "")
    )
    over = []
    for kind, (col, op, th, unit) in data.weather().get("thresholds", {}).items():
        x = v.get(col)
        if x is not None and (x >= th if op == ">=" else x <= th):
            n = sum(
                1
                for r in rows
                if r.get(col) is not None and (r[col] >= th if op == ">=" else r[col] <= th)
            )
            tail = f", {len(rows)}곳 중 {n}곳" if len(rows) > 1 else ""
            over.append(
                f"{kind} 기준({col_word(col)} {th:g}{unit} {'이상' if op == '>=' else '이하'}) "
                f"넘음{tail}"
            )
    return s + (f" — {', '.join(over)}" if over else "")


def _day_line(region: str, info: dict, day: str, call: str) -> str:
    r = info["regions"].get(region) or {}
    v = (r.get("days") or {}).get(day)
    period = info.get("period") or ["", ""]
    if not v:
        return (
            f"{region} {day} 관측 기록은 이 자료에 없음"
            f"(관측 기록은 {period[0]} ~ {period[1]}, {r.get('station', '')})"
        )
    over = []
    for kind, (col, op, th, unit) in info.get("thresholds", {}).items():
        x = v.get(col)
        if x is not None and (x >= th if op == ">=" else x <= th):
            over.append(
                f"{kind} 기준({col_word(col)} {th:g}{unit} {'이상' if op == '>=' else '이하'}) 넘음"
            )
    s = (
        f"{region} {day}({call}) 관측({r.get('station', '')}): "
        f"최저 {v['tmin']}℃ · 최고 {v['tmax']}℃"
        f" · 비 {v['rain']}mm · 새로 쌓인 눈 {v['snow']}cm"
    )
    return s + (f" — {', '.join(over)}" if over else "")


def col_word(col: str) -> str:
    return {"rain": "하루 비", "tmin": "최저기온", "snow": "새로 쌓인 눈", "tmax": "최고기온"}[col]


def _kind_days(
    region: str, info: dict, kind: str, until: date, span: tuple[date, date, str] | None = None
) -> str:
    """그 날씨 기준을 넘은 날(관측). until = 비서의 오늘, span = (첫날, 끝날, 부르는 말).

    【판단】 10-26 weather_16 T13: 되감기(오늘 = 2025-12-31)인데 그 뒤 2026년 관측까지 목록에 섞여
           '하반기'를 2025 · 2026으로 판마다 다르게 읽었다 → 오늘 뒤는 자르고, '하반기'처럼 기간을
           말하면 그 기간만 센 줄을 따로 준다(_half_span)
    """
    col, op, th, unit = info["thresholds"][kind]
    days = info["regions"].get(region, {}).get("days", {})
    # 【판단】 넘은 날마다 그날 값과 가장 심한 날을 함께 준다(10-15 페르소나 q02 T4: 날짜만 줘서
    #        '날짜별 최저기온은 자료에 없어요'라는 틀린 말이 나감 — 관측 기록은 날마다 있다)
    period = list(info.get("period") or ["", ""])
    end = min(until, span[1]).isoformat() if span else until.isoformat()
    period[1] = min(period[1], end) if period[1] else end
    start = span[0].isoformat() if span else ""
    if span:
        if period[0] and end < period[0]:
            # 0일이 아니라 그 기간 관측이 없다(자료는 2025-07부터)
            return f"{region} {span[2]}은 관측 자료가 없음(관측 기록은 {period[0]}부터)"
        period[0] = max(period[0], start)
    cut = 5 if period[0][:4] == period[1][:4] else 0  # 해가 넘어가면 해까지 적는다
    hits = [
        (d[cut:], v[col])
        for d, v in sorted(days.items())
        if start <= d <= end
        and v.get(col) is not None
        and (v[col] >= th if op == ">=" else v[col] <= th)
    ]
    when = f"{span[2]}({period[0]} ~ {period[1]})" if span else f"{period[0][:7]} ~ {period[1][:7]}"
    head = (
        f"{region} {when} {kind} 기준"
        f"({col_word(col)} {th:g}{unit} {'이상' if op == '>=' else '이하'})을 넘은 날 {len(hits)}일"
    )
    word = {"tmin": "가장 낮은 날", "tmax": "가장 높은 날"}.get(col, "가장 많은 날")
    if span:
        # 【판단】 10-26 예상 질문 2-15 '지난 12월에 제일 추웠던 날': 기준을 넘지 않았어도
        #        그 기간에서 가장 심한 날은 관측 기록에 있다(없다고 답했음)
        seen = [
            (d[cut:], v[col])
            for d, v in sorted(days.items())
            if start <= d <= end and v.get(col) is not None
        ]
        if seen:
            top = max(seen, key=lambda x: x[1]) if op == ">=" else min(seen, key=lambda x: x[1])
            head += f". 이 기간 {word}은 {top[0]}({top[1]:g}{unit}, 기준과 상관없이)"
    if not hits:
        return head
    worst = max(hits, key=lambda x: x[1]) if op == ">=" else min(hits, key=lambda x: x[1])
    # 【판단】 10-20 페르소나 o01 · h02 r2: 넘은 날 41일 목록이 묻지 않은 답마다 붙었다. 가장 최근
    #        다섯 날과 가장 심한 날만(그날 값을 물으면 그날 줄이 따로 간다)
    shown = hits[-5:]
    rest = len(hits) - len(shown)
    return (
        head
        + ": 가장 최근 "
        + " · ".join(f"{d}({v:g}{unit})" for d, v in shown)
        + (f" 외 {rest}일" if rest > 0 else "")
        + ("" if span else f". {word}은 {worst[0]}({worst[1]:g}{unit})")
    )


def _condition_rows(name: str, d: dict, p: dict | None, b: dict | None, w: str) -> list[str]:
    """그 날씨에서 함께 볼 이 동 자료.

    공개 자료에서 날씨에 맞춰 코드가 고른다(해석은 붙이지 않는다).
    """
    rows: list[str] = []
    s80 = d.get("solo80")
    if s80:
        rows.append(f"80세 이상 1인세대(주민등록 {B.reg()}): {s80['n']:,}명")
    h = d.get("housing") or {}
    if w == "비" and h:
        rows.append(f"지하층이 있는 30년 넘은 저층 주거 건물 {h['basement_old']:,}채")
    if w in ("비", "눈", "추위") and h:
        rows.append(
            f"30년 넘은 계단 집(승강기 없는 3~5층) {h['old_walkup_units']:,}가구"
            f"({h['old_walkup_share']:.0%})"
        )
    if w in ("추위", "더위") and p:
        rows.append(f"경로당 · 마을회관 {len(p['halls']['list'])}곳")
    if w == "더위" and p:
        meals = p.get("meals") or []
        rows.append(
            "무료급식소: "
            + (" · ".join(m["name"] for m in meals) if meals else f"{_unit(name)} 안에 없음")
        )
    if w in ("눈", "비") and d.get("diag"):
        rows += [s for s in d["diag"]["signals"] if "약국까지" in s or "버스 노선" in s]
    if w in ("눈", "비") and b:
        low = [
            f"{r['no']}(하루 약 {r['per_day']}번)" for r in b["routes"] if (r["per_day"] or 99) <= 3
        ]
        if low:
            rows.append("이 곳을 지나는 하루 3번 이하 마을버스: " + " · ".join(low))
    return rows


def _weather_facts(slots: Slots, data: DongData, f: Facts) -> None:
    """날씨 칸이 켜졌을 때 — 관측 기록(그 지역) + 그 날씨에서 함께 볼 동 자료."""
    info = data.weather()
    if not info:
        f.notes.append("날씨 관측 자료 파일이 없어요")
        return
    regions = list(dict.fromkeys(data.dong(n)["region"] for n in slots.dongs if data.dong(n)))
    regions = regions or [slots.region or "강남구"]
    today_, rewind = _today()
    day, call = _when(slots.period, today_)
    ahead = (date.fromisoformat(day) - today_).days
    w = slots.weather or "날씨"
    for region in regions:
        names = tuple(n for n in slots.dongs if (data.dong(n) or {}).get("region") == region)
        if rewind and ahead > 0:
            f.lines.append(
                f"{region} {day}({call}) — 되감기(오늘 = {today_}) 중이라 그 뒤 날씨는 없음"
            )
        elif rewind:
            f.lines.append(_day_line(region, info, day, call))
        elif 0 <= ahead <= AHEAD:
            f.lines.append(_forecast_line(region, names, data, day, call))
        elif ahead > AHEAD:
            f.lines.append(
                f"{region} {day}({call})은 아직 예보가 없음(기상청 단기예보는 오늘부터 사흘까지)"
            )
        else:
            f.lines.append(_day_line(region, info, day, call))
        if w in WEATHER_KIND:
            if span := _span(slots.period, today_):
                f.lines.append(_kind_days(region, info, WEATHER_KIND[w], today_, span))
            f.lines.append(_kind_days(region, info, WEATHER_KIND[w], today_))
    if w in WEATHER_KIND:
        for name in slots.dongs[:MAX_DONGS]:
            d = data.dong(name)
            if d is None:
                continue
            rows = _condition_rows(name, d, data.places(name), data.bus(name), w)
            if rows:
                f.lines.append(f"[{d['region']} {name}] {w}일 때 함께 볼 이 동 자료")
                f.lines += [f"- {r}" for r in rows]
    # 【판단】 관측소 안내는 물은 지역 것만(춘천을 물었는데 강남 관측소 안내가 붙지 않게)
    words = {"강남구": "강남", "춘천시": "춘천"}
    for n in info.get("notes", []):
        tagged = [r for r, k in words.items() if k in n]
        if not tagged or set(tagged) & set(regions):
            f.notes.append(n)
    if slots.dongs:
        # 【판단】 10-13 날씨 r8 T2: '역삼1동은 이 자료에 없어요'로 시작했다 — 동마다 나눈 관측이
        #        없다는 것을 사서가 먼저 밝힌다
        f.notes.append("날씨는 동마다 나눈 관측이 없어 구 · 시 관측소 값으로 답함")
    f.memo = (f.memo + " / " if f.memo else "") + f"날씨 {w}"


def _datasets(slots: Slots, data: DongData, f: Facts) -> None:
    """원문 자료 — 취약 돌보미가 쓰는 공개 자료 목록(이름 · 만든 곳 · 기준 · 이용 조건 · 받는 곳).

    【판단】 10-08 팀장 장면 ②("보건복지부 최근 자료 뭐 있어?" → 이름과 성질을 짧게 → 필요한 것을
           파일로). 목록에 없는 자료를 지어내지 않게 목록 파일(data/public/datasets.json)만 옮긴다.
           대회 제공 자료는 목록에도 넣지 않는다
    """
    ds = data.datasets()
    items = ds.get("items", [])
    if slots.region:
        items = [x for x in items if slots.region in x["regions"]]
    for x in items:
        where = x.get("url") or "이름의 포털 번호로 찾기"
        f.lines.append(
            f"{x['name']} — 만든 곳 {x['by']} · 기준 {_basis_now(x, data)} · "
            f"이용 조건 {x['license']}"
            f" · 받는 곳 {where} · 취약 돌보미에서 쓰는 것: {x['what']}"
        )
    if ds.get("share"):
        f.notes.append(ds["share"])
    f.memo = f"{slots.region or '두 지역'} 자료 목록 {len(items)}개"


# 【판단】 10-26 멘토 답 반영 측정(rules_v6_16 T4 세 번): '수서동 혼자 사는 할아버지'에 서울시 현황
#        남성 1,548명 줄이 맨 앞에 있었는데도 두 번은 '드릴 수 없어요 · 자료에 없어요'. 그 줄이 물은
#        것의 답이라는 표시가 없어 AI가 '혼자 사는 할아버지'와 '독거노인 현황 남성'을 잇지 못했다.
#        물은 조건(성별 · 나이)이 다 든 첫 줄에 코드가 표시를 붙인다(Anthropic 'Building effective
#        agents' — 실수하기 어렵게 인자 · 결과를 짜라. 에이전트 반복 대신 코드가 정확히 고른다)
ASKED_MARK = "물은 조건에 맞는 값 — "


def mark_asked(f: Facts, slots: Slots) -> None:
    """물은 성별 · 나이가 모두 든 첫 자료 줄에 ASKED_MARK 를 붙인다(없으면 그대로)."""
    want = []
    if slots.sex in SEX_WORD:
        want.append(SEX_WORD[slots.sex])
    if slots.ages and slots.ages.lo in (65, 80) and slots.ages.hi is None:
        want.append(f"{slots.ages.lo}세 이상")
    if not want:
        return
    for i, line in enumerate(f.lines):
        if (line.startswith("[") and line.endswith("]")) or ASKED_MARK in line:
            continue
        if all(w in line for w in want):
            body = line[2:] if line.startswith("- ") else line
            f.lines[i] = ("- " if line.startswith("- ") else "") + ASKED_MARK + body
            return


def gather_all(
    topics: tuple[str, ...], slots: Slots, data: DongData, asked: str = ""
) -> list[Facts]:
    """주제마다 사실 묶음 — 물은 조건에 맞는 줄에 표시(mark_asked)."""
    out = _gather_all(topics, slots, data, asked)
    for f in out:
        mark_asked(f, slots)
    return out


def _gather_all(
    topics: tuple[str, ...], slots: Slots, data: DongData, asked: str = ""
) -> list[Facts]:
    """주제마다 사실 묶음.

    【판단】 10-20 r1 T9 '걱정이 겹친 동 중에 경로당이 적은 곳은요?': 지역 판단(outlook, 동 없음)과
           동 주제(senior_hall)를 함께 물으면 동 주제가 동 없이 비어 '경로당 자료가 비어 있다'는
           틀린 말이 나갔다 → 동 주제는 겹친 걱정이 많은 동들(지역 판단의 위쪽)로 꺼낸다
    """
    if "outlook" in topics and not slots.dongs and slots.region:
        others = [t for t in topics if t != "outlook" and BY_ID[t].needs == "dong"]
        if others:
            from src.assistant import conditions as C

            target = "청년" if slots.target == "청년" else "어르신"
            tops = C.region_top(slots.region, target, data)[:MAX_DONGS]
            if tops:
                some = slots.model_copy(update={"dongs": tuple(tops)})
                return [gather(t, some if t in others else slots, data, asked) for t in topics]
    # 【판단】 10-25 페르소나 cli1 오린 T5: '강남구 22개 동이랑 춘천시 25개 읍면동 비교하면 어디가
    #        더 심각합니까'에 지역 칸이 강남구로 남아 강남 자료만 갔고, 글쓴이가 '춘천시는 자료에
    #        없어'(틀린 말)라고 했다. 두 지역을 견주자는 말이면 두 지역 자료를 다 주고, 같은 잣대
    #        숫자를 붙인다
    # 【판단】 10-25 페르소나 cli4 오린 T7: '개포3동은 … 쓰겠습니다. … "강남구와 춘천시 비교:"
    #        뒤에 들어갈 문장'에 데스크가 앞 문장의 개포3동을 동 칸에 넣어 위 길을 건너뛰었다
    #        (개포3동 자료만 가고 '춘천시 수치가 없어 견줄 수 없다').
    #        동이 한 지역 것뿐이면 그 동 자료에 두 지역 자료를 더 준다
    #        (두 지역 동을 견주는 말이면 동끼리 견줌이라 건드리지 않는다)
    if (
        slots.compare
        and BOTH_REGIONS_TEXT.search(asked or "")
        and not _spans_regions(slots.dongs, data)
    ):
        whole = slots.model_copy(update={"dongs": ()})
        out = [gather(t, slots, data, asked) for t in topics] if slots.dongs else []
        for t in topics:
            # 취약 돌보미 판단은 두 지역을 스스로 나란히 본다(견줌 줄 · 같은 잣대 줄) — 한 번만
            if t == "outlook":
                out.append(gather(t, whole, data, asked))
                continue
            if slots.dongs and BY_ID[t].needs == "dong":
                continue
            for region in ("강남구", "춘천시"):
                out.append(gather(t, whole.model_copy(update={"region": region}), data, asked))
        out.append(_two_regions(data))
        return out
    # 【판단】 10-29 변수 시험 c01_025 '강남구와 춘천시 각각에서 … 먼저 살펴봐야 할 순서대로'
    #        (대치2동 · 후평2동도 말함): 지역 칸이 비어 '어느 지역을 볼까요?'만 되물었다 → 두 지역
    #        이름을 다 말한 줄 세우기면 지역마다 줄 세우고, 말한 동은 그 지역 묶음에 함께
    if slots.rank and not slots.region and BOTH_REGIONS_TEXT.search(asked or ""):
        out = []
        for region in ("강남구", "춘천시"):
            mine = tuple(d for d in slots.dongs if d in data.region_dongs(region))
            each = slots.model_copy(update={"region": region, "dongs": mine})
            out += [gather(t, each, data, asked) for t in topics]
        return out
    return [gather(t, slots, data, asked) for t in topics]


def _spans_regions(dongs: tuple[str, ...], data: DongData) -> bool:
    """동 칸이 두 지역에 걸쳐 있나(강남 동 · 춘천 읍면동을 함께 말함)."""
    hit = {r for r in ("강남구", "춘천시") if set(dongs) & set(data.region_dongs(r))}
    return len(hit) > 1


BOTH_REGIONS_TEXT = re.compile(r"강남[^\n]{0,25}춘천|춘천[^\n]{0,25}강남")


def _two_regions(data: DongData) -> Facts:
    """두 지역을 같은 잣대로 — 지역 전체 65세 이상 · 80세 이상 · 청년 중 혼자 사는 몫(주민등록)."""
    f = Facts(title="두 지역 나란히(같은 잣대, 주민등록)")
    people = (data.people() or {}).get("dongs") or {}
    for region in ("강남구", "춘천시"):
        rows = [people.get(n) or {} for n in data.region_dongs(region)]

        def total(key: str, rows: list[dict] = rows) -> int:
            return sum(int(r.get(key) or 0) for r in rows)

        bits = [f"{region} {len(rows)}곳"]
        for solo, pop, word in (
            ("solo65", "pop65", "65세 이상"),
            ("solo80", "pop80", "80세 이상"),
            ("solo_youth", "pop_youth", "청년(19~34세)"),
        ):
            a, b = total(solo), total(pop)
            if a and b:
                bits.append(f"{word} {b:,}명 중 1인세대 {a:,}명({round(a / b * 100)}%)")
        f.lines.append(" · ".join(bits))
    f.notes.append(
        "두 지역 자료가 모두 있다. '어느 지역 자료가 없다'고 하지 않는다. "
        "취약 돌보미 동 순위 · 진단 · 취약 돌보미 판단은 "
        "지역 안에서 따로 매긴 것이라 두 지역 중 어디가 더 심각한지를 순위로 가르지 않는다. "
        "지역끼리는 위 같은 잣대 숫자만 나란히 보이고, 판단은 하지 않는다"
    )
    return f


SEASONS = {"봄": (3, 4, 5), "여름": (6, 7, 8), "가을": (9, 10, 11), "겨울": (12, 1, 2)}
WORST = {
    "비": ("rain", max, "비가 가장 많이 온 날"),
    "눈": ("snow", max, "눈이 가장 많이 온 날"),
    "추위": ("tmin", min, "가장 추웠던 날"),
    "더위": ("tmax", max, "가장 더웠던 날"),
}


def _season_day(period: str, weather: str | None, today_: date, data: DongData):
    """'작년 여름 폭우 때' · '이번 겨울'처럼 계절로 말한 때 → 그 계절 관측에서 날씨에 맞는 하루.

    【판단】 10-20 페르소나 o06 '작년 여름 폭우 때는 춘천에서 어떻게 판단하셨어요?': 날짜로 읽지
           못해 오늘로 판단했다. 관측(weather.json)이 있는 계절이면 그 계절에서 날씨 칸에 맞는
           가장 심한 날(날씨 칸이 없으면 여름은 비, 겨울은 추위)을 그날로 본다
    """
    season = next((k for k in SEASONS if k in period), None)
    if not season or any(w in period for w in ("내년", "다음", "앞으로")):
        return None  # 앞날의 계절은 관측이 없다(날짜로 읽을 수 없다는 안내로)
    last = any(w in period for w in ("작년", "지난해", "지난"))
    year = today_.year - 1 if last else today_.year
    months = SEASONS[season]
    # 【판단】 10-20 페르소나 f01 r4 T7: 10월에 '겨울 동안 언제 다시 볼지'를 묻자 '겨울'을 지난
    #        겨울(2025-12 ~ 2026-02)로 읽어 가장 추운 날 2026-01-22로 되감았다. 3월 뒤의 '겨울'은
    #        오는 겨울이고, 아직 시작하지 않은 계절은 앞날이라 되감지 않는다(날짜로 읽을 수 없다는
    #        안내로)
    if season == "겨울":
        if last or today_.month >= 3:
            spans = [(year, 12), (year + 1, 1), (year + 1, 2)]
        else:
            spans = [(year - 1, 12), (year, 1), (year, 2)]
    else:
        spans = [(year, m) for m in months]
    if not last and all((y, m) > (today_.year, today_.month) for y, m in spans):
        return None
    keep = {f"{y}-{m:02d}" for y, m in spans}
    w = weather if weather in WORST else ("비" if season == "여름" else "추위")
    col, pick, word = WORST[w]
    info = data.weather() or {}
    days = {}
    for r in (info.get("regions") or {}).values():
        for d, v in (r.get("days") or {}).items():
            if d[:7] in keep and v.get(col) is not None and date.fromisoformat(d) < today_:
                days[d] = pick(days.get(d, v[col]), v[col])
    if not days:
        return None
    best = pick(days, key=lambda d: days[d])
    return (
        date.fromisoformat(best),
        f"'{period}'은 관측 기록에서 그 계절 {word}({best})을 오늘로 보고 판단함",
    )


def _basis_now(x: dict, data: DongData) -> str:
    """자료 목록의 '기준' — 달마다 · 날마다 바뀌는 판은 지금 판으로(10-20).

    【판단】 10-20 페르소나 o01(도청 점검) r8: 목록에는 주민등록 '2025-07 ~ 2025-12' · 계산 기준일
           '2025-12-31'이 남아 있어 '판단에 2026-09 판을 썼다'는 답과 맞지 않았다
           (목록이 손으로 쓴 옛 판)
    """
    w = (data.weather() or {}).get("period") or []
    now = {
        "jumin": f"{B.reg_prev()} · {B.reg()}(1년 전 판 · 가장 새 판)",
        "shops": B.shops(),
        "asos": f"{w[0]} ~ {w[1]}(날마다)" if len(w) == 2 else x["basis"],
        "salpim": f"동 자료 기준 {data.basis}, 주민등록 {B.reg()} 판 · '오늘'은 진짜 오늘",
    }
    return now.get(x.get("id", ""), x["basis"])


# 말뜻 · 기준을 묻는 말과 출처를 묻는 말(자료 설명 주제를 둘로 가른다, 10-20)
MEANING = re.compile(
    r"뜻|무슨 말|정의|의미|어림|이란|기준이 뭐|기준은|어떻게 (?:계산|셌|세|만들|판단)|믿을 만|단위"
)
SOURCE_ASK = re.compile(r"출처|어디서|어디 자료|자료 이름|원자료|원문|받은|받아")


_FAR_WORDS = re.compile(r"년|여름|겨울|봄|가을|다음|내년|작년|지난해|달")
REGION_COMPARE_LINE = (
    "두 지역의 몫은 지역마다 그 지역 동들끼리 견준 기준(위쪽 3분의 1)으로 센 것이라, 이 몫으로 "
    "어느 지역 어르신 · 청년이 더 힘든지 가리지 않음. 같은 잣대로 견줄 수 있는 것은 정한 "
    "기준값으로 선 '지금 닥친 걱정' · '지난 궂은 날씨 뒤 걱정'의 동 수뿐(위 '같은 잣대' 줄)"
)
# 【판단】 10-20 페르소나 o06 r5 T2 '작년 여름 폭우 때 춘천에서는 어떻게 판단하셨어요?': 데스크가
#        때 칸을 채우지 않아(period keep) 오늘로 판단하고 '작년 여름 기록은 자료에 없다'고 했다
#        (관측은 2025-07부터 있음). 때 칸이 비었고 말에 계절이 있으면 말에서 읽는다
_SEASON_SAID = re.compile(r"(작년|지난해|올해|이번|지난)\s*(봄|여름|가을|겨울)")


# 【판단】 10-20 페르소나 o01 r8: '네 겹인데 왜 겹친 걱정이 없습니까?'를 세 번 물었는데
#        설명하지 못하고 자료 목록을 내놓았다. 까닭을 물으면 서지 않은 겹침마다 까닭
#        (conditions.misses)을 준다
WHY_ASK = re.compile(
    r"왜|어째서|이유|까닭|안 서|없다(?:고|는|니)|해당(?:이|하지) 않|맞지 않|모순|앞뒤|"
    r"빼고 세|규칙|어떻게 (?:없|안)"
)
BASIS_ASK = re.compile(
    r"상대 ?기준|정한 ?기준|3분의 ?1|위쪽|어떤 게 .*기준|기준.*구분|무조건 .*걸리"
)


def _basis(slots: Slots, data: DongData, asked: str) -> list[str]:
    """상대 기준 · 정한 기준을 물으면 기준 종류 줄과, 동마다(없으면 지역에서 겹친 걱정이 많은 세 곳)
    겹침의 조건을 나눈 줄(conditions.BASIS_LINE 위 판단)."""
    from src.assistant import conditions as C

    if not BASIS_ASK.search(asked):
        return []
    target = "청년" if slots.target == "청년" else "어르신"
    names = list(slots.dongs[: C.MAX_DONGS])
    if not names:
        names = C.region_top(slots.region or "강남구", target, data)[:3]
    out = [
        "기준 종류 답의 첫 문장: 조건마다 다르고 상대 기준과 정한 기준이 섞여 있다고 말한다. "
        "'고정 기준값이다' · '상대 순위가 아니다'처럼 한쪽으로 단정하지 않는다",
        C.BASIS_LINE,
    ]
    for n in names:
        out += C.basis_lines(n, target, data)
    return out


def _why(slots: Slots, data: DongData, asked: str) -> list[str]:
    """겹친 걱정이 왜 서지 않았나 — 물은 동마다 서지 않은 겹침의 까닭(WHY_ASK 위 판단)."""
    from src.assistant import conditions as C

    if not WHY_ASK.search(asked) or not slots.dongs:
        return []
    target = "청년" if slots.target == "청년" else "어르신"
    out = [C.OVERLAP_RULE]
    for n in slots.dongs[: C.MAX_DONGS]:
        s = C.sheet(n, target, data)
        if s is not None:
            out += [f"[{s.region} {n} {target}] {m}" for m in C.misses(s, data)]
    return out


def _outlook(slots: Slots, data: DongData, f: Facts, asked: str = "") -> None:
    """【정함 10-20 팀장】 '잘 지내?' 같은 판단 질문 — 조건 창고(conditions.py)의 조건표.

    【판단】 대상을 말하지 않으면 어르신 · 청년 둘 다(비서 설계 v3: 둘 다 메인).
           때를 지난 날로 말하면 그날을 오늘로 보고 판단한다(그 뒤 날씨는 관측).
           사흘 넘게 앞은 예보가 없어 오늘로 판단하고 밝힌다
    """
    from src.assistant import conditions as C

    f.style = "outlook"
    today_, _rewind = _today()
    as_of = None
    said = _SEASON_SAID.search(asked) if not slots.period else None
    season = _season_day(
        slots.period or (said.group(0) if said else ""), slots.weather, today_, data
    )
    if season:
        as_of, why = season
        f.notes.append(why)
    elif slots.period:
        day, call = _when(slots.period, today_)
        x = date.fromisoformat(day)
        if x < today_:
            as_of = x
            f.notes.append(f"{call}({day})을 오늘로 보고 그날까지의 자료 · 관측으로 판단함")
        elif (x - today_).days > AHEAD:
            f.notes.append(
                f"{call}은 아직 예보가 없어(기상청 단기예보는 사흘) 오늘을 기준으로 판단함"
            )
        elif call == "오늘" and _FAR_WORDS.search(slots.period):
            # 【판단】 10-20 r0 T11 '내년 여름에 대치1동 어르신들 괜찮으실까요?': 날짜로 읽을 수
            #        없는 때는 오늘로 판단하고, 그때 날씨는 예보가 없다고 밝힌다
            f.notes.append(
                f"'{slots.period}'은 날짜로 읽을 수 없어 오늘을 기준으로 판단함. "
                "그때의 날씨는 예보가 없음(기상청 단기예보는 사흘까지)"
            )
    targets = (
        ["청년"]
        if slots.target == "청년"
        else (["어르신"] if slots.target == "어르신" else ["어르신", "청년"])
    )
    if slots.dongs:
        sheets = []
        for name in slots.dongs[: C.MAX_DONGS]:
            for target in targets:
                s = C.sheet(name, target, data, as_of=as_of)
                if s is None:
                    continue
                sheets.append(s)
                f.lines.append(f"[{s.region} {name} {target}]")
                f.lines += C.facts_lines(s)
                f.notes += s.notes
        if len(slots.dongs) > C.MAX_DONGS:
            f.notes.append(f"한 번에 {C.MAX_DONGS}곳까지 판단해요. 나머지는 이어서 물어봐 주세요")
        if len(sheets) > 1:
            # 【판단】 10-20 r1 T7: 두 동 모두 겹친 걱정 2가지인데 글쓴이가 '역삼1동이 더
            #        걱정'이라고 지어냈다. 견줌은 코드가 센 숫자로만 주고, 같으면 같다고 적는다
            f.lines.append(
                "견줌(겹친 걱정 수 · 해당 조건 수): "
                + " / ".join(
                    f"{s.name} {s.target} {len(s.patterns)}가지 · {len(s.hits)}개" for s in sheets
                )
            )
            if len({len(s.patterns) for s in sheets}) == 1:
                f.lines.append("겹친 걱정 수가 같아 어느 쪽이 더 걱정이라고 가르지 않음")
            else:
                top = max(sheets, key=lambda s: len(s.patterns))
                f.lines.append(f"겹친 걱정이 더 많은 곳: {top.name} {top.target}")
    else:
        # 【판단】 10-20 엔진 시도 '강남 어르신들이랑 춘천 어르신들 중에 어디가 더 힘들까요?':
        #        강남만 답했다. 견주자는 말(compare)이면 두 지역을 다 보고 견줌 줄을 코드가 센다
        regions = ["강남구", "춘천시"] if slots.compare else [slots.region or "강남구"]
        counts = []
        for region in regions:
            for target in targets:
                rl = C.region_lines(region, target, data, as_of)
                if len(regions) > 1 or len(targets) > 1:
                    f.lines.append(f"[{region} {target} 전체]")
                f.lines += rl
                tops = C.region_top(region, target, data, as_of)
                counts.append((region, target, len(tops), len(data.region_dongs(region))))
        if len(regions) > 1:
            # 10-25 페르소나 cli4 오린 T9: 이 줄만 다음 턴에 이어 주자 뜻(지역 안 상대 기준)이
            #        빠져 '자료에 상대 기준이라는 말은 없다'고 뒤집었다 → 숫자 줄이 뜻을 함께 담는다
            f.lines.append(
                "견줌(겹친 걱정이 있는 동 몫): "
                + " / ".join(
                    f"{r} {t} {n}곳 중 {k}곳, {round(k / n * 100)}%" for r, t, k, n in counts
                )
                + " (지역마다 그 지역 동들끼리 견준 몫이라 지역끼리 우열은 가리지 않음)"
            )
            # 【판단】 10-20 페르소나 o06 r5 T1: '강남 41% · 춘천 28%라 강남 어르신들이 더
            #        힘들다'고 했다가 T6에 '직접 견줄 수 없다'로 뒤집고, T9에는 그 숫자가 '자료에
            #        없다'고 했다.
            #        몫은 지역마다 그 지역 동들끼리 견준 것이라 지역끼리 우열을 가리지 않는다
            # 10-20 페르소나 f02 r10 T5 ~ T6: '한 줄로' 견줌을 물었는데 동 목록 · 날씨 · 달력이
            #        통째로
            f.notes.append(
                "두 지역을 견주는 물음이면 겹친 걱정이 있는 동 몫과 같은 잣대로 센 동 수만 쓰고, "
                "동 목록 · 날씨 · 달력은 적지 않는다. "
                "겹친 걱정이 있는 동 몫(%)으로 두 지역의 우열을 말하지 않는다"
            )
            same = []
            for r, t, _k, _n in counts:
                kc = C.kind_counts(r, t, data, as_of)
                same.append(
                    f"{r} {t}은 지금 닥친 걱정이 있는 동 {kc['now']}곳 · "
                    f"지난 궂은 날씨 뒤 걱정이 있는 동 {kc['after']}곳"
                )
            f.lines.append("같은 잣대(정한 기준값)로 견준 것: " + " / ".join(same))
            f.lines.append(REGION_COMPARE_LINE)
    f.lines.append(C.RULE_LINE)
    f.notes += list(C.NOTES)
    f.memo = "취약 돌보미 판단 " + (" · ".join(slots.dongs[:3]) or (slots.region or ""))


# 【판단】 10-20 페르소나 o01 · h02 r2: 앞 턴의 날씨 칸이 남아 자료 설명 · 표 · 현황 답에도 날씨
#        기록이 붙었다. 날씨는 동 상황 · 갈 곳 · 버스 · 집 · 경로당 · 먼저 볼 동 · 진단에만 붙인다
WEATHER_TOPICS = {
    "dong_overview",
    "places",
    "bus",
    "housing",
    "senior_hall",
    "priority",
    "diagnosis",
}


def gather(topic: str, slots: Slots, data: DongData, asked: str = "") -> Facts:
    """주제 하나의 사실 묶음. 이륙 전 체크를 통과한 뒤에만 부른다(필요한 칸이 차 있음)."""
    t = BY_ID[topic]
    f = Facts(title=t.title)
    note = _age_note(slots)
    if note:
        f.notes.append(note)
    if topic == "outlook":
        # 날씨는 조건표의 '지난 날씨 · 앞으로 날씨' 겹이 본다(따로 날씨 줄을 겹쳐 넣지 않는다)
        _outlook(slots, data, f, asked)
        f.lines += _why(slots, data, asked)
        return f
    if slots.weather and topic in WEATHER_TOPICS:
        # 【판단】 날씨는 서가가 아니라 조건(10-13 팀장). 날씨 기록 · 함께 볼 동 자료를 앞에 두고,
        #        동 상황(dong_overview)을 물었으면 그것으로 끝(긴 동 상황 전체 대신 날씨에 맞춘 줄)
        _weather_facts(slots, data, f)
        if topic == "dong_overview":
            return f
    if slots.rank and topic in RANKABLE:
        _rank_by(topic, slots, data, f, asked)
        # 【판단】 10-29 변수 시험 c01_032 '압구정동 경로당 몇 개임? 거기 포함해서 강남구 상위
        #        3곳도': 순위만 주고 끝내 '압구정동 수는 자료에 없다'(거짓) → 동을 함께 말했으면
        #        그 동의 줄도 아래에서 같이 준다(동 순위는 위 순위 줄로 충분)
        if not slots.dongs or topic == "priority":
            return f
    if topic == "priority":
        region = slots.region or "강남구"
        top = data.ranked(region)[:5]
        f.lines.append(
            f"{region} 취약 돌보미 동 순위 위쪽 5곳(공개 자료, 기준 {data.basis}, 1위가 가장 먼저 볼 동): "  # noqa: E501
            + " · ".join(f"{r}위 {n}" for r, n in top)
        )
        # 【판단】 10-20 페르소나 f02(구청 예산) r8: '취약 돌보미 동 순위는 위 5곳만 자료에 있어요'
        #        (틀린 말 — 22곳 모두 매김). 전체 순서도 준다(글쓴이는 물은 것만 고른다)
        every = data.ranked(region)
        if len(every) > len(top):
            f.lines.append(
                f"{region} 취약 돌보미 동 순위 전체({len(every)}곳): "
                + " · ".join(f"{r}위 {n}" for r, n in every)
            )
        # 【판단】 10-15 페르소나 q02: '순위가 무엇을 기준으로?'에 '기준이 없어요'(틀린 말).
        #        기준은 big-contest src/bigcon/rank_v2.py 머리말(공개 모드) 그대로
        f.lines.append(
            PRIORITY_BASIS.get(region, PRIORITY_BASIS["강남구"]) + _tie_example(region, data)
        )
        # 【판단】 10-20 페르소나 o02: 순위 · 진단 · 취약 돌보미 판단을 섞어 '보고서엔 논현1동을
        #        먼저 쓰면
        #        돼'라고 권했다가 다음 턴에 개포3동으로 뒤집었다
        f.notes.append(
            "먼저 볼 동은 이 순위(취약 돌보미 동 순위 v2) 하나로만 말한다. 진단(신호 수)과 취약 돌보미 판단"  # noqa: E501
            "(겹친 걱정)은 순위와 다른 기준이라 섞지 않고, 어느 동을 먼저 쓰라고 권하지 않는다"
        )
        # 【판단】 10-20 페르소나 o05(기자) r2 T1: '고독사 위험이 제일 큰 동'이라는 사용자 말을
        #        그대로 받아 '고독사 위험이 가장 큰 동은 개포3동'으로 답했다
        f.notes.append(
            "'고독사 위험' · '위험 순위' · '가장 위험한 동'이라는 말은 이 자료에 없다. "
            "사용자가 그렇게 물어도 '취약 돌보미 동 순위 1위'처럼 자료의 이름으로만 답한다"
        )
        # 【판단】 10-15 100턴 T90 '역삼2동은 다시 매기면 몇 위예요?': 동을 함께 물었는데
        #        위 5곳만 줘서 '역삼2동 순위는 확인되지 않아요'(틀린 말, 세 번 모두).
        #        물은 동의 순위 줄도 준다
        for name in slots.dongs[:MAX_DONGS]:
            d = data.dong(name)
            if d is not None:
                d = {**d, "_p": _people(data, name)}
                f.lines += [f"[{d['region']} {name}] {x}" for x in _rank(name, d)]
        f.memo = f"{region} " + " · ".join(f"{r}위 {n}" for r, n in top)
        return f
    if topic == "sources" and MEANING.search(asked) and not SOURCE_ASK.search(asked):
        # 【판단】 10-20 페르소나 r3(o03 · o05 · o02): '어림이 무슨 뜻이에요?' · '믿을 만해?'에
        #        자료 목록
        #        24줄이 통째로(검사에 걸리면 두 번) 나갔다. 말뜻 · 기준을 물으면 말뜻만 준다
        hit = [
            (k, v)
            for k, v in GLOSSARY
            if any(w in asked for w in re.split(r"[ ·]", k) if len(w) > 1)
        ]
        rest = [(k, v) for k, v in GLOSSARY if (k, v) not in hit]
        f.lines += _basis(slots, data, asked) + _why(slots, data, asked)
        # 10-28 페르소나 p05_a r3 T3: '겹친 걱정이 무슨 뜻'에 맞는 말이 없어 뜻 풀이 전부가 나갔다
        #        → 맞는 말이 있으면 그것만(없을 때만 전부)
        f.lines += [f"말뜻 — {k}: {v}" for k, v in (hit or rest)]
        return f
    if topic == "sources":
        f.lines += _basis(slots, data, asked) + _why(slots, data, asked)
        # 【판단】 10-15 페르소나 q03: 옛 출처 목록에는 서울시 경로당 현황 2025-06이 빠져 있었고
        #        자료마다 기준 시점이 없어 '출처는 2022인데 기준일 2025?'로 헷갈렸다
        #        → 자료 목록(기관 · 기준)으로
        regions = [slots.region] if slots.region else ["강남구", "춘천시"]
        items = [x for x in data.datasets().get("items", []) if set(regions) & set(x["regions"])]
        for x in items:
            f.lines.append(
                f"자료: {x['name']} — {x['by']}, 기준 {_basis_now(x, data)} · 쓰는 곳: {x['what']}"
            )
        if not items:
            for reg in regions:
                f.lines.append(f"{reg} 자료 출처: " + " / ".join(data.sources(reg)))
        from src.assistant import forecast as fc

        # 【정함 10-16 팀장】 '오늘'은 진짜 오늘(날씨 · 카드). 동 숫자는 자료마다의 가장 새 판
        f.lines.append(
            f"취약 돌보미의 '오늘'은 진짜 오늘({fc.today_kst().isoformat()})이고 "
            "날씨는 기상청 예보 · 관측. "
            f"동 숫자는 주민등록 {B.reg()} 판(동 자료 기준 {data.basis}), 상가 {B.shops()} 판. "
            "자료마다 기준 시점은 위와 같고, 숫자는 그 자료에서 코드가 꺼내 계산했어요"
        )
        f.lines += [f"말뜻 — {k}: {v}" for k, v in GLOSSARY]
        return f
    if topic == "usage":
        f.lines.append(
            "물어볼 수 있는 것: "
            + " · ".join(BY_ID[i].title for i in READY_IDS if BY_ID[i].needs != "none")
        )
        f.lines.append("동 이름과 대상(어르신 · 청년)을 같이 말씀해 주시면 바로 찾아 드려요")
        # 【기능 10-27】 화면 기본기 — 대화 저장 · 복사 · 멈추기 · 글자 크기 · 도움말(chat.html).
        #        chuncheon_youth_60 T47 '이 대화 내용 PDF로 저장해 줄 수 있어요?'에 '저장 기능은
        #        없다'고 답했다(10-27부터 [대화 저장]이 있다)
        f.lines.append(
            "화면에서 할 수 있는 것: 위의 [대화 저장](지금 대화를 글 파일로 내려받음) · "
            "답마다 [복사] · [도움 됐어요] · [아쉬워요] · 답을 받는 중 [멈추기] · [글자 크기] · "
            "[도움말] · [지난 대화]. 대화를 PDF로 만드는 기능은 없고(브라우저 인쇄 → PDF로 저장), "
            "동 하나의 상황은 '○○동 상황 PDF로 만들어 줘'로 문서를 만든다"
        )
        # 10-21 팀장 "보고서 어떻게 쓰는 거야? 할 때 보여 주는 것도 필요할 듯"
        f.lines.append(
            "보고서에 쓰려면 이 차례로 물으면 됨: ① '먼저 볼 동'(취약 돌보미 동 순위) ② 그 동이 왜 앞인지"  # noqa: E501
            "(순위 까닭 — 위험 구간 · 혼자 사는 몫 · 자원 공백)와 진단(고립 신호 몇 가지) ③ 숫자 표"
            "('○○ 동별로 엑셀로', 열은 '열은 A · B · C'로 고름) ④ 동 상황 문서(PDF · PPTX) ⑤ 출처와 "  # noqa: E501
            "기준일('출처가 어디예요'). 어림은 '어림'이라 적고, 개인 명단은 없음. 순위 · 진단 · 취약 돌보미 "  # noqa: E501
            "판단은 기준이 다른 세 가지라 보고서에는 순위를 쓰고 나머지는 참고로"
        )
        if asked and re.search(r"보고서|보고 ?자료", asked):
            f.notes.append(
                "보고서 쓰는 법을 물었다. 위 '보고서에 쓰려면' 줄의 차례를 그대로 적는다"
            )
        return f
    if topic == "support":
        _support(slots, data, f)
        return f
    if topic == "datasets":
        _datasets(slots, data, f)
        return f
    for name in slots.dongs[:MAX_DONGS]:
        d = data.dong(name)
        if d is None:
            continue
        d = {**d, "_p": _people(data, name)}
        if topic == "places":
            p = data.places(name)
            ph = data.pharmacies(name) if hasattr(data, "pharmacies") else None
            rows = _places(name, p, d, data.region_places(d["region"]), f, bool(ph)) if p else []
            if ph:
                rows += _pharmacy_rows(name, ph, slots, data, asked)
                # 10-27 c2 2-8 T2 '약국 먼데는 어디': 가까운 약국만 답하고 먼 마을 줄을 쓰지 않음
                if FAR_ASK.search(asked or "") and any(
                    r.startswith("약국이 먼 마을") for r in rows
                ):
                    f.notes.append(
                        "약국이 먼 곳을 물었다 — '약국이 먼 마을' 줄의 5km 넘는 마을 수와 "
                        "먼 마을로 답한다(넘는 마을이 없으면 없다고 하고 "
                        "가장 먼 마을과 거리를 적는다)"
                    )
        elif topic == "bus":
            b = data.bus(name)
            rows = _bus(name, b, data.bus_info(), f) if b else []
        else:
            rows = _one_dong(topic, name, d, slots, f, data.places(name))
            if topic in ("solo_seniors", "dong_overview"):
                rows += _share(data, name) + _region_rank(data, name, "어르신")
            if topic in ("youth", "dong_overview"):
                rows += _youth_trend(data, name) + _region_rank(data, name, "청년")
            if topic == "housing":
                rows += _village_homes(data, name) + _empty_houses(d)
        if rows:
            f.lines.append(f"[{d['region']} {name}]")
            f.lines += [f"- {r}" for r in rows]
    # 【판단】 10-25 페르소나 cli1 노엘: 청년 어림의 나이별 비율 · 계산을 물었는데 '자료에 없어요' →
    #        방법 · 근거를 물으면 실제 계산에 쓴 숫자를 한 묶음으로(youth_method.json)
    if (
        topic in ("youth", "dong_overview")
        and METHOD_ASK.search(asked or "")
        and any("거의 집에만 있는 청년 어림" in x for x in f.lines)
    ):
        regions = {(data.dong(n) or {}).get("region") for n in slots.dongs[:MAX_DONGS]}
        f.lines += _youth_method(data, sorted(r for r in regions if r))
    # 【판단】 10-29 회귀 summary_recall_24 T23 '지금까지 … 물어본 동을 숫자와 함께 정리해 줘'(6곳):
    #        자세한 줄은 4곳까지라 글쓴이가 '한 번에 4곳까지만 … 이어서 물어봐 주세요'(앞 판들은
    #        기억 줄로 채워 맞았음). 여러 동을 한 번에 물은 말에 다 답하게 다섯째 동부터는 핵심
    #        줄(그 주제의 앞 두 줄)을 요약으로 준다(갈 곳 · 버스 목록은 길어 그대로 4곳)
    more = [n for n in slots.dongs[MAX_DONGS:MORE_DONGS] if data.dong(n) is not None]
    if more and topic not in ("places", "bus"):
        for name in more:
            d = {**data.dong(name), "_p": _people(data, name)}
            rows = _one_dong(topic, name, d, slots, Facts(title=""), data.places(name))[:2]
            if rows:
                f.lines.append(f"[{d['region']} {name}] (요약)")
                f.lines += [f"- {r}" for r in rows]
        f.notes.append(
            f"다섯째 동부터는 '(요약)' 줄(핵심 숫자)만 있다 — 그 숫자로 모든 동에 답하고 "
            f"'{MAX_DONGS}곳까지만'이라고 하지 않는다"
        )
    if topic == "solo_seniors" and len(slots.dongs) > 1:
        f.lines += _sum_rows(data, list(slots.dongs[:MORE_DONGS]))
    if topic == "senior_hall" and len(slots.dongs) > 1:
        f.lines += _sum_halls(data, list(slots.dongs[:MORE_DONGS]))
    if len(slots.dongs) > MAX_DONGS and (topic in ("places", "bus") or not more):
        f.notes.append(f"한 번에 {MAX_DONGS}곳까지 보여 드려요. 나머지는 이어서 물어봐 주세요")
    return f
