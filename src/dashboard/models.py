"""대시보드 표 — F 대시보드(예상·경보·현장 기록)

ERDCloud 다이어그램 SQL2 의 10/2 스냅숏에서 make_models.py 로 만든 파일이다.
https://www.erdcloud.com/d/7pZnAtirEeFc7iDba
표·칸을 바꾸려면 ERDCloud 를 고친 뒤 스냅숏을 다시 받아 다시 만든다(손으로 고치면 어긋난다).
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# ── F 대시보드(예상·경보) ──


class CardPayDay(Base):
    """카드 결제(일)"""

    __tablename__ = "card_pay_day"
    __table_args__ = {"comment": "카드 결제(일)"}

    day: Mapped[date] = mapped_column(Date, primary_key=True, comment="날짜")
    age_group: Mapped[str] = mapped_column(
        String(10), primary_key=True, comment="나이대(20대…80대 이상)"
    )
    industry_group: Mapped[str] = mapped_column(
        String(20), primary_key=True, comment="업종 묶음(의료·장보기·음식 등)"
    )
    time_band: Mapped[str] = mapped_column(String(10), primary_key=True, comment="시간대")
    sgg_cd: Mapped[str] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), primary_key=True, comment="시군구"
    )
    n: Mapped[int] = mapped_column(Integer, comment="결제 건수")
    amount: Mapped[int] = mapped_column(BigInteger, comment="결제액(원)")


class FlowMonth(Base):
    """유동 인구(월)"""

    __tablename__ = "flow_month"
    __table_args__ = {"comment": "유동 인구(월)"}

    ym: Mapped[str] = mapped_column(String(6), primary_key=True, comment="기준월")
    age_group: Mapped[str] = mapped_column(String(10), primary_key=True, comment="나이대")
    time_band: Mapped[str] = mapped_column(String(10), primary_key=True, comment="시간대")
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    n: Mapped[int] = mapped_column(Integer, comment="유동 인구")


class DashSeries(Base):
    """예상 줄"""

    __tablename__ = "dash_series"
    __table_args__ = (
        UniqueConstraint("sgg_cd", "age_group", "industry_group"),
        {"comment": "예상 줄"},
    )

    series_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="줄ID")
    sgg_cd: Mapped[str] = mapped_column(String(5), ForeignKey("region.sgg_cd"), comment="시군구")
    age_group: Mapped[str] = mapped_column(String(10), comment="나이대")
    industry_group: Mapped[str] = mapped_column(String(20), comment="업종 묶음")


class DashModel(Base):
    """예측 모델"""

    __tablename__ = "dash_model"
    __table_args__ = {"comment": "예측 모델"}

    model_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="모델ID")
    model_type: Mapped[str] = mapped_column(String(20), comment="종류(기준선·LightGBM·LSTM)")
    train_from: Mapped[date] = mapped_column(Date, comment="학습 시작일")
    train_to: Mapped[date] = mapped_column(Date, comment="학습 끝일")
    wape: Mapped[float | None] = mapped_column(Double, comment="오차율(WAPE)")
    is_active: Mapped[bool] = mapped_column(Boolean, comment="지금 쓰는 모델")
    code_ver: Mapped[str | None] = mapped_column(String(40), comment="계산 코드 판(git 커밋)")
    trained_at: Mapped[datetime] = mapped_column(DateTime, comment="학습한 때")


class DashPrediction(Base):
    """예측값"""

    __tablename__ = "dash_prediction"
    __table_args__ = {"comment": "예측값"}

    day: Mapped[date] = mapped_column(Date, primary_key=True, comment="날짜")
    series_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dash_series.series_id"), primary_key=True, comment="줄"
    )
    model_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dash_model.model_id"), primary_key=True, comment="모델"
    )
    expected: Mapped[float] = mapped_column(Double, comment="예상한 값")
    lo80: Mapped[float] = mapped_column(Double, comment="예상 범위 아래(열에 여덟)")
    hi80: Mapped[float] = mapped_column(Double, comment="예상 범위 위(열에 여덟)")
    lo95: Mapped[float] = mapped_column(Double, comment="예상 범위 아래(스물에 열아홉)")
    hi95: Mapped[float] = mapped_column(Double, comment="예상 범위 위(스물에 열아홉)")
    actual: Mapped[float | None] = mapped_column(Double, comment="실제 값(날이 지나면 채움)")


class DashEffect(Base):
    """효과 참고표"""

    __tablename__ = "dash_effect"
    __table_args__ = {"comment": "효과 참고표"}

    effect_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="효과ID")
    factor: Mapped[str] = mapped_column(String(30), comment="요인(추석·폭설·성탄절 등)")
    sgg_cd: Mapped[str | None] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), comment="시군구(지역마다 다르면)"
    )
    age_group: Mapped[str | None] = mapped_column(String(10), comment="나이대")
    pct: Mapped[float] = mapped_column(Double, comment="효과(%)")
    pct_lo: Mapped[float | None] = mapped_column(Double, comment="효과 범위 아래(%)")
    pct_hi: Mapped[float | None] = mapped_column(Double, comment="효과 범위 위(%)")
    note: Mapped[str | None] = mapped_column(String(200), comment="근거")


class DashAlert(Base):
    """줄 경보"""

    __tablename__ = "dash_alert"
    __table_args__ = {"comment": "줄 경보"}

    day: Mapped[date] = mapped_column(Date, primary_key=True, comment="날짜")
    series_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dash_series.series_id"), primary_key=True, comment="줄"
    )
    much_lower: Mapped[bool] = mapped_column(Boolean, comment="예상보다 많이 낮음")
    grade: Mapped[str | None] = mapped_column(String(4), comment="등급(관심·주의·경고·위험)")
    why: Mapped[str | None] = mapped_column(String(300), comment="이유 문장")


class DashDongGrade(Base):
    """동 등급"""

    __tablename__ = "dash_dong_grade"
    __table_args__ = (UniqueConstraint("dong_cd", "week_start"), {"comment": "동 등급"})

    grade_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="동 등급ID")
    dong_cd: Mapped[str] = mapped_column(String(8), ForeignKey("dong.dong_cd"), comment="행정동")
    week_start: Mapped[date] = mapped_column(Date, comment="주 시작일")
    grade: Mapped[str] = mapped_column(
        String(6), comment="등급(위험·경고·주의·관심·평상·등급 없음)"
    )
    grade_next: Mapped[str | None] = mapped_column(String(6), comment="다음 주 예상 등급")
    weeks_on: Mapped[int | None] = mapped_column(Integer, comment="몇 주째")
    days_low: Mapped[int | None] = mapped_column(Integer, comment="며칠째")
    why: Mapped[str | None] = mapped_column(String(300), comment="왜 이 등급인가")
    is_estimate: Mapped[bool] = mapped_column(Boolean, comment="구 값을 동으로 나눈 추정")


class DashDongGradeSeries(Base):
    """동 등급-줄 연결"""

    __tablename__ = "dash_dong_grade_series"
    __table_args__ = {"comment": "동 등급-줄 연결"}

    grade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dash_dong_grade.grade_id"), primary_key=True, comment="동 등급"
    )
    series_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dash_series.series_id"), primary_key=True, comment="줄"
    )


class DashVisit(Base):
    """현장 기록"""

    __tablename__ = "dash_visit"
    __table_args__ = {"comment": "현장 기록"}

    visit_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="기록 번호")
    dong_cd: Mapped[str] = mapped_column(String(8), ForeignKey("dong.dong_cd"), comment="다녀온 동")
    grade_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("dash_dong_grade.grade_id"),
        comment="확인하러 간 등급(경보 없이 들르면 비움)",
    )
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("member.member_id"), comment="쓴 담당자"
    )
    day: Mapped[date] = mapped_column(Date, comment="다녀온 날")
    result: Mapped[str] = mapped_column(String(6), comment="결과(문제 있음·문제 없음·못 만남)")
    reason: Mapped[str | None] = mapped_column(
        String(6), comment="이유(연락 닿음·입원·이사·날씨·기타)"
    )
    contacted: Mapped[int | None] = mapped_column(Integer, comment="연락한 인원")
    memo: Mapped[str | None] = mapped_column(String(300), comment="메모(저장 전 개인정보 검사)")
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="기록한 때")


class JobRun(Base):
    """작업 실행 기록"""

    __tablename__ = "job_run"
    __table_args__ = {"comment": "작업 실행 기록"}

    day: Mapped[date] = mapped_column(Date, primary_key=True, comment="날짜")
    job: Mapped[str] = mapped_column(
        String(20), primary_key=True, comment="작업(예보 받기·예상 계산·등급 계산·카드 만들기)"
    )
    status: Mapped[str] = mapped_column(String(4), comment="상태(대기·진행·완료·실패)")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, comment="시작한 때")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, comment="끝난 때")
    error: Mapped[str | None] = mapped_column(String(300), comment="실패 이유")
