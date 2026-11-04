# simulation — 시뮬레이션 (양정운)

'만약에' 계산 — 대상 동 · 사업 · 예산을 바꿔 결과를 비교한다. 난수 씨앗과 엔진 판을 남겨 다시 계산할 수 있게 한다.

## 파일

| 파일 | 하는 일 |
|---|---|
| `engine.py` | 계산 — 가상 주민 → 대상 고르기 → 돈으로 닿는 사람 → 36달 굴리기(사업 없음 vs 사업, 같은 주사위) → 모르는 값 50번 × 주사위 20번 → 여러 동 합치기 · 흔드는 값 · 거꾸로 계산 |
| `graph.py` | 한 번 실행하는 순서를 LangGraph 그래프로 — 이 안 → (대상 0명이면 끝) → 비교 안 · 보수적 경우 · 흔드는 값을 **동시에** → 결과 묶기 → 설명글 → (숫자가 다르면 글 빼기). `POST /api/simulation/run` 이 부른다 |
| `inputs.py` | 합계표에서 가상 주민을 만든다(`load` · `residents`) |
| `text.py` | 설명글 읽기(칸과 다르면 묻기, SIM-102 · 103) · 설명글 쓰기와 숫자 검사(SIM-107) |
| `models.py` | DB 표(ERD G 시뮬레이션) |

API 는 `src/api/main.py` — `POST /api/simulation/run` · `reverse` · `read`, `GET /api/simulation/demo`.

## 재료 파일

`src/simulation/inputs.py` 가 `data/derived_public/sim_inputs/` 의 합계표로 가상 주민을 만든다. 응답자 줄은 쓰지 않는다.
