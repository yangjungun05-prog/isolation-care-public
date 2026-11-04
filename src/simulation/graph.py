"""시뮬레이션 한 번 실행 흐름을 LangGraph 그래프로 — POST /api/simulation/run 이 이것을 부른다.

    START → run_plan(이 안) ─ 대상 0명 → END
             └→ run_compare(비교 안) · run_safe(보수적) · run_tornado(흔드는 값)  ← 동시에
                → assemble(결과 묶기) → paragraph(설명글) ─ 숫자 다름 → numbers_only → END
                                                          └→ END

【판단】 계산은 engine.py 그대로 부르고, 이 파일은 '무엇을 어떤 순서로 · 언제 멈추나'만 맡는다.
  10-26 사용자 "랭그래프로 옮겨줘 · 비서는 건들지 말고 내 부분만" — 비서(src/assistant)는
  그대로 둔다
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.simulation import engine, text

# 【판단】 노드 이름은 상태 칸 이름(plan · compare …)과 겹치면 안 된다(LangGraph 규칙)
#   → 노드에는 run_ 을 붙인다
FAN = ["run_compare", "run_safe", "run_tornado"]


class SimState(TypedDict, total=False):
    # 【기능】 그래프가 노드 사이로 넘기는 값 — 위 칸은 입력, 아래 칸은 노드가 채운다
    # 【문법】 total=False = 모든 칸이 처음부터 있을 필요는 없다(노드가 하나씩 채운다)
    request: dict  # 화면 입력 그대로(돌려줄 때 input 칸)
    dongs: list[str]  # 동 코드
    who: str
    kind: str
    budget: float  # 1년 돈(원)
    years: int
    order: str
    compare_order: str
    overrides: dict
    plan: dict | None
    compare: dict
    safe: dict | None
    tornado: dict
    out: dict


def _args(s: SimState) -> tuple:
    # 【기능】 engine.simulate 의 앞 인자 다섯 — 동 · 대상 · 종류 · 돈 · 기간
    return (s["dongs"], s["who"], s["kind"], s["budget"], s["years"])


def plan(s: SimState) -> dict:
    # 【기능】 이 안 — 고른 순서로 1,000번(모르는 값 50 × 주사위 20). 대상이 0명이면 None
    return {"plan": engine.simulate(*_args(s), s["order"], overrides=s["overrides"])}


def has_target(s: SimState) -> list[str] | str:
    # 【기능】 plan 다음 갈림길 — 대상 0명이면 끝, 아니면 세 노드로 동시에 갈라진다
    # 【판단】 셋은 서로의 값을 안 쓴다 → 같은 단계(superstep)에서 함께 돌려도 된다
    if s["plan"] is None:
        return END
    return FAN


def compare(s: SimState) -> dict:
    # 【기능】 비교 안 — 같은 돈 · 같은 동, 순서만 다르게(기본은 모델 위험 순)
    other = s["compare_order"] if s["compare_order"] != s["order"] else "무작위"
    b = engine.simulate(*_args(s), other, overrides=s["overrides"])
    return {"compare": {**b, "order": other}}


def safe(s: SimState) -> dict:
    # 【기능】 보수적 경우(SIM-106 ③) — 효과를 절반으로(NNT 두 배), 뽑기 20번
    return {"safe": engine.simulate(*_args(s), s["order"], draws=20, nnt_x=2)}


def tornado(s: SimState) -> dict:
    # 【기능】 값 하나씩 흔들기(SIM-106) — 씨앗 60개
    return {"tornado": engine.tornado(*_args(s), s["order"], seeds=60)}


def assemble(s: SimState) -> dict:
    # 【기능】 화면이 받는 결과 한 덩어리 — 예전 simulation_run 이 만들던 모양 그대로
    a, b = s["plan"], s["compare"]
    k = engine.KINDS[s["kind"]]
    over = s["overrides"]
    cost = over.get("cost", sum(k["cost"]) / 2)
    pairs = zip(a["finals"], b["finals"], strict=True)
    prob = sum(fb > fa for fa, fb in pairs) / len(a["finals"])
    out = {
        "input": s["request"],
        "plan": a,
        "compare": b,
        "prob_compare_better": round(prob, 2),
        "safe": s["safe"]["final"] if s["safe"] else None,
        "tornado": s["tornado"],
        "meet_n": round(s["budget"] / cost),
        "target_n": a["target_n"],
        "kind_src": k["src"],
        "used": {
            "cost": cost,
            "nnt": over.get("nnt", sum(k["nnt"]) / 2),
            "base_stay": over.get("base_stay", 24),
            "nnt_range": k["nnt"],
            "cost_range": k["cost"],
            "stay_range": engine.STAY_RANGE,
        },
    }
    return {"out": out}


def paragraph(s: SimState) -> dict:
    # 【기능】 설명글(SIM-107) 쓰기와 숫자 검사 — 결과에 없는 숫자 목록을 함께 남긴다
    para = text.write_paragraph(s["out"])
    bad = text.check_numbers(para, s["out"])
    return {"out": {**s["out"], "paragraph": para, "paragraph_bad_numbers": bad}}


def numbers_ok(s: SimState) -> str:
    # 【기능】 paragraph 다음 갈림길 — 숫자가 계산 결과와 다르면 글을 빼러 간다
    return "numbers_only" if s["out"]["paragraph_bad_numbers"] else END


def numbers_only(s: SimState) -> dict:
    # 【기능】 숫자가 틀린 글은 화면에 내지 않는다 — 화면은 숫자만 보인다
    return {"out": {**s["out"], "paragraph": None}}


def build() -> StateGraph:
    # 【기능】 노드 7개와 길을 이어 그래프 설계도를 만든다(compile 전)
    g = StateGraph(SimState)
    for name, fn in [
        ("run_plan", plan),
        ("run_compare", compare),
        ("run_safe", safe),
        ("run_tornado", tornado),
        ("assemble", assemble),
        ("paragraph", paragraph),
        ("numbers_only", numbers_only),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "run_plan")
    g.add_conditional_edges("run_plan", has_target, [*FAN, END])
    # 【문법】 add_edge([여러 노드], 다음) = 앞의 노드가 모두 끝나야 다음으로 간다(모으기)
    g.add_edge(FAN, "assemble")
    g.add_edge("assemble", "paragraph")
    g.add_conditional_edges("paragraph", numbers_ok, ["numbers_only", END])
    g.add_edge("numbers_only", END)
    return g


GRAPH = build().compile()


def run(
    request: dict,
    dongs: list[str],
    who: str,
    kind: str,
    budget: float,
    years: int,
    order: str = "무작위",
    compare_order: str = "모델 위험 순",
    overrides: dict | None = None,
) -> dict | None:
    # 【기능】 그래프를 한 번 돌려 결과를 돌려준다. 대상이 0명이면 None(화면 SIM-100E2)
    s = GRAPH.invoke(
        {
            "request": request,
            "dongs": dongs,
            "who": who,
            "kind": kind,
            "budget": budget,
            "years": years,
            "order": order,
            "compare_order": compare_order,
            "overrides": overrides or {},
        }
    )
    return None if s.get("plan") is None else s["out"]
