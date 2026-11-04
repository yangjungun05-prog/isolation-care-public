"""모든 표를 DB 에 만든다.

    uv run python -m src.common.init_db

이미 있는 표는 건드리지 않는다(create_all). 표 모양을 바꿨다면
docker compose down -v → docker compose up -d 로 DB 를 비운 뒤 다시 돌린다.
"""

import src.assistant.models  # noqa: F401 — import 해야 표가 Base.metadata 에 등록된다
import src.common.models  # noqa: F401
import src.dashboard.models  # noqa: F401
import src.simulation.models  # noqa: F401
from src.common.database import Base, engine


def create_tables() -> list[str]:
    # 【기능】 Base.metadata 에 모인 표를 DB 에 만들고, 표 이름 목록을 돌려준다
    Base.metadata.create_all(engine)
    return sorted(Base.metadata.tables)


if __name__ == "__main__":
    names = create_tables()
    print(f"표 {len(names)}개 준비됨")
