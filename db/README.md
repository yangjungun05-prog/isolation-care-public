# db

- `erdcloud_SQL2.json` — ERDCloud 다이어그램 SQL2(https://www.erdcloud.com/d/7pZnAtirEeFc7iDba)의 10/2 스냅숏. 표 49 · 외래키 71.
  - `src/*/models.py` 의 SQLAlchemy 모델이 이 스냅숏에서 만들어졌다.
  - `tests/test_models.py` 가 모델과 이 스냅숏이 같은지 검사한다.
- 표 만들기: `uv run python -m src.common.init_db` (Docker DB 를 켠 뒤)
- **표 바꾸기 — Alembic** (`migrations/`, 10/21)
  - 새 DB: `uv run alembic upgrade head` (첫 기록 `b4b88de6a3ad` = 모델 49개 그대로)
  - `init_db` 로 이미 표를 만든 DB: `uv run alembic stamp head` 한 번 → 이후부터 기록으로 관리
  - 모델을 고친 뒤: `uv run alembic revision --autogenerate -m "무엇을 바꿨나"` → 만든 파일을 읽어 보고 `upgrade head`
  - 기록 파일은 만들자마자 ruff 로 정리된다(`alembic.ini` post_write_hooks). 모델에 없는 표(예: `dash_dong_base`)는 비교에서 빠진다
