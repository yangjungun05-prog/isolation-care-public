"""시뮬레이션 표 — G 시뮬레이션

ERDCloud 다이어그램 SQL2 의 10/2 스냅숏에서 make_models.py 로 만든 파일이다.
https://www.erdcloud.com/d/7pZnAtirEeFc7iDba
표·칸을 바꾸려면 ERDCloud 를 고친 뒤 스냅숏을 다시 받아 다시 만든다(손으로 고치면 어긋난다).
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# ── G 시뮬레이션 ──


class BudgetProject(Base):
    """지방재정 사업"""

    __tablename__ = "budget_project"
    __table_args__ = {"comment": "지방재정 사업"}

    project_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="재정 사업ID")
    year: Mapped[int] = mapped_column(Integer, comment="회계연도")
    sgg_name: Mapped[str] = mapped_column(String(30), comment="지자체 이름(전국)")
    sgg_cd: Mapped[str | None] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), comment="시군구(우리 지역이면)"
    )
    name: Mapped[str] = mapped_column(String(200), comment="사업 이름")
    category: Mapped[str | None] = mapped_column(String(30), comment="분야(방문·안부 등)")
    amount: Mapped[int] = mapped_column(BigInteger, comment="예산(원)")


class Ordinance(Base):
    """조례"""

    __tablename__ = "ordinance"
    __table_args__ = {"comment": "조례"}

    ordinance_id: Mapped[str] = mapped_column(
        String(30), primary_key=True, comment="조례ID(자치법규)"
    )
    sgg_name: Mapped[str] = mapped_column(String(30), comment="지자체 이름")
    sgg_cd: Mapped[str | None] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), comment="시군구(우리 지역이면)"
    )
    name: Mapped[str] = mapped_column(String(200), comment="조례 이름")
    enacted_day: Mapped[date | None] = mapped_column(Date, comment="제정일")
    link: Mapped[str | None] = mapped_column(String(300), comment="원문 링크")


class SimRun(Base):
    """시뮬레이션 실행"""

    __tablename__ = "sim_run"
    __table_args__ = {"comment": "시뮬레이션 실행"}

    sim_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="실행ID")
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("member.member_id"), comment="실행한 회원"
    )
    sgg_cd: Mapped[str] = mapped_column(String(5), ForeignKey("region.sgg_cd"), comment="시군구")
    policy_type: Mapped[str] = mapped_column(String(30), comment="정책 종류")
    target_group: Mapped[str] = mapped_column(String(50), comment="누구에게")
    budget_input: Mapped[int | None] = mapped_column(BigInteger, comment="입력한 돈(1년, 원)")
    budget_used: Mapped[int] = mapped_column(BigInteger, comment="계산에 쓴 돈(1년, 원)")
    budget_by_ai: Mapped[bool] = mapped_column(Boolean, comment="AI가 돈 빈칸을 채움")
    period_years: Mapped[int] = mapped_column(Integer, comment="기간(해)")
    visits_per_week: Mapped[int | None] = mapped_column(Integer, comment="횟수(주)")
    start_ym: Mapped[str | None] = mapped_column(String(6), comment="AI가 제안한 시작 달")
    story: Mapped[str | None] = mapped_column(
        Text, comment="설명글(입력, 개인 정보가 있으면 실행 안 함)"
    )
    assumptions: Mapped[Any] = mapped_column(
        JSONB, nullable=False, comment="실제로 쓴 가정 값 (JSON)"
    )
    pauses: Mapped[Any] = mapped_column(JSONB, nullable=True, comment="멈춤에서 고른 것 (JSON)")
    result: Mapped[Any] = mapped_column(
        JSONB, nullable=True, comment="해마다 결과: 가운데 값·범위·1인당 비용 (JSON)"
    )
    headline: Mapped[str | None] = mapped_column(String(300), comment="한 줄 결론")
    explanation: Mapped[str | None] = mapped_column(Text, comment="보고용 설명글")
    saved_name: Mapped[str | None] = mapped_column(String(30), comment="저장 이름(A안 등)")
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("budget_project.project_id"), comment="이미 하는 사업"
    )
    ordinance_id: Mapped[str | None] = mapped_column(
        String(30), ForeignKey("ordinance.ordinance_id"), comment="근거 조례"
    )
    seed: Mapped[int] = mapped_column(BigInteger, comment="난수 씨앗(다시 계산용)")
    engine_ver: Mapped[str] = mapped_column(String(40), comment="계산 엔진 판(git 커밋)")
    status: Mapped[str] = mapped_column(String(4), comment="완료·실패")
    failed_stage: Mapped[str | None] = mapped_column(
        String(4), comment="멈춘 단계(정리·판단·계산·설명)"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="실행한 때")


class SimDong(Base):
    """시뮬레이션 대상 동"""

    __tablename__ = "sim_dong"
    __table_args__ = {"comment": "시뮬레이션 대상 동"}

    sim_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sim_run.sim_id"), primary_key=True, comment="실행"
    )
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    order_no: Mapped[int] = mapped_column(Integer, comment="AI가 제안한 순서")


class SimSimilar(Base):
    """유사 복지 사업"""

    __tablename__ = "sim_similar"
    __table_args__ = {"comment": "유사 복지 사업"}

    sim_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sim_run.sim_id"), primary_key=True, comment="실행"
    )
    program_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("program.program_id"), primary_key=True, comment="닮은 복지 사업"
    )
    rank_no: Mapped[int] = mapped_column(Integer, comment="닮은 순서")
