"""동별 표 내려받기(엑셀 · CSV) — 원문 자료 서가의 '그거 엑셀로'(10-14).

【판단】 10-08 팀장 장면 ②(원문 자료: "필요한 데이터 있으세요?" → 표 · CSV · 엑셀로)와 질문 모음의
       "강남구 22개 동 독거노인 수를 동별로 엑셀로 받을 수 있어?". 숫자는 사서와 같은 동 자료에서
       코드가 옮긴다(AI가 표를 쓰지 않는다). 공개 자료만이라 출처 줄을 붙여 건넨다
【판단】 엑셀(.xlsx)과 CSV(엑셀에서 한글이 깨지지 않게 UTF-8 BOM)를 함께 만든다
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.assistant import basis as B
from src.assistant.catalog import BY_ID
from src.assistant.data_source import DongData


def _get(*keys: str) -> Callable[[dict], object]:
    def f(d: dict) -> object:
        v: object = d
        for k in keys:
            if not isinstance(v, dict) or k not in v:
                return None
            v = v[k]
        return v

    return f


def _month(key: str, which: int) -> Callable[[dict], object]:
    """{'2025-09': a, '2026-09': b}에서 앞(0) · 뒤(1) 달 값 — 달을 코드에 박지 않는다(10-19)."""

    def f(d: dict) -> object:
        v = d.get(key)
        pm = B.months(v)
        return v[pm[which]] if pm else None

    return f


def _homebound(side: str) -> Callable[[dict], object]:
    def f(d: dict) -> object:
        h = (d.get("youth") or {}).get("homebound") or {}
        if h.get("under10"):
            return "10명 아래"
        return h.get(side)

    return f


def _p(key: str) -> Callable[[dict], object]:
    """주민등록 가장 새 판 · 1년 전 판(people.json, build 가 '_p'로 붙임)."""

    def f(d: dict) -> object:
        return (d.get("_p") or {}).get(key)

    return f


def _share(solo: str, pop: str) -> Callable[[dict], object]:
    """몫(%) — 혼자 사는 수 ÷ 그 나이 주민 × 100, 반올림(10-20 페르소나 o02 r8: 표에 몫이 없어
    '몫은 자료에 없다'고 함)."""

    def f(d: dict) -> object:
        p = d.get("_p") or {}
        return round(p[solo] / p[pop] * 100) if p.get(pop) and p.get(solo) is not None else None

    return f


def _change(new: Callable[[dict], object], old: Callable[[dict], object], pct: bool = False):
    """1년 새 늘고 준 수(명) · 비율(%) — 코드가 센다(10-20 페르소나 h02 r3: 글쓴이가 증감률을
    스스로 계산해 '없는 숫자'로 막힘)."""

    def f(d: dict) -> object:
        a, b = old(d), new(d)
        if not isinstance(a, int | float) or not isinstance(b, int | float):
            return None
        if pct:
            return round((b - a) / a * 100, 1) if a else None
        return b - a

    return f


_OUTING = re.compile(r"외출·연락이 모두 적은 어르신 ([\d.]+)%")


def _outing(d: dict) -> object:
    """외출 · 연락 모두 적은 어르신 몫(%) — 진단 신호 글에서(강남만). 10-20 페르소나 f02 r4: 표에는
    없어 '없음'으로 적고 글에서는 2.5%라고 해 같은 수가 '있다 · 없다'로 흔들렸다."""
    for s in (d.get("diag") or {}).get("signals") or []:
        m = _OUTING.search(s)
        if m:
            return float(m.group(1))
    return None


def _overlaps(target: str) -> Callable[[dict], object]:
    """취약 돌보미 판단의 겹친 걱정 수(conditions, 지역 값은 캐시) — 10-20 페르소나 f02 r7:
    '동 이름 · 순위 ·
    혼자 사는 몫 · 겹친 걱정 수' 표를 달라고 했는데 열이 없었다."""

    def f(d: dict) -> object:
        from src.assistant import conditions as C

        name = d.get("_name")
        if not name:
            return None
        s = C.sheet(name, target, _DATA[0], {}) if _DATA else None
        return len(s.patterns) if s else None

    return f


_DATA: list = []


def _signals(d: dict) -> object:
    s = (d.get("diag") or {}).get("signals")
    return " / ".join(s) if s else None


