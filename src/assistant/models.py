"""AI 비서 표 — C 판정 · D 비서가 쓰는 표

ERDCloud 다이어그램 SQL2 의 10/2 스냅숏에서 make_models.py 로 만든 파일이다.
https://www.erdcloud.com/d/7pZnAtirEeFc7iDba
표·칸을 바꾸려면 ERDCloud 를 고친 뒤 스냅숏을 다시 받아 다시 만든다(손으로 고치면 어긋난다).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Double, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# ── C 판정 ──


class DongRank(Base):
    """동 우선순위"""

    __tablename__ = "dong_rank"
    __table_args__ = {"comment": "동 우선순위"}

    ym: Mapped[str] = mapped_column(String(6), primary_key=True, comment="기준월")
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    alone_share: Mapped[float] = mapped_column(
        Double, comment="65세 이상 중 혼자 사는 몫(입소 정원 뺌)"
    )
    alone80: Mapped[int] = mapped_column(Integer, comment="80세 이상 혼자(입소 정원 뺌)")
    visibility_f60: Mapped[float | None] = mapped_column(
        Double, comment="60세 이상 여성 거리 가시성(강남)"
    )
    risk: Mapped[float] = mapped_column(Double, comment="위험 축")
    band: Mapped[int] = mapped_column(Integer, comment="위험 구간 1~5")
    resource_rank: Mapped[float] = mapped_column(Double, comment="자원 순위(65세 이상 1,000명당)")
    gap: Mapped[float] = mapped_column(Double, comment="자원 공백")
    rank_no: Mapped[int] = mapped_column(Integer, comment="순위")
    care_type: Mapped[str] = mapped_column(String(10), comment="처방 유형")
    care_why: Mapped[str] = mapped_column(String(200), comment="처방 이유")


class DiagItem(Base):
    """진단 항목"""

    __tablename__ = "diag_item"
    __table_args__ = {"comment": "진단 항목"}

    item_cd: Mapped[str] = mapped_column(String(12), primary_key=True, comment="가능성 코드")
    target: Mapped[str] = mapped_column(String(4), comment="대상(어르신·청년)")
    seq: Mapped[int] = mapped_column(Integer, comment="화면 순서")
    label: Mapped[str] = mapped_column(String(40), comment="쉬운 이름")
    rule: Mapped[str] = mapped_column(String(200), comment="해당 조건")
    scored: Mapped[bool] = mapped_column(Boolean, comment="겹친 수에 넣나")
    source_id: Mapped[str | None] = mapped_column(
        String(20), ForeignKey("source.source_id"), comment="주 자료"
    )


class DiagRun(Base):
    """진단 실행"""

    __tablename__ = "diag_run"
    __table_args__ = {"comment": "진단 실행"}

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="진단ID")
    sgg_cd: Mapped[str] = mapped_column(String(5), ForeignKey("region.sgg_cd"), comment="시군구")
    ym: Mapped[str] = mapped_column(String(6), comment="기준월(겨울 끝 달)")
    rule_ver: Mapped[str] = mapped_column(String(20), comment="기준값 판")
    q: Mapped[float] = mapped_column(Double, comment="해당 범위(위쪽 3분의 1 = 0.333)")
    winter_pp: Mapped[float | None] = mapped_column(Double, comment="겨울 악화 기준(%p)")
    code_ver: Mapped[str | None] = mapped_column(String(40), comment="계산 코드 판(git 커밋)")
    robust: Mapped[Any] = mapped_column(JSONB, nullable=True, comment="검증 결과 (JSON)")
    memos: Mapped[Any] = mapped_column(JSONB, nullable=True, comment="실무자 메모 (JSON)")
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="계산한 때")


class DiagCheck(Base):
    """동별 항목 판정"""

    __tablename__ = "diag_check"
    __table_args__ = {"comment": "동별 항목 판정"}

    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    item_cd: Mapped[str] = mapped_column(
        String(12), ForeignKey("diag_item.item_cd"), primary_key=True, comment="가능성"
    )
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("diag_run.run_id"), primary_key=True, comment="진단"
    )
    value: Mapped[float | None] = mapped_column(Double, comment="값")
    value_text: Mapped[str] = mapped_column(String(200), comment="화면 문장")
    rank_no: Mapped[int | None] = mapped_column(Integer, comment="순위(1이 가장 심함)")
    of_n: Mapped[int | None] = mapped_column(Integer, comment="몇 곳 중")
    pos: Mapped[float | None] = mapped_column(Double, comment="위치 0~1")
    hit: Mapped[bool | None] = mapped_column(Boolean, comment="해당")
    months: Mapped[Any] = mapped_column(JSONB, nullable=True, comment="7·8·11·12월 값 (JSON)")


class DiagDong(Base):
    """동 진단 결과"""

    __tablename__ = "diag_dong"
    __table_args__ = {"comment": "동 진단 결과"}

    target: Mapped[str] = mapped_column(String(4), primary_key=True, comment="대상(어르신·청년)")
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("diag_run.run_id"), primary_key=True, comment="진단"
    )
    order_no: Mapped[int] = mapped_column(Integer, comment="순서")
    grade: Mapped[str] = mapped_column(String(6), comment="단계(먼저 볼 동·살펴볼 동·지켜볼 동)")
    score: Mapped[int | None] = mapped_column(Integer, comment="겹친 수(어르신)")
    of_n: Mapped[int | None] = mapped_column(Integer, comment="가능성 수")
    rate: Mapped[float | None] = mapped_column(Double, comment="외출·연락 모두 적은 비율 %(청년)")
    ratio: Mapped[float | None] = mapped_column(Double, comment="구 평균 대비 배수(청년)")
    est_n: Mapped[int | None] = mapped_column(Integer, comment="외출·연락 모두 적은 사람 추정")
    type: Mapped[str | None] = mapped_column(String(40), comment="유형·모습")
    short: Mapped[str | None] = mapped_column(String(200), comment="한 줄 요약")
    conclusion: Mapped[str] = mapped_column(Text, comment="결론")
    actions: Mapped[Any] = mapped_column(JSONB, nullable=False, comment="현장에서 할 일 (JSON)")


class DiagTarget(Base):
    """진단 대상 동"""

    __tablename__ = "diag_target"
    __table_args__ = {"comment": "진단 대상 동"}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, comment="순서")
    kind: Mapped[str] = mapped_column(
        String(10), ForeignKey("todo_rule.kind"), primary_key=True, comment="카드 종류"
    )
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("diag_run.run_id"), primary_key=True, comment="진단"
    )
    dong_cd: Mapped[str] = mapped_column(String(8), ForeignKey("dong.dong_cd"), comment="행정동")
    value_text: Mapped[str] = mapped_column(String(60), comment="까닭 값")
    why: Mapped[str] = mapped_column(String(200), comment="고른 기준")


# ── D 비서가 쓰는 표 ──


class TodoRule(Base):
    """할 일 규칙"""

    __tablename__ = "todo_rule"
    __table_args__ = {"comment": "할 일 규칙"}

    kind: Mapped[str] = mapped_column(
        String(10),
        primary_key=True,
        comment="종류(폭우·한파·폭설·폭염·긴 연휴·교통 중단·월초 점검)",
    )
    threshold: Mapped[str] = mapped_column(String(40), comment="기준")
    target_rule: Mapped[str] = mapped_column(String(200), comment="먼저 볼 곳 고르는 법")
    enabled: Mapped[bool] = mapped_column(Boolean, comment="켜짐")


class TodoCard(Base):
    """할 일 카드"""

    __tablename__ = "todo_card"
    __table_args__ = {"comment": "할 일 카드"}

    card_id: Mapped[str] = mapped_column(
        String(80), primary_key=True, comment="카드ID(지역-종류-계기 첫날)"
    )
    kind: Mapped[str] = mapped_column(String(10), ForeignKey("todo_rule.kind"), comment="종류")
    sgg_cd: Mapped[str] = mapped_column(String(5), ForeignKey("region.sgg_cd"), comment="시군구")
    title: Mapped[str] = mapped_column(String(100), comment="제목")
    why: Mapped[str] = mapped_column(String(300), comment="왜(계기)")
    due: Mapped[str] = mapped_column(String(40), comment="기한")
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="만든 때")
    evidence: Mapped[Any] = mapped_column(
        JSONB, nullable=False, comment="근거와 믿을 만한 정도 (JSON)"
    )
    todo: Mapped[Any] = mapped_column(JSONB, nullable=False, comment="할 일 (JSON)")


class TodoTarget(Base):
    """카드 대상 동"""

    __tablename__ = "todo_target"
    __table_args__ = {"comment": "카드 대상 동"}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, comment="순서")
    card_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("todo_card.card_id"), primary_key=True, comment="카드"
    )
    dong_cd: Mapped[str] = mapped_column(String(8), ForeignKey("dong.dong_cd"), comment="행정동")
    note: Mapped[Any] = mapped_column(JSONB, nullable=False, comment="덧붙임 (JSON)")


class TodoDone(Base):
    """했어요 기록"""

    __tablename__ = "todo_done"
    __table_args__ = {"comment": "했어요 기록"}

    done_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="ID")
    card_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("todo_card.card_id"), comment="카드"
    )
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("member.member_id"), comment="누른 회원"
    )
    status: Mapped[str] = mapped_column(String(6), comment="했어요·해당 없음")
    reason: Mapped[str | None] = mapped_column(String(200), comment="해당 없음 이유")
    at: Mapped[datetime] = mapped_column(DateTime, comment="누른 때")


class ChatTurn(Base):
    """대화 문답"""

    __tablename__ = "chat_turn"
    __table_args__ = {"comment": "대화 문답"}

    turn_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="문답ID")
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("member.member_id"), comment="회원")
    session_id: Mapped[str] = mapped_column(String(36), comment="대화 묶음")
    seq: Mapped[int] = mapped_column(Integer, comment="대화 안 순서")
    ctx_card_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("todo_card.card_id"), comment="맥락 카드"
    )
    ctx_dong_cd: Mapped[str | None] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), comment="맥락 동"
    )
    question: Mapped[str | None] = mapped_column(Text, comment="질문(막은 질문은 비움)")
    intent: Mapped[str] = mapped_column(String(20), comment="알아들은 종류")
    blocked_why: Mapped[str | None] = mapped_column(String(40), comment="막은 이유")
    headline: Mapped[str] = mapped_column(String(300), comment="한 줄 답")
    ms: Mapped[int] = mapped_column(Integer, comment="걸린 시간(ms)")
    at: Mapped[datetime] = mapped_column(DateTime, comment="때")


class Briefing(Base):
    """브리핑"""

    __tablename__ = "briefing"
    __table_args__ = {"comment": "브리핑"}

    briefing_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="ID")
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("member.member_id"), comment="만든 회원"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="만든 때")
    card_id: Mapped[str | None] = mapped_column(
        String(80), ForeignKey("todo_card.card_id"), comment="출처 카드"
    )
    turn_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_turn.turn_id"), comment="출처 문답"
    )
    dong_cd: Mapped[str] = mapped_column(String(8), ForeignKey("dong.dong_cd"), comment="행정동")
    title: Mapped[str] = mapped_column(String(100), comment="제목")


class BriefingItem(Base):
    """브리핑 항목"""

    __tablename__ = "briefing_item"
    __table_args__ = {"comment": "브리핑 항목"}

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, comment="순서")
    briefing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("briefing.briefing_id"), primary_key=True, comment="브리핑"
    )
    kind: Mapped[str] = mapped_column(String(6), comment="누구·할 일·만날 곳·사업·발·출처")
    text: Mapped[str] = mapped_column(String(300), comment="내용")
    facility_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("facility.facility_id"), comment="시설"
    )
    program_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("program.program_id"), comment="사업"
    )
