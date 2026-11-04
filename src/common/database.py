"""DB 연결 — 엔진 · 세션 · 표 설계도의 부모(Base)."""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.common.settings import settings

# 【기능】 DB 주소로 엔진을 하나 만든다. 앱 전체가 이 엔진 하나(와 그 연결 통)를 같이 쓴다
# 【판단】 pool_pre_ping=True = 연결을 쓰기 전에 살아 있는지 확인해 "끊긴 연결" 오류를 줄인다
engine = create_engine(settings.database_url, pool_pre_ping=True)

# 【기능】 세션 공장. 세션이 필요할 때마다 SessionLocal.begin() 으로 하나씩 연다
# 【판단】 expire_on_commit=False = 저장한 뒤에도 객체 값을 DB 에 다시 묻지 않고 그대로 읽는다
SessionLocal = sessionmaker(engine, expire_on_commit=False)

# 【기능】 기본키·외래키·유일키 이름을 정해진 규칙으로 붙인다 (예: fk_dong_sgg_cd_region)
# 【판단】 이름이 일정해야 나중에 Alembic 으로 표를 바꿀 때 "이름 없는 제약" 문제가 안 생긴다
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# 【기능】 모든 표 설계도(모델 클래스)의 부모. 표 목록(Base.metadata)이 여기 모인다
# 【판단】 Base 는 하나만 둔다 — 그래야 create_all 한 번에 모든 표가 만들어진다
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def ping() -> int:
    # 【기능】 DB 에 연결해 SELECT 1 을 실행하고, 돌아온 1 을 반환한다
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1")).scalar_one()


def get_db() -> Iterator[Session]:
    # 【기능】 FastAPI 요청 하나에 세션 하나를 빌려 주고, 끝나면 저장(오류면 취소)하고 닫는다
    # 【문법】 yield = 여기서 세션을 넘겨주고, 요청이 끝나면 with 블록이 마저 닫힌다
    with SessionLocal.begin() as session:
        yield session
