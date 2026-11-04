"""긴 대화 시험 — 얼려 둔 시나리오를 진짜 Claude 데스크로 처음부터 끝까지 돌리고 턴마다 채점한다.

    uv run python evals/run_long.py --env-file ../big-contest/.env
    uv run python evals/run_long.py --env-file ../big-contest/.env --writer template --limit 20

    기본: 데스크 Haiku 5.5 × 3(다수결), 글쓴이 Claude(writer_model)

【판단】 키는 --env-file 로 다른 저장소의 .env 를 읽기만 한다(이 저장소로 키를 복사하지 않는다).
【판단】 채점은 결과를 보기 전에 얼린 시나리오의 기대값으로만 한다
       (kind · topic · dongs · target · region · has · not).
       결과: evals/results/<시나리오>_<날짜>_<tag>.json(턴마다 · 요약 · 비용).
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

from src.assistant import (  # noqa: E402
    llm,
    memory,
    query,
)
from src.assistant.config import AssistantSettings  # noqa: E402
from src.assistant.data_source import JsonDongData  # noqa: E402
from src.assistant.desk import ClaudeDesk  # noqa: E402
from src.assistant.doc import ClaudeDocWriter  # noqa: E402
from src.assistant.engine import Engine  # noqa: E402
from src.assistant.state import Profile  # noqa: E402
from src.assistant.store import MemoryStore  # noqa: E402
from src.assistant.writer import ClaudeWriter, TemplateWriter  # noqa: E402


def grade(exp: dict, reply) -> dict:
    s = reply.state.slots
    got = {
        "kind": reply.kind in exp["kind"],
        "topic": True,
        "dongs": True,
        "target": True,
        "region": True,
    }
    if "topic" in exp and reply.kind == "answer":
        got["topic"] = bool(set(exp["topic"]) & set(reply.topics))
    if "dongs" in exp:
        got["dongs"] = set(s.dongs) == set(exp["dongs"])
    if "target" in exp:
        got["target"] = s.target == exp["target"]
    if "region" in exp:
        got["region"] = s.region == exp["region"]
    # 【기능】 답 글에 꼭 있어야 할 말 · 있으면 안 되는 말(짓궂은 입력 시험: 숫자 부풀리기 요구 등)
    got["text"] = all(x in reply.text for x in exp.get("has", [])) and not any(
        x in reply.text for x in exp.get("not", [])
    )
    # 【기능】 10-29: 건넨 파일 — 파일 이름은 글이 아니라 단추 옆에 보인다(0-39 가독성)
    got["files"] = all(any(str(f).endswith(x) for f in reply.files) for x in exp.get("files", []))
    # 【기능】 칸 값(예: 주제가 바뀌면 성별 · 때가 비었나)과 기억에 남으면 안 되는 말(개인정보)
    #        — 10-12 rules_v6 시험지에서 더함. 없는 시험지는 늘 통과
    dump = s.model_dump(mode="json")
    got["slots"] = all(dump.get(k) == v for k, v in exp.get("slots", {}).items())
    mem = memory.render(reply.state) + "\n" + "\n".join(reply.state.facts)
    got["memory"] = not any(x in mem for x in exp.get("memory_not", []))
    got["all"] = all(got.values())
    return got


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default=str(ROOT / "evals" / "scenarios" / "long_100.json"))
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--writer", choices=["claude", "template"], default="claude")
    ap.add_argument("--votes", type=int, default=None)  # 주지 않으면 설정 기본값(10-12 저녁부터 1)
    # 【판단】 주지 않으면 설정 기본값(10-12부터 켬). --no-escalate 면 늘 3번 다수결
    ap.add_argument("--escalate", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--race", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    # 【판단】 10-25: 날씨 예보(forecast.Live)는 설정을 따로 읽어 --env-file 값이 닿지 않았다
    #        (이 PC BISU .env 는 키 칸이 비어 페르소나 시험 내내 '예보를 받지 못함').
    #        uv run --env-file 처럼 환경에도 올린다(이미 있는 값은 덮지 않음)
    load_dotenv(a.env_file, override=False)
    s = AssistantSettings(_env_file=a.env_file)  # pyright: ignore[reportCallIssue]
    if not s.anthropic_api_key:  # 10-27부터 API 하나(CLI 주석)
        sys.exit("ANTHROPIC_API_KEY 가 없다(--env-file)")
    if a.votes is None:
        a.votes = s.desk_votes
    if a.escalate is None:
        a.escalate = s.desk_escalate
    if a.race is None:
        a.race = s.desk_race
    s = s.model_copy(
        update={"desk_votes": a.votes, "desk_escalate": a.escalate, "desk_race": a.race}
    )
    sc = json.loads(Path(a.scenario).read_text(encoding="utf-8"))
    # 【기능】 시험지에 'as_of'가 있으면 그날을 비서의 오늘로 되감는다
    #        (10-19: 챗봇이 진짜 오늘이 되며 2025-12-31에 얼린 날씨 시험지를 그날로 돌림)
    if sc.get("as_of"):
        s = s.model_copy(update={"as_of": sc["as_of"]})
    turns = sc["turns"][: a.limit or None]
    usage_desk, usage_writer = llm.Usage(), llm.Usage()
    desk = ClaudeDesk(s, usage_desk)
    writer = ClaudeWriter(s, usage_writer) if a.writer == "claude" else TemplateWriter()
    usage_doc = llm.Usage()
    eng = Engine(
        desk,
        writer,
        JsonDongData(),
        MemoryStore(),
        s,
        ClaudeDocWriter(s, usage_doc),
        **query.planners(s, llm.Usage()),
    )
    eng.start("eval", Profile(**sc["profile"]))

    rows = []
    t_all = time.time()
    for i, exp in enumerate(turns, 1):
        t0 = time.time()
        first = None
        try:
            # 【기능】 흘려 보이기로 돌려서 첫 글이 보인 때(first_sec)도 잰다(10-12 팀장: 답이 늦다)
            for event, value in eng.turn_stream("eval", exp["say"]):
                if event in ("text", "replace") and first is None:
                    first = time.time() - t0
                if event == "done":
                    r = value
        except llm.CreditExhausted as e:
            print(f"API 크레딧 바닥 — 멈춤: {e}")
            break
        g = grade(exp, r)
        w = getattr(writer, "last", None)
        rows.append(
            {
                "turn": i,
                "say": exp["say"],
                "expect": {k: v for k, v in exp.items() if k != "say"},
                "kind": r.kind,
                "topics": list(r.topics),
                "slots": r.state.slots.model_dump(mode="json"),
                "reply": r.text,
                "restate": r.card.restate,
                "ok": g,
                "writer_ai": bool(w and w.used_ai) if r.kind == "answer" else None,
                "writer_problems": (w.problems if w and r.kind == "answer" else []),
                # 10-26 멘토 답 1: 글쓴이가 '근거: F1, F3'으로 적은 쓴 줄(없으면 None)
                "writer_cited": (getattr(w, "cited", None) if w and r.kind == "answer" else None),
                "memory_chars": len(memory.render(r.state)),
                # 10-26: 계산 길(판단 층 → 계획기 → 코드 계산)을 탔나
                "calc": any(f.title == "여러 조건 계산" for f in r.facts),
                "calc_lines": next((f.lines for f in r.facts if f.title == "여러 조건 계산"), None),
                "sec": round(time.time() - t0, 1),
                "first_sec": round(first if first is not None else time.time() - t0, 1),
            }
        )
        mark = "O" if g["all"] else "X"
        bad = ",".join(k for k, v in g.items() if not v and k != "all")
        calc = "계산" if rows[-1]["calc"] else "    "
        print(
            f"{i:3d} {mark} {calc} {r.kind:13s} {','.join(r.topics):28s} {bad:18s}"
            f" {exp['say'][:28]}"
        )

    n = len(rows)
    keys = ["kind", "topic", "dongs", "target", "region", "text", "slots", "memory", "all"]
    score = {k: sum(r["ok"][k] for r in rows) for k in keys}
    answers = [r for r in rows if r["kind"] == "answer"]
    report = {
        "scenario": sc["name"],
        "when": dt.datetime.now().isoformat(timespec="seconds"),
        "desk_model": s.desk_model,
        "writer": a.writer if a.writer == "template" else s.writer_model,
        "votes": a.votes,
        "turns": n,
        "score": score,
        "writer_ai_used": sum(1 for r in answers if r["writer_ai"]),
        "writer_fallbacks": sum(1 for r in answers if r["writer_ai"] is False),
        "desk_failures": desk.failures,
        "desk_escalate": a.escalate,
        "desk_race": a.race,
        "writer_mode": s.writer_mode,
        "desk_escalations": desk.escalations,
        "memory_chars_first10_max": max((r["memory_chars"] for r in rows[:10]), default=0),
        "memory_chars_last10_max": max((r["memory_chars"] for r in rows[-10:]), default=0),
        "sec_total": round(time.time() - t_all, 1),
        "sec_avg": round(sum(r["sec"] for r in rows) / max(n, 1), 2),
        "first_sec_avg": round(sum(r["first_sec"] for r in rows) / max(n, 1), 2),
        "answer_chars_avg": round(sum(len(r["reply"]) for r in answers) / max(len(answers), 1)),
        "usage": {
            "desk": {
                "calls": usage_desk.calls,
                "real_tokens": usage_desk.real_tokens,
                "usd": round(usage_desk.usd, 4),
                "cache_read": usage_desk.cache_read,
            },
            "writer": {
                "calls": usage_writer.calls,
                "real_tokens": usage_writer.real_tokens,
                "usd": round(usage_writer.usd, 4),
            },
            # 【기능】 동 상황 문서 글쓴이(Sonnet 5.5, 10-13).
            #        같은 자료면 저장해 둔 문서를 다시 써 0일 수 있다
            "doc": {
                "calls": usage_doc.calls,
                "real_tokens": usage_doc.real_tokens,
                "usd": round(usage_doc.usd, 4),
            },
        },
        "rows": rows,
    }
    out = ROOT / "evals" / "results"
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{sc['name']}_{dt.date.today():%Y%m%d}" + (f"_{a.tag}" if a.tag else "")
    (out / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=1)
    )


if __name__ == "__main__":
    main()
