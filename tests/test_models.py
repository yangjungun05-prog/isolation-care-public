"""모델(Base.metadata)이 ERDCloud 스냅숏(db/erdcloud_SQL2.json)과 같은지 본다. DB 없이 돈다."""

import json
from pathlib import Path

import src.common.init_db  # noqa: F401 — 모든 모델을 Base.metadata 에 등록
from src.common.database import Base

SNAPSHOT = Path(__file__).parents[1] / "db" / "erdcloud_SQL2.json"

# SQLAlchemy 형 이름 → ERDCloud 자료형 (JSONB 는 ERDCloud 에서 TEXT 로 보인다)
ERD_TYPE = {
    "Integer": "INT",
    "BigInteger": "BIGINT",
    "Double": "DOUBLE",
    "Date": "DATE",
    "DateTime": "DATETIME",
    "Text": "TEXT",
    "Boolean": "BOOLEAN",
    "JSONB": "TEXT",
}


def load_snapshot() -> dict:
    return {t["t"]: t for t in json.loads(SNAPSHOT.read_text(encoding="utf-8"))}


def erd_type(column) -> str:
    name = type(column.type).__name__
    if name == "String":
        return f"VARCHAR({column.type.length})"
    return ERD_TYPE[name]


def test_same_tables_as_erdcloud():
    assert set(Base.metadata.tables) == set(load_snapshot())


def test_columns_match_erdcloud():
    for name, t in load_snapshot().items():
        table = Base.metadata.tables[name]
        assert table.comment == t["n"], name
        expected = t["pk"] + t["fk"] + t["f"]
        assert [c.name for c in table.columns] == [c[0] for c in expected], name
        pk = {c[0] for c in t["pk"] + t["fk"]}
        for col_name, typ, allow_null, comment, ref_table, ref_col in expected:
            column = table.columns[col_name]
            where = f"{name}.{col_name}"
            assert erd_type(column) == typ, where
            assert column.nullable == bool(allow_null), where
            assert column.primary_key == (col_name in pk), where
            assert column.comment == comment, where
            targets = {f"{fk.column.table.name}.{fk.column.name}" for fk in column.foreign_keys}
            assert targets == ({f"{ref_table}.{ref_col}"} if ref_table else set()), where


def test_foreign_key_count():
    n = sum(len(t.foreign_keys) for t in Base.metadata.tables.values())
    expected = sum(1 for t in load_snapshot().values() for c in t["pk"] + t["fk"] + t["f"] if c[4])
    assert n == expected == 71
