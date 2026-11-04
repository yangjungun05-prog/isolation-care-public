"""PostgreSQL 저장소 — DB 없이 가짜 연결로 약속(불러오기 · 저장 · 실패에도 대화 잇기)을 본다(10-15).

진짜 DB 확인은 Docker를 켠 뒤 `uv run python evals/check_pg_store.py` (팀원 저장소의 postgres 18).
"""

import json

from src.assistant.slots import Slots
from src.assistant.state import DialogueState, Profile
from src.assistant.store_pg import PgStore


class FakeConn:
    """psycopg 연결 흉내 — SQL 을 받아 dict 표에 쓴다(jsonb 는 dict 로 돌려준다)."""

    def __init__(self, table: dict, fail: bool = False) -> None:
        self.table, self.fail, self._row = table, fail, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql: str, params: tuple = ()):
        if self.fail:
            raise ConnectionError("db down")
        if sql.startswith("SELECT"):
            self._row = (self.table[params[0]],) if params[0] in self.table else None
        elif sql.startswith("INSERT"):
            self.table[params[0]] = json.loads(params[1])
        return self

    def fetchone(self):
        return self._row


def test_round_trip_and_sqlalchemy_url():
    table: dict = {}
    seen: list[str] = []

    def connect(url: str):
        seen.append(url)
        return FakeConn(table)

    s = PgStore("postgresql+psycopg://user:pw@localhost:5432/AgentDB", connect)
    assert s.load("a") is None
    st = DialogueState(turn=3, profile=Profile(member_region="강남구"),
                       slots=Slots(region="강남구", dongs=("수서동",)))  # fmt: skip
    s.save("a", st)
    assert s.load("a") == st and table["a"]["turn"] == 3
    assert seen[0].startswith("postgresql://")


def test_db_down_keeps_conversation_going():
    s = PgStore("postgresql://x", lambda url: FakeConn({}, fail=True))
    s.save("a", DialogueState())  # 올리지 않는다
    assert s.last_error and "저장 실패" in s.last_error
    assert s.load("a") is None and "불러오기 실패" in s.last_error
