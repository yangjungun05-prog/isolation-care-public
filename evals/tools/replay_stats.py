"""페르소나 대화 · 재생 결과를 같은 기준으로 센다(10-15). 고치기 전 · 뒤를 견줄 때 쓴다.

    uv run python evals/tools/replay_stats.py evals/results/personas_20b_20261015 \
        evals/results/personas_20b_replay_20261015

【판단】 10-13까지 재생 수치는 그때그때 손으로 셌다(HANDOVER 0-4 '세는 도구'). 같은 기준으로 세야
       고치기 전 · 뒤가 견줘진다. 세는 것:
- 답한 턴(answer) · 막음(blocked) · 못 알아들음(unclear) · 범위 밖 · 되묻기(ask_slot)
- 코드 기본 답(글쓴이가 AI 답을 못 써서 표를 그대로 낸 턴 = 같은 표 되풀이의 뿌리)
- '자료에 없' · '확인되지 않' 같은 없다는 말이 든 답
- '어느 동을 볼까요?'
- 개인정보 가림 안내가 붙은 답
- 바로 앞 답에 있던 숫자(세 자리 이상)를 이번 답에서 '없다'고 한 턴(앞뒤 말 다름의 어림)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

NONE_WORDS = re.compile(r"자료에 없|확인되지 않|자료로 확인할 수 없|나와 있지 않")
NUM = re.compile(r"\d[\d,]{2,}")


def stats(folder: Path) -> dict:
    c: Counter = Counter()
    secs: list[float] = []
    for f in sorted(folder.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        prev = ""
        for t in d.get("turns", []):
            b = t.get("bot") or {}
            reply = b.get("reply") or ""
            c["턴"] += 1
            c[f"종류 {b.get('kind')}"] += 1
            w = b.get("writer") or {}
            if b.get("kind") == "answer" and w and not w.get("used_ai", True):
                c["코드 기본 답"] += 1
            if NONE_WORDS.search(reply):
                c["없다는 말"] += 1
                # 바로 앞 답의 큰 숫자가 이번 사용자 말에 다시 나왔는데 '없다'고 하면 뒤집기로 셈
                said = (t.get("user") or {}).get("message") or ""
                back = {n for n in NUM.findall(prev)} & {n for n in NUM.findall(said)}
                if back:
                    c["앞 답 숫자를 없다고 함(어림)"] += 1
            if "어느 동을 볼까요" in reply:
                c["'어느 동을 볼까요?'"] += 1
            if "가리고 받았어요" in reply:
                c["개인정보 가림 안내"] += 1
            if b.get("total_sec"):
                secs.append(float(b["total_sec"]))
            prev = reply
    out = dict(sorted(c.items()))
    if secs:
        out["평균 초"] = round(sum(secs) / len(secs), 2)
    return out


def main(paths: list[str]) -> None:
    rows = {Path(p).name: stats(Path(p)) for p in paths}
    keys = sorted({k for r in rows.values() for k in r})
    names = list(rows)
    print("| 항목 | " + " | ".join(names) + " |")
    print("|---|" + "---|" * len(names))
    for k in keys:
        print(f"| {k} | " + " | ".join(str(rows[n].get(k, 0)) for n in names) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
