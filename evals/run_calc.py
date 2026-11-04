"""계산 계획 시험(10-26) — 실무형 질문을 계산 계획으로 옮기는 일을
Haiku · Sonnet · 계단식으로 견준다.

    uv run python evals/run_calc.py --env-file <.env> --tag r1

【판단】 계단식 = Haiku가 짠 계획을 코드 검사기(router.check)가 보고, 빠뜨림이 있을 때만 Sonnet으로
       다시 짠다(FrugalGPT 꼴, 채점기 대신 코드 검사). 셋을 같은 문항으로 채점한다(계획 채점:
       시험지 accept — 기준마다 받아 줄 (지표, 연산) 후보, 동 · 방식 · 묶기 · 모르는 조건 따위)
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
from src.assistant import router as R  # noqa: E402
from src.assistant.config import AssistantSettings  # noqa: E402
from src.assistant.data_source import JsonDongData  # noqa: E402

SCENARIO = ROOT / "evals" / "scenarios" / "calc_27.json"
SONNET = "claude-sonnet-5-5"


def _used(plan: Q.Plan) -> list[Q.Ref]:
    refs: list[Q.Ref] = list(plan.conds) + list(plan.show)
    if plan.sort:
        refs.append(plan.sort)
    return refs


def _match(conds: list[Q.Cond], options: list[list], used: set[int]) -> int | None:
    for i, c in enumerate(conds):
        if i in used:
            continue
        for opt in options:
            m, op = opt[0], opt[1]
            if c.metric != m or c.op != op:
                continue
            if len(opt) > 2 and opt[2] is not None:
                lo, hi = opt[2]
                if c.value is None or not (lo <= c.value <= hi):
                    continue
            return i
    return None


def _criteria(conds: list[Q.Cond], crit: list[list[list]], k: int = 0, used=None) -> bool:
    used = used or set()
    if k == len(crit):
        return True
    # 기준마다 다른 계획 조건을 짝짓는다(되돌아보며)
    for i, c in enumerate(conds):
        if i in used:
            continue
        if _match([c], crit[k], set()) is not None and _criteria(conds, crit, k + 1, used | {i}):
            return True
    return False


def grade(plan: Q.Plan | None, it: dict, data) -> list[str]:
    """빈 목록이면 맞음. 틀린 까닭을 적어 돌려준다."""
    if plan is None:
        return ["계획 없음"]
    acc = it["accept"]
    bad: list[str] = []
    # 10-26 오후: 계획기가 계산 여부(need)도 정한다 — 이 시험지는 모두 계산이 필요한 말
    if plan.need != "계산":
        bad.append(f"need {plan.need}")
    res = Q.run(plan, data, prev=it.get("prev_calc"))
    used = {r.metric for r in _used(plan)}
    every = data.region_dongs(it["region"])
    if "dongs" in acc:
        want = set(acc["dongs"]) or set(every)
        got = set(res.candidates)
        if acc["dongs"] and got != want:
            bad.append(f"동 {sorted(got)} ≠ {sorted(want)}")
        if not acc["dongs"] and plan.dongs:
            bad.append(f"동을 좁힘 {plan.dongs}")
    if "mode" in acc and plan.mode not in acc["mode"]:
        bad.append(f"방식 {plan.mode}")
    if "criteria" in acc and not _criteria(list(plan.conds), acc["criteria"]):
        got = [(c.metric, c.op, c.value) for c in plan.conds]
        bad.append(f"기준 {len(acc['criteria'])}개를 다 짝짓지 못함: {got}")
    for k in acc.get("present", []):
        if k not in used:
            bad.append(f"'{k}' 없음")
    if acc.get("present_any") and not used & set(acc["present_any"]):
        bad.append(f"{acc['present_any']} 가운데 하나도 없음")
    if acc.get("present_per"):
        ok = any((r.metric, r.per) == tuple(pp) for r in _used(plan) for pp in acc["present_per"])
        alt = acc.get("present_or")
        if not ok and not (alt and all(set(x) <= used for x in alt)):
            bad.append(f"나눈 지표 {acc['present_per']} 없음")
    if "per" in acc:
        m, per = acc["per"]
        if not any(c.metric == m and c.per == per for c in plan.conds):
            bad.append(f"{m} ÷ {per} 조건 없음")
    if "kind" in acc and plan.kind != acc["kind"]:
        bad.append(f"kind {plan.kind}")
    if "use_prev" in acc and plan.use_prev != acc["use_prev"]:
        bad.append(f"use_prev {plan.use_prev}")
    if "agg" in acc and acc["agg"] not in plan.agg:
        bad.append(f"agg {plan.agg}")
    if "limit" in acc and plan.limit != acc["limit"]:
        bad.append(f"limit {plan.limit}")
    if "limit_min" in acc and plan.limit < acc["limit_min"]:
        bad.append(f"limit {plan.limit} < {acc['limit_min']}")
    if "unknown" in acc and bool(plan.unknown) != acc["unknown"]:
        bad.append(f"unknown {plan.unknown}")
    if "cross" in acc and plan.cross != acc["cross"]:
        bad.append(f"cross {plan.cross}")
    if acc.get("restate") and not plan.restate:
        bad.append("restate 없음")
    if "top1" in acc and (not res.matched or res.matched[0] != acc["top1"]):
        bad.append(f"1위 {res.matched[:1]} ≠ {acc['top1']}")
    if "top_set" in acc and set(res.matched[: len(acc["top_set"])]) != set(acc["top_set"]):
        bad.append(f"위 {res.matched[:3]} ≠ {acc['top_set']}")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--only", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-sonnet-all", action="store_true")
    a = ap.parse_args()
    load_dotenv(a.env_file, override=False)
    s = AssistantSettings(_env_file=a.env_file)  # pyright: ignore[reportCallIssue]
    sc = json.loads(SCENARIO.read_text(encoding="utf-8"))
    items = [it for it in sc["items"] if not a.only or it["id"] in a.only.split(",")]
    data = JsonDongData()
    haiku = Q.ClaudePlanner(s, llm.Usage())
    sonnet = Q.ClaudePlanner(s, llm.Usage(), model=SONNET, effort="medium")
    rows = []
    for it in items:
        ctx = it.get("prev_user", "")
        if it.get("prev_calc"):
            prev = it["prev_calc"]
            ctx += f"\n앞 결과 동 {len(prev)}곳: {' · '.join(prev[:12])}"
        t0 = time.time()
        ph = haiku.plan(it["say"], it["region"], ctx)
        sh = round(time.time() - t0, 1)
        sig = R.signals(it["say"])
        if ctx and not sig.concepts:
            sig.concepts = R.signals(ctx).concepts
        issues = R.check(ph, sig)
        ps, ss = None, 0.0
        if issues or not a.no_sonnet_all:
            t0 = time.time()
            ps = sonnet.plan(it["say"], it["region"], ctx)
            ss = round(time.time() - t0, 1)
        cascade = ps if (issues and ps is not None) else ph
        gh, gs, gc = grade(ph, it, data), grade(ps, it, data), grade(cascade, it, data)
        rows.append(
            {
                "id": it["id"],
                "say": it["say"][:120],
                "haiku": {
                    "ok": not gh,
                    "why": gh,
                    "sec": sh,
                    "plan": ph.model_dump(mode="json") if ph else None,
                },
                "sonnet": {
                    "ok": not gs,
                    "why": gs,
                    "sec": ss,
                    "plan": ps.model_dump(mode="json") if ps else None,
                },
                "check_issues": issues,
                "cascade": {
                    "ok": not gc,
                    "why": gc,
                    "escalated": bool(issues),
                    "sec": round(sh + (ss if issues else 0), 1),
                },
            }
        )
        print(
            f"{it['id']} 하이쿠 {'O' if not gh else 'X'}({sh}초) 소넷 {'O' if not gs else 'X'}"
            f"({ss}초) 계단식 {'O' if not gc else 'X'}{' ↑' if issues else ''} | "
            f"{(gh or gc)[:2]}"
        )
    n = len(rows)

    def med(xs: list[float]) -> float | None:
        xs = sorted(x for x in xs if x)
        return xs[len(xs) // 2] if xs else None

    report = {
        "scenario": sc["name"],
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "items": n,
        "score": {
            "haiku": sum(r["haiku"]["ok"] for r in rows),
            "sonnet": sum(r["sonnet"]["ok"] for r in rows),
            "cascade": sum(r["cascade"]["ok"] for r in rows),
            "escalated": sum(r["cascade"]["escalated"] for r in rows),
        },
        "sec_median": {
            "haiku": med([r["haiku"]["sec"] for r in rows]),
            "sonnet": med([r["sonnet"]["sec"] for r in rows]),
            "cascade": med([r["cascade"]["sec"] for r in rows]),
        },
        "rows": rows,
    }
    out = (
        ROOT
        / "evals"
        / "results"
        / (f"{sc['name']}_{dt.date.today():%Y%m%d}{'_' + a.tag if a.tag else ''}.json")
    )
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("items", "score", "sec_median")}, ensure_ascii=False))
    print(out)


if __name__ == "__main__":
    main()
