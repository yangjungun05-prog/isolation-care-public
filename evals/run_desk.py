"""데스크만 재는 시험 — 문제마다 데스크(AI)를 여러 번 따로 불러 흔들림을 센다(문제 목록 2-5).

    uv run python evals/run_desk.py --env-file ../big-contest/.env --runs 5
    uv run python evals/run_desk.py --env-file ../big-contest/.env \
        --model claude-sonnet-5-5 --tag sonnet

한 장 한 장을 실제 코드(데스크 대조 → 칸 적용 → 이륙 전 체크)에 넣어
어떤 판단이 되는지 채점한다.
글쓴이(답 글)는 부르지 않는다.

【판단】 긴 대화 시험지는 턴마다 데스크를 한 번(또는 3장 다수결)만 써서, 한 장이 틀려도 다른 장이
       맞으면 놓친다(100턴 T50 은 20번 중 4번만 틀림). 문제마다 여러 번 따로 재야 흔들림이 보인다.
【판단】 문제지는 고치기 전에 얼린다(evals/scenarios/desk_only_60.json). 결과:
       evals/results/desk_only_60_<날짜>_<tag>.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant import llm  # noqa: E402
from src.assistant.config import AssistantSettings  # noqa: E402
from src.assistant.data_source import JsonDongData  # noqa: E402
from src.assistant.desk import ClaudeDesk, user_text, vote  # noqa: E402
from src.assistant.engine import POLISH, POLISH_PASTED, prepare_input  # noqa: E402
from src.assistant.policy import DISTRESS, desk_sanity, dongs_in_text, preflight  # noqa: E402
from src.assistant.slots import AgeRange, DeskCard, Slots  # noqa: E402
from src.assistant.state import DialogueState, Profile, apply_card, new_state  # noqa: E402


def build_state(given: dict) -> DialogueState:
    st = new_state(Profile(**given.get("profile", {})))
    if "slots" in given:
        raw = dict(given["slots"])
        if raw.get("ages"):
            raw["ages"] = AgeRange(**raw["ages"])
        raw["dongs"] = tuple(raw.get("dongs", ()))
        st = st.model_copy(update={"slots": Slots(**raw)})
    upd = {}
    for k in ("topics", "pending_topics"):
        if k in given:
            upd[k] = tuple(given[k])
    for k in ("pending", "last_question"):
        if k in given:
            upd[k] = given[k]
    return st.model_copy(update=upd)


def judge(state: DialogueState, card: DeskCard, text: str, hidden: list[str], data):
    """한 장 → 코드를 거친 판단(엔진과 같은 순서)."""
    card, _ = desk_sanity(card, text, False, hidden)
    applied = apply_card(state, card, text)
    plan = preflight(applied, card, data)
    # 【기능】 엔진과 같게: 지쳤다는 말은 범위 밖 · 못 알아들음이어도 상담 창구(chitchat 길, 10-14)
    if plan.kind in ("out_of_scope", "unclear") and DISTRESS.search(text):
        plan.kind = "chitchat"
    # 【기능】 엔진과 같게(10-27): '보고서 문장 다듬어 줘'는 되묻기(짧으면) · 범위 밖(글을
    #        붙여 넣었으면) — engine.POLISH. 데스크만 재는 시험이 엔진에서 바뀌는 판단을
    #        틀림으로 세던 것(desk_new_21 O03)
    if POLISH.search(text) and not dongs_in_text(text):
        plan.kind = "out_of_scope" if len(text) > POLISH_PASTED else "unclear"
    return plan, applied.state.slots


def grade(exp: dict, plan, slots: Slots) -> dict:
    got = {"kind": plan.kind in exp["kind"]}
    if "topics" in exp and plan.kind == "answer":
        got["topics"] = bool(set(exp["topics"]) & set(plan.topics))
    if "dongs" in exp:
        got["dongs"] = set(slots.dongs) == set(exp["dongs"])
    for k in ("region", "target", "weather", "rank", "sex", "fmt"):
        if k in exp:
            got[k] = getattr(slots, k) == exp[k]
    if "ages" in exp:
        a = slots.ages
        got["ages"] = (a is None) if exp["ages"] is None else (a == AgeRange(**exp["ages"]))
    got["all"] = all(got.values())
    return got


def signature(plan, slots: Slots) -> str:
    return json.dumps(
        [
            plan.kind,
            sorted(plan.topics),
            sorted(slots.dongs),
            slots.region,
            slots.target,
            slots.weather,
            slots.rank,
        ],
        ensure_ascii=False,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(ROOT / "evals" / "scenarios" / "desk_only_60.json"))
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--model", default="")
    ap.add_argument("--only", default="", help="쉼표로 문제 id(예: A01,B08)")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    # 【판단】 10-25: 날씨 예보(forecast.Live)는 설정을 따로 읽어 --env-file 값이 닿지 않았다
    #        (이 PC BISU .env 는 키 칸이 비어 페르소나 시험 내내 '예보를 받지 못함').
    #        uv run --env-file 처럼 환경에도 올린다(이미 있는 값은 덮지 않음)
    load_dotenv(a.env_file, override=False)
    s = AssistantSettings(_env_file=a.env_file)  # pyright: ignore[reportCallIssue]
    if not s.anthropic_api_key:  # 10-27부터 API 하나(CLI 주석)
        sys.exit("ANTHROPIC_API_KEY 가 없다(--env-file)")
    if a.model:
        s = s.model_copy(update={"desk_model": a.model})
    sc = json.loads(Path(a.scenario).read_text(encoding="utf-8"))
    cases = sc["cases"]
    if a.only:
        want = set(a.only.split(","))
        cases = [c for c in cases if c["id"] in want]
    usage = llm.Usage()
    desk = ClaudeDesk(s, usage)
    data = JsonDongData()

    rows = []
    t_all = time.time()
    for c in cases:
        st = build_state(c.get("given", {}))
        text, hidden, typed = prepare_input(c["say"])
        user = user_text(st, text)
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=a.runs) as ex:
            futures = [ex.submit(desk._one, user) for _ in range(a.runs)]
        cards = []
        for f in futures:
            try:
                cards.append(f.result())
            except llm.CreditExhausted as e:
                sys.exit(f"API 크레딧 바닥 — 멈춤: {e}")
            except llm.LLMError:
                cards.append(None)
        runs = []
        for card in cards:
            if card is None:
                runs.append({"failed": True, "ok": {"all": False}})
                continue
            plan, slots = judge(st, card, text, hidden, data)
            runs.append(
                {
                    "kind": plan.kind,
                    "topics": list(plan.topics),
                    "slots": slots.model_dump(mode="json"),
                    "mentions": list(card.dong_mentions),
                    "restate": card.restate,
                    "sig": signature(plan, slots),
                    "ok": grade(c["expect"], plan, slots),
                }
            )
        good = [cd for cd in cards[:3] if cd is not None]
        if good:
            vplan, vslots = judge(st, vote(good), text, hidden, data)
            vote_ok = grade(c["expect"], vplan, vslots)["all"]
        else:
            vote_ok = False
        passed = sum(r["ok"]["all"] for r in runs)
        sigs = sorted({r["sig"] for r in runs if not r.get("failed")})
        rows.append(
            {
                "id": c["id"],
                "say": c["say"],
                "sent": text,
                "typed": typed,
                "expect": c["expect"],
                "passed": passed,
                "runs": runs,
                "vote3_ok": vote_ok,
                "unstable": len(sigs) > 1,
                "sec": round(time.time() - t0, 1),
            }
        )
        bad = sorted({k for r in runs for k, v in r["ok"].items() if not v and k != "all"})
        mark = "O" if passed == a.runs else ("~" if passed else "X")
        head = f"{c['id']} {mark} {passed}/{a.runs} 3장={int(vote_ok)}"
        print(f"{head} {','.join(bad):22s} {c['say'][:30]}")

    n_runs = sum(len(r["runs"]) for r in rows)
    report = {
        "scenario": sc["name"],
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "desk_model": s.desk_model,
        "runs_per_case": a.runs,
        "cases": len(rows),
        "single_ok": sum(r["passed"] for r in rows),
        "single_total": n_runs,
        "cases_all_ok": sum(r["passed"] == len(r["runs"]) for r in rows),
        "cases_any_bad": sum(r["passed"] < len(r["runs"]) for r in rows),
        "cases_unstable": sum(r["unstable"] for r in rows),
        "vote3_ok": sum(r["vote3_ok"] for r in rows),
        "sec_total": round(time.time() - t_all, 1),
        "usage": {
            "calls": usage.calls,
            "real_tokens": usage.real_tokens,
            "usd": round(usage.usd, 4),
        },
        "rows": rows,
    }
    out = ROOT / "evals" / "results"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{sc['name']}_{dt.date.today():%Y%m%d}" + (f"_{a.tag}" if a.tag else "")
    (out / f"{stem}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
