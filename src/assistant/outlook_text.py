"""취약 돌보미 판단의 근거 줄 — 코드가 그대로 붙인다(AI가 다시 쓰지 않는다).

【판단】 10-20 새벽 시험(outlook r1 · 엔진 시도)에서 글쓴이가 근거 줄을 다시 쓰다 틀렸다:
       지역 판단에 없는 '조건 A·B·D'를 동마다 지어 붙이고, 겹침에 든 조건 A를 빼고는 '조건 A는
       이번 판단에 들지 않았다'고 썼다. 조건 · 겹침 · 괜찮은 쪽 · 살펴본 겹은 사서가 만든 줄을
       코드가 그대로 붙이고, AI는 맨 앞 판단 두세 문장만 쓴다(writer.OUTLOOK_SYSTEM).
       숫자 · 글자 · 해당 여부가 사서 줄과 늘 같다
"""

from __future__ import annotations

import re

from src.assistant.librarian import Facts

# 【판단】 이어 묻는 말이 '가장 · 제일 · 이번 주 · 하나만'이면 첫 겹침(앞으로 사흘 날씨가 든 것이
#        먼저 온다)과 그 조건만 붙인다(10-20 r0 T3: 같은 답 전체를 되풀이)
FOCUS = re.compile(r"제일|가장|이번 ?주|하나만|뭐가 먼저|무엇부터|뭐부터")
_PATTERN = re.compile(r"^겹침 \d+: (.+?)\(조건 ([A-Z·]+), (.+?)\)\. 뜻: (.+)$")
_COND = re.compile(r"^해당 조건 ([A-Z]): (.+)$")
_LAYER = re.compile(r" \[[^\]]+\]$")
_HEAD = re.compile(r"^\[(?:강남구|춘천시) [^\]]+\]$")


# 【판단】 10-20 페르소나 r3(o04 · o06): '같은 조건 열 개 목록이 계속' · '겹친 걱정은 크지 않다는
#        첫 말과 조건 열 개가 안 맞아 보인다'
#        → 겹침에 든 조건 + 따로 해당하는 조건 두 개까지만 보이고 나머지는 개수로
#        (물으면 다 보인다). 괜찮은 쪽도 세 가지까지
EXTRA = 2
# 10-20 페르소나 f02 r4 T5: '나머지는 참고로 적겠습니다 … 결론만 한 줄로'에 '나머지'가 걸려 근거가
#        다 붙었다 → 보여 달라는 꼴일 때만
ALL = re.compile(
    r"나머지(?:도| 조건|를|까지)|전부 (?:보여|알려|다)|모든 조건|다 보여|모두 보여|조건 다"
)


def _sheet_block(lines: list[str], focus: bool, every: bool = False) -> list[str]:
    conds: dict[str, str] = {}
    pats: list[tuple[str, list[str], str, str]] = []
    out_head: list[str] = []
    tail: list[str] = []
    for x in lines:
        if m := _COND.match(x):
            conds[m.group(1)] = _LAYER.sub("", m.group(2))
        elif m := _PATTERN.match(x):
            pats.append((m.group(1), m.group(2).split("·"), m.group(3), m.group(4)))
        elif x.startswith("해당하지 않는 조건(괜찮은 쪽): "):
            tail.append("괜찮은 쪽: " + x.split(": ", 1)[1])
        elif x.startswith("살펴본 겹 "):
            tail.append(x)
        elif x.startswith("[") and x.endswith("]"):
            out_head.append(x)
    more = 0
    if focus and pats:
        pats = pats[:1]
        keep = set(pats[0][1])
        conds = {k: v for k, v in conds.items() if k in keep}
    elif not every:
        used = {x for p in pats for x in p[1]}
        extra = [k for k in sorted(conds) if k not in used]
        cap = EXTRA if pats else EXTRA + 2
        keep = used | set(extra[:cap])
        more = len(conds) - len(keep)
        conds = {k: v for k, v in conds.items() if k in keep}
        tail = [
            ("괜찮은 쪽: " + " / ".join(x.split(": ", 1)[1].split(" / ")[:3]))
            if x.startswith("괜찮은 쪽: ")
            else x
            for x in tail
        ]
    body = [f"· 조건 {k}: {v}" for k, v in sorted(conds.items())]
    if more:
        body.append(
            f"· 그 밖에 따로 해당하는 조건 {more}개('나머지 조건도 보여 줘'라고 하시면 보여 드려요)"
        )
    for title, letters, how, meaning in pats:
        body.append(f"겹침: {title}(조건 {'·'.join(letters)}, {how}) → {meaning}")
    return out_head + body + ([] if focus else tail)


