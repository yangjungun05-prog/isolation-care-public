# web

화면 — 오늘의 보드 · 동 상세 · 닮은 동네 · 자원 배치 · 대상자 기록 · 시뮬레이션 (빌드 없는 HTML · CSS · JS).

```bash
uv run uvicorn src.api.main:app --port 8000   # → http://127.0.0.1:8000
```

- 자료: `src/api/main.py` 의 `/api/*` → `src/dashboard/cards.py` 가 `data/derived_public/` 을 읽는다
- 오른쪽 비서 창: 비서(`src/api/assistant.py`)를 따로 켜고, 주소가 8010 이 아니면 `ASSISTANT_URL` 로 알려 준다
- 색 · 글꼴은 동네 디오라마 시안(10/2)을 따른다. 3D 지도는 오늘의 보드 "동네 지도" 칸에 붙일 예정
