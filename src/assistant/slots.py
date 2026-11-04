"""슬롯(대화의 변수)과 안내 데스크 카드의 모양.

【기능】 Slots = 지금까지 정해진 칸.
       DeskCard = 데스크가 한 말을 읽고 낸 카드(슬롯마다 그대로 · 새 값 · 지움).
【판단】 데스크는 '이번 말이 상태를 어떻게 바꾸나'만 낸다.
       받아들일지 · 언제까지 들고 갈지는 state.py(코드)가 정한다.
       근거: 슬롯 넘기기(Naik 2018) · 함수 호출로 상태 추적(FnCTOD 2024). docs/research 2-3.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.assistant.catalog import DATA_IDS, TOPIC_IDS

Region = Literal["강남구", "춘천시"]
Target = Literal["어르신", "청년", "둘 다"]
Sex = Literal["남", "여"]
Fmt = Literal["답", "PDF", "PPTX", "엑셀"]
# 【기능】 날씨 조건(10-13 팀장 결정: 날씨 서가는 없애고 날씨는 동 상황의 조건으로).
#        날씨 = 날씨 자체를 물음(오늘 · 그날 기록), 비 · 눈 · 추위 · 더위 = 그 날씨일 때
Weather = Literal["날씨", "비", "눈", "추위", "더위"]
Op = Literal["keep", "set", "clear"]
Act = Literal["ask", "chitchat", "out_of_scope", "blocked", "unclear"]
Block = Literal["none", "person", "emergency"]

REGIONS: tuple[str, ...] = ("강남구", "춘천시")
TARGETS: tuple[str, ...] = ("어르신", "청년", "둘 다")
WEATHERS: tuple[str, ...] = ("날씨", "비", "눈", "추위", "더위")


class AgeRange(BaseModel):
    model_config = ConfigDict(frozen=True)

    # 【판단】 None 은 열린 끝. 65세 이상 → lo=65, hi=None
    lo: int | None = None
    hi: int | None = None


class Slots(BaseModel):
    """지금까지 정해진 칸. 불변 — 바꿀 때는 model_copy(update=...)로 새로 만든다.

    【판단】 이음(e-EUM)은 상태 dict 를 제자리에서 고쳐 저장소를 바꿀 때 7곳을 다 고쳐야 했다(조사
    3절).
    """

    model_config = ConfigDict(frozen=True)

    region: Region | None = None
    dongs: tuple[str, ...] = ()
    target: Target | None = None
    ages: AgeRange | None = None
    sex: Sex | None = None
    alone: bool | None = None
    period: str | None = None
    weather: Weather | None = None
    compare: bool = False
    # 【기능】 이번 질문만: 동 하나가 아니라 지역의 동들을 한 지표로 줄 세워 달라("○○ 많은 동")
    rank: bool = False
    fmt: Fmt = "답"


class DeskCard(BaseModel):
    """데스크 카드 한 장(데스크가 한 번 부를 때 나오는 것)."""

    model_config = ConfigDict(frozen=True)

    restate: str = ""
    act: Act = "unclear"
    topics: tuple[str, ...] = ()
    region_op: Op = "keep"
    region: str = ""
    dong_op: Op = "keep"
    dong_mentions: tuple[str, ...] = ()
    # 【기능】 10-26 팀장 '긍정 · 부정 칸': 보지 말라는 동(아니라 · 말고 · 빼고) · 머뭇거린 동
    #        (인가 · 일지도). 코드가 말과 대조한다(polarity.reconcile)
    dong_not: tuple[str, ...] = ()
    dong_unsure: tuple[str, ...] = ()
    target_op: Op = "keep"
    target: str = ""
    ages_op: Op = "keep"
    age_lo: int = -1
    age_hi: int = -1
    sex_op: Op = "keep"
    sex: str = ""
    alone_op: Op = "keep"
    alone: bool = False
    period_op: Op = "keep"
    period: str = ""
    weather_op: Op = "keep"
    weather: str = ""
    compare: bool = False
    fmt: Fmt = "답"
    new_facts: tuple[str, ...] = Field(default=(), max_length=5)
    suggest: tuple[str, ...] = ()
    block: Block = "none"
    rank: bool = False
    # 【기능】 10-26: 답하려면 여러 자료를 묶어 계산해야 하는 말(질문 받는 AI가 뜻으로 판정)
    calc: bool = False
    # 【기능】 칸에 담지 못한 조건 · 부탁(예: '기초수급 받는').
    #        비어 있지 않으면 답 앞에 코드가 밝힌다
    unmet: tuple[str, ...] = ()
    # 【기능】 말의 꼴(10-21): 말투 · 사투리와 상관없이 데스크가 뜻으로 판정. 코드 정규식은 보조
    farewell: bool = False  # 대화를 끝내는 말
    urgent: bool = False  # 어떤 사람이 지금 걱정됨(연락 끊김 · 안 보임)
    brief: bool = False  # 짧게 · 한 줄 · 결론만


# 【기능】 칸 이름(켠 칸만 적는 카드에서 '끄기'에 쓰는 이름)
SLOT_NAMES: tuple[str, ...] = (
    "region",
    "dongs",
    "target",
    "ages",
    "sex",
    "alone",
    "period",
    "weather",
)


def desk_tool_schema() -> dict:
    """데스크 strict 도구의 입력 스키마 — 켠 칸만 적는다(10-12 v6).

    【판단】 10-12 팀장: "필수로 채워야 하는 칸이 있고 나머지는 선택" ·
           "1번 3번 4번 8번 9번이 On되면
           이걸로". 전에는 23칸을 매번 다 적어 '고마워요'에도 약 580토큰 · 3초였다.
           그냥 선택으로만 바꾸면 값은 적고 '바꿈' 표시(*_op)를 빼먹었다(세곡동 · 대치1동 · 비교).
           그래서 표시 칸을 없앴다: 값을 적으면 켜짐(바꿈), 지울 칸은 off 에 이름, 안 적으면 그대로.
           필수는 restate · act · topics 셋.
    """
    props = {
        "restate": {"type": "string"},
        "act": {
            "type": "string",
            "enum": ["ask", "chitchat", "out_of_scope", "blocked", "unclear"],
        },
        "topics": {"type": "array", "items": {"type": "string", "enum": list(TOPIC_IDS)}},
        # 【판단】 고를 값이 있는 칸에는 '비움'('' · none · 답)도 둔다.
        #        v6 첫판(10-12 r9)은 block 에 none 이 없어, AI가 습관대로 block 을 적으면
        #        person · emergency 중 하나를 골라야 했다 → 평범한 질문 20턴 넘게
        #        '개인 질문' · '위급'으로 막힘. 빈 값은 '그대로'로 읽는다
        "region": {"type": "string", "enum": ["", *REGIONS]},
        "dongs": {"type": "array", "items": {"type": "string"}},
        "not_dongs": {"type": "array", "items": {"type": "string"}},
        "unsure_dongs": {"type": "array", "items": {"type": "string"}},
        "target": {"type": "string", "enum": ["", *TARGETS]},
        "age_lo": {"type": "integer"},
        "age_hi": {"type": "integer"},
        "sex": {"type": "string", "enum": ["", "남", "여"]},
        "alone": {"type": "boolean"},
        "period": {"type": "string"},
        "weather": {"type": "string", "enum": ["", *WEATHERS]},
        "compare": {"type": "boolean"},
        "rank": {"type": "boolean"},
        "calc": {"type": "boolean"},
        "fmt": {"type": "string", "enum": ["답", "PDF", "PPTX", "엑셀"]},
        "off": {"type": "array", "items": {"type": "string", "enum": list(SLOT_NAMES)}},
        "unmet": {"type": "array", "items": {"type": "string"}},
        "new_facts": {"type": "array", "items": {"type": "string"}},
        "suggest": {"type": "array", "items": {"type": "string", "enum": list(DATA_IDS)}},
        "block": {"type": "string", "enum": ["none", "person", "emergency"]},
        "farewell": {"type": "boolean"},
        "urgent": {"type": "boolean"},
        "brief": {"type": "boolean"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["restate", "act", "topics"],
        "properties": props,
    }


def _op() -> dict:
    return {"type": "string", "enum": ["keep", "set", "clear"]}


def desk_tool_schema_v5() -> dict:
    """10-12 v5까지의 스키마(23칸 다 필수 · *_op 표시). 견줌 시험용으로만 남긴다."""
    props = {
        "restate": {"type": "string"},
        "act": {
            "type": "string",
            "enum": ["ask", "chitchat", "out_of_scope", "blocked", "unclear"],
        },
        "topics": {"type": "array", "items": {"type": "string", "enum": list(TOPIC_IDS)}},
        "region_op": _op(),
        "region": {"type": "string", "enum": ["", *REGIONS]},
        "dong_op": _op(),
        "dong_mentions": {"type": "array", "items": {"type": "string"}},
        "target_op": _op(),
        "target": {"type": "string", "enum": ["", *TARGETS]},
        "ages_op": _op(),
        "age_lo": {"type": "integer"},
        "age_hi": {"type": "integer"},
        "sex_op": _op(),
        "sex": {"type": "string", "enum": ["", "남", "여"]},
        "alone_op": _op(),
        "alone": {"type": "boolean"},
        "period_op": _op(),
        "period": {"type": "string"},
        "compare": {"type": "boolean"},
        "fmt": {"type": "string", "enum": ["답", "PDF", "PPTX", "엑셀"]},
        "new_facts": {"type": "array", "items": {"type": "string"}},
        "suggest": {"type": "array", "items": {"type": "string", "enum": list(DATA_IDS)}},
        "block": {"type": "string", "enum": ["none", "person", "emergency"]},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(props),
        "properties": props,
    }


def _clean_common(raw: dict) -> dict:
    return {
        "restate": str(raw.get("restate", "")),
        "act": raw.get("act", "unclear"),
        "topics": tuple(t for t in raw.get("topics", []) if t in TOPIC_IDS)[:3],
        "suggest": tuple(dict.fromkeys(t for t in raw.get("suggest", []) if t in DATA_IDS))[:2],
        "new_facts": tuple(str(f).strip()[:80] for f in raw.get("new_facts", []) if f)[:5],
        "compare": bool(raw.get("compare", False)),
        "rank": bool(raw.get("rank", False)),
        "calc": bool(raw.get("calc", False)),
        "unmet": tuple(str(u).strip()[:40] for u in raw.get("unmet", []) if str(u).strip())[:3],
        "block": raw.get("block") or "none",
        "fmt": raw.get("fmt") or "답",
        "farewell": bool(raw.get("farewell", False)),
        "urgent": bool(raw.get("urgent", False)),
        "brief": bool(raw.get("brief", False)),
    }


def card_from_tool(raw: dict) -> DeskCard:
    """도구 입력(dict) → DeskCard(칸마다 keep · set · clear).
    목록 밖 주제 · 너무 많은 사실은 거른다.

    【기능】 켠 칸만 적는 카드(v6): 값이 있으면 set, off 에 있으면 clear, 없으면 keep.
           옛 카드(*_op 가 있는 v5)도 그대로 받는다.
    """
    data = _clean_common(raw)
    if any(k.endswith("_op") for k in raw):  # v5 카드
        for k in ("region", "target", "sex", "period"):
            data[f"{k}_op"], data[k] = raw.get(f"{k}_op", "keep"), raw.get(k, "")
        for k in ("dong", "ages", "alone"):
            data[f"{k}_op"] = raw.get(f"{k}_op", "keep")
        data["dong_mentions"] = tuple(str(m).strip() for m in raw.get("dong_mentions", []) if m)
        data["age_lo"], data["age_hi"] = raw.get("age_lo", -1), raw.get("age_hi", -1)
        data["alone"] = bool(raw.get("alone", False))
        return DeskCard.model_validate(data)
    off = set(raw.get("off") or [])

    def op(name: str, on: bool) -> str:
        return "set" if on else "clear" if name in off else "keep"

    region = raw.get("region") if raw.get("region") in REGIONS else ""
    dongs = tuple(str(m).strip() for m in raw.get("dongs") or [] if str(m).strip())
    target = raw.get("target") if raw.get("target") in TARGETS else ""
    lo = raw.get("age_lo") if isinstance(raw.get("age_lo"), int) else -1
    hi = raw.get("age_hi") if isinstance(raw.get("age_hi"), int) else -1
    sex = raw.get("sex") if raw.get("sex") in ("남", "여") else ""
    period = str(raw.get("period") or "").strip()
    weather = raw.get("weather") if raw.get("weather") in WEATHERS else ""
    data.update(
        region_op=op("region", bool(region)),
        region=region,
        dong_op=op("dongs", bool(dongs)),
        dong_mentions=dongs,
        dong_not=tuple(str(m).strip() for m in raw.get("not_dongs") or [] if str(m).strip()),
        dong_unsure=tuple(str(m).strip() for m in raw.get("unsure_dongs") or [] if str(m).strip()),
        target_op=op("target", bool(target)),
        target=target,
        ages_op=op("ages", lo >= 0 or hi >= 0),
        age_lo=lo,
        age_hi=hi,
        sex_op=op("sex", bool(sex)),
        sex=sex,
        # 【판단】 false 는 '안 말함'으로 본다(습관처럼 false 를 적어도 칸이 켜지지 않게)
        alone_op=op("alone", raw.get("alone") is True),
        alone=raw.get("alone") is True,
        period_op=op("period", bool(period)),
        period=period,
        weather_op=op("weather", bool(weather)),
        weather=weather,
    )
    return DeskCard.model_validate(data)