# 【기능】 주제 → (열 이름, 동 자료에서 꺼내는 법). 그 지역 동에 값이 하나도 없는 열은 뺀다
COLS: dict[str, list[tuple[str, Callable[[dict], object]]]] = {
    "priority": [
        ("취약 돌보미 동 순위", _get("rank", "now")),
        ("실제 1인 가구로 고쳐 센 순위", _get("rank", "fix")),
        ("순위를 매긴 동 수", _get("rank", "of")),
        # 10-20 페르소나 f02 r10 T7 ~ T9: '위험 구간 · 혼자 사는 몫 · 자원 공백' 표를 달라는데
        #        열이 없어 글쓴이가 등수 · '없음'으로 채웠다 — 순위의 재료를 열로
        ("위험 구간(5구간 중)", _get("rank", "band")),
        ("65세 이상 중 혼자 사는 몫(%)", _share("solo65", "pop65")),
        ("자원 공백(1에 가까울수록 자원 없음)", _get("rank", "gap")),
    ],
    "diagnosis": [
        ("진단", _get("diag", "level")),
        ("해당 신호 수", _get("diag", "n")),
        ("본 신호 수", _get("diag", "of")),
        ("해당 신호", _signals),
        ("외출·연락 모두 적은 어르신(%)", _outing),
        ("겹친 걱정 수(취약 돌보미 판단, 어르신)", _overlaps("어르신")),
    ],
    "solo_seniors": [
        ("65세 이상 1인세대 {prev}", _month("solo65", 0)),
        ("65세 이상 1인세대 {reg}", _month("solo65", 1)),
        ("80세 이상 1인세대 {reg}", _get("solo80", "n")),
        ("실제로 혼자 사는 65세 이상 어림(아래)", _get("solo65_est", "lo")),
        ("실제로 혼자 사는 65세 이상 어림(위)", _get("solo65_est", "hi")),
        ("노인복지시설 정원", _get("solo80", "care_cap")),
        ("65세 이상 1인세대 1년 새 증감(명)", _change(_month("solo65", 1), _month("solo65", 0))),
        (
            "65세 이상 1인세대 1년 새 증감률(%)",
            _change(_month("solo65", 1), _month("solo65", 0), pct=True),
        ),
        ("65세 이상 주민 {reg}", _p("pop65")),
        ("65세 이상 중 혼자 사는 몫(%)", _share("solo65", "pop65")),
        ("취약 돌보미 동 순위", _get("rank", "now")),
        ("진단 해당 신호 수", _get("diag", "n")),
        ("외출·연락 모두 적은 어르신(%)", _outing),
        ("겹친 걱정 수(취약 돌보미 판단, 어르신)", _overlaps("어르신")),
        # 10-21 r14 오린 T5: '순위 · 위험 구간 · 자원 공백' 표를 혼자 사는 어르신 주제로 달라고 해
        #        열이 없어 4위부터 '-' → 순위 재료 열을 여기에도
        ("위험 구간(5구간 중)", _get("rank", "band")),
        ("자원 공백(1에 가까울수록 자원 없음)", _get("rank", "gap")),
    ],
    "seoul_lonely": [
        ("서울시 독거노인 2023", _get("seoul_lonely", "2023")),
        ("서울시 독거노인 2024", _get("seoul_lonely", "2024")),
        ("서울시 독거노인 2025", _get("seoul_lonely", "2025")),
        ("그중 기초생활수급권자 2025", _get("seoul_lonely_kind", "2025", "수급")),
        ("그중 저소득 2025", _get("seoul_lonely_kind", "2025", "저소득")),
        ("그중 일반 2025", _get("seoul_lonely_kind", "2025", "일반")),
        ("80세 이상 독거노인 2025", _get("seoul_lonely_kind", "80+", "2025")),
    ],
    "livelihood": [
        ("기초생활수급자(명)", _get("livelihood", "people")),
        ("기초생활수급 가구", _get("livelihood", "households")),
        ("주민 100명당 수급자", _get("livelihood", "per100")),
        ("수급자 기준 해", _get("livelihood", "year")),
        ("수급자 지난해(명)", _get("livelihood", "prev")),
        ("수급권자 독거노인 2024", _get("seoul_lonely_kind", "2024", "수급")),
        ("수급권자 독거노인 2025", _get("seoul_lonely_kind", "2025", "수급")),
        ("빈집", _get("empty_houses", "n")),
    ],
    "youth": [
        ("청년(19~34세) {reg}", _get("youth", "total")),
        ("19~24세", _get("youth", "bands", "19-24")),
        ("25~29세", _get("youth", "bands", "25-29")),
        ("30~34세", _get("youth", "bands", "30-34")),
        ("청년 1인세대 {prev}", _p("solo_youth_prev")),
        ("청년 1인세대 {reg}", _get("youth", "solo")),
        ("청년 1인세대 1년 새 증감(명)", _change(_get("youth", "solo"), _p("solo_youth_prev"))),
        (
            "청년 1인세대 1년 새 증감률(%)",
            _change(_get("youth", "solo"), _p("solo_youth_prev"), pct=True),
        ),
        ("청년 중 1인세대 몫(%)", _share("solo_youth", "pop_youth")),
        ("거의 집에만 있는 청년 어림(아래)", _homebound("lo")),
        ("거의 집에만 있는 청년 어림(위)", _homebound("hi")),
    ],
    "senior_hall": [
        ("경로당 수", _get("senior_hall", "halls")),
        ("경로당 넓이(㎡)", _get("senior_hall", "area")),
        ("65세 이상 100명당 넓이(㎡)", _get("senior_hall", "per100")),
        ("경로당 자료 해", _get("senior_hall", "year")),
    ],
    "housing": [
        ("주거 가구", _get("housing", "res_units")),
        ("30년 넘은 계단 집 가구", _get("housing", "old_walkup_units")),
        ("30년 넘은 계단 집 비율(%)", _get("housing", "old_walkup_share")),
        ("지하층이 있는 30년 넘은 저층 주거 건물", _get("housing", "basement_old")),
    ],
}
# 【판단】 동 상황(dong_overview)은 위 표의 대표 열을 모은다
COLS["dong_overview"] = (
    COLS["priority"][:1]
    + COLS["diagnosis"][:1]
    + COLS["solo_seniors"][1:3]
    + COLS["youth"][:1]
    + [("주민 수", _get("residents"))]
)
TABLE_TOPICS = tuple(COLS)
# 더하면 뜻이 없는 열(비율 · 순위 · 신호 수 · 어림 · 해 · 넓이 비율)
NOT_SUMMED = (
    "%",
    "순위",
    "신호",
    "몫",
    "어림",
    "증감률",
    "해",
    "기준",
    "100명당",
    "1,000명당",
    "동 수",
    # 10-25 페르소나 cli1 오린 T7: '위험 구간 66 · 겹친 걱정 수 13'처럼 더하면 안 되는 합계
    "구간",
    "겹친 걱정",
    "자원 공백",
)


