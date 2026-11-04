"""시뮬레이션 엔진이 공개판 기준값을 다시 내는지 — 재료 파일(git 제외)이 있을 때만 돈다."""

import numpy as np
import pytest

from src.simulation import engine, inputs

pytestmark = pytest.mark.skipif(inputs.load() is None, reason="시뮬레이션 재료 없음(git 제외)")
YEOKSAM1 = "11230640"
BASIC = "기초수급 주민(나이 무관)"
VISIT = "찾아가서 살피기(방문)"


def test_residents_match_notebook():
    # 공개판 기준값 — 역삼1동 가상 주민 3,248명(성인 수 ÷ 10), 기초수급 890명
    r = inputs.residents(YEOKSAM1)
    assert len(r["risk"]) == 3248
    assert int(engine.who_mask(r, BASIC).sum()) * engine.SCALE == 890


def test_scenario_control():
    # 노트북 34단계 대조 — 기본 가정(24달 · NNT 12.3 · 100만원 · 무작위 3년) 씨앗 20개 = 2.5명
    r = inputs.residents(YEOKSAM1)
    met, _ = engine.reached(r, engine.who_mask(r, BASIC), 100_000_000, 1_000_000)
    prog = 1 - 1 / engine.stay_from_nnt(12.3)
    gap, none = engine.run_paths(r, met, engine.STAY, prog, months_on=36)
    assert gap.shape == none.shape == (20, 37)
    assert round(float(gap[:, 36].mean()), 1) == 3.0


def test_probability_match_notebook():
    # 노트북 35단계 — A 무작위 3년 4.5 [3.0, 6.0] · B 고립자 먼저 1년 반 2.5 [0.5, 4.0] · 확률 0.16
    guesses = engine.draw_unknowns(VISIT, draws=100)
    a = engine.simulate_dong(YEOKSAM1, BASIC, 100_000_000, guesses, 36, "무작위")
    b = engine.simulate_dong(YEOKSAM1, BASIC, 100_000_000, guesses, 18, "고립자 먼저")
    fa, fb = a["gap"][:, 36], b["gap"][:, 36]
    assert round(float(np.median(fa)), 1) == 3.0
    assert np.percentile(fa, [10, 90]).round(1).tolist() == [2.0, 5.5]
    assert round(float(np.median(fb)), 1) == 2.0
    assert round(float((fb > fa).mean()), 2) == 0.22


def test_effect_needs_money_and_effect():
    # 대조 — 돈이 0 이면, 효과가 없으면(NNT 아주 큼) 줄어든 사람도 0
    args = ([YEOKSAM1], BASIC, VISIT)
    assert engine.simulate(*args, 0, 3, draws=5)["final"]["median"] == 0
    s = engine.simulate(*args, 100_000_000, 3, draws=5, overrides={"nnt": 1e9})
    assert s["final"]["median"] == 0


def test_tornado_order():
    # 노트북 34단계 — 가장 크게 흔드는 값은 "누구부터 만나나", 가장 작은 값은 비용
    t = engine.tornado([YEOKSAM1], BASIC, VISIT, 100_000_000, 3)
    names = [row["name"] for row in t["rows"]]
    assert names[0] == "누구부터 만나나" and names[-1] == "1인당 1년 비용"


def test_youth_homebound_control():
    # 【기능】 청년 은둔 맞추기 — 은둔 수 = 어림 가운데 값, 청년 밖 고립은 그대로,
    #   사업이 없으면 36달 동안 고립 인원이 처음 근처에 머문다(집단별 맞추기 대조)
    r = inputs.residents(YEOKSAM1)
    r2, youth = engine.as_homebound(r, YEOKSAM1)
    assert int(r2["risk"][youth].sum()) * engine.SCALE == round(engine.youth_homebound(YEOKSAM1))
    assert (r2["risk"][~youth] == r["risk"][~youth]).all()
    s = engine.simulate([YEOKSAM1], engine.YOUTH, "청년 관계 회복(사례관리)", 0, 3, draws=5)
    assert abs(s["none"][-1] - s["none"][0]) / s["none"][0] < 0.02


def test_youth_apply_meets_applicants():
    # 【기능】 알려서 신청받기(10-29) — 만나는 수는 돈과 신청자 중 작은 쪽, 만난 사람 중 은둔 몫은
    #   신청자 중 대상 비율 근처. 돈을 100배 늘려도 신청자보다 많이 만나지 못한다(대조)
    r, youth = engine.as_homebound(inputs.residents(YEOKSAM1), YEOKSAM1)
    sick = r["risk"] == 1
    rate, hit, cost = 0.02, 0.5, 3_700_000
    asked = (youth & sick).sum() * rate / hit
    small, _ = engine.reached(r, youth, 100_000_000, cost, engine.APPLY, 400, (rate, hit))
    big, _ = engine.reached(r, youth, 10_000_000_000, cost, engine.APPLY, 400, (rate, hit))
    assert abs(small.sum(axis=1).mean() - min(1e8 / cost / engine.SCALE, asked)) < 0.3
    assert abs(big.sum(axis=1).mean() - asked) < 0.3
    assert abs((small & sick).sum() / small.sum() - hit) < 0.1


def test_youth_apply_between_random_and_upper():
    # 【기능】 청년 1억 3년 — 무작위 ≤ 알려서 신청받기 ≤ 은둔 청년 먼저(상한)
    kind = "청년 관계 회복(사례관리)"
    got = {
        o: engine.simulate([YEOKSAM1], engine.YOUTH, kind, 100_000_000, 3, o)["final"]["median"]
        for o in ("무작위", engine.APPLY, "고립자 먼저")
    }
    assert got["무작위"] <= got[engine.APPLY] <= got["고립자 먼저"]
    assert got[engine.APPLY] > got["무작위"]
