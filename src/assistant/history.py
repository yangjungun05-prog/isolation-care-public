"""비서 대화 기록 — 질문 하나에 팀 표 chat_turn 한 줄(10-25 팀장 "대화기록도 해줘").

    rec = DbHistory()                       # 팀 .env 의 DATABASE_URL(src/common/database)
    rec.add(member_id, session_id, 질문, reply, ms)
    rec.sessions(member_id)                 # 지난 대화 묶음(최근 것부터)
    rec.turns(member_id, session_id)        # 한 묶음의 문답

【판단】 표는 팀 ERD(ERDCloud 스냅숏) 그대로 쓴다 — 칸을 더하지 않는다(tests/test_models.py).
       chat_turn = 회원 · 대화 묶음 · 순서 · 맥락 동 · 질문 · 알아들은 종류 · 막은 이유 · 한 줄 답 ·
       걸린 시간 · 때. 답 전체는 칸이 없어 '한 줄 답'(300자)으로 줄여 남긴다
【판단】 10-29 팀장 '대화가 가독성이 별로야 … | <- 이런 건 왜 있는거야': 지난 대화를 다시 열면 한 줄
       답만 있어 표가 '|' 글자로 뭉개지고 엑셀 단추가 없었다 → 답 전체 · 건넨 파일 이름은 팀 ERD
       밖의 chat_answer 표(chat_turn.turn_id 하나에 한 줄)에 둔다. chat_state(store_pg)처럼 팀 표를
       고치지 않고 처음 쓸 때 만든다 — 표 이름 · 칸은 팀원 확인 전 제안
【판단】 막은 질문(개인 찾기 · 긴급)과 1,000자 넘는 글은 질문 원문을 남기지 않는다(AI비서 ERD
       인수인계서 '막은 질문은 원문을 저장하지 않는다'). 나머지 질문도 이름 · 전화번호 같은 것은
       가린 뒤(pii.mask) 남긴다
【판단】 기록은 그 회원 것만 읽는다. 기록이 실패해도 이번 답은 나간다(대화 저장소와 같음) —
       실패는 last_error 에 남긴다
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import Column, Integer, MetaData, Table, Text, func, select
from sqlalchemy.orm import Session, sessionmaker

from src.assistant import pii
from src.assistant.models import ChatTurn
from src.common.models import Dong

if TYPE_CHECKING:
    from src.assistant.engine import Reply

KST = timezone(timedelta(hours=9))
HEADLINE_MAX = 300  # chat_turn.headline
INTENT_MAX = 20  # chat_turn.intent
NO_QUESTION = ("blocked", "too_long")  # 질문 원문을 남기지 않는 답 종류
WHY = {"person": "개인 찾기", "emergency": "긴급 상황"}
SGG = {"강남구": "11230", "춘천시": "32010"}


ANSWER_MAX = 20_000  # 답 전체(표 포함)는 이만큼까지
# 팀 ERD(Base.metadata) 밖의 표 — tests/test_models.py 의 ERD 대조에 들지 않는다
_EXTRA = MetaData()
CHAT_ANSWER = Table(
    "chat_answer",
    _EXTRA,
    Column("turn_id", Integer, primary_key=True, comment="chat_turn.turn_id"),
    Column("answer", Text, nullable=False, comment="답 전체(표 포함)"),
    Column("files", Text, comment="건넨 파일 이름(줄마다 하나)"),
    comment="대화 답 전체 — 지난 대화를 표 · 내려받기 단추 그대로 다시 그린다(10-29)",
)


def headline(text: str) -> str:
    """답을 한 줄로(줄바꿈을 빈칸으로) — 300자를 넘으면 자르고 '…'."""
    one = " ".join((text or "").split())
    return one if len(one) <= HEADLINE_MAX else one[: HEADLINE_MAX - 1] + "…"


def question_kept(text: str, kind: str) -> str | None:
    """남길 질문 — 막은 질문 · 너무 긴 글은 비우고, 나머지는 개인정보를 가린 글."""
    if kind in NO_QUESTION:
        return None
    masked, _ = pii.mask((text or "").strip())
    return masked or None


def blocked_why(reply: Reply) -> str | None:
    if reply.kind == "blocked":
        return WHY.get(reply.card.block, "막음")
    if reply.kind == "too_long":
        return "1,000자 넘음"
    return None


def _now() -> datetime:
    # 회원 표(login_log 등)와 같게 한국 시각, 시간대 표시 없이
    return datetime.now(KST).replace(tzinfo=None)


def _dong_cd(db: Session, reply: Reply) -> str | None:
    """대화가 보던 동(첫 동) → 행정동 코드. 동을 안 골랐거나 표에 없으면 비움."""
    slots = reply.state.slots
    if not slots.dongs:
        return None
    sgg = SGG.get(slots.region or reply.state.profile.member_region or "")
    q = select(Dong.dong_cd).where(Dong.name == slots.dongs[0])
    if sgg:
        q = q.where(Dong.sgg_cd == sgg)
    return db.scalars(q).first()


def _at(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M")


class DbHistory:
    def __init__(self, maker: sessionmaker | None = None) -> None:
        self._maker = maker
        self.last_error: str | None = None
        self._answer_ready = False

    def _answer_table(self, db: Session) -> None:
        if not self._answer_ready:
            CHAT_ANSWER.create(db.connection(), checkfirst=True)
            self._answer_ready = True

    def _session(self) -> sessionmaker:
        if self._maker is None:
            from src.common.database import SessionLocal  # noqa: PLC0415 — 쓸 때만(DB 연결 설정)

            self._maker = SessionLocal
        return self._maker

    def add(self, member_id: int, session_id: str, text: str, reply: Reply, ms: int) -> None:
        try:
            with self._session().begin() as db:
                last = db.scalar(
                    select(func.max(ChatTurn.seq)).where(
                        ChatTurn.member_id == member_id, ChatTurn.session_id == session_id
                    )
                )
                turn = ChatTurn(
                    member_id=member_id,
                    session_id=session_id,
                    seq=(last or 0) + 1,
                    ctx_card_id=None,
                    ctx_dong_cd=_dong_cd(db, reply),
                    question=question_kept(text, reply.kind),
                    intent=reply.kind[:INTENT_MAX],
                    blocked_why=blocked_why(reply),
                    headline=headline(reply.text),
                    ms=ms,
                    at=_now(),
                )
                db.add(turn)
                db.flush()
                self._answer_table(db)
                files = "\n".join(Path(f).name for f in reply.files) or None
                db.execute(
                    CHAT_ANSWER.insert().values(
                        turn_id=turn.turn_id, answer=(reply.text or "")[:ANSWER_MAX], files=files
                    )
                )
        except Exception as e:  # noqa: BLE001 — 기록이 안 돼도 대화는 잇는다
            self.last_error = f"대화 기록 실패: {type(e).__name__}"

    def sessions(self, member_id: int, limit: int = 20) -> list[dict]:
        """지난 대화 묶음 — 마지막으로 말한 때가 최근인 것부터(첫 질문 · 문답 수 · 처음 · 끝)."""
        with self._session().begin() as db:
            rows = db.execute(
                select(
                    ChatTurn.session_id,
                    func.count(),
                    func.min(ChatTurn.at),
                    func.max(ChatTurn.at),
                )
                .where(ChatTurn.member_id == member_id)
                .group_by(ChatTurn.session_id)
                # 【판단】 10-27: 같은 초에 끝난 두 묶음은 순서가 흔들렸다(시험이 가끔 실패) —
                #        같은 때면 나중에 적힌 줄(문답ID)이 큰 쪽을 먼저
                .order_by(func.max(ChatTurn.at).desc(), func.max(ChatTurn.turn_id).desc())
                .limit(limit)
            ).all()
            ids = [r[0] for r in rows]
            first = dict(
                db.execute(
                    select(ChatTurn.session_id, ChatTurn.question).where(
                        ChatTurn.member_id == member_id,
                        ChatTurn.session_id.in_(ids),
                        ChatTurn.seq == 1,
                    )
                ).all()
            )
        return [
            {
                "session_id": sid,
                "first": first.get(sid),
                "turns": n,
                "started": _at(start),
                "last": _at(end),
            }
            for sid, n, start, end in rows
        ]

    def turns(self, member_id: int, session_id: str) -> list[dict]:
        """한 묶음의 문답 — 순서대로. 다른 회원의 묶음은 비어 나온다."""
        with self._session().begin() as db:
            rows = db.scalars(
                select(ChatTurn)
                .where(ChatTurn.member_id == member_id, ChatTurn.session_id == session_id)
                .order_by(ChatTurn.seq)
            ).all()
            self._answer_table(db)
            full = {
                r.turn_id: r
                for r in db.execute(
                    select(CHAT_ANSWER).where(CHAT_ANSWER.c.turn_id.in_([t.turn_id for t in rows]))
                ).all()
            }
            return [
                {
                    "seq": t.seq,
                    "question": t.question,
                    "intent": t.intent,
                    "blocked_why": t.blocked_why,
                    "headline": t.headline,
                    # 10-29: 답 전체 · 파일(없으면 옛 기록 — 화면은 한 줄 답을 쓴다)
                    "answer": full[t.turn_id].answer if t.turn_id in full else None,
                    "files": (full[t.turn_id].files or "").split("\n")
                    if t.turn_id in full and full[t.turn_id].files
                    else [],
                    "ms": t.ms,
                    "at": _at(t.at),
                }
                for t in rows
            ]
