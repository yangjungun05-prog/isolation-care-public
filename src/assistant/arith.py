"""사용자가 적은 셈을 코드가 계산한다(10-26).

【판단】 10-26 페르소나 c01 2판: '2,543 + 1,285 + 1,262 = 5,090이 맞나'를 다섯 턴 동안 '자료에
       합계가 없어 검산할 수 없다'고 답했다(글쓴이는 숫자를 직접 셈하지 않는다는 규칙).
       c04 '45.6÷8.1 해 보면 5.63' · '19,769÷98,431'도 같았다. 사용자가 숫자와 셈 기호를
       적었으면 코드가 그 셈을 그대로 계산해 사실 줄로 건넨다 — 숫자가 자료 값과 같은지는 다른
       사실 줄로 따로 본다.
       날짜(2026-09) · 범위(250~260)를 셈으로 읽지 않게 '-' · '/'는 앞뒤에 빈칸이 있을 때만 받는다.
"""

from __future__ import annotations

import re

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_UNIT = r"(?:\s?(?:명|곳|채|가구|원|세대|%))?"
_OP = r"(?:\s*[+×*÷]\s*|\s+[-−x/]\s+)"
EXPR = re.compile(rf"(?<![\d.,])(?:{_NUM}){_UNIT}(?:{_OP}(?:{_NUM}){_UNIT})+")
_TOKEN = re.compile(rf"({_NUM})(\s?%)?|([+\-−×x*÷/])")


def _value(num: str, pct: str | None) -> float:
    v = float(num.replace(",", ""))
    return v / 100 if pct else v


def evaluate(expr: str) -> float | None:
    """+ - × ÷ 만, 곱하기 · 나누기 먼저. 0으로 나누면 None."""
    nums: list[float] = []
    ops: list[str] = []
    for m in _TOKEN.finditer(expr):
        if m.group(1):
            nums.append(_value(m.group(1), m.group(2)))
        else:
            ops.append({"−": "-", "x": "×", "*": "×", "/": "÷"}.get(m.group(3), m.group(3)))
    if len(nums) != len(ops) + 1 or not ops:
        return None
    # 곱하기 · 나누기 먼저
    vals, rest = [nums[0]], []
    for op, n in zip(ops, nums[1:], strict=True):
        if op in "×÷":
            if op == "÷" and n == 0:
                return None
            vals[-1] = vals[-1] * n if op == "×" else vals[-1] / n
        else:
            rest.append(op)
            vals.append(n)
    out = vals[0]
    for op, n in zip(rest, vals[1:], strict=True):
        out = out + n if op == "+" else out - n
    return out


def _show(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return f"{round(v):,}"
    if abs(v) < 1:
        return f"{v:.4f}(약 {v * 100:.1f}%)"
    return f"{v:,.2f}"


def lines(text: str) -> list[str]:
    """말 속 셈마다 한 줄. 셈이 없으면 빈 목록."""
    out = []
    for m in EXPR.finditer(text):
        expr = m.group(0).strip()
        v = evaluate(expr)
        if v is not None:
            out.append(f"[사용자가 적은 셈] {expr} = {_show(v)}")
    return out[:6]


# 【판단】 10-26 예상 질문 2-14 '우리 부서 경로당 목록이에요: 개포1동 5곳, 개포2동 12곳, …
#        우리 자료랑 비서 자료에서 경로당 수가 다른 동을 찾아 줘': 붙여 넣은 숫자는 [자료]가
#        아니라서 글쓴이가 '부서 목록 숫자는 자료에 없어 대조하지 못했다'고 했다. 위 셈처럼
#        사용자가
#        '동 이름 + 숫자'를 셋 이상 붙여 넣고 그 숫자의 지표 말(경로당 등)이 있으면 코드가 우리 값과
#        대조해 사실 줄로 건넨다
_PAIR_UNIT = r"(곳|명|개|세대|가구|채)"


def pasted(text: str, data, region: str | None = None) -> list[str]:
    """붙여 넣은 '동 + 숫자' 목록을 우리 지표 값과 대조한 줄(목록이 아니면 빈 목록)."""
    from src.assistant import query
    from src.assistant.policy import dongs_in_text

    pairs: dict[str, float] = {}
    for name in dongs_in_text(text):
        m = re.search(rf"{re.escape(name)}\s*[:：]?\s*({_NUM})\s*{_PAIR_UNIT}", text)
        if m:
            pairs[name] = float(m.group(1).replace(",", ""))
    if len(pairs) < 3:
        return []
    unit = re.search(rf"(?:{_NUM})\s*{_PAIR_UNIT}", text).group(1)
    found = [
        mt
        for mt in query.METRICS
        if mt.unit == unit and any(w.strip() and w.strip() in text for w in mt.words.split(","))
    ]
    if not found:
        return []
    mt = found[0]
    people = (data.people() or {}).get("dongs") or {}
    region = region or (data.dong(next(iter(pairs))) or {}).get("region")
    ours = {}
    for n in data.region_dongs(region):
        v = mt.get(data.dong(n) or {}, data.places(n) or {}, people.get(n) or {})
        if v is not None:
            ours[n] = v
    diff = [(n, x, ours[n]) for n, x in pairs.items() if n in ours and ours[n] != x]
    same = [n for n, x in pairs.items() if n in ours and ours[n] == x]
    out = [
        f"[붙여 넣은 동별 숫자 대조] 지표 {mt.name}({mt.unit}), {region} — "
        f"붙여 넣은 {len(pairs)}곳 중 "
        f"다른 동 {len(diff)}곳 · 같은 동 {len(same)}곳(코드가 대조함)"
    ]
    if diff:
        out.append(
            "[다른 동] "
            + " · ".join(
                f"{n}(붙여 넣은 수 {x:g}{unit} · 취약 돌보미 {v:g}{unit})" for n, x, v in diff
            )
        )
    missing = [n for n in ours if n not in pairs]
    if missing and len(pairs) * 2 >= len(ours):  # 지역 목록을 통째로 붙였는데 빠진 동만
        out.append("[붙여 넣은 목록에 없는 동] " + " · ".join(missing))
    if basis := query.metric_basis(mt.key, region):
        out.append(basis)
    return out
