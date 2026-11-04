"""[했어요] 기록 — 카드마다 회원이 누른 것(10-15).

팀 ERD todo_done 과 같은 모양: 했어요 · 해당 없음 + 이유.

【판단】 09-27 팀장 결정(챗봇을 비서로): 알림은 '오늘 챙길 일' 카드와 [했어요].
       스토리보드 확정 초안은 기록 팝업(CHT-105)을 가리키지만 그 장은 덱에 없다.
       그래서 팀원과 확정한 표(todo_done: status '했어요 · 해당 없음',
       reason '해당 없음 이유' 200자)를 그대로 따른다
【판단】 개인 이름 · 연락처는 받지 않는다(스토리보드 DSH-105B "동과 집단 단위로만 기록"). 이유 글에
       이름 · 전화 같은 것이 섞이면 pii.mask 로 가린 뒤 저장하고, 가렸다고 돌려준다
【판단】 다시 누르면 새 줄을 더한다(지난 기록을 지우지 않음). 화면에는 가장 최근 것을 보인다
【판단】 저장소는 약속(DoneStore)으로 두고 지금은 메모리 · JSON 줄 파일.
       팀 저장소에서는 todo_done 표
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from src.assistant import pii

STATUSES = ("했어요", "해당 없음")
REASON_MAX = 200
# 팀 ERD todo_card.card_id — 시군구 코드-종류-계기 첫날(today.Card.id). 청년 카드는 '청년-'이
# 붙고(10-19), 큰비 · 눈이 그친 뒤 카드는 '폭우 뒤' · '폭설 뒤'(10-20)
CARD_ID = re.compile(
    r"^\d{5}-(청년-)?(폭우|한파|폭설|폭염|폭우 뒤|폭설 뒤|긴 연휴|교통 중단|월초 점검)"
    r"-\d{4}-\d{2}-\d{2}$"
)
KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Done:
    card_id: str
    member_id: int
    status: str
    reason: str | None
    at: str
    masked: tuple[str, ...] = ()  # 가린 것의 종류(이름 · 전화번호 …)


def make(card_id: str, member_id: int, status: str, reason: str | None = None) -> Done:
    """화면에서 받은 값을 검사해 기록 한 줄로. 틀리면 ValueError."""
    if not CARD_ID.match(card_id):
        raise ValueError("카드 번호가 맞지 않아요")
    if status not in STATUSES:
        raise ValueError("'했어요' 또는 '해당 없음'만 받아요")
    text = (reason or "").strip()
    if status == "했어요":
        text = ""  # 【판단】 ERD reason 은 '해당 없음 이유' — 했어요에는 남기지 않는다
    if len(text) > REASON_MAX:
        raise ValueError(f"이유는 {REASON_MAX}자까지 받아요")
    masked, kinds = pii.mask(text) if text else ("", [])
    return Done(
        card_id=card_id,
        member_id=member_id,
        status=status,
        reason=masked or None,
        at=datetime.now(KST).isoformat(timespec="seconds"),
        masked=tuple(dict.fromkeys(kinds)),
    )


class DoneStore(Protocol):
    def add(self, rec: Done) -> None: ...

    def latest(self, member_id: int, card_ids: Iterable[str]) -> dict[str, Done]: ...


class MemoryDoneStore:
    def __init__(self) -> None:
        self._rows: list[Done] = []

    def add(self, rec: Done) -> None:
        self._rows.append(rec)

    def latest(self, member_id: int, card_ids: Iterable[str]) -> dict[str, Done]:
        want = set(card_ids)
        out: dict[str, Done] = {}
        for r in self._rows:  # 뒤에 더한 것이 이긴다
            if r.member_id == member_id and r.card_id in want:
                out[r.card_id] = r
        return out


class JsonlDoneStore:
    """기록마다 한 줄(더하기만). 개발 · 시험 화면용 — 운영은 팀 DB todo_done."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def add(self, rec: Done) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(rec), ensure_ascii=False) + "\n"
        with self._lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(line)

    def latest(self, member_id: int, card_ids: Iterable[str]) -> dict[str, Done]:
        want = set(card_ids)
        out: dict[str, Done] = {}
        if not self.path.exists():
            return out
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        for raw in lines:
            if not raw.strip():
                continue
            d = json.loads(raw)
            if d["member_id"] == member_id and d["card_id"] in want:
                out[d["card_id"]] = Done(**{**d, "masked": tuple(d.get("masked") or ())})
        return out


def erd_row(rec: Done) -> dict:
    """팀 ERD todo_done 한 줄 모양(done_id 는 DB 가 매긴다)."""
    return {
        "card_id": rec.card_id,
        "member_id": rec.member_id,
        "status": rec.status,
        "reason": rec.reason,
        "at": rec.at,
    }
