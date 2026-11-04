"""같이 쓰는 표 — A 기준·출처 · B 공개 자료 · E 회원

ERDCloud 다이어그램 SQL2 의 10/2 스냅숏에서 make_models.py 로 만든 파일이다.
https://www.erdcloud.com/d/7pZnAtirEeFc7iDba
표·칸을 바꾸려면 ERDCloud 를 고친 뒤 스냅숏을 다시 받아 다시 만든다(손으로 고치면 어긋난다).
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base

# ── A 기준·출처 ──


class Region(Base):
    """시군구"""

    __tablename__ = "region"
    __table_args__ = {"comment": "시군구"}

    sgg_cd: Mapped[str] = mapped_column(
        String(5), primary_key=True, comment="시군구코드(통계청 5자리)"
    )
    name: Mapped[str] = mapped_column(String(20), comment="이름")


class Dong(Base):
    """행정동"""

    __tablename__ = "dong"
    __table_args__ = (UniqueConstraint("mois_cd"), {"comment": "행정동"})

    dong_cd: Mapped[str] = mapped_column(
        String(8), primary_key=True, comment="행정동코드(통계청 8자리)"
    )
    mois_cd: Mapped[str] = mapped_column(
        String(10), comment="행정기관코드(행안부 10자리, 주민등록과 잇는다)"
    )
    sgg_cd: Mapped[str] = mapped_column(String(5), ForeignKey("region.sgg_cd"), comment="시군구")
    name: Mapped[str] = mapped_column(String(20), comment="이름")
    family: Mapped[str | None] = mapped_column(
        String(20), comment="묶음 이름(대치1·2·4동 → 대치동)"
    )
    kind: Mapped[str] = mapped_column(String(2), comment="동·읍·면")
    geom: Mapped[str | None] = mapped_column(Text, comment="경계(GeoJSON)")


class Holiday(Base):
    """공휴일"""

    __tablename__ = "holiday"
    __table_args__ = {"comment": "공휴일"}

    day: Mapped[date] = mapped_column(Date, primary_key=True, comment="날짜")
    name: Mapped[str] = mapped_column(String(20), comment="이름")


class Source(Base):
    """자료 출처"""

    __tablename__ = "source"
    __table_args__ = {"comment": "자료 출처"}

    source_id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="출처ID")
    name: Mapped[str] = mapped_column(String(120), comment="자료 이름")
    org: Mapped[str] = mapped_column(String(60), comment="제공 기관")
    portal_no: Mapped[str | None] = mapped_column(String(30), comment="포털 번호")
    license: Mapped[str] = mapped_column(String(60), comment="이용 조건(원문 표기)")
    attribution: Mapped[str | None] = mapped_column(String(200), comment="출처 문구")
    how: Mapped[str] = mapped_column(String(10), comment="받는 방법(파일·API·손으로)")
    status: Mapped[str] = mapped_column(String(40), comment="상태(있음·받을 것·신청)")
    into_table: Mapped[str] = mapped_column(String(40), comment="들어가는 표")
    replaces: Mapped[str | None] = mapped_column(String(120), comment="대신하는 옛 자료")


# ── B 공개 자료 ──


class Population(Base):
    """인구"""

    __tablename__ = "population"
    __table_args__ = {"comment": "인구"}

    ym: Mapped[str] = mapped_column(String(6), primary_key=True, comment="기준월(YYYYMM)")
    sex: Mapped[str] = mapped_column(String(1), primary_key=True, comment="성(M·F)")
    age5: Mapped[str] = mapped_column(String(3), primary_key=True, comment="5세 연령(0·5…100)")
    kind: Mapped[str] = mapped_column(String(6), primary_key=True, comment="인구·1인 세대")
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    n: Mapped[int] = mapped_column(Integer, comment="사람 수")


class PhoneSignal(Base):
    """통신 신호 통계"""

    __tablename__ = "phone_signal"
    __table_args__ = {"comment": "통신 신호 통계"}

    ym: Mapped[str] = mapped_column(String(6), primary_key=True, comment="기준월")
    sex: Mapped[str] = mapped_column(String(1), primary_key=True, comment="성(M·F, T는 전체)")
    age5: Mapped[str] = mapped_column(
        String(3), primary_key=True, comment="5세 연령(20…75, 60U, ALL)"
    )
    measure: Mapped[str] = mapped_column(
        String(20), primary_key=True, comment="무엇(외출·연락 모두 적음 등)"
    )
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    source_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("source.source_id"),
        primary_key=True,
        comment="출처(시민생활·생활인구)",
    )
    value: Mapped[float] = mapped_column(Double, comment="값(추정 인원·몫)")


class LoneElder(Base):
    """혼자 사는 어르신"""

    __tablename__ = "lone_elder"
    __table_args__ = {"comment": "혼자 사는 어르신"}

    year: Mapped[int] = mapped_column(Integer, primary_key=True, comment="연도")
    kind: Mapped[str] = mapped_column(
        String(6), primary_key=True, comment="합계·수급권자·저소득·일반"
    )
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    n: Mapped[int] = mapped_column(Integer, comment="사람 수")


class BuildingDong(Base):
    """동별 주거 건물"""

    __tablename__ = "building_dong"
    __table_args__ = {"comment": "동별 주거 건물"}

    asof: Mapped[date] = mapped_column(Date, primary_key=True, comment="받은 날")
    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동"
    )
    res_units: Mapped[int] = mapped_column(Integer, comment="주거 가구")
    walkup_units: Mapped[int] = mapped_column(
        Integer, comment="계단만 있는 오래된 집(30년+, 승강기 없는 3~5층) 가구"
    )
    walkup_share: Mapped[float] = mapped_column(Double, comment="그 몫")
    basement_old: Mapped[int] = mapped_column(Integer, comment="지하층 있는 30년+ 저층 주거 건물")
    officetel_units: Mapped[int | None] = mapped_column(Integer, comment="오피스텔 호수")


class Facility(Base):
    """시설"""

    __tablename__ = "facility"
    __table_args__ = {"comment": "시설"}

    facility_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="시설ID")
    source_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("source.source_id"), comment="출처"
    )
    kind: Mapped[str] = mapped_column(String(20), comment="종류(경로당·약국·장기요양·청년 창구 등)")
    grp: Mapped[str] = mapped_column(
        String(10), comment="묶음(공공 자원·생활 접점·입소 시설·청년 창구)"
    )
    name: Mapped[str] = mapped_column(String(100), comment="이름")
    addr: Mapped[str | None] = mapped_column(String(200), comment="주소")
    tel: Mapped[str | None] = mapped_column(String(30), comment="대표번호(기관만)")
    lat: Mapped[float | None] = mapped_column(Double, comment="위도")
    lon: Mapped[float | None] = mapped_column(Double, comment="경도")
    dong_cd: Mapped[str] = mapped_column(String(8), ForeignKey("dong.dong_cd"), comment="행정동")
    capacity: Mapped[int | None] = mapped_column(Integer, comment="정원(입소 시설)")


class WeatherDay(Base):
    """날씨(일)"""

    __tablename__ = "weather_day"
    __table_args__ = {"comment": "날씨(일)"}

    day: Mapped[date] = mapped_column(Date, primary_key=True, comment="날짜")
    kind: Mapped[str] = mapped_column(String(2), primary_key=True, comment="관측·예보")
    sgg_cd: Mapped[str] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), primary_key=True, comment="시군구"
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, comment="예보 발표 시각")
    tmax: Mapped[float | None] = mapped_column(Double, comment="최고기온(℃)")
    tmin: Mapped[float | None] = mapped_column(Double, comment="최저기온(℃)")
    rain: Mapped[float | None] = mapped_column(Double, comment="비(mm)")
    snow: Mapped[float | None] = mapped_column(Double, comment="새로 쌓인 눈(cm)")
    station: Mapped[str] = mapped_column(String(20), comment="관측소·예보 격자")


class EmsMonth(Base):
    """구급 출동(월)"""

    __tablename__ = "ems_month"
    __table_args__ = {"comment": "구급 출동(월)"}

    ym: Mapped[str] = mapped_column(String(6), primary_key=True, comment="기준월")
    sgg_cd: Mapped[str] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), primary_key=True, comment="시군구"
    )
    n: Mapped[int] = mapped_column(Integer, comment="70세 이상 집에서 구급 출동(건)")


class Program(Base):
    """복지 사업"""

    __tablename__ = "program"
    __table_args__ = {"comment": "복지 사업"}

    program_id: Mapped[str] = mapped_column(
        String(30), primary_key=True, comment="서비스ID(복지로)"
    )
    source_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("source.source_id"), comment="출처(중앙부처·지자체)"
    )
    name: Mapped[str] = mapped_column(String(150), comment="이름")
    owner: Mapped[str] = mapped_column(String(80), comment="맡은 곳")
    sgg_cd: Mapped[str | None] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), comment="시군구(지자체 사업만)"
    )
    life_stage: Mapped[str | None] = mapped_column(String(80), comment="생애주기")
    summary: Mapped[str | None] = mapped_column(Text, comment="요약(원문)")
    link: Mapped[str | None] = mapped_column(String(300), comment="원문 링크")


class DongAccess(Base):
    """동 접근성"""

    __tablename__ = "dong_access"
    __table_args__ = {"comment": "동 접근성"}

    dong_cd: Mapped[str] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), primary_key=True, comment="행정동(읍·면)"
    )
    villages: Mapped[int] = mapped_column(Integer, comment="마을 수(경로당·마을회관)")
    pharmacy_km_median: Mapped[float] = mapped_column(Double, comment="약국까지 가운데값(km)")
    villages_over5km: Mapped[int] = mapped_column(Integer, comment="약국까지 5km 넘는 마을")
    low_freq_routes: Mapped[int | None] = mapped_column(
        Integer, comment="하루 3번 이하 노선 수(TAGO)"
    )
    low_freq_names: Mapped[str | None] = mapped_column(String(200), comment="그 노선들")
    winter_routes: Mapped[str | None] = mapped_column(
        String(100), comment="겨울 운휴 노선(시 공지)"
    )


class SurveyFact(Base):
    """조사 통계"""

    __tablename__ = "survey_fact"
    __table_args__ = {"comment": "조사 통계"}

    scope: Mapped[str] = mapped_column(
        String(12), primary_key=True, comment="범위(전국·서울·강남 수서동)"
    )
    item: Mapped[str] = mapped_column(String(60), primary_key=True, comment="항목")
    source_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("source.source_id"), primary_key=True, comment="출처(조사·보도)"
    )
    value: Mapped[float] = mapped_column(Double, comment="값")
    unit: Mapped[str] = mapped_column(String(4), comment="단위(%·명)")
    n: Mapped[int | None] = mapped_column(Integer, comment="응답 수")


# ── E 회원 ──


class Org(Base):
    """기관"""

    __tablename__ = "org"
    __table_args__ = (UniqueConstraint("join_code"), {"comment": "기관"})

    org_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="기관ID")
    name: Mapped[str] = mapped_column(String(60), comment="기관 이름")
    kind: Mapped[str] = mapped_column(String(4), comment="공공·민간")
    sgg_cd: Mapped[str | None] = mapped_column(
        String(5), ForeignKey("region.sgg_cd"), comment="주 시군구"
    )
    join_code: Mapped[str] = mapped_column(String(12), comment="가입 코드(기관 담당자가 나눠 준다)")


class Member(Base):
    """회원"""

    __tablename__ = "member"
    __table_args__ = (UniqueConstraint("login_id"), UniqueConstraint("email"), {"comment": "회원"})

    member_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="회원ID")
    login_id: Mapped[str] = mapped_column(String(40), comment="아이디")
    password_hash: Mapped[str] = mapped_column(String(200), comment="비밀번호 해시")
    kind: Mapped[str] = mapped_column(String(4), comment="회원 유형(공공·민간·개인)")
    name: Mapped[str] = mapped_column(String(20), comment="이름")
    email: Mapped[str] = mapped_column(String(120), comment="이메일(인증·비밀번호 찾기)")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, comment="이메일 인증한 때")
    org_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("org.org_id"), comment="기관(개인은 비움)"
    )
    job: Mapped[str | None] = mapped_column(
        String(20), comment="하는 일(사회복지 담당·방문 간호 등)"
    )
    role: Mapped[str] = mapped_column(String(6), comment="실무자·중간관리자·관리자")
    fail_count: Mapped[int] = mapped_column(Integer, comment="비밀번호 틀린 횟수(5번이면 잠금)")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, comment="잠금 풀리는 때")
    created_at: Mapped[datetime] = mapped_column(DateTime, comment="가입한 때")
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime, comment="탈퇴한 때(개인정보는 지운다)"
    )


class MemberRegion(Base):
    """회원 담당 지역"""

    __tablename__ = "member_region"
    __table_args__ = {"comment": "회원 담당 지역"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="ID")
    member_id: Mapped[int] = mapped_column(Integer, ForeignKey("member.member_id"), comment="회원")
    sgg_cd: Mapped[str] = mapped_column(String(5), ForeignKey("region.sgg_cd"), comment="시군구")
    dong_cd: Mapped[str | None] = mapped_column(
        String(8), ForeignKey("dong.dong_cd"), comment="동(시군구 전체면 비움)"
    )


class TermsAgree(Base):
    """약관 동의"""

    __tablename__ = "terms_agree"
    __table_args__ = {"comment": "약관 동의"}

    terms_cd: Mapped[str] = mapped_column(
        String(20), primary_key=True, comment="약관(이용·개인정보 수집·마케팅)"
    )
    version: Mapped[str] = mapped_column(String(10), primary_key=True, comment="약관 판")
    member_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("member.member_id"), primary_key=True, comment="회원"
    )
    agreed: Mapped[bool] = mapped_column(Boolean, comment="동의")
    at: Mapped[datetime] = mapped_column(DateTime, comment="누른 때")


class EmailCode(Base):
    """이메일 인증번호"""

    __tablename__ = "email_code"
    __table_args__ = {"comment": "이메일 인증번호"}

    code_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="ID")
    email: Mapped[str] = mapped_column(String(120), comment="보낸 이메일")
    purpose: Mapped[str] = mapped_column(String(10), comment="가입·비밀번호 찾기")
    code_hash: Mapped[str] = mapped_column(String(200), comment="인증번호 해시(10분 뒤 못 씀)")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="끝나는 때")
    used_at: Mapped[datetime | None] = mapped_column(DateTime, comment="쓴 때")


class LoginLog(Base):
    """로그인 기록"""

    __tablename__ = "login_log"
    __table_args__ = {"comment": "로그인 기록"}

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="ID")
    member_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("member.member_id"), comment="회원(없는 아이디면 비움)"
    )
    login_id_tried: Mapped[str] = mapped_column(String(40), comment="넣은 아이디")
    ok: Mapped[bool] = mapped_column(Boolean, comment="성공")
    at: Mapped[datetime] = mapped_column(DateTime, comment="때")
    ip_hash: Mapped[str | None] = mapped_column(String(64), comment="IP 해시")
