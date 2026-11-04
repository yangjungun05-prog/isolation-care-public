"""PostgreSQL 대화 상태 저장소 — 팀 저장소(uv · PostgreSQL 18 · psycopg 3)로 옮길 때 쓴다(10-15).

    from src.common.settings import settings
    store = PgStore(settings.database_url)        # 팀 .env 의 DATABASE_URL 그대로
    store.ensure_table()                          # chat_state 표가 없으면 만든다

【판단】 팀 ERD 의 chat_turn 에는 대화 상태(칸 · 기억) 칸이 없다(HANDOVER 5절). 상태 하나를 통째로
       JSONB 로 두는 chat_state 표를 따로 둔다. 턴 원문 기록(chat_turn)과 섞지 않아 팀 표를 고치지
       않아도 된다. 표 이름 · 칸은 팀원 확인 전 제안이다
【판단】 저장소 약속(Store)은 메모리 · JSON 파일과 같다. 저장이 실패해도 이번 답은 내보낸다
       (last_error 에 남김). 불러오기가 실패하면 새 대화로 시작한다
【판단】 psycopg 는 쓸 때만 가져온다(이 저장소 시험은 DB 없이 돈다. 팀 저장소에는 이미 있다)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from src.assistant.state import DialogueState

DDL = """CREATE TABLE IF NOT EXISTS chat_state (
    session_id varchar(64) PRIMARY KEY,
    state      jsonb       NOT NULL,
    turn       integer     NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
)"""
LOAD = "SELECT state FROM chat_state WHERE session_id = %s"
SAVE = (
    "INSERT INTO chat_state (session_id, state, turn, updated_at) "
    "VALUES (%s, %s::jsonb, %s, now()) "
    "ON CONFLICT (session_id) DO UPDATE "
    "SET state = EXCLUDED.state, turn = EXCLUDED.turn, updated_at = now()"
)


def _psycopg_connect(url: str) -> Any:
    import psycopg  # noqa: PLC0415 — 쓸 때만

    return psycopg.connect(url, autocommit=True)


class PgStore:
    def __init__(self, url: str, connect: Callable[[str], Any] | None = None) -> None:
        # 【기능】 SQLAlchemy 주소(postgresql+psycopg://)를 psycopg 주소로
        self.url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._connect = connect or _psycopg_connect
        self.last_error: str | None = None

    def ensure_table(self) -> None:
        with self._connect(self.url) as conn:
            conn.execute(DDL)

    def load(self, session_id: str) -> DialogueState | None:
        try:
            with self._connect(self.url) as conn:
                row = conn.execute(LOAD, (session_id,)).fetchone()
        except Exception as e:  # noqa: BLE001 — DB 오류는 새 대화로
            self.last_error = f"불러오기 실패(새로 시작): {type(e).__name__}"
            return None
        if not row:
            return None
        raw = row[0]
        try:
            return DialogueState.model_validate(raw if isinstance(raw, dict) else json.loads(raw))
        except ValueError as e:
            self.last_error = f"복원 실패(새로 시작): {e}"
            return None

    def save(self, session_id: str, state: DialogueState) -> None:
        try:
            with self._connect(self.url) as conn:
                conn.execute(SAVE, (session_id, state.model_dump_json(), state.turn))
        except Exception as e:  # noqa: BLE001 — 저장 실패에도 대화는 잇는다
            self.last_error = f"저장 실패: {type(e).__name__}"
