"""Alembic 실행 설정 — 모델(Base.metadata)과 DB 를 비교해 표 변경을 기록하고 적용한다.

    uv run alembic upgrade head                    # 기록된 변경을 DB 에 적용
    uv run alembic revision --autogenerate -m "…"  # 모델을 고친 뒤 변경 기록 만들기
    uv run alembic stamp head                      # create_all 로 만든 DB 에 "최신" 표시

다른 DB 에 쓰려면  uv run alembic -x url=postgresql+psycopg://… upgrade head

【판단】 alembic.ini 에는 한글을 쓰지 않는다(영어 · ASCII 만). alembic 과 logging 이
  그 파일을 OS 기본 인코딩으로 읽어서, 한국어 Windows(cp949)에서는 한글 주석 한 줄에
  UnicodeDecodeError 로 멈췄다(10-26). 그래서 alembic.ini 의 설명은 여기에 둔다:
  · DB 주소는 alembic.ini 에 적지 않는다 — 아래 db_url() 이 .env 의 DATABASE_URL 을 읽는다
  · post_write_hooks = 새 변경 기록 파일을 바로 ruff 로 정리한다(CI 의 ruff 검사 통과)
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import src.assistant.models  # noqa: F401 — import 해야 표가 Base.metadata 에 등록된다
import src.common.models  # noqa: F401
import src.dashboard.models  # noqa: F401
import src.simulation.models  # noqa: F401
from src.common.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def db_url() -> str:
    # 【기능】 DB 주소 — `-x url=…` 로 주면 그것, 아니면 .env 의 DATABASE_URL
    # 【판단】 settings 는 여기서 늦게 부른다 — 오프라인(-x url)일 때 .env 가 없어도 돌게
    url = context.get_x_argument(as_dictionary=True).get("url")
    if url:
        return url
    from src.common.settings import settings

    return settings.database_url


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    # 【기능】 비교할 대상을 고른다 — 모델에 없는데 DB 에만 있는 표는 건너뛴다
    # 【판단】 dash_dong_base 처럼 로더가 직접 만든 표를 autogenerate 가 "지우기"로 적지 않게 한다
    return not (type_ == "table" and reflected and compare_to is None)


def run_migrations_offline() -> None:
    # 【기능】 DB 에 붙지 않고 SQL 글만 찍는다 (alembic upgrade head --sql)
    context.configure(
        url=db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 【기능】 DB 에 붙어서 바로 적용한다
    connectable = create_engine(db_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            # 【판단】 칸 종류(VARCHAR(10) → VARCHAR(20) 등)가 바뀐 것도 잡는다
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