@dataclass
class Table:
    title: str
    header: list[str]
    rows: list[list[object]]
    footer: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # 표로 만들지 않는 주제(제목)
    picked: bool = False  # 사용자가 고른 열만 남긴 표(파일 이름에 열 수를 붙임)
    # 주제마다 (주제, 그 주제의 열) — build 차례
    groups: list[tuple[str, list[str]]] = field(default_factory=list)


SORT_DESC = re.compile(r"많은 순|내림차순|높은 순|큰 순|많은 동 위|많은 쪽부터")
SORT_ASC = re.compile(r"적은 순|오름차순|낮은 순|작은 순")
# 열 목록 끝의 군더더기('다섯 개만요' · '이렇게' · '정도')
_FILLER = re.compile(
    r"^(?:\d+|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열)$"
    r"|^(?:\d+|하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열)?(?:개|가지|개만요|개면|정도|이렇게|이면|만요|정도면)"
)

# 【판단】 10-24: 한 글자 낱말을 모두 빼면 '혼자 사는 몫'의 '몫'까지 빠져 그 열을 못 찾았다
#        (r15 ⑩ 뒤 단위 시험이 빨갛던 까닭) → 수 · 군더더기 한 글자('세 개만' · '1년 새')만 뺀다
_ONE_FILLER = frozenset("새세네두한개만등및")


def _bare(h: str) -> str:
    return re.sub(r"\(.*?\)|\d{4}-\d{2}|\s", "", h)


# 【판단】 10-25 페르소나 cli1 오린 T6 ~ T8 · 노엘 T3 ~ T5: '동 이름, 취약 돌보미 동 순위, 혼자 사는
#        어르신 수, 진단, 취약 돌보미 판단 정도면 됩니다' · '… 2026-09 · 1년 증감(명) 7개 열
#        전부'처럼
#        열 목록이 '열'이라는 말보다 앞에 오거나 '열'이 없고, 열 이름과 다른 말('취약 돌보미 판단'
#        = 겹친
#        걱정 수)로 불러 고르기가 통째로 빠졌다(같은 표를 세 번 붙임) → 목록의 토막마다 열을 찾는다
COL_CUE = re.compile(r"열|항목|컬럼|정도면|면 됩니다|표만|만으로|만 넣|만 주|들어간")
# 비율 · 몫을 말한 토막은 몫(%) · 비율 열에서만 찾는다('65세 이상 1인세대 비율' ≠ 1인세대 수)
RATIO = re.compile(r"비율|몫|%|퍼센트|률")
# 열 이름과 다른 말(토막 안에 그 열 이름이 통째로 없을 때만 본다)
ALIAS: tuple[tuple[re.Pattern[str], Callable[[str], bool]], ...] = (
    (
        re.compile(r"(?:취약\s*돌보미|살핌)\s*판단|겹친\s*걱정"),
        lambda b: b.startswith("겹친걱정수"),
    ),
    (
        re.compile(r"(?:혼자\s*사(?:는|시는)|1인\s*세대|독거)[^,·/]{0,8}(?:비율|몫)"),
        lambda b: b.endswith("혼자사는몫") or b.endswith("1인세대몫"),
    ),
    (
        re.compile(r"혼자\s*사(?:는|시는)\s*(?:어르신|노인|분)|독거\s*노인\s*수"),
        lambda b: b == "65세이상1인세대",
    ),
    # '고립 신호 해당 수'처럼 낱말 순서가 달라도
    (re.compile(r"신호[^,·/]{0,5}(?:수|개수|갯수)"), lambda b: b.endswith("해당신호수")),
    (re.compile(r"순위"), lambda b: b == "취약돌보미동순위"),
    (re.compile(r"진단"), lambda b: b == "진단"),
)
_DATE = re.compile(r"\d{4}-\d{2}")


