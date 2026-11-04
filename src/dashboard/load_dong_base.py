"""동 바탕 고립 인원·이유를 DB 에 넣는다 — 노트북 02 의 19단계 결과(CSV) → dash_dong_base 표.

    uv run python -m src.dashboard.load_dong_base

dash_dong_base 는 통합 ERD(erd_dash_sim.sql, 10/13)에는 있지만 ERDCloud 스냅숏에는 아직 없다.
그래서 models.py 에 넣지 않고(테스트가 "모델 = ERDCloud" 를 검사한다) 여기서 표를 직접 만든다.
ERDCloud 에 표를 올리고 make_models.py 를 다시 돌리면 이 파일의 CREATE 는 필요 없어진다.
"""

from pathlib import Path

import pandas as pd
from sqlalchemy import text

from src.common.database import engine

CSV = Path(__file__).parents[2] / "data" / "processed" / "dong_base_2025.csv"

# 【판단】 ERD 와 같은 칸. JSON 칸은 저장소 규칙(10/2: ERDCloud 의 TEXT → Postgres JSONB)을 따른다
CREATE_SQL = """
CREATE TABLE IF NOT EXISTS dash_dong_base (
    base_id SERIAL PRIMARY KEY,
    dong_cd VARCHAR(8) NOT NULL REFERENCES dong (dong_cd),
    base_year INTEGER NOT NULL,
    adult INTEGER NOT NULL,
    rate DOUBLE PRECISION NOT NULL,
    est_n INTEGER NOT NULL,
    who_75 DOUBLE PRECISION,
    who_alone DOUBLE PRECISION,
    who_basic DOUBLE PRECISION,
    standout JSONB,
    detail JSONB,
    model_ver VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_dash_dong_base_dong_cd_base_year UNIQUE (dong_cd, base_year)
);
COMMENT ON TABLE dash_dong_base IS '동 바탕 고립 인원·이유(해마다)';
"""

# 【판단】 같은 (동, 연도) 가 이미 있으면 새 값으로 덮어쓴다 → 몇 번을 돌려도 47줄
UPSERT_SQL = """
INSERT INTO dash_dong_base (dong_cd, base_year, adult, rate, est_n, who_75, who_alone, who_basic,
                            standout, detail, model_ver, created_at)
VALUES (:dong_cd, :base_year, :adult, :rate, :est_n, :who_75, :who_alone, :who_basic,
        CAST(:standout AS JSONB), CAST(:detail AS JSONB), :model_ver, :created_at)
ON CONFLICT (dong_cd, base_year) DO UPDATE SET
    adult = EXCLUDED.adult, rate = EXCLUDED.rate, est_n = EXCLUDED.est_n,
    who_75 = EXCLUDED.who_75, who_alone = EXCLUDED.who_alone, who_basic = EXCLUDED.who_basic,
    standout = EXCLUDED.standout, detail = EXCLUDED.detail,
    model_ver = EXCLUDED.model_ver, created_at = EXCLUDED.created_at
"""


def load_dong_base(csv_path: Path = CSV) -> int:
    # 【기능】 표가 없으면 만들고, CSV 의 줄을 넣거나 덮어쓴 뒤, 표의 줄 수를 돌려준다
    rows = pd.read_csv(csv_path, dtype={"dong_cd": str}).drop(columns=["dong"])
    # 【판단】 응답자가 적은 동은 세부 비율이 비어 있다 — 빈칸은 NULL 로 넣는다
    rows = rows.astype(object).where(rows.notna(), None)
    with engine.begin() as conn:
        conn.execute(text(CREATE_SQL))
        conn.execute(text(UPSERT_SQL), rows.to_dict(orient="records"))
        return conn.execute(text("SELECT count(*) FROM dash_dong_base")).scalar_one()


if __name__ == "__main__":
    n = load_dong_base()
    print(f"dash_dong_base {n}줄")
