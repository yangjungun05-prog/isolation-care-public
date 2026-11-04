"""여러 조건 질문 시험(10-26 시제품) — 같은 질문을 시제품(조건 옮기기 + 코드 조회)과
지금 엔진에 넣어 견준다.

    uv run python evals/run_multi.py --env-file <.env> --runs 1 --engine --tag r1

【판단】 정답은 시험지의 손으로 옮긴 조건(plan)을 코드(query.run)로 돌려 얻은 동이다
       (AI 결과를 보기 전에 얼림). 시제품은 '모두 맞는 동'이 정답과 같은가,
       지금 엔진은 답에 정답 동이 다 나오나 · 정답이 아닌 동을 몇 곳 말했나를 센다
       (엔진 답은 글이라 동 이름만 센다 — 사람이 대화록도 읽는다)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant import llm  # noqa: E402
from src.assistant import query as Q  # noqa: E402
from src.assistant.config import AssistantSettings  # noqa: E402
from src.assistant.data_source import JsonDongData  # noqa: E402

SCENARIO = ROOT / "evals" / "scenarios" / "multi_16.json"


def truth(item: dict, data, people) -> Q.Result:
    return Q.run(Q.Plan(**item["plan"]), data, people)


def conds_key(plan: Q.Plan) -> set[tuple]:
    return {(c.metric, c.op, c.value) for c in plan.conds}


def mentioned(text: str, names: list[str]) -> list[str]:
    # 【판단】 긴 이름부터 세고 지운다 — 짧은 이름이 긴 이름 안에서 한 번 더 세지지 않게
    found, t = [], text
    for n in sorted(names, key=len, reverse=True):
        if n in t:
            found.append(n)
            t = t.replace(n, " ")
    return found


def same(it: dict, plan: Q.Plan | None, got: Q.Result | None, want: Q.Result) -> bool:
    """정답과 같은가 — 줄 세우기를 물었으면 위 limit 곳의 순서까지,
    목록에 없는 조건은 밝혔나까지."""
    if not plan or not got:
        return False
    p = Q.Plan(**it["plan"])
    if p.sort:
        ok = got.matched[: p.limit] == want.matched[: p.limit]
    else:
        ok = set(got.matched) == set(want.matched)
    if "expect_unknown" in it:
        ok = ok and bool(plan.unknown) == it["expect_unknown"]
    return ok


def run_proto(items, data, people, s, runs) -> list[dict]:
    usage = llm.Usage()
    planner = Q.ClaudePlanner(s, usage)
    rows = []
    for k in range(runs):
        for it in items:
            want = truth(it, data, people)
            t0 = time.time()
            plan = planner.plan(it["say"], it["region"])
            sec = round(time.time() - t0, 1)
            got = Q.run(plan, data, people) if plan else None
            same_set = same(it, plan, got, want)
            rows.append(
                {
                    "run": k + 1,
                    "id": it["id"],
                    "say": it["say"],
                    "plan": plan.model_dump(mode="json") if plan else None,
                    "same_conds": bool(plan) and conds_key(plan) == conds_key(Q.Plan(**it["plan"])),
                    "matched": got.matched if got else None,
                    "want": want.matched,
                    "ok": same_set,
                    "lines": got.lines if got else [],
                    "sec": sec,
                }
            )
            print(
                f"시제품 {k + 1} {it['id']} {'O' if same_set else 'X'} {sec:5.1f}초 "
                f"{got.matched if got else None}"
            )
    return rows


def run_engine(items, data, people, s, env_file) -> list[dict]:
    from src.assistant.desk import ClaudeDesk
    from src.assistant.doc import ClaudeDocWriter
    from src.assistant.engine import Engine
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import ClaudeWriter

    ud, uw, uo = llm.Usage(), llm.Usage(), llm.Usage()
    eng = Engine(
        ClaudeDesk(s, ud),
        ClaudeWriter(s, uw),
        data,
        MemoryStore(),
        s,
        ClaudeDocWriter(s, uo),
        **Q.planners(s, llm.Usage()),
    )
    rows = []
    for it in items:
        want = truth(it, data, people)
        sid = f"multi_{it['id']}"
        eng.start(sid, Profile(member_region=it["region"]))
        t0 = time.time()
        r = None
        for event, value in eng.turn_stream(sid, it["say"]):
            if event == "done":
                r = value
        sec = round(time.time() - t0, 1)
        names = data.region_dongs(it["region"])
        said = mentioned(r.text if r else "", names)
        rows.append(
            {
                "id": it["id"],
                "say": it["say"],
                "kind": r.kind if r else None,
                "topics": list(r.topics) if r else [],
                "slots": r.state.slots.model_dump(mode="json") if r else None,
                "reply": r.text if r else "",
                "want": want.matched,
                "near": [n for n, _ in want.near],
                "said": said,
                "recall": all(n in said for n in want.matched[: Q.Plan(**it["plan"]).limit]),
                "extra": [n for n in said if n not in want.matched],
                "sec": sec,
            }
        )
        print(
            f"엔진 {it['id']} 정답 다 말함 {all(n in said for n in want.matched)} · "
            f"말한 동 {said} · {sec}초"
        )
    return rows


def regrade(path: Path) -> None:
    """남은 결과 파일을 지금 코드의 정답으로 다시 채점한다(AI는 다시 부르지 않음).

    【판단】 10-26 r1을 돌리는 사이 정답 계산의 결함(같은 값을 이름순으로 다른 등수)을 고쳤다.
           답은 파일에 남아 있어 정답만 다시 셀 수 있다
    """
    rep = json.loads(path.read_text(encoding="utf-8"))
    sc = json.loads(
        (ROOT / "evals" / "scenarios" / f"{rep['scenario']}.json").read_text(encoding="utf-8")
    )
    by_id = {it["id"]: it for it in sc["items"]}
    data = JsonDongData()
    people = json.loads((ROOT / "data" / "public" / "people.json").read_text(encoding="utf-8"))[
        "dongs"
    ]
    for r in rep["rows_proto"]:
        want = truth(by_id[r["id"]], data, people)
        got = Q.run(Q.Plan(**r["plan"]), data, people) if r["plan"] else None
        r["want"], r["matched"] = want.matched, got.matched if got else None
        plan = Q.Plan(**r["plan"]) if r["plan"] else None
        r["ok"] = same(by_id[r["id"]], plan, got, want)
        r["lines"] = got.lines if got else []
    for r in rep["rows_engine"]:
        it = by_id[r["id"]]
        want = truth(it, data, people)
        r["want"], r["near"] = want.matched, [n for n, _ in want.near]
        # 【판단】 '세 곳만'처럼 개수를 물었으면 정답 위 그 수만 나오면 된다(C4 · G4)
        top = want.matched[: Q.Plan(**it["plan"]).limit]
        r["recall"] = all(n in r["said"] for n in top)
        r["extra"] = [n for n in r["said"] if n not in want.matched]
    rep["proto"]["same_set"] = sum(r["ok"] for r in rep["rows_proto"])
    rep["engine"]["recall_all"] = sum(r["recall"] for r in rep["rows_engine"])
    rep["engine"]["extra_dongs"] = sum(len(r["extra"]) for r in rep["rows_engine"])
    rep["regraded"] = dt.datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("proto", "engine")}, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--engine", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--regrade", default="")
    ap.add_argument("--scenario", default=str(SCENARIO))
    a = ap.parse_args()
    if a.regrade:
        regrade(Path(a.regrade))
        return
    load_dotenv(a.env_file, override=False)
    s = AssistantSettings(_env_file=a.env_file)  # pyright: ignore[reportCallIssue]
    sc = json.loads(Path(a.scenario).read_text(encoding="utf-8"))
    items = [it for it in sc["items"] if not a.only or it["id"] in a.only.split(",")]
    data = JsonDongData()
    people = json.loads((ROOT / "data" / "public" / "people.json").read_text(encoding="utf-8"))[
        "dongs"
    ]
    proto = run_proto(items, data, people, s, a.runs)
    eng = run_engine(items, data, people, s, a.env_file) if a.engine else []
    n = len(proto)
    report = {
        "scenario": sc["name"],
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "model": s.desk_model,
        "proto": {
            "runs": a.runs,
            "items": n,
            "same_set": sum(r["ok"] for r in proto),
            "same_conds": sum(r["same_conds"] for r in proto),
            "sec_median": sorted(r["sec"] for r in proto)[n // 2] if n else None,
        },
        "engine": {
            "items": len(eng),
            "recall_all": sum(r["recall"] for r in eng),
            "extra_dongs": sum(len(r["extra"]) for r in eng),
            "sec_median": sorted(r["sec"] for r in eng)[len(eng) // 2] if eng else None,
        },
        "rows_proto": proto,
        "rows_engine": eng,
    }
    out = (
        ROOT
        / "evals"
        / "results"
        / f"{sc['name']}_{dt.date.today():%Y%m%d}{'_' + a.tag if a.tag else ''}.json"
    )
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("proto", "engine")}, ensure_ascii=False))
    print(out)


if __name__ == "__main__":
    main()