def _norm(s: str) -> str:
    """열 이름 견주기용 — 괄호 속 · 날짜 · 빈칸 · 군더더기 '새'를 뺀다
    ('1년 증감' = '1년 새 증감')."""
    return re.sub(r"\(.*?\)|\d{4}-\d{2}|\s|새", "", s)


def _named(header: list[str], text: str) -> list[str]:
    """말 속 목록의 토막마다 그 토막이 가리키는 열(말한 차례대로).

    토막 안에 열 이름이 통째로 있으면 가장 긴 것, 없으면 다른 말(ALIAS). 괄호 속
    ('진단(해당 신호 수)')을 먼저 본다. 날짜를 말하지 않았으면 가장 새 판 열
    """
    cols = header[2:]
    said = set(_DATE.findall(text))
    out: list[str] = []
    last_base = ""

    def choose(cands: list[str], dates: list[str]) -> str | None:
        if dates:
            cands = [h for h in cands if not _DATE.findall(h) or _DATE.findall(h)[0] in dates]
        elif len(cands) > 1:
            dated = [h for h in cands if _DATE.findall(h)]
            pref = [h for h in dated if _DATE.findall(h)[0] in said]
            newest = sorted(dated, key=lambda h: _DATE.findall(h)[0])[-1:]
            cands = pref or newest or cands
        return cands[0] if cands else None

    def find(piece: str, dates: list[str]) -> str | None:
        # '독거'는 1인세대('80세 이상 독거 수' = 80세 이상 1인세대)
        n = _norm(re.sub(r"독거(?:\s*노인)?", "1인세대", piece))
        if not n:
            return None
        ratio = bool(RATIO.search(piece))
        pool = [h for h in cols if bool(RATIO.search(h)) == ratio]
        whole = [h for h in pool if _norm(h) and _norm(h) in n]
        if whole:
            top = max(len(_norm(h)) for h in whole)
            return choose([h for h in whole if len(_norm(h)) == top], dates)
        # 열 이름의 뒷부분만 말함('1년 증감' → '청년 1인세대 1년 새 증감(명)', '…증감률'은 아님)
        tail = [h for h in pool if len(n) >= 3 and _norm(h).endswith(n)]
        if tail:
            return choose(tail, dates)
        for pat, ok in ALIAS:
            if pat.search(piece):
                hit = [h for h in cols if ok(_norm(h))]
                if hit:
                    return choose(hit, dates)
        return None

    # 목록이 든 문장(구분표가 가장 많은 문장) 하나만 본다 — 다른 문장의 열 이름('위험 구간 66처럼
    # 더해 놓으셨는데, 그건 빼 주세요')은 고르지 않는다
    sentences = re.split(r"(?<!\d)[.?!](?!\d)|\n", text)
    listed = max(sentences, key=lambda x: len(re.findall(r"[,·/]", x)), default="")
    for piece in re.split(r"[,·/]|\s+\|\s+|\s그리고\s", listed):
        # '… 다섯 열만으로' · '7개 열 전부'처럼 목록 끝에 붙은 말은 뗀다
        piece = re.sub(
            r"(?:\s*(?:\d+|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*개?\s*)?(?:열|항목)\S*.*$",
            "",
            piece,
        )
        dates = _DATE.findall(piece)
        if dates and not _norm(piece) and last_base:
            piece = f"{last_base} {dates[0]}"  # '청년 1인세대 2025-09 · 2026-09'의 뒤 토막
        inner = re.findall(r"\((.*?)\)", piece)
        got = next((h for h in (find(x, dates) for x in inner) if h), None)
        got = got or find(re.sub(r"\(.*?\)", "", piece), dates)
        if got and got not in out:
            out.append(got)
            last_base = _DATE.sub("", got)
    return out


# 【정함 10-29 팀장 '너무 길어 … 깔끔하게 정리해서 엑셀 표처럼'】 채팅 표는 동 + 값 3열까지만(전에는
#        8열). 나머지 열은 엑셀 파일 · '○○ 열도 보여 줘'로
CHAT_COLS = 4


