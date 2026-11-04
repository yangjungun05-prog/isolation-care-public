"""동 이름의 긍정 · 부정 · 머뭇 — AI가 붙이고 코드가 대조한다(10-26).

【판단】 10-26 팀장: "긍정이랑 부정 슬롯을 따로 만들자. 이거는 ai가 판단할 수 있게 하는게 맞는 것
       같은데. 코드가 그대로 가져오되, 대조를 통해 맞는지 아닌지를 판단하는게 낫지 않을까?"
       - 코드: 말 속 동 이름을 빠짐없이 뽑는다(policy.dongs_in_text — 이름 목록과 그대로 맞춤)
       - AI(질문 받는 AI): 동마다 본다(dongs) · 뺀다(not_dongs) · 머뭇(unsure_dongs)을 적는다
       - 코드 대조: ① 말에 없는 동을 '뺀다 · 머뭇'에 적었으면 버린다 ② 동 이름 바로 뒤에 부정 말
         ('이 아니라 · 말고 · 빼고 · 제외 · 아닌')이 붙었는데 AI가 '본다'에 적었으면 '뺀다'로 옮기고
         밝힌다 ③ 말에 나온 동을 AI가 어디에도 안 적었고 바로 뒤에 부정 · 머뭇 말이 있으면 그쪽으로
         넣는다(부정 말이 없으면 AI가 일부러 뺀 것일 수 있어 두지 않는다 — '일원본동은 아까 봤고')
       부정 말은 동 이름 바로 뒤(조사 하나까지)만 본다 — '수서동 어르신 아니라 청년'의 '아니라'는
       어르신에 걸린 말이다. 정해진 낱말을 이름 바로 곁에서만 찾는 방식은 의료 기록의 부정 찾기
       NegEx(Chapman 외 2001, J Biomed Inform 34(5))와 같은 꼴이다.
"""

from __future__ import annotations

import re

# 동 이름 바로 뒤(조사 하나까지) — 부정
_NEG_AFTER = re.compile(
    r"^\s?(?:이|가|은|는|도)?\s?(?:아니라|아니고|아니야|아니에요|아닌|아니|말고|빼고|빼|제외|말구)"
)
# 동 이름 바로 뒤 — 머뭇('○○보다 많아?'의 '보다'는 견줌이라 넣지 않는다. '보다는'은 뒤에 '..'
# · '글쎄'가 붙을 때만)
_UNSURE_AFTER = re.compile(
    r"^\s?(?:이|가|은|는)?\s?(?:인가|이었나|였나|일지도|일까|보다는\s?(?:\.{2,}|…|글쎄))"
)


# 말에 없는 동을 가리키는 말(데스크 지시문 '거기 · 그 동 · 아까 그 동 · 첫 번째 동 · 3위였던 동',
# 회원 담당 동 '우리 동 · 담당')
_POINTS = re.compile(
    r"거기|그\s?(?:동|면|읍|곳|데|지역|중)|아까|앞에서|방금|위에서|첫\s?번째|\d\s?위|"
    r"우리\s?(?:동|면|읍|동네|지역)|담당|저희|같은\s?(?:동|곳)|이\s?(?:동|면|읍|곳)"
)


# 견주자는 말 — '○○이랑 비교하면?'은 지금 칸의 동과 ○○을 둘 다 본다(데스크 지시문)
_COMPARE = re.compile(r"비교|견주|견줘|대비|차이|나란히|(?:이)?랑|하고 |보다")


def cues(text: str, dong: str) -> str:
    """'not' · 'unsure' · ''. 이름이 여러 번 나오면 하나라도 걸리면 그것."""
    out = ""
    for m in re.finditer(rf"(?<![가-힣0-9]){re.escape(dong)}", text):
        tail = text[m.end() : m.end() + 12]
        if _NEG_AFTER.search(tail):
            return "not"
        if _UNSURE_AFTER.search(tail):
            out = "unsure"
    return out


