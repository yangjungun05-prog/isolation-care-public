import numpy as np

from src.simulation import inputs

STAY = 1 - 1 / 24
SCALE = 10
KINDS = {
    "찾아가서 살피기(방문)": {
        "nnt": (10.3, 14.4),
        "cost": (980_000, 1_070_000),
        "src": "효과: 안부확인 d .263(보건사회연구원) · 비용: 노인맞춤돌봄 98~107만원",
    },
    "안부 확인(전화 · IoT)": {
        "nnt": (13.7, 50.0),
        "cost": (28_000, 60_000),
        "src": "효과: 사회적 지지형 메타분석 13.7(위쪽 50 은 가정) · 비용: 서울 · 경기 2.8~6만원",
    },
    "함께 모이는 활동": {
        "nnt": (6.9, 9.3),
        "cost": (140_000, 350_000),
        "src": "효과: 공동체 d .384(보건사회연구원) · 비용: KYN 14만~상담 35만원(빌린 값)",
    },
    "생활 지원": {
        "nnt": (7.9, 10.7),
        "cost": (980_000, 1_070_000),
        "src": "효과: 혼합 d .340(보건사회연구원) · 비용: 노인맞춤돌봄 98~107만원",
    },
    # 【판단】 고립 · 은둔 청년(10/23 사용자 결정으로 대상 추가). 청년 사업의 효과 크기 연구 값이
    #   없어 혼합형(d .340)을 빌린다 — 화면에 "빌린 값"으로 보인다
    "청년 관계 회복(사례관리)": {
        "nnt": (7.9, 10.7),
        "cost": (2_730_000, 4_670_000),
        "src": "효과: 혼합 d .340 빌린 값(청년 연구 없음) · 비용: 서울 고립은둔청년 273~467만원 · "
        "알려서 신청받기: 한 해 신청 0.87~3.6% · 신청자 중 대상 40~57%"
        "(서울 2024 · 2025, 복지부 2023)",
    },
}

WHO = {
    "80세 이상 혼자 사는 분": lambda r: (r["age"] >= 80) & r["alone"],
    "65세 이상 혼자 사는 분": lambda r: (r["age"] >= 65) & r["alone"],
    "기초수급 어르신": lambda r: (r["age"] >= 65) & r["basic"],
    "기초수급 주민(나이 무관)": lambda r: r["basic"],
    # 【판단】 은둔 청년은 부모와 사는 경우가 많다 → 1인가구로 거르지 않고 청년 전체를 대상으로.
    #   누가 은둔인지는 as_homebound 로 맞춘다(10/23 사용자 결정 2번)
    "고립·은둔 청년(19~34세)": lambda r: (r["age"] >= 19) & (r["age"] <= 34),
}
YOUTH = "고립·은둔 청년(19~34세)"

# 【판단】 청년만의 순서 '알려서 신청받기'(10-29 사용자 결정 C — 찾기 + 돕기). 청년은 은둔을 고르게
#   뿌려서 모델 점수가 은둔을 못 가른다 → 점수 대신 '손을 든 사람'을 만난다. 두 값은 서울 실적
#   - 한 해 신청 = 은둔 · 고립 청년 어림의 0.87 ~ 3.6%:
#     신청 1,119(2024) · 4,681(2025) ÷ 서울 추정 12.9만(2022)
#   - 신청자 중 대상 = 40 ~ 57%: 2025 지원 1,882 / 신청 4,681 · 2024 선정 557 / 신청 1,119 ·
#     복지부 2023 온라인 위험군 12,105 / 응답 21,360
#   서울 추정은 19~39세 고립 + 은둔, 우리 어림은 19~34세 거의 집에만 있는 청년이라
#   정의가 다르다 → 어림
APPLY = "알려서 신청받기"
APPLY_RATE = (0.0087, 0.036)
APPLY_HIT = (0.40, 0.57)


def who_mask(r: dict, who: str) -> np.ndarray:

    return WHO[who](r)


# ── 여기부터 노트북에서 옮긴 것(Claude) — 바깥 변수 대신 인자로 받게만 바꿨다 ──


def stay_from_nnt(nnt: float, months: int = 12, base_stay: float = 24) -> float:
    # 【기능】 노트북 33단계 그대로 — "months 달 동안 nnt 명을 도우면 1명이 더 벗어난다"는 근거를
    #   만난 고립자가 머무는 평균 달로 바꿔 돌려준다
    base_leave = 1 - (1 - 1 / base_stay) ** months
    with_leave = min(base_leave + 1 / nnt, 0.99)
    stay = (1 - with_leave) ** (1 / months)
    return 1 / (1 - stay)


