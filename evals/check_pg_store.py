"""PostgreSQL 저장소를 진짜 DB로 확인한다(10-15).

Docker Desktop을 켜고 팀원 저장소의 postgres 18을 띄운 뒤:

    cd ../bigcontest14-isolation-agent && docker compose up -d
    uv run --group pg python evals/check_pg_store.py   # 기본: 팀 .env.example 의 개발용 주소
    uv run --group pg python evals/check_pg_store.py --url postgresql://…

【판단】 시험용 세션 하나를 쓰고 읽은 뒤 지운다. 팀원 표(49개)는 건드리지 않고 chat_state 만 만든다
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant.slots import Slots  # noqa: E402
from src.assistant.state import DialogueState, Profile  # noqa: E402
from src.assistant.store_pg import PgStore, _psycopg_connect  # noqa: E402

DEV_URL = "postgresql://user:1234@localhost:5432/AgentDB"  # 팀원 저장소 .env.example 의 개발용 주소


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEV_URL)
    a = ap.parse_args()
    s = PgStore(a.url)
    s.ensure_table()
    st = DialogueState(turn=7, profile=Profile(member_region="춘천시"),
                       slots=Slots(region="춘천시", dongs=("북산면",)))  # fmt: skip
    s.save("check_pg_store", st)
    back = s.load("check_pg_store")
    with _psycopg_connect(s.url) as conn:
        conn.execute("DELETE FROM chat_state WHERE session_id = %s", ("check_pg_store",))
    ok = back == st and s.last_error is None
    print("PostgreSQL 저장소:", "됨" if ok else f"안 됨({s.last_error})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
