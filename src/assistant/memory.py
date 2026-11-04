"""긴 대화 기억 — 코드가 쌓고, 매 턴 데스크에게 같은 크기로 그려 준다.

【판단】 대화 원문을 통째로 다시 넣지 않는다(docs/research 1절).
       - 원문이 길수록 정확도가 떨어진다(Context Rot 2025 · Lost in the Middle 2024)
       - AI 요약은 다시 쓸 때마다 앞의 말이 닳는다(이음 실측, 재귀 요약의 약점)
       그래서 사실 · 다룬 질문 · 나온 동은 코드가 쌓고, 넘치면 정해진 규칙으로 줄인다.
       100턴째에도 지시문 크기는 아래 상한만큼이다.
【판단】 그리는 순서: 오래 안 바뀌는 것(사실) 앞 → 상태 → 목록들 → 최근 원문
       → 이번 말(맨 끝, desk.py)
"""

from __future__ import annotations

import re

from src.assistant.catalog import BY_ID
from src.assistant.state import DialogueState, LogEntry, TurnText

LOG_KEEP = 50  # 저장해 두는 다룬 질문 수
LOG_SHOW = 15  # 데스크에게 보여 주는 수
DONG_KEEP = 8
TEXT_CUT = 200  # 최근 원문 한 줄 최대 글자


def _norm(s: str) -> str:
    return re.sub(r"[\s.,!?~·]+", "", s)


def fold_facts(old: tuple[str, ...], new: tuple[str, ...], head: int, tail: int) -> tuple[str, ...]:
    """사실 목록을 쌓는다. 중복은 빼고, 넘치면 '가운데'를 버린다(LLM 안 부름).

    【판단】 앞(담당 기관 · 동처럼 안 바뀌는 것)과 뒤(지금 관심)를 남긴다. 흐려도 되는 건 중간이다.
           이음(e-EUM) fold_facts 와 같은 원칙(앞 12 · 뒤 18).
    """
    out = list(old)
    seen = {_norm(x) for x in out}
    for f in new:
        f = re.sub(r"\s+", " ", f).strip()[:80]
        if f and _norm(f) not in seen:
            out.append(f)
            seen.add(_norm(f))
    if len(out) > head + tail:
        out = out[:head] + out[-tail:]
    return tuple(out)


def note_dongs(
    seen: tuple[tuple[str, int], ...], dongs: tuple[str, ...], turn: int
) -> tuple[tuple[str, int], ...]:
    """이번 턴에 쓴 동을 맨 앞으로(최근 순), 최대 DONG_KEEP 개."""
    rest = [(d, t) for d, t in seen if d not in dongs]
    return (tuple((d, turn) for d in dongs) + tuple(rest))[:DONG_KEEP]


def add_log(log: tuple[LogEntry, ...], entry: LogEntry) -> tuple[LogEntry, ...]:
    return (log + (entry,))[-LOG_KEEP:]


def add_recent(recent: tuple[TurnText, ...], item: TurnText, keep: int) -> tuple[TurnText, ...]:
    cut = TurnText(turn=item.turn, user=item.user[:TEXT_CUT], bot=item.bot[:TEXT_CUT])
    return (recent + (cut,))[-keep:]


def _slots_text(state: DialogueState) -> str:
    s = state.slots
    ages = ""
    if s.ages:
        lo = f"{s.ages.lo}" if s.ages.lo is not None else ""
        hi = f"{s.ages.hi}" if s.ages.hi is not None else ""
        ages = f"{lo}~{hi}세"
    parts = [
        f"지역={s.region or '-'}",
        f"동={', '.join(s.dongs) or '-'}",
        f"대상={s.target or '-'}",
        f"나이={ages or '-'}",
        f"성별={s.sex or '-'}",
        f"혼자={'예' if s.alone else '아니오' if s.alone is False else '-'}",
        f"때={s.period or '-'}",
        f"날씨={s.weather or '-'}",
        f"직전 주제={', '.join(state.topics) or '-'}",
    ]
    p = state.profile
    member = f"{p.member_region or '-'}{' ' + p.member_dong if p.member_dong else ''}"
    keep = ""
    if state.standing:
        # 【기능】 계속 쓰는 조건(10-14) — 데스크도 보게 한다
        keep = "\n계속 쓰는 조건: " + " · ".join(x.words() for x in state.standing)
    return " · ".join(parts) + f"\n회원 담당 지역: {member}" + keep


def render(state: DialogueState) -> str:
    """데스크에게 줄 기억(이번 말 앞까지). 턴 수와 상관없이 크기 상한이 있다."""
    blocks = []
    if state.facts:
        blocks.append("[앞선 대화에서 확인된 사실]\n" + "\n".join(f"· {f}" for f in state.facts))
    blocks.append("[지금 정해진 칸]\n" + _slots_text(state))
    old_notes = [e for e in state.log[:-LOG_SHOW] if e.note][-5:]
    if old_notes:
        rows = [f"· T{e.turn} {e.note}" for e in old_notes]
        blocks.append("[앞서 답한 목록(오래된 것)]\n" + "\n".join(rows))
    if state.log:
        rows = []
        for e in state.log[-LOG_SHOW:]:
            title = BY_ID[e.topic].title if e.topic in BY_ID else e.topic
            where = ", ".join(e.dongs) or "-"
            row = f"· T{e.turn} {title} · {where}" + (f" · {e.target}" if e.target else "")
            rows.append(row + (f" · 답한 것: {e.note}" if e.note else ""))
        blocks.append("[다룬 질문(오래된 것 → 최근)]\n" + "\n".join(rows))
    if state.dong_seen:
        seen = ", ".join(f"{d}(T{t})" for d, t in state.dong_seen)
        blocks.append(f"[최근 나온 동(최근 순)]\n{seen}")
    if state.last_question:
        blocks.append(f"[방금 내가 물은 것]\n{state.last_question}")
    if state.recent:
        rows = []
        for r in state.recent:
            rows.append(f"사용자(T{r.turn}): {r.user}")
            rows.append(f"비서(T{r.turn}): {r.bot}")
        blocks.append("[최근 대화]\n" + "\n".join(rows))
    return "\n\n".join(blocks)
