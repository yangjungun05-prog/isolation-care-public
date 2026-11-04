"""회원 가입에 필요한 것을 넣는다 — 담당 지역을 고르는 지역 · 동(47곳). 표를 만든 뒤 한 번.

    uv run python -m src.auth.seed

【판단】 10-25 팀장 "그냥 기관목록을 넣지말자" — 시험 기관 · 가입 코드는 넣지 않는다(지운다).
       지역 · 동은 공용 src/common/regions.py 가 넣는다
"""

from sqlalchemy import delete

from src.common.models import Org

# 10-24에 넣었던 시험 기관(이제 쓰지 않음) — 남아 있으면 지운다
OLD_DEMO_CODES = ["GN-4827", "GN-7310", "CC-3154", "CC-5520"]


if __name__ == "__main__":
    from src.common.database import SessionLocal
    from src.common.regions import seed_regions

    with SessionLocal.begin() as session:
        print("지역 · 동", seed_regions(session))
        gone = session.execute(delete(Org).where(Org.join_code.in_(OLD_DEMO_CODES))).rowcount
        print("옛 시험 기관 지움", gone)