_AGE_BAND = re.compile(r"^\d+~\d+세$")


def chat_view(t: Table, alone: bool | None = None) -> tuple[Table, int]:
    """채팅에 붙일 표(보일 열을 앞으로)와 보일 열 수(동 포함) — 엑셀 파일은 build 그대로.

    【판단】 10-29 브라우저 시험(담당 개포3동) '우리동 혼자사는 어르신이랑 혼자사는 청년 둘다
           작년꺼랑 같이 표로': 표는 주제 차례로 열을 이어 붙여 앞 3열이 모두 어르신 열이었고 청년은
           '안 보인 열' 줄로만 갔다(글에는 둘 다). 주제가 둘 넘으면 주제마다 앞 열을 고루(둘이면
           2열씩 — 동 + 4열) 보인다. 혼자 사는 분을 물었으면(데스크 칸 alone) 1인세대 · 혼자 열을
           먼저, 나이 구간 열(19~24세)은 뒤로. 사용자가 열을 골랐거나 주제가 하나면 그대로
    """
    if t.picked or len(t.groups) < 2:
        return t, CHAT_COLS
    per = 2 if len(t.groups) == 2 else 1
    # 혼자 사는 어르신 주제가 함께면 다른 주제도 1인세대 열로 맞춘다(같은 날 다시: 데스크가 이번
    # 말의 혼자 칸을 놓치자 청년 쪽이 '청년 전체 · 1인세대 작년'으로 골라져 올해 수가 빠짐)
    alone = alone or any(tp == "solo_seniors" for tp, _ in t.groups)

    def rank(h: str) -> tuple[bool, bool]:
        return (bool(alone) and not ("1인세대" in h or "혼자" in h), bool(_AGE_BAND.match(h)))

    lead = [h for _, g in t.groups for h in sorted(g, key=rank)[:per]][:CHAT_COLS]
    order = [0, 1] + [t.header.index(h) for h in lead]
    order += [i for i in range(2, len(t.header)) if i not in order]
    header = [t.header[i] for i in order]
    rows = [[r[i] for i in order] for r in t.rows]
    return Table(t.title, header, rows, t.footer, t.skipped, t.picked), 1 + len(lead)


def shown_header(t: Table, max_cols: int = CHAT_COLS) -> list[str]:
    """채팅에 붙는 표에 보이는 열(지역 뺌) — 글쓴이가 안 보이는 열을 '있다'고 쓰지 않게(10-25)."""
    return list(t.header[1:])[:max_cols]