# 【판단】 10-20 페르소나 6명 모두 '같은 표를 계속 되풀이'를 가장 큰 불만으로 꼽았다. 같은 조건표
#        (같은 동 · 대상의 머리 줄)를 바로 앞 답에서 이미 보였으면 다시 다 붙이지 않는다
SAME_AS_BEFORE = "(근거 조건은 바로 앞 답과 같아요.)"
_LIST_LINE = re.compile(
    r"^\s*(?:[·•\-]\s*)?"
    r"(?:조건 [A-Z]\s*[:：]|겹침\s*[:：]|괜찮은 쪽|살펴본 겹|\[(?:강남구|춘천시) )"
)
_LIST_PARA = re.compile(r"^\s*(?:괜찮은 쪽으로는|살펴본 겹은|모든 값은 동 단위)")


def strip_lists(text: str) -> str:
    """AI가 쓰지 말라는 목록 줄(조건 · 겹침 · 괜찮은 쪽 · 살펴본 겹)을 스스로 썼으면 걸러 낸다.

    【판단】 10-20 페르소나 o01 T2: AI 글에 조건 목록이 들어가고 코드가 또 붙여 같은 목록이 두 벌
    """
    keep = [
        x for x in (text or "").splitlines() if not _LIST_LINE.match(x) and not _LIST_PARA.match(x)
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


BRIEF = re.compile(
    r"짧게|한 ?줄|한 ?문장|결론만|간단히|요점만|길게 말고|숫자만|한 ?마디|이름만|한 ?개만|하나만"
    r"|예 ?아니오|예나 아니오|긴 ?말 ?말고|길게 (?:쓰|하|말하)지"
    # r9 f01 T7 ~ T8: '판단 기준 긴 설명은 이제 안 붙이셔도 됩니다'를 두 번 말했는데 또 붙음
    r"|안 붙이셔도|붙이지 마|붙이지 않아도|핵심만|그만 붙"
)
BRIEF_TAIL = "근거(조건 · 겹침)는 '근거 보여 줘'라고 하시면 보여 드려요."
# 【정함 10-27 팀장】 "처음엔 접기" — '대답해야 하는 것만 대답 안 하고 자꾸 그 이상을 대답한다'.
#        예상 질문 q2 ~ q7: '오늘 챙길 일이 뭐예요?'(13자)에 1,384자,
#        폭우 질문에 2,278자(대부분 근거 줄).
#        Google 대화 설계 '너무 많이 말하는 것도 너무 적게 말하는 것만큼 비협조적'
#        (developers.google.com/assistant/conversation-design/learn-about-conversation),
#        단계적 공개(요약 먼저, 자세한 것은 바랄 때, arXiv 1811.02164).
#        판단 문장은 글쓴이가 쓰고, 근거 줄은 근거 · 조건 · 까닭을 물을 때만 붙인다
#        ('근거 보여 줘'는 데스크가 같은 동 판단으로 받는다)
SHOW = re.compile(
    r"근거|조건|겹침|나머지|자세히|자세하게|왜|이유|까닭"
    r"|무엇 때문|뭐 때문|어째서|풀어|따져|판단 기준"
)


def render(facts: list[Facts], said: str = "", before: str = "") -> str:
    """사실 묶음(취약 돌보미 판단)의 근거 부분. 조건표가 여럿이면 표마다 나눠 붙인다.

    before = 바로 앞 답. 같은 조건표를 이미 보였으면 이어 묻는 말은 첫 겹침만(제일 · 이번 주),
    아니면 한 줄로 앞 답을 가리킨다.
    """
    # 짧게 달라면 근거 줄을 붙이지 않고 한 줄로 가리킨다(BRIEF 위 판단).
    # '근거 · 나머지'를 물으면 다 보인다
    # 앞 턴에서 짧게 달라고 했으면(Facts.brief, 엔진이 표시) 이번에도 한 줄로
    brief = BRIEF.search(said) or any(getattr(f, "brief", False) for f in facts)
    # 【판단】 10-27 밤 페르소나 h01 T8: '매번 붙는 근거 보여 줘 문장은 귀찮다 · 이제 빼줘'
    #        → 안내는 세션에서 한 번만(엔진이 앞 답들에 이 문장이 있었으면 tail_shown 표시)
    tail = "" if any(getattr(f, "tail_shown", False) for f in facts) else BRIEF_TAIL
    if brief and not ALL.search(said) and "근거" not in said:
        return tail
    if not (ALL.search(said or "") or SHOW.search(said or "")):
        return tail
    focus = bool(FOCUS.search(said or ""))
    heads = [x for f in facts if f.style == "outlook" for x in f.lines if _HEAD.match(x)]
    again = bool(heads) and all(h in (before or "") for h in heads)
    if again and not focus:
        return SAME_AS_BEFORE
    if not again:
        # 첫 질문에 '이번 주'가 들어 있어도 근거는 다 보인다(10-20 페르소나 o01 T1)
        focus = False
    out: list[str] = []
    for f in facts:
        if f.style != "outlook":
            continue
        groups: list[list[str]] = []
        rules = [x for x in f.lines if x.startswith("판단 기준: ")]
        for x in f.lines:
            if x.startswith("판단 기준: "):
                continue
            if x.startswith("[") and x.endswith("]"):
                groups.append([x])
            elif groups:
                groups[-1].append(x)
            else:
                groups.append([x])
        sheets = [g for g in groups if any(_COND.match(x) or _PATTERN.match(x) for x in g)]
        if len(sheets) > 1:
            focus = False
        for g in groups:
            if any(_COND.match(x) or _PATTERN.match(x) for x in g) or any(
                x.startswith("살펴본 겹 ") for x in g
            ):
                out += _sheet_block(g, focus, bool(ALL.search(said or "")))
            else:
                # 지역 판단 · 견줌 줄은 그대로(판단 첫 줄은 AI가 말한다)
                out += [
                    x if x.startswith(("[", "·")) else f"· {x}"
                    for x in g
                    if "취약 돌보미 판단:" not in x
                ]
            out.append("")
        # 판단 기준은 물을 때만(기준 · 정의 · 뜻 · 왜)
        if rules and re.search(r"기준|정의|뜻|어떻게 판단|왜", said or ""):
            out += rules + [""]
        out.append(
            "모든 값은 동(읍면동) 단위 공개 자료라 한 분 한 분의 사정은 이 자료로 알 수 없어요."
        )
    return "\n".join(x for x in out).strip()


_WORSE = re.compile(r"더 (?:많이 )?(?:힘들|어렵|걱정|안고|취약|위험|나쁘)|훨씬|더 심각")
# 【판단】 10-25 페르소나 cli2 오린 T4 ~ T5: '어디가 더 심각하냐'에 '더 심각하다고 가를 수 없어요'
#        처럼 우열을 말하지 않는다는 문장까지 걸려 코드 기본 답(긴 원자료)이 나갔다 → 같은 문장에
#        부정이 있으면 우열을 말한 것이 아니다
_NOT = re.compile(r"수 없|않|못|가리지|가르지")


def claims(text: str, facts: list[Facts]) -> list[str]:
    """AI 판단 문장의 검사 — 두 지역 견줌에서 우열을 말하면 문제(REGION_COMPARE_LINE)."""
    from src.assistant.librarian import REGION_COMPARE_LINE

    lines = [x for f in facts if f.style == "outlook" for x in f.lines]
    if REGION_COMPARE_LINE not in lines:
        return []
    for s in re.split(r"(?<=[.?!])\s+|\n", text):
        if _WORSE.search(s) and not _NOT.search(s):
            return ["두 지역 견줌에서 우열을 말함"]
    return []


def verdicts(facts: list[Facts]) -> str:
    """AI가 쓰지 못했을 때(검사에 걸림 · 오류) 맨 앞에 둘 판단 줄 — 사서 줄 그대로."""
    return "\n".join(
        x for f in facts if f.style == "outlook" for x in f.lines if "취약 돌보미 판단:" in x
    )
