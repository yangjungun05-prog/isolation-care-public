"""시뮬레이션 재료 — 공개판은 합계표에서 가상 주민을 만든다.

건강조사 응답자 줄은 쓰지 않는다. 쓰는 것은 data/derived_public/sim_inputs/ 의 표 셋이다.
- cells.csv: 나이 9구간 × 혼자 삶 × 기초수급 칸마다 고립 비율(전국 약 46만 명, 칸 최소 86명)
- shares.csv: 동마다 칸 구성 비율
- dongs.csv: 동마다 성인 수 · 고립 비율

【판단】 칸 안에서는 사람을 가르지 못한다. 그래서 '모델 위험 순'은 칸 비율 순이 되고,
       응답자 줄과 모델 점수로 계산한 대회판보다 효과가 작게 나온다.
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from src.dashboard import cards


def inputs_dir() -> Path:
    # 【판단】 cards.DERIVED 를 부를 때마다 읽는다 — 시험에서 폴더를 바꿔 끼울 수 있게
    return cards.DERIVED / "sim_inputs"


@lru_cache(maxsize=1)
def load() -> dict | None:
    # 【기능】 표 셋을 읽어 돌려준다. 없으면 None
    out = inputs_dir()
    if not (out / "cells.csv").exists():
        return None
    shares = pd.read_csv(out / "shares.csv", dtype={"dong_cd": str})
    return {
        "cells": pd.read_csv(out / "cells.csv"),
        "shares": dict(tuple(shares.groupby("dong_cd"))),
        "dongs": pd.read_csv(out / "dongs.csv", dtype={"dong_cd": str}).set_index("dong_cd"),
    }


def residents(dong_cd: str, scale: int = 10, seed: int = 0) -> dict[str, np.ndarray]:
    # 【기능】 (성인 ÷ scale)명을 칸 비율대로 뽑아 나이 · 혼자 삶 · 수급 · 고립 · 점수를 만든다
    src = load()
    if src is None:
        raise FileNotFoundError(f"시뮬레이션 재료가 없어요: {inputs_dir()}")
    part = src["shares"][dong_cd]
    n = int(round(src["dongs"].loc[dong_cd, "adult"] / scale))
    rng = np.random.default_rng(seed)
    weights = (part["share"] / part["share"].sum()).to_numpy()
    c = src["cells"].iloc[rng.choice(part["cell"].to_numpy(), size=n, p=weights)]
    # 【판단】 칸 비율은 전국 값이라 그 동의 고립 비율에 맞춰 한 번에 키우거나 줄인다
    base = c["rate"].to_numpy()
    p = np.clip(base * src["dongs"].loc[dong_cd, "rate"] / max(base.mean(), 1e-9), 0, 1)
    return {
        "age": rng.integers(c["age_lo"].to_numpy(), c["age_hi"].to_numpy() + 1).astype(float),
        "alone": c["alone"].to_numpy() == 1,
        "basic": c["basic"].to_numpy() == 1,
        "risk": (rng.random(n) < p).astype(int),
        "p": p,
    }