def reconcile(card, text: str):
    """카드의 본다 · 뺀다 · 머뭇을 말 속 동 이름과 대조해 고친 카드와 밝힐 말."""
    from src.assistant.policy import dongs_in_text

    said = dongs_in_text(text)

    def canon(names) -> list[str]:
        out: list[str] = []
        for n in names:
            got = dongs_in_text(n) or [n]
            out += [g for g in got if g not in out]
        return out

    pos = canon(card.dong_mentions)
    neg = [d for d in canon(card.dong_not) if d in said]  # ① 말에 없는 동은 버림
    uns = [d for d in canon(card.dong_unsure) if d in said and d not in neg]
    moved: list[str] = []
    for d in said:
        c = cues(text, d)
        if c == "not":
            if d in pos:  # ② 바로 뒤에 부정 말인데 '본다'에 있음 → 뺀다
                pos.remove(d)
                moved.append(d)
            if d not in neg:
                neg.append(d)
            if d in uns:
                uns.remove(d)
        elif c == "unsure":
            if d in pos and len(pos) >= 2:  # 다른 동을 이어 말했으면 머뭇거린 동은 뺀다
                pos.remove(d)
            if d not in pos and d not in neg and d not in uns:
                uns.append(d)  # ③ AI가 어디에도 안 적은 동
    pos = [d for d in pos if d not in neg and d not in uns]
    # ④ 10-26 예상 질문 2-26 '1. 동면이 춘천에서 어떤 편인지 2. 80세 이상 …': AI가 말에 없는 앞 동
    #    (신북읍)을 '본다'에 적고 말에 나온 동면은 빠뜨렸다. 가리키는 말(거기 · 그 동 · 아까 · 우리
    #    동 …)이 없으면 말에 없는 동 대신 말에 나온 동을 본다(AI가 일부러 뺀 동은 말에 있는 동이라
    #    ③과 부딪히지 않는다)
    #    q2: AI가 '신북읍 · 동면' 둘 다 적고 다시 쓴 질문도 '신북읍의 80세 이상 …' → 견주자는 말이
    #    아니면 말에 없는 동은 빼고, 다시 쓴 질문은 사용자 원문으로(글쓴이가 옛 동을 따라가지 않게)
    away = [d for d in pos if d not in said]  # canon 뒤라 '역삼 1동'처럼 써도 같은 이름
    left = [d for d in said if d not in pos and d not in neg and d not in uns]
    kept = [d for d in pos if d in said]
    plain = not _POINTS.search(text) and not _COMPARE.search(text)
    fixed = bool(away and (kept or left) and plain)
    if fixed:
        pos = kept + left
    # ⑤ q3 2-26: AI가 동을 하나도 안 적어(칸 그대로) 앞 동 신북읍이 쓰였다 → 묻는 말(ask)에 동이
    #    나왔고 줄 세우기 · 계산 · 견줌 · 가리키는 말이 아니면 말에 나온 동을 본다
    elif (
        not pos
        and left
        and plain
        and card.act == "ask"
        and card.dong_op == "keep"
        and not card.rank
        and not getattr(card, "calc", False)
    ):
        pos, fixed = left, True
    note = ""
    if moved:
        note += f"({' · '.join(moved)}은(는) 아니라고 하셔서 빼고 봤어요.)\n"
    if uns and pos:
        note += (
            f"({' · '.join(uns)}은(는) 같이 볼지 분명하지 않아 빼고 봤어요. "
            "같이 보시려면 말씀해 주세요.)\n"
        )
    upd = {"dong_not": tuple(neg), "dong_unsure": tuple(uns)}
    if tuple(pos) != tuple(canon(card.dong_mentions)):
        upd["dong_mentions"] = tuple(pos)
        if not pos and card.dong_op == "set":
            upd["dong_op"] = "keep"
    if fixed:
        upd["restate"] = text
        if pos:
            upd["dong_op"] = "set"
    # ⑥ q4 2-26: 동 칸은 동면으로 맞았는데 다시 쓴 질문이 '신북읍의 … 가까운 보건지소'라
    #    글쓴이가 앞 턴 자료에서 신북읍 보건지소를 골랐다 → 이번 말이 동을 정했고(말에 동이
    #    있음) 다시 쓴 질문에 말에도 칸에도 없는 동이 있으면 원문으로. '청년은?'처럼 동 없이 이어
    #    묻는 말은 다시 쓴 질문이 지금 동을 채우는 것이 맞아 건드리지 않는다
    elif (
        plain
        and pos
        and said
        and any(
            d not in said and d not in pos
            for d in dongs_in_text(getattr(card, "restate", "") or "")
        )
    ):
        upd["restate"] = text
    return card.model_copy(update=upd), note
