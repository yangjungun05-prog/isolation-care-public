"""데스크 시험 결과에서 틀린 장만 보인다(10-14).

uv run python evals/tools/desk_bad.py evals/results/desk_only_60_<날짜>_<태그>.json [A01,B08]
"""

import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
for r in d["rows"]:
    if only and r["id"] not in only:
        continue
    if r["passed"] == len(r["runs"]) and not only:
        continue
    want = json.dumps(r["expect"], ensure_ascii=False)
    print(f"== {r['id']} {r['say']} (보낸 말: {r['sent']}) 기대 {want}")
    for x in r["runs"]:
        if x.get("failed"):
            print("   실패")
            continue
        s = x["slots"]
        mark = "O" if x["ok"]["all"] else "X"
        print(
            f"   {mark} {x['kind']:12s} {x['topics']} 동={s['dongs']} 지역={s['region']}"
            f" 대상={s['target']}"
            f" 쓴동={x['mentions']} | {x['restate'][:70]}"
        )