def pick(t: Table, text: str) -> Table:
    """사용자가 열 이름을 말했으면 그 열만(지역 · 동은 늘), '순위'를 말했으면 첫 숫자 열로 순위 열.

    【판단】 10-20 페르소나 h02 r8 T4 ~ T9: '순위 · 동 · 청년 1인세대 2026-09 세 열만'을 다섯 번
           말했는데 파일은 늘 11열이었고 글쓴이는 '세 열만 맞아요'(거짓) · '엑셀은 만들 수 없어요'
           (거짓)라고 썼다. 열은 코드가 고른다. 열 이름에 날짜가 있으면 말한 날짜와 맞는 것만
    """
    # 열을 고르는 말('열은 · 세 열만 · 항목')이 있을 때만
    # — '청년 표'의 '청년'은 주제이지 열이 아니다
    if not re.search(r"열|항목|컬럼", text) and not (
        SORT_DESC.search(text) or SORT_ASC.search(text) or COL_CUE.search(text)
    ):
        return t
    named = _named(t.header, text)
    # 열 하나만 고른 말('동 / 해당 신호 수 두 열만' — 동은 늘 들어간다, 10-25 오린 cli3 T10)
    one = len(named) == 1 and re.search(r"(?:한|두|1|2)\s*(?:개\s*)?열|열\s*하나", text)
    if len(named) >= 2 or one:
        return _keep(t, named, text)
    flat = re.sub(r"\s", "", text)
    said_dates = set(re.findall(r"\d{4}-\d{2}", text))
    # 사용자가 적은 열 목록('열은 순위 · 동 · 청년 1인세대 2026-09 이면 됩니다') — r9 h02 T4:
    # '증감률'처럼 열 이름의 일부만 말해도 그 열을 고른다. 절반도 못 맞으면 표 전체를 준다
    m = re.search(
        r"열(?:은|:|만|이|로|로는|을)?\s*([^\n]{0,160}?)"
        r"(?:이면|정도면|입니다|이에요|면 됩니다|로요|$)",
        text,
    )
    chunks = []
    # 목록이려면 구분표(· , /)가 있어야 한다('세 열만 있는 파일로'는 목록이 아님)
    if m and re.search(r"[,·/]", m.group(1)):
        for c in re.split(r"[,·/]|\s+\|\s+", m.group(1)):
            # 괄호 속('증감(명)')은 떼고 본다 — r15 노엘 '1년 새 증감(명)' 열이 다섯 번 빠짐
            plain = re.sub(r"\(.*?\)", "", re.sub(r"\d{4}-\d{2}", "", c))
            # 군더더기 한 글자('새' · '세')는 뺀다
            # — '1년 새 증감 세 개만'이 '세'로 끝나 열이 안 맞던 것
            words = [
                w.strip(".,!?")
                for w in plain.split()
                if w.strip(".,!?")
                and w.strip(".,!?") not in _ONE_FILLER
                and not _FILLER.match(w.strip(".,!?"))
            ]
            if words and c.strip() not in ("동", "지역", "동 이름", "동이름"):
                chunks.append((words, re.findall(r"\d{4}-\d{2}", c)))
    want = []
    hit = 0
    if chunks:
        for words, dates in chunks:
            found = False
            for h in t.header[2:]:
                bare = _bare(h)
                # 여러 낱말('청년 1인세대')이면 열 이름(날짜 뺀 것)과 같을 때만,
                # 한 낱말('증감률')이면 열 이름의 일부여도 된다
                # 여러 낱말('혼자 사는 몫' · '취약 돌보미 순위')은 열 이름의 끝부분이거나
                # 낱말이 다 들어 있고 열 이름이 그보다 두 글자 넘게 길지 않을 때만
                joined = "".join(words)
                # 여러 낱말('1년 새 증감' · '혼자 사는 몫' · '취약 돌보미 순위')은 낱말이 다 들어
                #        있고
                # 마지막 낱말로 끝나는 열('…1년 새 증감' ○, '…증감률' ×)
                if len(words) > 1 and not (
                    bare.endswith(joined)
                    or (all(w in bare for w in words) and bare.endswith(words[-1]))
                ):
                    continue
                if len(words) == 1 and words[0] not in bare:
                    continue
                hd = re.findall(r"\d{4}-\d{2}", h)
                if hd and dates and hd[0] not in dates:
                    continue
                if hd and not dates and said_dates and hd[0] not in said_dates:
                    continue
                if h not in want:
                    want.append(h)
                found = True
            hit += found
        if hit * 2 < len(chunks):
            return t
    if not chunks:
        # 열 목록이 없거나('세 열만 있는 파일로') 하나도 안 맞으면 말 속의 열 이름으로
        want = []
        for h in t.header[2:]:
            bare = _bare(h)
            if not bare or bare not in flat:
                continue
            dates = re.findall(r"\d{4}-\d{2}", h)
            if dates and said_dates and dates[0] not in said_dates:
                continue
            want.append(h)
        # '청년 1인세대'를 말하면 '청년(19~34세)'(앞부분만 같은 열)은 고르지 않는다
        bares = [_bare(h) for h in want]
        want = [
            h for h, b in zip(want, bares, strict=True) if not any(b != o and b in o for o in bares)
        ]
    return _keep(t, want, text)


def _keep(t: Table, want: list[str], text: str) -> Table:
    """고른 열(비면 전체)만 남기고, 줄 세우라는 말이면 줄 세운다."""
    # 10-20 페르소나 h02 r12 T7: '많은 순(내림차순)으로 정렬된 엑셀로' — 열 목록이 없어도 줄 세운다
    asc = bool(SORT_ASC.search(text))
    explicit = asc or bool(SORT_DESC.search(text))
    want_sort = explicit or "순위" in text
    if not want and not want_sort:
        return t
    keep = [0, 1] + [t.header.index(h) for h in want] if want else list(range(len(t.header)))
    header = [t.header[i] for i in keep]
    rows = [[r[i] for i in keep] for r in t.rows]
    # 10-25 오린 T8: 순위 · 1인세대 · 진단 · 겹친 걱정 줄을 순위 차례로 원했는데 1인세대 많은 순으로
    #        섰다. 많은 순 · 적은 순을 말하지 않았고 취약 돌보미 동 순위 열이 있으면 순위 차례로
    if want_sort and not explicit and "취약 돌보미 동 순위" in header:
        k = header.index("취약 돌보미 동 순위")
        rows.sort(key=lambda r: (r[k] is None, r[k] or 0))
    elif want_sort:
        k = _sort_col(header, rows)
        if k is not None:
            rows.sort(key=lambda r: (r[k] is None, (r[k] or 0) if asc else -(r[k] or 0)))
            if "순위" in text and not any("순위" in h for h in header):
                header.insert(2, "순위")
                rows = [[*r[:2], i, *r[2:]] for i, r in enumerate(rows, 1)]
    footer = [x for x in t.footer if not x.startswith("합계(")] if want else list(t.footer)
    return Table(t.title, header, rows, footer, t.skipped, picked=bool(want))


