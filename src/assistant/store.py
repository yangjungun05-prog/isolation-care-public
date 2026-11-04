"""대화 상태 저장소 — 턴이 끝날 때마다 상태 하나를 통째로 쓴다.

【판단】 이음은 메모리 dict 만 써서 서버가 다시 켜지면 40턴짜리 대화가 사라졌다(조사 3절).
       저장소를 인터페이스로 두고, 지금은 메모리 · JSON 파일. 팀 저장소에서는 PostgreSQL 표로.
       팀 ERD chat_turn 에는 상태 칸이 없어 chat_state 표나 chat_turn.slots 칸을
       더해야 한다(HANDOVER).
【판단】 저장이 실패해도 이번 답은 내보낸다(대화는 잇는다). 실패는 last_error 에 남긴다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

from src.assistant.state import DialogueState

_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class Store(Protocol):
    def load(self, session_id: str) -> DialogueState | None: ...

    def save(self, session_id: str, state: DialogueState) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}
        self.last_error: str | None = None

    def load(self, session_id: str) -> DialogueState | None:
        raw = self._d.get(session_id)
        return DialogueState.model_validate_json(raw) if raw else None

    def save(self, session_id: str, state: DialogueState) -> None:
        # 【판단】 JSON 문자열로 넣어 둔다 — 밖에서 객체를 제자리에서 고쳐도 저장본은 안 바뀐다
        self._d[session_id] = state.model_dump_json()


class JsonFileStore:
    """세션마다 JSON 파일 하나. 개발 · 시험용.

    【판단】 여러 프로세스가 같은 세션을 동시에 쓰는 것은 막지 않는다(운영은 DB 저장소).
    """

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.last_error: str | None = None

    def _path(self, session_id: str) -> Path:
        if not _SAFE.match(session_id):
            raise ValueError("session_id 는 영문 · 숫자 · _ · - 64자 이내")
        return self.folder / f"{session_id}.json"

    def load(self, session_id: str) -> DialogueState | None:
        p = self._path(session_id)
        if not p.exists():
            return None
        try:
            return DialogueState.model_validate_json(p.read_text(encoding="utf-8"))
        except ValueError as e:
            self.last_error = f"복원 실패(새로 시작): {e}"
            return None

    def save(self, session_id: str, state: DialogueState) -> None:
        p = self._path(session_id)
        tmp = p.with_suffix(".tmp")
        try:
            tmp.write_text(state.model_dump_json(indent=1), encoding="utf-8")
            tmp.replace(p)
        except OSError as e:
            self.last_error = f"저장 실패: {e}"
