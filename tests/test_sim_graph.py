"""시뮬레이션 실행 그래프(src/simulation/graph.py) — 모양 · 갈림길 · 예전 순서와 같은 값."""

import pytest

from src.simulation import engine, inputs, text
from src.simulation import graph as G

need_inputs = pytest.mark.skipif(inputs.load() is None, reason="시뮬레이션 재료 없음(git 제외)")
KIND = "찾아가서 살피기(방문)"


def test_shape():
    # 노드 7개 · plan 에서 셋으로 갈라졌다가 assemble 로 모인다 · 갈림길 두 곳
    g = G.GRAPH.get_graph()
    nodes = set(g.nodes) - {"__start__", "__end__"}
    assert nodes == {"run_plan", *G.FAN, "assemble", "paragraph", "numbers_only"}
    edges = {(e.source, e.target, e.conditional) for e in g.edges}
    assert {("run_plan", n, True) for n in G.FAN} <= edges
    assert {(n, "assemble", False) for n in G.FAN} <= edges
    assert ("run_plan", "__end__", True) in edges
    assert ("paragraph", "numbers_only", True) in edges


def fake_result(median: float) -> dict:
    # 【기능】 engine.simulate 가 돌려주는 모양의 가짜 — 재료 파일 없이 갈림길만 시험한다
    return {
        "final": {"p10": median - 1, "median": median, "p90": median + 1},
        "finals": [median] * 4,
        "target_n": 100,
    }


@pytest.fixture
def fake_engine(monkeypatch):
    calls = []

    def simulate(dongs, who, kind, budget, years, order="무작위", **kw):
        calls.append(order)
        return fake_result(5.0 if order == "무작위" else 7.0)

    monkeypatch.setattr(engine, "simulate", simulate)
    monkeypatch.setattr(
        engine, "tornado", lambda *a, **k: {"base": 5.0, "rows": [{"name": "누구부터 만나나"}]}
    )
    return calls


def go(**kw):
    request = {"dongs": ["역삼1동"], "who": "65세 이상 혼자 사는 분", "kind": KIND}
    request |= {"money": 10_000, "years": 3}
    return G.run(request, ["역삼1동"], request["who"], KIND, 1e8, 3, **kw)


def test_no_target_stops_early(monkeypatch, fake_engine):
    # 대조 — 이 안이 None(대상 0명)이면 비교 안 · 보수적 · 흔드는 값을 부르지 않고 끝난다
    monkeypatch.setattr(engine, "simulate", lambda *a, **k: fake_engine.append(a[5]) or None)
    assert go() is None
    assert fake_engine == ["무작위"]


def test_fan_out_and_paragraph(fake_engine):
    out = go()
    # 이 안(무작위) · 비교 안(모델 위험 순) · 보수적(무작위) 세 번 — 갈라진 셋이 모두 돌았다
    assert sorted(fake_engine) == ["모델 위험 순", "무작위", "무작위"]
    assert out["compare"]["order"] == "모델 위험 순"
    assert out["prob_compare_better"] == 1.0  # 7 > 5 가 넷 다
    assert "1년 1억을" in out["paragraph"] and out["paragraph_bad_numbers"] == []


def test_bad_numbers_drop_paragraph(monkeypatch, fake_engine):
    # 대조 — 설명글 숫자 검사에 걸리면 numbers_only 로 가서 글을 뺀다
    monkeypatch.setattr(text, "check_numbers", lambda para, res: ["9.9"])
    out = go()
    assert out["paragraph"] is None and out["paragraph_bad_numbers"] == ["9.9"]


@need_inputs
def test_same_as_before():
    # 그래프로 옮기기 전(engine 을 차례로 부르던 순서)과 같은 값이 나온다
    d = inputs.load()["dongs"]
    cd = d.index[d["dong"] == "역삼1동"][0]
    who, kind, budget = "65세 이상 혼자 사는 분", "함께 모이는 활동", 1e8
    a = engine.simulate([cd], who, kind, budget, 3, "무작위", overrides={})
    b = engine.simulate([cd], who, kind, budget, 3, "모델 위험 순", overrides={})
    safe = engine.simulate([cd], who, kind, budget, 3, "무작위", draws=20, nnt_x=2)
    torn = engine.tornado([cd], who, kind, budget, 3, "무작위", seeds=60)
    out = G.run(
        {"dongs": ["역삼1동"], "who": who, "kind": kind, "money": 10_000, "years": 3},
        [cd],
        who,
        kind,
        budget,
        3,
    )
    assert out["plan"]["finals"] == a["finals"] and out["compare"]["finals"] == b["finals"]
    assert out["safe"] == safe["final"] and out["tornado"] == torn
    assert out["plan"]["final"]["median"] == 10.75 and out["compare"]["final"]["median"] == 17.5