def markdown(t: Table, max_cols: int = CHAT_COLS) -> str:
    """표를 마크다운으로(코드가 그린다 — 글쓴이가 줄을 빠뜨리거나 '-'로 채우지 않게).

    【판단】 10-21 r14 오린 T5 ~ T6 '4위부터 22위까지 위험 구간이 전부 -' · r12 노엘 '11곳만 옮길 수
           있었고': 표의 줄 수 · 숫자는 코드가 다 아는데 글쓴이가 옮기다 흘렸다 → 표 자체는 코드가
           답 아래에 붙이고 글쓴이는 한두 문장만 쓴다. 열이 많으면(고르지 않은 전체 표) 앞 열부터
    """
    header = list(t.header[1:])  # 지역은 뺀다(한 지역 표)
    rows = [list(r[1:]) for r in t.rows]
    cut = header[max_cols:]
    if cut:
        header, rows = header[:max_cols], [r[:max_cols] for r in rows]

    def cell(v: object) -> str:
        if v is None or v == "":
            return ""
        if isinstance(v, bool):
            return "예" if v else "아니요"
        if isinstance(v, int):
            return f"{v:,}"
        if isinstance(v, float):
            return f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:,.0f}"
        return str(v).replace("|", "/")

    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    # 표 아래 줄은 한 줄에 하나씩(화면이 작은 글씨로 그린다). 합계는 세 곳 넘을 때 · 보이는 열만
    foot = [x for x in t.footer if x.startswith("기준일")]
    for x in t.footer:
        if x.startswith("합계(") and len(rows) >= 3:
            head, _, items = x.partition(": ")
            got = [i for i in items.split(" · ") if any(i.startswith(h + " ") for h in header[1:])]
            if got:
                foot.append(f"{head}: " + " · ".join(got))
    # 10-25 오린 T6 ~ T7: 열이 많아 앞 열만 보였는데 말없이 잘려 '순위 · 진단 열이 없다'
    if cut:
        names = " · ".join(cut[:3]) + (f" 외 {len(cut) - 3}개" if len(cut) > 3 else "")
        foot.append(f"(안 보인 열: {names} — '○○ 열도 보여 줘'라고 하시면 붙여 드려요)")
    return "\n".join(lines) + ("\n\n" + "\n".join(foot) if foot else "")


_KO_N = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "열": 10}
_TOP_N = re.compile(
    r"(?:상위|위|top|TOP|Top)\s*(\d{1,2}|한|두|세|네|다섯|여섯|일곱|여덟|열)\s*(?:곳|개|동|군데)?"
)


def top_n(text: str) -> int | None:
    """'상위 5곳 · 위 세 곳 · top5' → 5 · 3 · 5(말하지 않았으면 None)."""
    m = _TOP_N.search(text or "")
    if not m:
        return None
    n = _KO_N.get(m.group(1)) or int(m.group(1))
    return n if 0 < n < 100 else None


def order_top(t: Table, topics: tuple[str, ...], text: str) -> Table:
    """먼저 볼 동 표는 순위 차례로, '상위 N곳'이면 그 N곳만.

    【판단】 10-26 예상 질문 1-20 '강남에서 먼저 볼 동 상위 5곳을 표로': 22곳 전체가 동 목록 차례
           (신사동이 맨 위)로 붙었다. 순위 열이 있으면 순위 차례로 세우고, 위 N곳을 말했으면 자른다.
           순위 열이 없으면 줄 세울 열(_sort_col) 많은 순으로
    """
    n = top_n(text)
    rank = next(
        (j for j, h in enumerate(t.header) if h.endswith("동 순위") and "고쳐" not in h), None
    )
    if rank is not None and "priority" in topics:
        rows = sorted(t.rows, key=lambda r: (r[rank] is None, r[rank] or 0))
    elif n:
        k = _sort_col(t.header, t.rows)
        if k is None:
            return t
        rows = sorted(t.rows, key=lambda r: (r[k] is None, -(r[k] or 0)))
    else:
        return t
    return Table(
        t.title, t.header, rows[:n] if n else rows, t.footer, t.skipped, t.picked, t.groups
    )


def _sort_col(header: list[str], rows: list[list[object]]) -> int | None:
    """줄 세울 열 — 1인세대(이번 판) 열이 있으면 그것, 없으면 첫 숫자 열."""
    for j, h in enumerate(header[2:], start=2):
        if "1인세대" in h and re.search(r"\d{4}-\d{2}", h) and "2025" not in h:
            return j
    return next(
        (j for j in range(2, len(header)) if any(isinstance(r[j], int | float) for r in rows)),
        None,
    )


