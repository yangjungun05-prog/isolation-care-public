"""대화 상태와 상태 갱신 — 데스크가 제안하고 코드가 통제한다.

【기능】 apply_card(): 데스크 카드(슬롯마다 그대로 · 새 값 · 지움)를 받아
       검증 · 수명 · 우선순위를 적용해 새 상태를 돌려준다.
       상태는 불변이라 이전 상태는 그대로 남는다(되돌리기 · 시험이 쉽다).
【판단】 수명 규칙(docs/design 3-1):
       - 지역 · 동 · 대상: 바꿀 때까지 들고 간다(주제가 바뀌어도 '거기'로 부를 수 있게)
       - 나이: 대상이 바뀌면 지운다(어르신 80세 → 청년이면 뜻이 없다).
         이번 말에서 새로 말했으면 둔다
       - 때: 질문 주제가 바뀌면 지운다
       - 견주기 · 형식: 이번 질문만
       - 우선순위: 이번 말 > 지금 상태 > 회원 기본값
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from src.assistant import dongname
from src.assistant.catalog import BY_ID
from src.assistant.slots import REGIONS, TARGETS, WEATHERS, AgeRange, DeskCard, Region, Slots

# 취약 돌보미 판단 다음의 숫자 · 늘고 줄음 질문(판단 말이 없을 때만 현황 주제로)
NUMBER_ASK = re.compile(
    r"몇 ?(명|분|곳|가구|세대)|늘었|줄었|늘어났|줄어들|늘었나|작년보다|지난해보다|얼마나 늘"
)
# 【판단】 10-20 r2 · r6 chuncheon_youth_60 T51 '교동 수급자 현황은 괜찮죠?': 데스크가 '괜찮'만 보고
#        판단(outlook)으로 보냈다. '현황'에 자료 이름이 붙으면 그 현황 주제다
STATUS_OF = (
    ("수급", "livelihood"),
    ("경로당", "senior_hall"),
    ("청년", "youth"),
    ("독거", "solo_seniors"),
    ("혼자", "solo_seniors"),
)
JUDGE_ASK = re.compile(
    r"괜찮|잘 지내|어때|어떠|힘들|힘드|걱정|조심|위험|외로|버티|지내기|살기|괴로"
)


class Profile(BaseModel):
    """회원 정보 중 비서가 쓰는 것. 팀 ERD member_region(sgg_cd + 비어도 되는 dong_cd)에 해당."""

    model_config = ConfigDict(frozen=True)

    member_region: Region | None = None
    member_dong: str | None = None


class LogEntry(BaseModel):
    """다룬 질문 한 줄. '아까 그거'를 찾을 때 쓴다(코드가 기계적으로 만든다)."""

    model_config = ConfigDict(frozen=True)

    turn: int
    topic: str
    dongs: tuple[str, ...] = ()
    target: str | None = None
    # 【기능】 우리가 답한 핵심 한 줄(예: 먼저 볼 동 1~5위). '아까 3위였던 동'을 풀 때 쓴다
    note: str = ""


class TurnText(BaseModel):
    model_config = ConfigDict(frozen=True)

    turn: int
    user: str
    bot: str


class Standing(BaseModel):
    """'앞으로 ○○만'처럼 계속 쓰기로 한 조건(대상마다 하나, 10-14 문제 목록 4-3)."""

    model_config = ConfigDict(frozen=True)

    target: str
    ages: AgeRange | None = None
    sex: str | None = None

    def words(self) -> str:
        """'80세 이상 어르신' · '25~29세 청년' · '여성 어르신'."""
        parts = []
        if self.ages:
            lo, hi = self.ages.lo, self.ages.hi
            parts.append(
                f"{lo}~{hi}세"
                if lo is not None and hi is not None
                else f"{lo}세 이상"
                if lo is not None
                else f"{hi}세 이하"
            )
        if self.sex:
            parts.append("여성" if self.sex == "여" else "남성")
        return " ".join(parts + [self.target])


class TableSpec(BaseModel):
    """앞 턴에 코드가 그린 채팅 표의 모양(10-28, table_edit) — 고치는 말이 이어받는다."""

    model_config = ConfigDict(frozen=True)

    region: str
    topics: tuple[str, ...]
    dongs: tuple[str, ...] = ()
    cols: tuple[str, ...] = ()  # 보인 열(동 · 지역 뺌)
    sort: str = ""  # 줄 세운 열(없으면 동 목록 차례)
    desc: bool = True
    top: int | None = None  # 위 N곳만


class DialogueState(BaseModel):
    """한 대화의 상태 전부. 저장소에 이것 하나를 JSON 으로 쓴다."""

    model_config = ConfigDict(frozen=True)

    turn: int = 0
    profile: Profile = Profile()
    slots: Slots = Slots()
    topics: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    log: tuple[LogEntry, ...] = ()
    # 【기능】 최근 나온 동(최근 순) — (동, 마지막 턴). "거기 · 그 동"을 풀 때 데스크가 본다
    dong_seen: tuple[tuple[str, int], ...] = ()
    # 【기능】 방금 비서가 물은 것 — 이음 실측: 직전 질문 한 줄로 지시하는 말이 풀렸다
    last_question: str | None = None
    # 【기능】 되묻기 중인 칸("dong" · "region")과 그때의 주제
    pending: str | None = None
    pending_topics: tuple[str, ...] = ()
    recent: tuple[TurnText, ...] = ()
    # 【기능】 직전 자료 답(800자까지) — 글쓴이가 앞 답을 뒤집지 않게(10-15 페르소나 q03)
    last_answer: str = ""
    # 【기능】 직전 자료 답에 쓴 자료 줄(60줄까지) — 앞 답을 되짚는 말에 이어 준다
    #        (10-15 engine.carry_facts)
    last_facts: tuple[str, ...] = ()
    # 【기능】 그 전 자료 답들에 쓴 자료 줄(120줄까지, 새것부터) — 몇 턴 앞 답의 숫자를 되짚는
    #        말에도 이어 준다(10-20 페르소나 o06 r5 T9)
    older_facts: tuple[str, ...] = ()
    # 【기능】 답에서 실제로 말한 숫자의 근거 줄(80줄까지, 새것부터) — 위 120줄은 두 턴이면
    #        밀려나 네 턴 앞에 말한 '22곳 중 8곳'을 '자료에 없다'고 했다(10-25 페르소나 오린 T9)
    said_facts: tuple[str, ...] = ()
    # 【기능】 가장 최근에 가린 글의 가린 자리(앞뒤 몇 글자, 가린 말은 '[이름]'처럼 빠짐) —
    #        '무엇을 가렸나'에 코드가 답한다(10-25 페르소나 세라핀 T8 · T9, engine.mask_answer)
    masked: tuple[str, ...] = ()
    # 【기능】 계속 쓰는 조건('앞으로 80세 이상 어르신만').
    #        주제가 바뀌어 나이 · 성별을 비울 때 다시 채운다
    standing: tuple[Standing, ...] = ()
    # 【기능】 바로 앞 '여러 조건 계산'에서 고른 동(보인 순서).
    #        '그중에서 · 위 3곳 합치면'이 이어 받는다(10-26 판단 층, engine._calc).
    #        다른 자료 답이 나오면 비운다
    last_calc: tuple[str, ...] = ()
    # 앞 계산 조건(사람이 읽는 꼴) — 다음 계획기에게 '같은 기준'을 알려 준다(10-26)
    last_calc_conds: tuple[str, ...] = ()
    # 【기능 10-27 팀장】 세션 제목 — "각 세션마다 제목을 정할 수 있게 해줘. 만일 안정해져있다면
    #        세션의 제목을 '사용자의 첫 대화 문장'으로". title 은 사용자가 정한 것, first 는 첫 질문
    #        (가린 뒤의 글, 막은 질문은 넣지 않음). since 는 이 세션이 시작한 턴 — 앞 세션을 이어
    #        만든 세션은 턴 번호를 이어 쓰므로 '이 세션의 대화 수'는 turn - since
    title: str = ""
    first: str = ""
    since: int = 0
    # 【기능】 10-27 밤: '근거 보여 줘' 안내를 이 세션에서 이미 했음
    #        (최근 원문은 200자로 잘려 꼬리를 못 봄)
    tail_shown: bool = False
    # 【기능 10-28】 앞 턴에 코드가 그린 채팅 표 · 그린 턴 — '정렬해 줘 · 열 더해 줘'가 이어받는다
    table_spec: TableSpec | None = None
    table_turn: int = 0
    # 【기능 10-28】 앞 '여러 조건 계산'의 전체 표(머리 줄 + 후보 동 모두) · 그 턴 · 지역 · 기준 —
    #        다음 턴의 '엑셀로'가 이 표로 파일을 만든다(p09_c)
    calc_sheet: tuple[tuple[str, ...], ...] = ()
    calc_turn: int = 0
    calc_region: str = ""
    calc_rules: tuple[str, ...] = ()
    # 【기능 10-28 재심사 q05_a】 이 세션의 계산 기록(턴 · 기준 · 맞은 곳, 최근 4번) — 뒤 계산이
    #        앞 기준을 덮어써 '처음 고른 8곳은 어떤 기준?'에 뒤 계산의 기준으로 답했다
    calc_log: tuple[str, ...] = ()


def new_state(profile: Profile | None = None) -> DialogueState:
    p = profile or Profile()
    dongs = (p.member_dong,) if p.member_dong else ()
    return DialogueState(profile=p, slots=Slots(region=p.member_region, dongs=dongs))


@dataclass
class Applied:
    state: DialogueState
    # 【기능】 못 정한 동 이름 — (쓴 이름, 비슷한 이름들). 이륙 전 체크가 되묻는다
    unknown_dongs: list[tuple[str, list[str]]] = field(default_factory=list)
    # 【기능】 이번 턴에 바뀐 칸 이름(시험 · 로그용)
    changed: set[str] = field(default_factory=set)
    # 【기능】 이번 턴 사용자 말(가린 뒤) — 이륙 전 체크가 낱말을 볼 때(10-28)
    said: str = ""
    # 【기능】 오타로 짐작한 동 — (쓴 이름, 정한 동). 답 앞에 '이렇게 알아들었다'고 밝힌다
    guessed: list[tuple[str, str]] = field(default_factory=list)
    # 【기능】 춘천 마을(리)을 읍면으로 읽은 것 — (쓴 이름, 읍면). 답 앞에 밝힌다(10-15)
    villages: list[tuple[str, str]] = field(default_factory=list)
    # 【기능】 계속 쓰는 조건으로 나이 · 성별을 다시 채웠으면 그 조건(답 앞에 밝힌다)
    standing_used: list[str] = field(default_factory=list)
    # 【기능】 옛 이름을 지금 이름으로 바꾼 것 — (옛 이름, 지금 이름).
    #        10-12 페르소나: 일원2동을 말없이
    #        개포3동으로 바꿔 '오작동'으로 보였다
    renamed: list[tuple[str, str]] = field(default_factory=list)


def _region_for(dongs: tuple[str, ...]) -> Region | None:
    regs = {dongname.region_of(d) for d in dongs}
    return regs.pop() if len(regs) == 1 else None  # type: ignore[return-value]


def _ages(card: DeskCard) -> AgeRange | None:
    lo = card.age_lo if 0 <= card.age_lo <= 120 else None
    hi = card.age_hi if 0 <= card.age_hi <= 120 else None
    if lo is None and hi is None:
        return None
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return AgeRange(lo=lo, hi=hi)


# 【판단】 계속 쓰기로 하는 말 · 그 조건을 푸는 말(10-14 문제 목록 4-3)
STANDING_WORD = re.compile(r"앞으로|계속|항상|이제부터|매번|언제나|늘 ")
# 【기능】 대상을 통째로 다시 말함 · 나이를 말함 · 앞에서 좁힌 무리를 가리킴
#        (10-27 apply_card 나이 풀기)
WHOLE_GROUP = re.compile(
    r"(?:혼자\s?사(?:는|시는)|독거|1인\s?(?:가구|세대))\s?(?:어르신|노인|분)|독거\s?노인|"
    r"(?:혼자\s?사(?:는|시는)|1인)\s?청년"
)
AGE_SAID = re.compile(r"\d{2}\s*(?:세|대)|여든|팔십|초고령|고령|나이|연령")
BACK_REF = re.compile(
    r"그\s?중|그\s?가운데|그분들|그 분들|그 사람들|거기서|같은 조건|그 기준|그대로"
)
STANDING_OFF = re.compile(r"상관없이|전체로|빼고|풀어|없이|다 봐|모두 봐")


def _target_of(target: str | None, ages: AgeRange | None) -> str | None:
    if target:
        return target
    if ages and ages.lo is not None and ages.lo >= 60:
        return "어르신"
    if ages and ages.hi is not None and ages.hi <= 39:
        return "청년"
    return None


# 【판단】 둘을 함께 들고 가라는 말 — 이런 말이 없으면 이번 말에 쓰인 동만 남긴다
_BOTH = re.compile(r"둘 ?다|모두|같이|함께|비교|견주|차이|랑|하고|와 |과 ")


_ROUTE = re.compile(r"^([가-힣]{2,})(\d+)(?:-\d+)?$")


def _route_like(mention: str) -> bool:
    """'사북2' · '신북3'처럼 면 이름 + 숫자는 춘천 마을버스 번호다(동 이름이 아님).

    【판단】 10-20 페르소나 h01 r8 T7: '천전1리야 사북2야 둘 중 어디가 더 드문거야?'에
           '사북2를 사북면으로 알아들었어요' → 노선 번호를 동으로 짐작하지 않는다.
           '역삼1'처럼 숫자까지 동 이름의 일부(역삼1동)면 그대로 둔다
    """
    g = _ROUTE.match(mention.replace(" ", ""))
    if not g:
        return False
    stem, num = g.group(1), g.group(2)
    if dongname.region_of(f"{stem}{num}동"):
        return False
    return any(dongname.region_of(x) == "춘천시" for x in (stem, f"{stem}면", f"{stem}읍"))


def _only_said(card: DeskCard, text: str) -> tuple[str, ...]:
    """새 동을 말하면 그 동으로 바꾼다 — 견주자는 말이 없으면 이번 말에 실제로 쓰인 동만 남긴다.

    【판단】 10-12 멘토: "세곡동 다음에 수서동이 나오면 지역 슬롯을 교체하고, '둘 다' · '비교해서'
           같은 표현이 있을 때만 두 값을 유지". 떠보기(10-12)에서 데스크가 앞 동(세곡동)을 함께 적어
           수서동 질문에 세곡동이 남은 일이 있었다. 이번 말에 동 이름이 하나도 없으면('거기')
           데스크가 기억에서 찾은 것을 그대로 쓴다.
    """
    mentions = card.dong_mentions
    if card.compare or not text or _BOTH.search(text):
        return mentions
    flat = re.sub(r"\s", "", text)
    said = tuple(m for m in mentions if re.sub(r"\s", "", m) in flat)
    return said if said else mentions


NUMBERED_DONG = re.compile(r"(?<![가-힣0-9])[가-힣]{1,3}\d동")


def apply_card(state: DialogueState, card: DeskCard, text: str = "") -> Applied:
    s = state.slots
    upd: dict = {}
    out = Applied(state=state, said=text or "")

    # ── 지역 ──
    if card.region_op == "set" and card.region in REGIONS:
        upd["region"] = card.region
    elif card.region_op == "clear":
        upd["region"] = state.profile.member_region

    # ── 동: 이름은 코드(dongname)가 정한다. 못 정하면 칸을 바꾸지 않고 되묻는다 ──
    mentions = tuple(m for m in _only_said(card, text) if not _route_like(m))
    # 【판단】 10-28 새벽 짓궂은 시험 T15 '역삼3동 어르신': 데스크가 없는 동을 칸에 넣지 않아 앞 동
    #        (삼성1 · 2동) 숫자로 답했다 → 말에 '이름+숫자+동' 꼴이 있는데 카드에 없으면 코드가
    #        넣어 되묻는다
    #        있는 동은 넣지 않는다 — '역삼1동 아닌 역삼2동'처럼 데스크가 일부러 뺀 동일 수 있다
    numbered = tuple(
        m
        for m in NUMBERED_DONG.findall(text or "")
        if m not in mentions and dongname.region_of(m) is None
    )
    if numbered:
        mentions += numbered
        card = card.model_copy(update={"dong_op": "set"})
    if card.dong_op == "set" and mentions:
        got = dongname.confirm(list(mentions), upd.get("region", s.region))
        out.unknown_dongs = got["unknown"]
        # 【판단】 오타 짐작은 틀릴 수 있다(신교동 → 신사동). 조용히 쓰지 않고 답 앞에 밝힌다
        for said, how in got["how"]:
            if how.startswith("옛 이름"):
                old, new = how[len("옛 이름(") : -1].split(" → ")
                out.renamed.append((old, new))
            if how.startswith("오타"):
                hit = dongname.resolve(said, upd.get("region", s.region))["dongs"]
                out.guessed.append((said, "·".join(hit)))
            if how.startswith("마을("):
                out.villages.append((said, how[len("마을(") : -1].split(" → ")[1]))
        if got["dongs"]:
            upd["dongs"] = tuple(got["dongs"])
            # 【판단】 동을 정하면 지역도 그 동의 지역으로 맞춘다. 두 지역 동이 섞이면 지역은 비운다
            upd["region"] = _region_for(upd["dongs"])
    elif card.dong_op == "clear":
        upd["dongs"] = ()
    if card.region_op == "set" and "region" in upd and "dongs" not in upd:
        # 【판단】 지역만 바꾸라고 했으면 그 지역에 없는 동은 칸에서 뺀다.
        #        안 빼면 '강남구'인데 칸에 춘천 효자2동이 남아 춘천 자료로 답한다
        #        (100턴 시나리오를 짜다 찾음)
        upd["dongs"] = tuple(d for d in s.dongs if dongname.region_of(d) == upd["region"])

    topics = card.topics
    if card.act == "ask" and not topics and state.topics:
        # 【판단】 "그럼 청년은?"처럼 주제를 생략하면 직전 주제를 잇는다
        topics = state.topics
    # 【판단】 10-20 r2 chuncheon_youth_60 T12: 취약 돌보미 판단(outlook) 다음 '작년보다
    #        늘었나요?'가
    #        직전 주제를 이어 판단으로 갔다. 판단 말 없이 숫자 · 늘고 줄음만 물으면 그 대상의
    #        현황 주제다(어르신 → solo_seniors, 청년 → youth)
    if tuple(topics) == ("outlook",) and NUMBER_ASK.search(text) and not JUDGE_ASK.search(text):
        who = card.target if card.target_op == "set" else s.target
        topics = ("youth",) if who == "청년" else ("solo_seniors",)
    elif tuple(topics) == ("outlook",) and "현황" in text:
        named = next((t for w, t in STATUS_OF if w in text), None)
        if named:
            topics = (named,)
    # 【판단】 10-12 멘토: "주제가 바뀌면 조건 슬롯은 비우고 계속 필요한 정보만 남기면".
    #        자료 주제가 바뀌면 나이 · 성별 · 혼자 · 때를 비운다(이번 말에서 다시 말한 것은 둔다).
    #        동 · 지역 · 대상은 '거기'로 부를 수 있게 남긴다.
    #        말뜻 · 쓰는 법 같은 곁질문은 바꾸지 않는다
    data_topics = {t for t in topics if t in BY_ID and BY_ID[t].needs != "none"}
    topic_changed = card.act == "ask" and bool(data_topics) and not data_topics & set(state.topics)

    # ── 대상 · 나이: 대상이나 주제가 바뀌면 나이를 지운다(이번 말에서 새로 말한 나이는 둔다) ──
    if card.target_op == "set" and card.target in TARGETS:
        upd["target"] = card.target
    elif card.target_op == "clear":
        upd["target"] = None
    target_changed = "target" in upd and upd["target"] != s.target
    if card.ages_op == "set":
        upd["ages"] = _ages(card)
    elif card.ages_op == "clear" or target_changed or topic_changed:
        upd["ages"] = None
    elif (
        s.ages
        and text
        and WHOLE_GROUP.search(text)
        and not AGE_SAID.search(text)
        and not BACK_REF.search(text)
        and not STANDING_WORD.search(text)
        and not any(
            x.target == _target_of(upd.get("target", s.target), s.ages) and x.ages
            for x in state.standing
        )
    ):
        # 【판단】 10-27 qbank P1-03(API): '그중에 80세 이상만 따로' 다음 '작년이랑 비교해서 혼자
        #        사는 어르신이 늘었어요?'에 80세가 남아 '알 수 없어요'로 시작했다. 대상을
        #        통째로 다시 말하고 나이 · '그중' 같은 말이 없으면 좁힌 나이를 푼다
        #        ('앞으로 ○○만'은 그대로)
        upd["ages"] = None

    # ── 성별 · 혼자 · 때 ──
    if card.sex_op == "set" and card.sex in ("남", "여"):
        upd["sex"] = card.sex
    elif card.sex_op == "clear" or topic_changed:
        upd["sex"] = None
    if card.alone_op == "set":
        upd["alone"] = card.alone
    elif card.alone_op == "clear" or topic_changed:
        upd["alone"] = None
    # 【판단】 10-20 취약 돌보미 판단(outlook)은 그날을 오늘로 보고 판단한다. 때는 그 말에만 쓴다
    #        (outlook 시험지 r0 T11 · T12: '7월 16일 폭우 때 …' 다음 '내년 여름에 …', '다 잘
    #        지내시죠?'까지 7월 16일로 판단했다)
    one_turn = "outlook" in topics
    if card.period_op == "set" and card.period.strip():
        upd["period"] = card.period.strip()[:40]
    elif card.period_op == "clear" or topic_changed or one_turn:
        upd["period"] = None
    # 【판단】 날씨 조건도 자료 주제가 바뀌면 비운다(10-13, '날씨 말고 그냥 청년은?')
    if card.weather_op == "set" and card.weather in WEATHERS:
        upd["weather"] = card.weather
    elif card.weather_op == "clear" or topic_changed:
        upd["weather"] = None

    # ── 계속 쓰는 조건('앞으로 ○○만') ──
    # 【판단】 전에는 데스크(AI)가 사실 목록을 읽어야만 지켜졌다(문제 목록 4-3).
    #        말에 '앞으로 · 계속'이 있고 이번 카드가 나이 · 성별을 정하면 그 대상의 조건으로 둔다.
    #        주제 · 대상이 바뀌어 코드가 나이 · 성별을 비울 때(이번 말에 다시 말하지 않았으면)
    #        그 조건을 다시 채우고 답 앞에 밝힌다
    standing = list(state.standing)
    tgt = upd.get("target", s.target)
    if text and STANDING_WORD.search(text):
        who = _target_of(tgt, upd.get("ages", s.ages))
        if STANDING_OFF.search(text) or card.ages_op == "clear":
            standing = [x for x in standing if who and x.target != who]
        elif who and (card.ages_op == "set" or card.sex_op == "set"):
            rule = Standing(
                target=who,
                ages=upd.get("ages") if card.ages_op == "set" else None,
                sex=upd.get("sex") if card.sex_op == "set" else None,
            )
            standing = [x for x in standing if x.target != who] + [rule]
    else:
        rule = next((x for x in standing if x.target == tgt), None)
        if (
            rule
            and rule.ages
            and card.ages_op not in ("set", "clear")
            and upd.get("ages", s.ages) is None
        ):
            upd["ages"] = rule.ages
            out.standing_used.append(rule.words())
        if (
            rule
            and rule.sex
            and card.sex_op not in ("set", "clear")
            and upd.get("sex", s.sex) is None
        ):
            upd["sex"] = rule.sex
            if rule.words() not in out.standing_used:
                out.standing_used.append(rule.words())

    # ── 이번 질문만 쓰는 칸 ──
    upd["compare"] = card.compare
    # 【판단】 10-20 페르소나 h02 r2: 22개 동 표를 받은 뒤 '19~39세로 같은 표 형식으로'에 '어느 동을
    #        볼까요?'. 같은 주제를 동 없이 이어 물으면 앞 턴의 줄 세우기를 잇는다
    carry_rank = (
        card.act == "ask"
        and not card.rank
        and card.dong_op == "keep"
        and not card.dong_mentions
        and not s.dongs
        and s.rank
        and bool(set(topics) & set(state.topics))
    )
    upd["rank"] = card.rank or carry_rank
    upd["fmt"] = card.fmt

    new_slots = s.model_copy(update=upd)
    out.changed = {k for k in upd if getattr(s, k) != getattr(new_slots, k)}
    new_topics = topics if card.act == "ask" else state.topics
    out.state = state.model_copy(
        update={"slots": new_slots, "topics": new_topics, "standing": tuple(standing)}
    )
    return out