def reached(
    r: dict,
    target: np.ndarray,
    budget: float,
    cost: float,
    order: str = "무작위",
    seeds: int = 20,
    apply: tuple[float, float] | None = None,
) -> tuple[np.ndarray, float]:
    # 【기능】 1년 돈으로 실제로 만나는 사람을 주사위(씨앗)마다 고른다
    #   돌려주는 값: (seeds, 주민 수) 참 / 거짓 표, 대상 중 닿는 비율 reach
    n = len(target)
    idx = np.flatnonzero(target)
    # 【판단】 노트북 26단계 with_budget — 만날 수 있는 실제 사람 ÷ 대상 실제 사람. 1 을 넘으면 전원
    reach = min(1.0, budget / cost / max(len(idx) * SCALE, 1))
    if order == APPLY:
        mid = (sum(APPLY_RATE) / 2, sum(APPLY_HIT) / 2)
        return applied(target, r["risk"], budget, cost, apply or mid, seeds)
    if order == "무작위":
        # 【판단】 노트북 34단계와 같은 뽑기 — 씨앗 s 마다 주사위 s + 10_000 으로 대상 중 reach 만큼
        pick = np.stack([np.random.default_rng(s + 10_000).random(n) for s in range(seeds)])
        return target & (pick < reach), reach
    # 【판단】 점수 높은 순 k 명(노트북 27단계) — 모델 위험 순은 p, 고립자 먼저는 고립(0/1) + p
    score = r["p"] if order == "모델 위험 순" else r["risk"] + r["p"]
    k = int(round(len(idx) * reach))
    # 【판단】 합계표 주민은 칸마다 점수가 같다 → 동점 순서가 컴퓨터마다 같게 stable 정렬
    top = idx[np.argsort(-score[idx], kind="stable")[:k]]
    one = np.zeros(n, dtype=bool)
    one[top] = True
    # 【문법】 np.tile(배열, (seeds, 1)) = 같은 줄을 seeds 번 쌓는다 — 점수 순은 주사위와 상관없다
    return np.tile(one, (seeds, 1)), reach


def applied(
    target: np.ndarray,
    risk: np.ndarray,
    budget: float,
    cost: float,
    apply: tuple[float, float],
    seeds: int,
) -> tuple[np.ndarray, float]:
    # 【기능】 '알려서 신청받기' — 손을 든 사람 중에서 돈만큼 만난다. 돌려주는 값은 reached 와 같다
    # 【판단】 신청자 수 = 대상 중 고립(은둔) × 한 해 신청 비율 ÷ 신청자 중 대상 비율.
    #   만나는 수는 돈과 신청자 중 작은 쪽 — 신청자보다 돈이 많아도 더 만나지 못한다(알리기의 한계)
    rate, hit = apply
    n = len(target)
    sick = target & (risk == 1)
    well = target & (risk == 0)
    asked = sick.sum() * rate / hit
    meet = min(budget / cost / SCALE, asked)
    p_sick = min(1.0, meet * hit / max(int(sick.sum()), 1))
    p_well = min(1.0, meet * (1 - hit) / max(int(well.sum()), 1))
    # 【판단】 무작위와 같은 방식으로 씨앗마다 주사위를 굴리되, 고립 · 아님에 다른 확률을 쓴다
    dice = np.stack([np.random.default_rng(s + 30_000).random(n) for s in range(seeds)])
    pick = np.where(sick, dice < p_sick, np.where(well, dice < p_well, False))
    return pick, float(meet / max(int(target.sum()), 1))