def with_named_topics(topics: tuple[str, ...], text: str) -> tuple[str, ...]:
    """말한 열이 다른 주제 표에만 있으면 그 주제도 더한다(표 주제가 하나도 없으면 그대로).

    【판단】 10-25 페르소나 cli3 오린 T7 · T10: '동 이름 / … / 고립 신호 해당 수' ·
           '동 / 해당 신호 수 두 열만'을 순위 주제 표로 달라 해 신호 수 열이 없었고, 글쓴이는
           '자료에 없다'고 했다(진단 주제 표에 있음). 열 이름만 견주므로 표를 따로 만들지 않는다
    """
    if not any(t in COLS for t in topics) or not (
        re.search(r"열|항목|컬럼", text) or COL_CUE.search(text)
    ):
        return topics

    def names(tps: tuple[str, ...]) -> list[str]:
        cols = [n.format(reg=B.reg(), prev=B.reg_prev()) for t in tps for n, _ in COLS.get(t, [])]
        return ["지역", "동", *dict.fromkeys(cols)]

    have = set(names(topics))
    extra = [
        tp
        for tp in COLS
        if tp not in topics
        and tp != "dong_overview"
        and any(h not in have for h in _named(names((tp,)), text))
    ]
    return topics + tuple(extra)


def build(topics: tuple[str, ...], region: str, dongs: list[str], data: DongData) -> Table:
    """주제들 · 동들 → 표. dongs 가 비면 그 지역 모든 동."""
    use = [t for t in topics if t in COLS]
    skipped = [BY_ID[t].title for t in topics if t not in COLS and t in BY_ID]
    names = dongs or data.region_dongs(region)
    people = (data.people() or {}).get("dongs") or {}
    _DATA[:] = [data]
    profiles = [(n, data.dong(n)) for n in names]
    profiles = [
        (n, {**d, "_p": people.get(n) or {}, "_name": n}) for n, d in profiles if d is not None
    ]
    cols: list[tuple[str, Callable[[dict], object]]] = []
    groups: list[tuple[str, list[str]]] = []
    for t in use:
        groups.append((t, []))
        for name, get in COLS[t]:
            name = name.format(reg=B.reg(), prev=B.reg_prev())
            if name not in [c for c, _ in cols] and any(get(d) is not None for _, d in profiles):
                cols.append((name, get))
                groups[-1][1].append(name)
    rows = [[d["region"], n, *[get(d) for _, get in cols]] for n, d in profiles]
    title = " · ".join(BY_ID[t].title for t in use)
    srcs = [
        x
        for x in data.datasets().get("items", [])
        if region in x["regions"] and set(x["topics"]) & set(use)
    ]
    footer = [f"기준일 {data.basis} · 취약 돌보미(공개 자료로 정리)"]
    # 【판단】 10-20 페르소나 h02 r5: '22개 동 합계 행을 넣어 달라'에 글쓴이가 '합계는 자료에
    #        없어요'를 여덟 번(글쓴이는 숫자를 만들지 않는다). 사람 · 가구 · 건물 수 열은 코드가
    #        더해 적는다
    totals = []
    for i, (name, _get) in enumerate(cols, start=2):
        if any(w in name for w in NOT_SUMMED):
            continue
        vals = [r[i] for r in rows if isinstance(r[i], int | float) and not isinstance(r[i], bool)]
        if vals and len(vals) == len(rows):
            totals.append(f"{name} {sum(vals):,}")
    if totals and len(rows) > 1:
        footer.append(f"합계({len(rows)}곳, 코드가 더함): " + " · ".join(totals))
    footer += [f"출처: {x['name']} — {x['by']} · {x['license']}" for x in srcs]
    head = ["지역", "동", *[c for c, _ in cols]]
    return Table(title, head, rows, footer, skipped, groups=[g for g in groups if g[1]])


def _file_stem(region: str, title: str, basis: str) -> str:
    words = re.sub(r"[^0-9A-Za-z가-힣]+", "_", f"{region}_{title}").strip("_")
    return f"{words}_{basis}"


def save(table: Table, region: str, basis: str, folder: Path) -> list[Path]:
    """엑셀(.xlsx) · CSV 두 파일을 문서 폴더에 쓴다."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = _file_stem(region, table.title, basis)
    if table.picked:
        stem += f"_{len(table.header) - 2}열"
    out_csv = folder / f"{stem}.csv"
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(table.header)
        w.writerows(["" if v is None else v for v in r] for r in table.rows)
        w.writerow([])
        for line in table.footer:
            w.writerow([line])
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "표"
    ws.append(table.header)
    for r in table.rows:
        ws.append(["" if v is None else v for v in r])
    ws.append([])
    for line in table.footer:
        ws.append([line])
    for i, name in enumerate(table.header, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = max(8, min(40, len(name) * 2))
    out_xlsx = folder / f"{stem}.xlsx"
    wb.save(out_xlsx)
    return [out_xlsx, out_csv]
