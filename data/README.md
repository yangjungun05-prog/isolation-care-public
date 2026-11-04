# data

| 폴더 | 들어갈 것 | git |
|---|---|---|
| `raw/` | 비어 있음(원자료는 올리지 않는다) | **제외** |
| `derived_public/` | 공개판 대시보드 · 시뮬레이션 재료(나우캐스트 · 합계표) | 포함 |
| `public/` | 공개 자료 원본 또는 받는 스크립트 | 포함 |
| `processed/` | 동별 고립 위험 합계 | 포함 |

## 공개 자료 목록

새 자료를 넣을 때 한 줄씩 더한다.

| 자료 | 출처 | 이용 조건 | 폴더 |
|---|---|---|---|
| 행정동 경계 ver20251231 (강남 22 · 춘천 25) | 통계청 SGIS 행정동 경계 → github.com/vuski/admdongkor 가공 | 공공누리 1유형 + CC BY 4.0 (출처 표시) | `public/admdong_ver20251231.geojson` |
| AI 비서 동 자료 스냅숏(강남 22 · 춘천 25): 순위 · 진단 · 혼자 사는 어르신 · 청년 · 집 · 수급 등 | 행정안전부 주민등록(2026-09) · 통계청 인구총조사 · 서울시 독거노인 현황 · 서울 생활인구 · 건축물대장 · 춘천시 자료 등 공개 자료로 계산(김정준 big-contest 저장소 `scripts/export_bisu_data.py`). 칸마다 출처는 `public/SOURCES.md` | 공공누리 1유형 · 이용허락범위 제한 없음 등 상업 이용 가능 표시가 있는 자료만 | `public/dong_profiles.json` |
| AI 비서 갈 곳 · 지원 기관(경로당 · 급식소 · 보건기관 · 약국 · 장기요양 · 행정복지센터) | 서울시 경로당 현황 · 시설 표준데이터 · 심평원 · 상가(상권)정보(2026-06) · 건보공단 장기요양기관 | 같음(`public/SOURCES.md`) | `public/places.json` |
| AI 비서 카드: 날씨마다 먼저 볼 곳(지하층 집 · 산사태 · 급경사지 · 침수 흔적 · 약한 지붕 · 요일별 문 연 약국) | 건축물대장 표제부 · 층별개요 · 강원 산사태취약지역 · 행정안전부 급경사지 · 서울시 침수흔적도 · 국립중앙의료원 약국 정보 | 같음(`public/SOURCES.md`) | `public/focus.json` |
| AI 비서 날씨 관측 · 예보 격자 · 공휴일 · 사람 수 · 춘천 버스 · 자료 목록 | 기상청 ASOS 일자료 · 단기예보 격자 · 한국천문연구원 특일 · 주민등록 · TAGO · 춘천시 정류장 노선 | 같음(`public/SOURCES.md`) | `public/weather.json` · `grids.json` · `holidays.json` · `people.json` · `bus.json` · `datasets.json` |
