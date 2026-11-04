"""판단 층(10-26) — 이번 말을 '바로(자료 하나 꺼내기)' · '기억(앞에서 말한 것)'
· '깊은 고민(여러 조건 · 묶어서 계산)' 가운데 어디로 보낼지 정한다.

【판단】 10-26 팀장 "사용자의 자연어를 알아듣고 '바로 내가 대답할 수 있는 것인지 = 단순
       데이터를 꺼내오는 건지, 혹은 아까 사용자가 말했던 건지'를 판단할 수 있는 것. 그리고 '더
       집중적으로 고민을 해 봐야 하는 건지' … haiku 하나로는 판단하기가 힘들 것 같은데.
       치밀하게 조직해서" — 5단계
  1) 판단: 지금은 데스크(Haiku) 카드 한 장이 다 정한다. 카드에는 줄 세우기 칸이 지표 하나뿐이라
     조건이 여럿인 말은 '바로' 길로 가서 나머지 조건이 빠진다(multi_16 엔진 9/16)
  2) 남들: 쉬운 · 흔한 질문은 Haiku 같은 작은 모델로, 어렵거나 드문 질문은
     Sonnet 같은 큰 모델로 보내는 라우팅(Anthropic 'Building effective agents'),
     싼 모델 답을 채점해 모자랄 때만 큰 모델로 올리는 계단식(FrugalGPT, arXiv 2305.05176)
  3) 환경: FrugalGPT의 채점기는 학습한 작은 모델인데 우리는 학습할 자료가 없다 → 채점기 대신 코드
     신호(지표 낱말 · 계산 말 · 앞말 참조)와 데스크 카드를 맞대 보는 규칙 · 계획 검사기를 쓴다.
     큰 모델(Sonnet)은 계획이 검사를 못 넘을 때만(깊은 고민 길에서만)
  4) 세 목소리: ① 코드 신호(0초, 늘 같음) ② 데스크 카드(Haiku, 이미 부름) ③ 계산 계획(Haiku →
     검사 → 필요하면 Sonnet). 길은 ①②를 맞대 정하고, ③이 틀리면 한 단계 올린다
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.assistant import dongname
from src.assistant.policy import dongs_in_text

# 【기능】 지표 개념 낱말(겹치지 않게 긴 것부터 지운다). 키는 query.METRICS 키
# 【판단】 10-26 route_50 r1: '80 넘은 분'(W06) · '청년 1인세대 … 증감'(P06)을 못 읽었다 → 넣음
_AGE80 = r"(80|여든|팔십)\s?(세\s?)?(이상|넘(은|는|으신)?|초과)"
CONCEPTS: tuple[tuple[str, str], ...] = (
    ("youth_homebound", r"은둔\s?(청년)?|집에만\s?있는\s?청년|고립\s?·?\s?은둔"),
    (
        "youth_solo_rise",
        r"(1인|혼자|청년).{0,15}(증감|늘었|줄었|늘어난|줄어든)",
    ),
    ("youth_solo", r"(혼자\s?사는|1인\s?(가구|세대)?)\s?청년|청년\s?1인"),
    ("youth", r"청년"),
    ("lonely_outside_share", r"사각지대|명단\s?밖|공적\s?지원\s?밖|지원\s?밖"),
    ("lonely_poor", r"(기초)?수급\s?(받는)?\s?(독거|혼자)"),
    ("livelihood", r"기초\s?수급|수급자|기초생활"),
    # 10-28 p09: '80세 이상, 여성, 혼자 사는, …' 나열 속 단독 '여성'도(계획기가 빼면 검사에 걸리게)
    (
        "lonely_female",
        r"(혼자\s?사는|독거)\s?(할머니|여성|여자)|할머니"
        r"|(?:^|[,·/]\s*)(?:여성|여자)(?=\s*(?:[,·/]|이고|이면서|그리고))",
    ),
    ("lonely_male", r"(혼자\s?사는|독거)\s?(할아버지|남성|남자)|할아버지"),
    (
        "solo80",
        _AGE80 + r".{0,8}(혼자|독거|1인)|(혼자|독거|1인).{0,10}" + _AGE80 + r"|초고령\s?(1인|독거)",
    ),
    ("pop80", _AGE80 + r"|초고령"),
    ("solo65_rise", r"(혼자|독거|1인).{0,12}(늘|증가|많아졌|증감)|새로\s?혼자"),
    (
        "solo65_share",
        r"(혼자\s?사는|독거|1인\s?가구|1인\s?세대)\s?(어르신)?\s?(의\s?)?(비율|몫|비중|%)",
    ),
    ("solo65", r"혼자\s?사(는|시는)\s?(어르신|노인|분)|독거\s?(노인|어르신)?|1인\s?(가구|세대)"),
    ("pop65", r"65세\s?이상|노인\s?인구|어르신\s?(수|인구)"),
    (
        "old_walkup",
        r"계단\s?집|엘리베이터\s?없|승강기\s?없|노후\s?(주거|주택)|낡은\s?(집|주택)|오래된\s?(집|주택)",
    ),
    ("basement_old", r"반\s?지하|지하층|지하\s?(집|방)"),
    ("halls", r"경로당|마을\s?회관"),
    ("meals", r"무료\s?급식|급식소"),
    # 10-27 마을 지표(query.VILLAGE_METRICS): '버스가 하루 5번 이하' · '버스가 드문 마을'
    ("v_bus", r"버스.{0,12}(드문|드물|적게|자주\s?안|하루\s?\d+\s?(번|회)|몇\s?번\s?(이하|안))"),
    ("pharmacy_km", r"약국.{0,6}(멀|먼|거리|km)"),
    ("pharmacies", r"약국"),
    ("clinics", r"의원|병원"),
    ("ltc_res", r"요양원|입소\s?시설|요양\s?시설"),
    ("ltc_home", r"방문\s?요양|재가|주야간\s?보호|돌봄\s?기관"),
    ("gap", r"(돌봄|생활)\s?자원|도움\s?거리|자원이?\s?(적|부족)|갈\s?곳이?\s?(적|부족)"),
    ("empty_houses", r"빈집"),
    ("diag", r"진단|신호"),
    ("risk_band", r"위험\s?구간"),
    ("priority", r"먼저\s?볼|(?:살핌|취약\s?돌보미)\s?(동\s?)?순위|동\s?순위"),
)
_CONCEPT_RE = [(k, re.compile(p)) for k, p in CONCEPTS]

# 【기능】 묶어서 계산해 달라는 말(평균 · 합 · 당 · 배 · 비교 · 기준 맞추기 · 골라 줘)
CALC = re.compile(
    r"평균|합계|합치|다\s?더하|더해|총\s?몇|모두\s?몇|명당|곳당|가구당|당\s?몇|대비|몇\s?배|비율|비중|%|"
    r"나누|소수점|정확히|증감|"
    r"조건|기준에\s?맞|해당하는|항목|가점|공모|지침|많이\s?맞|잘\s?맞|"
    r"어디부터|어느\s?(동|곳)(부터|이|을|가)|골라|추려|뽑아|묶|나란히|비교|견줘|순서대로|순으로|"
    r"(많|적|높|낮)고|(없|있)고|이면서|중에서|가운데서|"
    r"늘었|줄었|증가|감소|많아(?:졌|진)"
)
# 【기능】 앞 말의 지표를 이어 받아도 될 만큼 계산이 분명한 말(그냥 '비율'은 확인일 수 있어 뺌)
# 【판단】 route_50 r1 뒤: '정확히 무슨 뜻'(P12) · 동 하나의 '증감'(P05)은 계산이 아니라 뺌
STRONG = re.compile(
    r"합계|합산|총합|총계|합치|합쳐|다\s?더하|더해|더하면|평균|나누|소수점|명당|곳당|÷"
)
# 【기능】 말뜻 · 기준 · 출처를 묻는 말 — 지표 이름이 여럿 나와도 계산이 아니다
#        (따로 시험지 G05 · G18 · G22 · Q08: 계획기도 '바로 · 되짚기'로 봄 → 계획기를 부르지
#        않아 4 ~ 5초를 아낀다)
DEFINE = re.compile(
    r"무슨\s?뜻|뜻이\s?뭐|뜻인지|뭐가\s?달라|뭐가\s?다른|차이가\s?뭐|뭘\s?기준|무슨\s?기준|"
    r"어떤\s?기준|어디\s?기준|기준이\s?뭐|어떻게\s?(뽑|세|계산|매기|나온|정해)|어디서\s?나온|"
    r"무슨\s?지표|뭘\s?본\s?거|"
    # 10-27 hold2 G28 '…비율이에요 아니면 전체 주민 중이에요?' — 둘 중 어느 뜻이냐는 말
    r"(?:이에요|예요|인가요|입니까|이야)\s?아니면"
)
CONFIRM_ASK = re.compile(r"맞는지|맞으면|확인해\s?(?:줘|주세요|주십시오)|검토해|대조해")
CITED_NUM = re.compile(r"\d[\d,.]*\s?(?:명|곳|%|가구|세대|채|mm|km)")
# 늘고 줄음 말 — 앞 답을 따질 때 그대로 옮겨 오는 말이라 새 계산 말로 치지 않는다(hold2 G41)
CHANGE_WORD = re.compile(r"늘었|줄었|증가|감소|많아(?:졌|진)|정확히")
# 【기능】 앞 답을 따지거나 되묻는 말(10-27 hold H10 · H13 · hold2 G23 · G29 · G41 · Q17 · Q23 ·
#        route_50 P14 · P16 — 계산 · 바로 찾기로 보내면 앞 답을 다시 대지 못한다)
CHALLENGE = re.compile(
    r"(?:하셨|했|하시)잖|(?:라고|다고|이라고)\s?(?:하셨|했|하시)[^\n?]{0,3}(?:는데|어\?|어요\?|나요)|"
    r"[다라]더니|모른다며|없다며|앞뒤|반대잖|잘못\s?들었|이번\s?답은|"
    r"(?:적혀|나와|돼|되어)\s?있었는데|줄이\s?(?:아예\s?)?(?:없|빠)|빠진\s?걸|"
    r"[다라]는\s?거(?:야|예요|에요)\s?아니|한\s?번만\s?더|다시\s?(?:알려|말해)"
)
# 【기능】 줄 세우기만 바라는 말(지표 하나면 지금 길의 줄 세우기로 충분)
ORDER_ONLY = re.compile(r"순서대로|순으로|골라|추려|뽑아|많은\s?(동|곳|순)|적은\s?(동|곳|순)")
# 【기능】 일부만 보라는 말(면만 · 도심 빼고 · 퇴계동은 빼고)
# '역삼1동만'의 '동만'은 거르기가 아니다(P05) — 앞에 글자가 없는 '동만'만
SUBSET = re.compile(
    r"빼고|빼라|빼서|제외|면만|면\s?중|읍면|읍\s?·?\s?면|도심|시내\s?동|(?<![가-힣0-9])동만"
)
# 【기능】 앞에서 말한 것을 가리키는 말
REFER = re.compile(
    r"아까|방금|앞에서|앞서|위에서|위\s?\d+\s?곳|그\s?중|그중|그\s?동들?|그\s?세\s?곳|그\s?곳들|"
    r"말씀하신|말한|얘기한|이전에|지난번|그\s?숫자|그거|거기서|처음에"
)
# 【기능】 앞에서 들은 것을 다시 묻거나 맞는지 확인하는 말(새 계산 없음)
RECALL = re.compile(
    r"이었|였(지|는지|나요|죠|어요)|했던|셨던|한\s?번만\s?더|다시\s?(알려|말)|"
    r"정리하면|라는\s?거(지|죠|예요|군요)|이게\s?전부|맞(아|죠|나요|습니까|는지)\s?\??"
)
# 【기능】 가. 나. · 1) 2) 처럼 항목을 늘어놓은 말(공모 · 지침 조건)
LIST_ITEM = re.compile(r"(?m)^\s*(?:[가-사]\.|\d\)|\d\.|[①-⑨]|-)\s?\S")
# 【기능】 지역 안에서 견줘 달라는 말 — 동 하나여도 평균 · 등수가 필요해 깊은 고민
# 【판단】 route_50 r1 P05: '2025년 9월 대비 2026년 9월'은 때를 견주는 말이라 뺀다
REGION_CMP = re.compile(
    r"평균|(?<!월\s)(?<!년\s)(?<!월)(?<!년)대비|몇\s?배|몇\s?위|몇\s?번째|등수|(많|높|적|낮)은\s?편|"
    r"다른\s?동(보다|에\s?비해|과|이랑|하고)|"
    r"(구|시)\s?전체(보다|에\s?비해|와|랑)"
)
REGION_WIDE = re.compile(r"비율|몫|전체|어디가\s?더|어느\s?쪽이\s?더|평균")
TABLE_ASK = re.compile(r"표로|표만|표\s?로|한\s?표에|표를")
YESNO = re.compile(r"(많|적|높|낮|크|넘)(아|어|나|니|은가|은\s?편|은가요|아요|나요|은\s?거)\??\s*$")
GANGNAM = re.compile(r"강남(?!동)")  # 춘천 강남동은 빼고
CHUNCHEON = re.compile(r"춘천")


@dataclass
class Signals:
    """코드가 센 것(늘 같은 값, 0초)."""

    concepts: list[str] = field(default_factory=list)
    calc: list[str] = field(default_factory=list)
    refer: list[str] = field(default_factory=list)
    dongs: list[str] = field(default_factory=list)
    items: int = 0
    yesno: bool = False
    region_cmp: bool = False
    strong: bool = False
    order_only: bool = False
    subset: bool = False
    recall: bool = False
    regions: tuple[str, ...] = ()  # 말에 나온 지역(이름 · 동으로)
    carried: bool = False  # 지표를 앞 말에서 이어 받았나
    # 지역 전체를 견주는 말(10-26 페르소나 c04 T2 '강남이랑 춘천 중에 비율 어디가 더 높아'
    # → 동을 되물음)
    region_wide: bool = False

    @property
    def deep(self) -> bool:
        """코드만 보고 '깊은 고민'일 만한가."""
        n = len(set(self.concepts))
        if not n:
            return False
        if len(self.regions) >= 2 and not (self.strong or self.region_wide):
            # 두 지역을 나란히 놓기만 — 지금 길의 견주기. 평균 · 합계를 두 지역에 바라면 계산 길
            # (엔진이 지역마다 따로 계산한다, route_50 r1 P11)
            return False
        if self.region_cmp or self.subset or self.strong:
            return True
        if self.items >= 2:
            return True
        if n == 1 and self.order_only and not self.dongs:
            return False  # 지표 하나 줄 세우기(지금 길)
        if n >= 2 and (len(self.dongs) != 1 or self.calc):
            return True
        return bool(self.calc) and len(self.dongs) != 1


def _regions(text: str, dongs: list[str]) -> tuple[str, ...]:
    out = []
    if GANGNAM.search(text):
        out.append("강남구")
    if CHUNCHEON.search(text):
        out.append("춘천시")
    for d in dongs:
        r = dongname.region_of(d)
        if r and r not in out:
            out.append(r)
    return tuple(out)


def signals(text: str) -> Signals:
    t = text
    found: list[str] = []
    for key, rx in _CONCEPT_RE:
        for m in rx.finditer(t):
            found.append(key)
            t = t[: m.start()] + " " * (m.end() - m.start()) + t[m.end() :]
    calc = [m.group(0) for m in CALC.finditer(text)]
    dongs = dongs_in_text(text)
    return Signals(
        concepts=list(dict.fromkeys(found)),
        calc=calc,
        refer=[m.group(0) for m in REFER.finditer(text)],
        dongs=dongs,
        items=len(LIST_ITEM.findall(text)),
        yesno=bool(YESNO.search(text.strip())),
        region_cmp=bool(REGION_CMP.search(text)),
        strong=bool(STRONG.search(text)),
        order_only=bool(calc) and all(ORDER_ONLY.fullmatch(c) for c in calc),
        subset=bool(SUBSET.search(text)),
        recall=bool(RECALL.search(text)),
        regions=_regions(text, dongs),
        region_wide=bool(REGION_WIDE.search(text)),
    )


@dataclass
class Decision:
    route: str  # '바로' · '기억' · '깊은 고민' · '그 밖'
    why: str
    sig: Signals


# 【기능】 데스크가 '나눠 볼 수 없다'며 뺀 조건(unmet) 가운데 우리가 계산할 수 있는 것
def _unmet_computable(unmet: tuple[str, ...]) -> list[str]:
    out = []
    for u in unmet:
        s = signals(u)
        if s.concepts:
            out.append(u)
    return out


def decide(
    text: str,
    card,
    has_prev_calc: bool = False,
    prev_user: str = "",
    prev_bot: str = "",
) -> Decision:
    """코드 신호 + 데스크 카드 → 길.

    【판단】 길을 정하는 데 AI를 한 번 더 부르지 않는다 — 데스크 카드는 이미 있고,
           깊은 고민 길에서는 계산 계획을 짜는 AI가 한 번 더 알아듣는다
           (그 계획이 틀리면 검사기가 큰 모델로 올린다)
    【판단】 10-26 route_hold_32 r1 뒤: 여기의 '깊은 고민'은 후보다. 계획기가 need로 '계산'이라고
           해야 계산 길로 간다(Plan.need, 엔진 _calc)
    """
    sig = signals(text)
    # 10-26 긍정 · 부정 칸: 빼라는 동 · 머뭇거린 동은 '말에 나온 동'으로 세지 않는다
    off = set(getattr(card, "dong_not", ())) | set(getattr(card, "dong_unsure", ()))
    if off:
        sig.dongs = [d for d in sig.dongs if d not in off]
    # 【판단】 '22개 동 다 더해서 합계 줘' · '면 중에서 1위'처럼 지표 이름이 없는 계산 말은 앞 말의
    #        지표를 잇는다(페르소나 p13 noarin T3 · h02 noel r5 T6 · q11 brann T11). 그냥 '비율'
    #        같은 말은 확인('정리하면 비율은 없는 거지?', p02 kairan T8)일 수 있어 잇지 않는다
    if (sig.strong or sig.subset) and not sig.concepts:
        for prev in (prev_user, prev_bot[:300]):
            got = signals(prev).concepts if prev else []
            if got:
                sig.concepts, sig.carried = got, True
                break
    if card.act != "ask":
        return Decision("그 밖", f"데스크가 '{card.act}'로 봄", sig)
    topics = tuple(t for t in card.topics if t not in ("sources", "recall"))
    if "recall" in card.topics and not (sig.strong and sig.concepts):
        return Decision("기억", "데스크가 되짚기로 봄", sig)
    # 【판단】 10-26 팀장 "설마 사용자가 말하는 자연어를 코딩으로 받는거였어? … 하드코딩으로밖에
    #        이해를 못해서 망할거같은데": 후보는 먼저 질문 받는 AI가 뜻으로 고른다(card.calc).
    #        아래 낱말 신호는 AI가 놓쳤을 때의 보조 그물이다. 마지막은 계획기 need
    # 【판단】 10-27 long_100 T46(api13): '먼저 볼 동' 다음 '청년 몇 명이에요?'에 질문 받는
    #        AI가 그 판만 '계산 필요'로 찍어 앞에 보인 5곳을 묻지도 않았는데 합쳤다(다른 판은
    #        동을 되물음 — 같은 말이 판마다 다른 길). 지표가 하나뿐이고 계산 · 묶기 · 거르기 ·
    #        줄 세우기 · 표 · 앞말 말이 하나도 없으면 AI 표시 하나만으로는 계산 길로 보내지
    #        않는다
    plain_one = (
        len(set(sig.concepts)) <= 1
        and not (sig.calc or sig.refer or sig.subset or sig.strong or sig.region_cmp)
        and not (sig.region_wide or sig.recall or sig.items >= 2 or len(sig.regions) >= 2)
        and not ORDER_ONLY.search(text)
        and not TABLE_ASK.search(text)
        and not getattr(card, "rank", False)
        and not _unmet_computable(getattr(card, "unmet", ()))
    )
    # 【판단】 10-27 hold H29 · hold2 Q15 '강남이랑 춘천 중에 어디가 더 심각해요?': 지표 없이 두
    #        지역을 견주는 말은 지금 길(두 지역 견줌 — 우열은 말하지 않음)이다
    two_regions_only = len(sig.regions) >= 2 and not sig.concepts and not sig.strong
    # 【판단】 10-27: 앞 답을 따지거나 되묻는 말은 기억 길(새 계산 · 새 자료 찾기가 아님). 다만
    #        새 질문이 따로 붙었으면 그쪽 — 말뜻 · 기준(hold2 Q19 '앞뒤가 안 맞습니다. 순위는 뭘
    #        기준으로?'), 새 계산 말(Q20 '…이면서 … 몇 퍼센트입니까'), 숫자 여럿 확인(hold H17)
    new_calc = [c for c in sig.calc if not CHANGE_WORD.fullmatch(c)]
    if (
        CHALLENGE.search(text)
        and not (sig.strong or sig.subset or sig.items >= 2 or new_calc)
        and not DEFINE.search(text)
        # 여러 동 · 여러 숫자를 적어 맞는지 확인해 달라는 말은 확인 계산(hold H17). 동 하나 ·
        # 숫자 하나를 다시 묻는 말은 기억(route_50 P16 '처음에 본 일원1동 … 몇 명이었는지')
        and not (
            CONFIRM_ASK.search(text) and (len(sig.dongs) >= 2 or len(CITED_NUM.findall(text)) >= 2)
        )
    ):
        return Decision("기억", "앞 답을 따지거나 되묻는 말", sig)
    if getattr(card, "calc", False) and not plain_one and not two_regions_only:
        return Decision("깊은 고민", "질문 받는 AI가 계산이 필요하다고 봄", sig)
    if (
        (sig.refer or sig.subset)
        and has_prev_calc
        and (sig.concepts or sig.calc or TABLE_ASK.search(text))
    ):
        return Decision("깊은 고민", f"앞 계산을 이어 받음({' · '.join(sig.refer[:2])})", sig)
    if (
        DEFINE.search(text)
        and not (sig.strong or sig.subset or sig.region_cmp or sig.items >= 2)
        and not (sig.refer and has_prev_calc)
    ):
        return Decision("바로", "말뜻 · 기준 · 출처를 묻는 말", sig)
    if sig.recall and (len(sig.dongs) >= 3 or len(set(sig.concepts)) >= 2) and sig.concepts:
        # 여러 동의 숫자를 적어 '맞는지 확인'하거나 지표 여럿을 다시 달라는 말 — 되짚기인지
        # 계산인지는 계획기가 정한다(hold H17 · hold2 Q02)
        return Decision("깊은 고민", f"확인이지만 동 {len(sig.dongs)}곳 · 지표 여럿", sig)
    if sig.recall and not sig.strong and not sig.items:
        return Decision("기억", "앞에서 들은 것을 다시 묻거나 확인함", sig)
    if sig.deep:
        why = []
        if len(set(sig.concepts)) >= 2:
            why.append(f"지표 {len(set(sig.concepts))}가지")
        if sig.calc:
            why.append(f"계산 말 '{sig.calc[0]}'")
        if sig.subset:
            why.append("일부만 보기")
        if sig.items >= 2:
            why.append(f"항목 {sig.items}개")
        if sig.carried:
            why.append("지표는 앞 말에서")
        return Decision("깊은 고민", " · ".join(why), sig)
    # 데스크 카드가 '여럿'을 본 경우(코드 낱말에 없는 말투)
    if len(sig.regions) < 2:
        if card.rank and (len(topics) >= 2 or _unmet_computable(card.unmet)):
            return Decision("깊은 고민", "데스크가 줄 세우기 + 조건 여럿", sig)
        if _unmet_computable(card.unmet) and len(sig.dongs) != 1:
            return Decision("깊은 고민", f"데스크가 뺀 조건이 계산 가능({card.unmet[0]})", sig)
    if sig.refer and not sig.concepts:
        return Decision("기억", f"앞말 참조({sig.refer[0]})", sig)
    return Decision("바로", "조건 하나 · 동 하나 또는 자료 하나", sig)


def check(plan, sig: Signals) -> list[str]:
    """계산 계획 검사 — 코드가 찾은 지표가 계획에 빠졌으면 문제(빈 목록이면 통과).

    【판단】 FrugalGPT의 채점기 자리. 학습한 모델 대신 코드 신호와 맞대 본다: 말 속 지표 개념이
           조건 · 함께 보일 지표 · 줄 세우기 · 모르는 조건 어디에도 없으면 '빠뜨림'
    """
    if plan is None:
        return ["계획 없음"]
    if sig.items >= 2 and not plan.conds:
        # 10-26 calc_27 r2 C01: 공모 기준 가~사를 조건 없이 지표 표로만 짰다(Sonnet은 맞음)
        return [f"항목 {sig.items}개를 조건으로 옮기지 않음"]
    used = {c.metric for c in plan.conds} | {r.metric for r in plan.show}
    if plan.sort:
        used.add(plan.sort.metric)
    near = {
        "solo65": {"solo65_share", "solo65_rise", "solo80", "lonely_total", "lonely_general"},
        "solo80": {"lonely80", "pop80"},
        "pop80": {"solo80", "lonely80"},
        "pharmacies": {"pharmacy_km"},
        "lonely_female": {"solo65", "lonely_total"},
        "lonely_male": {"solo65", "lonely_total"},
        "livelihood": {"livelihood_per100", "lonely_poor"},
        "youth": {"youth_solo", "youth_homebound"},
        "old_walkup": {"old_walkup_share"},
        "halls": {"hall_area_per100"},
        "priority": {"risk_band"},
    }
    unknown = " ".join(plan.unknown)
    miss = []
    for k in set(sig.concepts):
        if k in used or used & near.get(k, set()):
            continue
        if unknown:
            continue  # 모르는 조건으로 밝혔으면 넘어감(지어 붙이지 않은 것)
        miss.append(k)
    out = [f"말 속 '{k}'이(가) 계획에 없음" for k in sorted(miss)]
    if not plan.conds and not plan.sort and not plan.show and not plan.agg:
        out.append("조건 · 줄 세우기 · 보일 지표가 모두 비었음")
    return out
