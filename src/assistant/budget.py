"""답 쓰는 AI에게 보낼 자료가 너무 크면 덜 중요한 것부터 덜어 낸다(10-26).

【판단】 10-26 팀장: "억지로 막는건 없이. 자연스럽게 필요 없는것들만 짤라내는방법으로."
       Haiku 5.5는 한 번 부를 때 입력이 10만 토큰을 넘으면 그 한 번이 다섯 배 값이다(공식 값표
       platform.claude.com/docs/en/about-claude/pricing, 10-26 확인). 장부의 Haiku 4만 5,401번 중
       가장 큰 한 번이 약 5.1만이라 드물지만, 넘을 때를 대비해 9만(어림)을 넘으면 덜어 낸다.
       - 사용자 말 · 이번 질문의 자료는 그대로 둔다. 답은 늘 나간다(막지 않는다)
       - 덜어 내는 차례: ① '앞서 답할 때 본 자료' 뒤쪽 줄 ② 줄이 가장 많은 묶음의 꼬리(40줄 넘는 것)
       - 덜어 낸 묶음에는 '자리가 넘쳐 뒤 N줄은 줄였어요'를 붙인다(글쓴이가 없다고 하지 않게)
       토큰은 글자 수로 어림한다 — 한국어는 글자 하나가 대략 1토큰(llm.py 10-12 count_tokens 셈).
"""

from __future__ import annotations

from dataclasses import replace

PROMPT_BUDGET = 90_000
KEEP_LINES = 40


def tokens(s: str) -> int:
    return int(len(s) * 1.1) + 1


def _size(facts, base: int) -> int:
    return base + sum(tokens(f.title) + sum(tokens(x) + 4 for x in f.lines) for f in facts)


def fit(facts: list, texts: tuple[str, ...], carry_title: str, budget: int = PROMPT_BUDGET):
    """(덜어 낸 사실 묶음, 덜어 낸 줄 수)."""
    base = sum(tokens(t) for t in texts)
    if _size(facts, base) <= budget:
        return facts, 0
    out = list(facts)
    cut = 0

    def shrink(i: int, keep: int) -> None:
        nonlocal cut
        f = out[i]
        gone = len(f.lines) - keep
        if gone <= 0:
            return
        cut += gone
        note = f"(자리가 넘쳐 이 묶음의 뒤 {gone}줄은 줄였어요 — 없는 자료가 아니다)"
        out[i] = replace(f, lines=f.lines[:keep], notes=[*f.notes, note])

    # ① 앞서 답할 때 본 자료부터 — 뒤쪽 줄을 한 번에 반씩
    for i, f in enumerate(out):
        while f.title == carry_title and f.lines and _size(out, base) > budget:
            shrink(i, len(out[i].lines) // 2)
            f = out[i]
    # ② 줄이 가장 많은 묶음의 꼬리
    while _size(out, base) > budget:
        i = max(range(len(out)), key=lambda k: len(out[k].lines))
        if len(out[i].lines) <= KEEP_LINES:
            break  # 더 덜어 낼 군더더기가 없다 — 그대로 보낸다(막지 않음)
        shrink(i, max(KEEP_LINES, len(out[i].lines) // 2))
    return out, cut
