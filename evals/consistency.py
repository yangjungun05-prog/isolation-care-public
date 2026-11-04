"""같은 시험지를 여러 번 돌린 결과를 견줘 '모두 같은 답 비율'을 잰다(멘토 답 4, 10-26).

    uv run python evals/run_long.py --env-file <.env> --scenario <시험지> --tag rep1   # 세 번
    uv run python evals/consistency.py evals/results/<시험지>_<날짜>_rep1.json … _rep3.json

【판단】 LLM은 같은 입력에도 늘 같은 답을 내지 않는다. 흔들림을 0으로 만들기보다 재서 줄인다.
       턴마다 세 가지를 본다 — ① 판단(종류 · 주제 · '없다'고 했나) ② 답에 나온 숫자
       ③ 맞았나(시험지 기대값). '핵심 턴'은 기대값에 숫자 · 낱말(has)이 있는 턴(숫자 · 자료 유무를
       확인하는 문제)이고, 멘토 답대로 핵심 턴은 모두 같아야 통과로 본다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant.engine import num_keys  # noqa: E402

# 【기능】 '없다'고 했나(넓게 — '자료에 없어요'도)
NONE_SAID = re.compile(
    r"자료에 없|자료가 없|확인되지 않|확인할 수 없|알 수 없|나와 있지 않|없어서|찾지 못"
)


def signature(row: dict) -> dict:
    reply = row.get("reply") or ""
    return {
        "judge": (
            row.get("kind"),
            tuple(sorted(row.get("topics") or ())),
            bool(NONE_SAID.search(reply)),
        ),
        "numbers": tuple(sorted(num_keys(reply))) if row.get("kind") == "answer" else (),
        "ok": bool((row.get("ok") or {}).get("all")),
    }


def compare(runs: list[dict]) -> dict:
    """runs = run_long 결과(JSON) 여러 개 → 비율과 다른 턴 목록."""
    n = min(len(r["rows"]) for r in runs)
    same_judge = same_numbers = all_ok = 0
    core = core_same = 0
    differ = []
    for i in range(n):
        rows = [r["rows"][i] for r in runs]
        sigs = [signature(x) for x in rows]
        j = len({s["judge"] for s in sigs}) == 1
        k = len({s["numbers"] for s in sigs}) == 1
        same_judge += j
        same_numbers += k
        all_ok += all(s["ok"] for s in sigs)
        has = (rows[0].get("expect") or {}).get("has") or []
        if has:
            # 【판단】 10-26 고침 3: 핵심 턴은 답에 나온 숫자 전부가 아니라 기대한 핵심 값(has)이
            #        세 번 똑같이 나왔나와 판단만 본다(Self-Consistency arXiv 2203.11171 — 풀이가
            #        아니라 최종 답을 견준다 · 멘토 답 4 '핵심 문항 3/3 일치'). 전부 견주기는 참고
            got = {tuple(h for h in has if h in (x.get("reply") or "")) for x in rows}
            core += 1
            core_same += j and len(got) == 1
        if not (j and k):
            differ.append(
                {
                    "turn": rows[0]["turn"],
                    "say": rows[0]["say"],
                    "judge": [list(s["judge"][:2]) + [s["judge"][2]] for s in sigs],
                    "numbers": [list(s["numbers"]) for s in sigs],
                    "ok": [s["ok"] for s in sigs],
                }
            )
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    return {
        "scenario": runs[0].get("scenario"),
        "runs": len(runs),
        "turns": n,
        "score_each": [r["score"]["all"] for r in runs],
        "all_ok_pct": pct(all_ok, n),
        "same_judge_pct": pct(same_judge, n),
        "same_numbers_pct": pct(same_numbers, n),  # 참고: 답의 숫자 전부(덧붙인 숫자도 셈)
        "core_turns": core,
        "core_same_pct": pct(core_same, core),
        "differ": differ,
    }


def main() -> None:
    files = [Path(p) for p in sys.argv[1:]]
    if len(files) < 2:
        sys.exit("결과 파일을 둘 이상 주세요")
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    out = compare(runs)
    head = {k: v for k, v in out.items() if k != "differ"}
    print(json.dumps(head, ensure_ascii=False, indent=1))
    for d in out["differ"]:
        print(f"- T{d['turn']} {d['say'][:40]} | 판단 {d['judge']} | 맞음 {d['ok']}")


if __name__ == "__main__":
    main()
