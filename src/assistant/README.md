# assistant — AI 비서 (김정준)

오늘 챙길 일 카드 · 동 순위 답 · 주변 시설·연계 사업 · 현장 브리핑.

## 지금 들어 있는 것(10-19, 깔끔한 버전 `regionse/BIGCONTEST_AI_BISU`에서 옮김)

- **대화**: 안내 데스크(Claude Haiku 5.5)가 질문의 칸(동 · 대상 · 나이 · 때 · 원하는 것)을 채움 → 이륙 전 체크(`policy.py`) → 서가(`librarian.py`)가 공개 자료에서 사실을 꺼냄 → 글쓴이(`writer.py`)가 그 사실로만 답함 → 검문소(`checks.py`)가 자료에 없는 숫자 · 날짜를 막음
- **서가**: 혼자 사는 어르신 · 청년 · 먼저 볼 동(동 순위) · 진단 · 갈 곳 · 지원 기관 · 춘천 버스 · 원문 자료 · 동별 표(엑셀 · CSV) · 동 상황 문서(PDF · PPTX, Claude Sonnet 5.5, `doc.py`) · 날씨(오늘 ~ 모레는 기상청 단기예보, 지난 날은 관측)
- **오늘 챙길 일 카드**(`today.py` · `today_api.py`): 기상청 특보 · 단기예보 · 긴 연휴 · 월초 점검. 담당 지역의 상태(먼저 볼 곳)만 보여 주고 할 일은 적지 않음. 읍면은 취약점이 두드러진 마을 이름. [했어요] 기록(`done.py`, ERD `todo_done` 모양)
- **자료**: `data/public/*.json`(공개 자료만, 대회 자료 없음). 자료의 때는 `basis.py`가 읽음
- **설정**: `config.py`(비서에만 필요한 값). 공통 `src/common/settings.py`는 바꾸지 않음
- **API · 시험 화면**: `src/api/assistant.py`(`uv run uvicorn src.api.assistant:app --port 8010` → http://127.0.0.1:8010)
- **시험**: `tests/`(API 없이), `evals/`(진짜 API로 긴 대화 시험지)
- **AI 부르는 길(10-27)**: **API 하나**(`llm.py`, `.env`의 `ANTHROPIC_API_KEY`). 10-24 ~ 10-27 아침까지 쓰던 Claude CLI(구독) 길은 `llm.py` 맨 아래 주석 블록에 남겨 두었다(API가 심하게 모자랄 때 되살림, `cli.py`는 그대로 있음). 환경 변수 `BISU_LLM=cli`는 지금 받지 않는다(오류로 알림)
- **Claude API 장부 · 예산**: 응답마다 `api_usage/ledger_<컴퓨터 이름>.jsonl`에 한 줄, 합계가 `api_usage/budget.json`의 한도($100)에 닿으면 멈춤(`ledger.py`). 8할을 넘으면 장부 줄에 `warn`, `GET /assistant/status`에 예산 · 쓴 돈 · 남은 돈이 보인다. 아끼는 기본값(10-27): 데스크는 먼저 한 장만 묻고 애매할 때만 3장(`DESK_RACE=false`), 고정 지시문은 모두 프롬프트 캐시, 9만 5천 자 넘는 요청은 부르기 전에 막음(다섯 배 값 문턱)
