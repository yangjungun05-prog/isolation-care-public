"""판단 층 시험(10-26) — 말 하나를 '바로 · 기억 · 깊은 고민 · 그 밖' 가운데 어디로 보낼지 견준다.

    uv run python evals/run_route.py --env-file <.env> --tag r1
    uv run python evals/run_route.py --scenario route_hold_32 --tag r1
    uv run python evals/run_route.py --replay evals/results/route_50_20261026_r1.json --tag r2

--replay: 지난 결과에 남은 데스크 카드를 다시 쓰고 판단 층만 새로 돌린다(AI를 부르지 않음).
--judge: 판단 층이 '깊은 고민' 후보로 본 말만 계산 계획기(Haiku)를 불러 need로 마지막 길을 정한다
         (엔진 _calc 와 같음). --judge-all 은 모든 말에 계획기를 불러 need를 남긴다(분석용)
--reuse-need: --replay 와 같이 — 지난 --judge-all 결과의 need를 다시 써서 판단 층만 새로 돌린다
         (계획기의 need는 판단 층 규칙과 상관없이 정해지므로 AI를 다시 부르지 않아도 같다)
시험지 문항에 alt(받아 줄 다른 길)가 있으면 '너그러운 점수'도 함께 센다.

【판단】 세 가지를 같은 말로 잰다: ① 코드 신호만 ② 데스크 카드만(Haiku, 지금 엔진이 보는 것)
       ③ 판단 층(코드 신호 + 데스크 카드, router.decide). 데스크는 엔진과 똑같이 부른다
       (말 다듬기 prepare_input → desk.read → desk_sanity)
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant import llm  # noqa: E402
from src.assistant import query as Q  # noqa: E402
from src.assistant import router as R  # noqa: E402
from src.assistant.config import AssistantSettings  # noqa: E402
from src.assistant.desk import ClaudeDesk  # noqa: E402
from src.assistant.engine import prepare_input  # noqa: E402
from src.assistant.policy import desk_sanity, dongs_in_text  # noqa: E402
from src.assistant.state import Profile, TurnText, new_state  # noqa: E402

SCENARIOS = ROOT / "evals" / "scenarios"


def state_of(it: dict):
    st = new_state(Profile(member_region=it["region"]))
    if it.get("prev_user"):
        st = st.model_copy(
            update={
                "turn": 1,
                "recent": (TurnText(turn=1, user=it["prev_user"], bot=it.get("prev_bot", "")),),
                "last_answer": it.get("prev_bot", ""),
            }
        )
    return st


def desk_only(card) -> str:
    """지금 엔진이 카드만으로 갈 길.

    깊은 고민 길이 없으니 줄 세우기 + 주제 여럿을 깊은 고민으로 센다.
    """
    if card.act != "ask":
        return "그 밖"
    if "recall" in card.topics:
        return "기억"
    if getattr(card, "calc", False):
        return "깊은 고민"  # 10-26 질문 받는 AI의 '계산 필요' 칸
    topics = [t for t in card.topics if t not in ("sources",)]
    if card.rank and len(topics) >= 2:
        return "깊은 고민"
    return "바로"


def code_only(sig: R.Signals) -> str:
    if sig.deep:
        return "깊은 고민"
    if sig.refer:
        return "기억"
    return "바로"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--only", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("--scenario", default="route_50")
    ap.add_argument("--replay", default="")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--judge-all", action="store_true")
    ap.add_argument("--reuse-need", action="store_true")
    a = ap.parse_args()
    old = {}
    if a.replay:
        rep = json.loads(Path(a.replay).read_text(encoding="utf-8"))
        a.scenario = rep["scenario"]
        old = {r["id"]: r for r in rep["rows"]}
    sc = json.loads((SCENARIOS / f"{a.scenario}.json").read_text(encoding="utf-8"))
    items = [it for it in sc["items"] if not a.only or it["id"] in a.only.split(",")]
    desk = planner = None
    if not a.replay or a.judge or a.judge_all:
        load_dotenv(a.env_file, override=False)
        s = AssistantSettings(_env_file=a.env_file)  # pyright: ignore[reportCallIssue]
        if not a.replay:
            desk = ClaudeDesk(s, llm.Usage())
        if a.judge or a.judge_all:
            planner = Q.ClaudePlanner(s, llm.Usage())
    rows = []
    for it in items:
        st = state_of(it)
        text, hidden, _ = prepare_input(it["say"])
        t0 = time.time()
        if desk is None:
            card = SimpleNamespace(**old[it["id"]]["card"])
        else:
            card = desk.read(st, text)
            card, _ = desk_sanity(card, text, False, hidden)
        sec = round(time.time() - t0, 1) if desk else old[it["id"]]["sec"]
        dec = R.decide(
            text,
            card,
            has_prev_calc=bool(it.get("prev_calc"))
            or len(dongs_in_text(it.get("prev_bot", ""))) >= 2,
            prev_user=it.get("prev_user", ""),
            prev_bot=it.get("prev_bot", ""),
        )
        sig = R.signals(text)
        need, psec = None, 0.0
        if a.reuse_need:
            need, psec = old[it["id"]].get("need"), old[it["id"]].get("plan_sec", 0.0)
        elif planner is not None and (a.judge_all or dec.route == "깊은 고민"):
            t1 = time.time()
            reg = it["region"]
            ctx = it.get("prev_user", "")[:300]
            prev = it.get("prev_calc") or dongs_in_text(it.get("prev_bot", ""))
            if len(prev) >= 2 or it.get("prev_calc"):
                ctx += f"\n앞 결과 동 {len(prev)}곳: {' · '.join(prev[:12])}"
            p = planner.plan(text, reg, ctx)
            psec = round(time.time() - t1, 1)
            need = p.need if p is not None else "없음"
        final = dec.route
        if a.judge or a.judge_all or a.reuse_need:
            if dec.route == "깊은 고민" and need != "계산":
                final = "기억" if need == "되짚기" else "바로"
        row = {
            "id": it["id"],
            "say": it["say"][:120],
            "label": it["label"],
            "alt": it.get("alt", []),
            "router": final,
            "candidate": dec.route,
            "need": need,
            "plan_sec": psec,
            "why": dec.why,
            "desk": desk_only(card),
            "code": code_only(sig),
            "card": {
                "act": card.act,
                "topics": list(card.topics),
                "rank": card.rank,
                "unmet": list(card.unmet),
                "calc": bool(getattr(card, "calc", False)),
            },
            "sig": {"concepts": dec.sig.concepts, "calc": dec.sig.calc[:3], "refer": dec.sig.refer},
            "sec": sec,
        }
        rows.append(row)
        mark = "O" if final == it["label"] else "X"
        print(
            f"{mark} {it['id']} 정답 {it['label']} | 판단 층 {final}"
            f"(후보 {dec.route} · need {need})"
            f" | 데스크만 {row['desk']} "
            f"| 코드만 {row['code']} | {dec.why}"
        )
    n = len(rows)
    score = {k: sum(r[k] == r["label"] for r in rows) for k in ("router", "desk", "code")}
    loose = {
        k: sum(r[k] == r["label"] or r[k] in r["alt"] for r in rows)
        for k in ("router", "desk", "code")
    }
    deep = {
        k: sum((r[k] == "깊은 고민") == (r["label"] == "깊은 고민") for r in rows)
        for k in ("router", "desk", "code")
    }
    conf = collections.Counter((r["label"], r["router"]) for r in rows)
    report = {
        "scenario": sc["name"],
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "items": n,
        "score": score,
        "score_loose": loose,
        "score_deep_or_not": deep,
        "replay_of": a.replay,
        "confusion_router": {f"{a}→{b}": v for (a, b), v in sorted(conf.items())},
        "rows": rows,
    }
    out = (
        ROOT
        / "evals"
        / "results"
        / (f"{sc['name']}_{dt.date.today():%Y%m%d}{'_' + a.tag if a.tag else ''}.json")
    )
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {
                "items": n,
                "score": score,
                "loose": loose,
                "deep_or_not": deep,
                "confusion": report["confusion_router"],
            },
            ensure_ascii=False,
        )
    )
    print(out)


if __name__ == "__main__":
    main()