def run_paths(
    r: dict,
    met: np.ndarray,
    stay0: float,
    stay_prog: float,
    months_on: int,
    months: int = 36,
    enter: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:

    s0, p = r["risk"], r["p"]
    seeds, n = met.shape
    # 【판단】 enter 를 주면 그대로 쓴다 — 청년처럼 집단마다 따로 맞춘 확률(calibrate)을 넣을 때
    if enter is None:
        enter = (1 - stay0) * s0.sum() / p[s0 == 0].sum() * p
    stay_on = np.where(met, stay_prog, stay0)
    rngs = [np.random.default_rng(s) for s in range(seeds)]
    a = np.tile(s0, (seeds, 1))
    b = a.copy()
    gap, none = [np.zeros(seeds)], [a.mean(axis=1)]
    for month in range(months):
        u = np.stack([g.random(n) for g in rngs])
        a = np.where(a == 1, u < stay0, u < enter).astype(int)
        stay_b = stay_on if month < months_on else stay0
        b = np.where(b == 1, u < stay_b, u < enter).astype(int)
        gap.append(a.mean(axis=1) - b.mean(axis=1))
        none.append(a.mean(axis=1))
    return np.array(gap).T * n * SCALE, np.array(none).T * n * SCALE


# ── 노트북 35단계에서 옮긴 것(Claude) — 모르는 값을 범위 안에서 뽑아 여러 번 ──

STAY_RANGE = (12, 36)  # 고립이 평균 몇 달 이어지나 — 근거 없음, 넓게 흔든다(노트북 34단계)


def draw_unknowns(
    kind: str, draws: int = 50, overrides: dict | None = None, seed: int = 2026, nnt_x: float = 1.0
) -> list:
    # 【기능】 모르는 값 셋(머무는 달 · 효과 NNT · 1인당 비용)을 범위 안에서 draws 번 고르게 뽑는다
    # 【판단】 [고치기]로 정한 값(overrides)은 뽑은 값을 덮어쓴다. 뽑기는 그대로 해서 나머지 값의
    #   순서가 안 바뀌게 한다 → 한 값만 고쳐도 다른 값은 같은 것으로 비교된다
    rng = np.random.default_rng(seed)
    # 【판단】 '알려서 신청받기' 두 값은 다른 주사위(seed + 1)로 뽑는다 — 기존 세 값의 순서가
    #   그대로라 예전 결과(노트북 대조 시험)가 바뀌지 않는다
    rng2 = np.random.default_rng(seed + 1)
    # 【판단】 nnt_x = 2 는 "보수적" 경우(SIM-106 ③) — 전후 비교 연구의 효과는 무작위 대조
    #   연구로 보면 약 절반(Masi 0.37 → 0.20, 근거조사 4절)이라 NNT 를 두 배로 본다
    lo, hi = KINDS[kind]["nnt"]
    ranges = {"base_stay": STAY_RANGE, "nnt": (lo * nnt_x, hi * nnt_x), "cost": KINDS[kind]["cost"]}
    out = []
    for _ in range(draws):
        guess = {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in ranges.items()}
        guess |= {
            "apply_rate": float(rng2.uniform(*APPLY_RATE)),
            "apply_hit": float(rng2.uniform(*APPLY_HIT)),
        }
        out.append({**guess, **(overrides or {})})
    return out


def youth_homebound(dong_cd: str) -> float | None:
    # 【기능】 그 동의 '거의 집에만 있는 청년' 어림 가운데 값(실제 사람) — 비서 · 대시보드와
    #   같은 자료(청년의 삶 실태조사 2024 나이별 비율 × 동 나이 구성). 10명 미만이거나 없으면 None
    from src.dashboard import grades

    src = inputs.load()
    if src is None:
        return None
    name = src["dongs"].loc[dong_cd, "dong"]
    h = (grades.profiles().get(name, {}).get("youth") or {}).get("homebound") or {}
    if not h or h.get("under10"):
        return None
    return (h["lo"] + h["hi"]) / 2


def as_homebound(r: dict, dong_cd: str, seed: int = 0) -> tuple[dict, np.ndarray]:
    # 【기능】 청년의 고립 상태를 은둔 어림 수에 맞춘 주민 사본과 청년 표시를 돌려준다
    # 【판단】 건강조사에는 은둔 문항이 없다 → 청년 중 어림 수만큼을 씨앗을 고정해 고르게 뽑아
    #   '고립(은둔)'으로 둔다. 누가 은둔인지는 모르니 고르게 뽑는 것이 가장 덜 꾸민 가정이다
    youth = WHO[YOUTH](r)
    hb = youth_homebound(dong_cd)
    if hb is None:
        return r, youth
    idx = np.flatnonzero(youth)
    k = min(len(idx), int(round(hb / SCALE)))
    pick = np.random.default_rng(seed + 20_000).choice(idx, size=k, replace=False)
    risk = r["risk"].copy()
    risk[idx] = 0
    risk[pick] = 1
    return {**r, "risk": risk}, youth


def calibrate(r: dict, stay0: float, groups: list[np.ndarray]) -> np.ndarray:
    # 【기능】 집단마다 따로 "벗어나는 수 = 들어오는 수"가 되게 새로 고립될 확률을 맞춘다
    #   (노트북 38단계 집단별 맞추기)
    s0, p = r["risk"], r["p"]
    enter = np.zeros(len(s0))
    for g in groups:
        free = p[g & (s0 == 0)].sum()
        enter[g] = (1 - stay0) * s0[g].sum() / free * p[g] if free > 0 else 0.0
    return enter


def simulate_dong(
    dong_cd: str,
    who: str,
    budget: float,
    guesses: list,
    months_on: int,
    order: str = "무작위",
    seeds: int = 20,
    months: int = 36,
) -> dict:
    # 【기능】 동 하나를 뽑은 값(guesses)마다 돌려, 씨앗 평균 경로를 뽑은 값 수만큼 쌓아 돌려준다
    #   gap · none: (뽑은 값 수, months + 1) — 줄어든 고립 · 사업 없을 때 고립(실제 사람)
    r = inputs.residents(dong_cd)
    youth = None
    if who == YOUTH:
        # 【판단】 청년은 은둔 어림으로 고립 상태를 맞추고, 청년 · 나머지를 따로 맞춘다
        r, youth = as_homebound(r, dong_cd)
    target = who_mask(r, who)
    gaps, nones, reaches = [], [], []
    for g in guesses:
        stay0 = 1 - 1 / g["base_stay"]
        prog = 1 - 1 / stay_from_nnt(g["nnt"], base_stay=g["base_stay"])
        apply = (g["apply_rate"], g["apply_hit"])
        met, reach = reached(r, target, budget, g["cost"], order, seeds, apply)
        enter = None if youth is None else calibrate(r, stay0, [youth, ~youth])
        gap, none = run_paths(r, met, stay0, prog, months_on, months, enter)
        gaps.append(gap.mean(axis=0))
        nones.append(none.mean(axis=0))
        reaches.append(reach)
    return {
        "gap": np.array(gaps),
        "none": np.array(nones),
        "target_n": int(target.sum()) * SCALE,
        "isolated_n": int(r["risk"].sum()) * SCALE,
        "target_isolated_n": int(r["risk"][target].sum()) * SCALE,
        "reach": float(np.median(reaches)),
    }


def simulate(
    dongs: list[str],
    who: str,
    kind: str,
    budget: float,
    years: int,
    order: str = "무작위",
    draws: int = 50,
    seeds: int = 20,
    overrides: dict | None = None,
    nnt_x: float = 1.0,
) -> dict | None:
    # 【기능】 고른 동들에 1년 돈을 대상 인원 비율로 나눠 동마다 돌리고, 뽑은 값마다 더해 요약한다
    #   대상이 한 명도 없으면 None(화면 SIM-100E2 "대상 0명")
    guesses = draw_unknowns(kind, draws, overrides, nnt_x=nnt_x)
    sizes = {cd: int(who_mask(inputs.residents(cd), who).sum()) for cd in dongs}
    total = sum(sizes.values())
    if total == 0:
        return None
    # 【판단】 돈은 대상 인원 비율로 나눈다(대상이 많은 동에 더 많이). 뽑은 값은 모든 동이 같다
    per = {
        cd: simulate_dong(cd, who, budget * n / total, guesses, years * 12, order, seeds)
        for cd, n in sizes.items()
        if n > 0
    }
    # 【문법】 np.sum(배열 목록, axis=0) = 같은 모양 배열을 칸마다 더한다 → (뽑은 값 수, 37)
    gap = np.sum([x["gap"] for x in per.values()], axis=0)
    none = np.sum([x["none"] for x in per.values()], axis=0)

    def spread(arr: np.ndarray) -> dict:
        # 【기능】 뽑은 값 축(0번)을 따라 10% · 가운데 · 90% 자리 값
        q = np.percentile(arr, [10, 50, 90], axis=0).round(2)
        return {"p10": q[0].tolist(), "median": q[1].tolist(), "p90": q[2].tolist()}

    return {
        "final": spread(gap[:, -1]),
        "path": spread(gap),
        "none": np.median(none, axis=0).round(1).tolist(),
        "yearly": [round(float(np.median(gap[:, 12 * y])), 2) for y in (1, 2, 3)],
        "target_n": total * SCALE,
        "target_isolated_n": sum(x["target_isolated_n"] for x in per.values()),
        "per_dong": {cd: round(float(np.median(x["gap"][:, -1])), 2) for cd, x in per.items()},
        "runs": len(guesses) * seeds,
        # 【기능】 뽑은 값마다 3년 뒤 값 — 두 안을 같은 뽑은 값끼리 견줄 때(B 가 나을 확률) 쓴다
        "finals": gap[:, -1].round(2).tolist(),
    }


# ── 노트북 34단계에서 옮긴 것(Claude) — 값 하나씩 흔들기(토네이도) ──


def tornado(
    dongs: list[str],
    who: str,
    kind: str,
    budget: float,
    years: int,
    order: str = "무작위",
    seeds: int = 100,
) -> dict:
    # 【기능】 값 하나만 낮은 쪽 · 높은 쪽으로 바꾸고 나머지는 가운데에 둔 채 3년 뒤 줄어든
    #   고립을 다시 센다 → 흔드는 폭이 큰 순서로. 화면 SIM-106 "제일 흔드는 값 ★"
    # 【판단】 씨앗 20개는 0.5명 단위로 흔들려 순서가 뒤집혔다(노트북 34단계) → 기본 100개
    k = KINDS[kind]
    mid = {"base_stay": 24.0, "nnt": sum(k["nnt"]) / 2, "cost": sum(k["cost"]) / 2}

    def run(over: dict | None = None, yrs: int = years, odr: str = order) -> float:
        s = simulate(
            dongs,
            who,
            kind,
            budget,
            yrs,
            odr,
            draws=1,
            seeds=seeds,
            overrides={**mid, **(over or {})},
        )
        return 0.0 if s is None else s["final"]["median"]

    base = run()
    other = "고립자 먼저" if order != "고립자 먼저" else "무작위"
    tests = [
        (
            "고립이 이어지는 기간",
            "가정",
            "12달",
            "36달",
            run({"base_stay": 12}),
            run({"base_stay": 36}),
        ),
        (
            "몇 명 도와야 1명 나아지나",
            "연구",
            f"{k['nnt'][1]}명",
            f"{k['nnt'][0]}명",
            run({"nnt": k["nnt"][1]}),
            run({"nnt": k["nnt"][0]}),
        ),
        (
            "1인당 1년 비용",
            "조사",
            f"{k['cost'][1] // 10_000}만원",
            f"{k['cost'][0] // 10_000}만원",
            run({"cost": k["cost"][1]}),
            run({"cost": k["cost"][0]}),
        ),
        ("사업 기간", "고를 수 있음", "1년", "3년", run(yrs=1), run(yrs=3)),
        ("누구부터 만나나", "고를 수 있음", order, other, base, run(odr=other)),
    ]
    rows = [
        {
            "name": n,
            "src": src,
            "lo_label": a,
            "hi_label": b,
            "lo": lo,
            "hi": hi,
            "swing": abs(hi - lo),
        }
        for n, src, a, b, lo, hi in tests
    ]
    return {"base": base, "rows": sorted(rows, key=lambda x: -x["swing"])}


def reverse(
    dongs: list[str],
    who: str,
    kind: str,
    goal: float,
    years: int,
    order: str = "무작위",
    draws: int = 10,
    seeds: int = 10,
    overrides: dict | None = None,
) -> dict | None:
    # 【판단】 [고치기]로 정한 값(overrides)이 있으면 거꾸로 계산도 같은 값으로 — 화면 결과와 맞게
    cost = (overrides or {}).get("cost", sum(KINDS[kind]["cost"]) / 2)
    first = simulate(dongs, who, kind, 1, years, order, draws=1, seeds=1)
    if first is None:
        return None

    def got(budget: float) -> float:
        s = simulate(dongs, who, kind, budget, years, order, draws, seeds, overrides)
        return 0.0 if s is None else s["final"]["median"]

    hi = first["target_n"] * cost
    best = got(hi)
    if best < goal:
        return {"budget": None, "best": best, "all_budget": hi}
    # 【판단】 반으로 좁혀 찾기 — 가운데 돈으로 목표에 닿으면 위 끝을, 못 닿으면 아래 끝을 옮긴다.
    #   12번이면 처음 폭의 4,096분의 1 까지 좁아진다
    lo = 0.0
    for _ in range(12):
        mid = (lo + hi) / 2
        if got(mid) >= goal:
            hi = mid
        else:
            lo = mid
    budget = float(np.ceil(hi / 1_000_000) * 1_000_000)
    # 【판단】 위에서는 빨리 찾으려고 100번(10 × 10)만 돌렸다. 화면은 1,000번(50 × 20)으로
    #   계산하므로 그 금액을 1,000번으로 한 번 더 재고, 모자라면 10%씩 올린다
    #   → [이 금액으로 다시 계산]을 누르면 목표에 닿는다
    all_budget = first["target_n"] * cost
    while budget < all_budget:
        s = simulate(dongs, who, kind, budget, years, order, overrides=overrides)
        if s is not None and s["final"]["median"] >= goal:
            break
        budget = float(np.ceil(budget * 1.1 / 1_000_000) * 1_000_000)
    return {"budget": min(budget, all_budget), "best": best, "all_budget": all_budget}
