"""비서 설정 — Claude 키 · 모델 · 대화 기록 크기.

【판단】 팀원 저장소의 src/common/settings.py 는 공통 코드라 바꾸면 상대 확인이 필요하다(팀원 규칙).
       비서에만 필요한 값은 여기 따로 둬서, 이 폴더를 그대로 옮겨도 공통 코드는 안 바뀌게 한다.
       같은 .env 를 읽는다.
"""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AssistantSettings(BaseSettings):
    # 【문법】 extra="ignore" = .env 에 DATABASE_URL 같은 다른 이름이 있어도 오류 내지 말라
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

    # 【판단】 키가 없어도 시험(가짜 데스크)은 돌아야 해서 빈 문자열이 기본값.
    #        쓰는 곳에서 비었는지 본다
    anthropic_api_key: str = ""
    # 【기능】 공공데이터포털 일반 인증키 — 기상청 단기예보 · 특보(10-16 카드의 진짜 오늘 날씨)
    # 【판단】 10-24: 같은 키가 big-contest .env 에는 DATA_OPENAPI 라는 이름으로 있다(그 저장소
    #        CLAUDE.md 1번). 이 PC 시연 화면은 big-contest .env 를 읽어 날씨 키가 비었다
    #        → 둘 다 읽는다
    data_go_kr_service_key: str = Field(
        "", validation_alias=AliasChoices("DATA_GO_KR_SERVICE_KEY", "DATA_OPENAPI")
    )
    # 【기능】 서울 열린데이터광장 키(10-16 팀장이 넣음) — 강남 주민센터 · 노인복지관
    seoul_open_api: str = ""
    # 【정함 10-16 팀장】 비서의 '오늘'은 진짜 오늘. 'live' 가 아니라 날짜(YYYY-MM-DD)를 주면
    #        그날 기준으로 지난 관측을 되짚는다(시험 · 시연 되감기)
    as_of: str = "live"

    # 【기능】 안내 데스크(슬롯 채우기). 10-11 팀장 결정: Claude Haiku 5.5
    desk_model: str = "claude-haiku-5-5"
    # 【기능】 답 쓰기. 10-12 팀장: Haiku 5.5("하이쿠로 싹 다 바꾸지 뭐 그러면. 솔라 쓰지 마")
    writer_model: str = "claude-haiku-5-5"
    # 【기능】 free = AI가 답 전체를 씀(지금) · lead = AI는 맨 앞 한 문장만, 숫자 줄은 사서 그대로
    #        (HANDOVER 10-3 발전 1번 — 100턴으로 견준 뒤 팀장이 정함)
    writer_mode: str = "free"
    # 【판단】 데스크는 같은 질문을 몇 번 물어 다수결할지.
    #        10-12 시험(big-contest check_desk vote4): 3번이 흔들림을 잡았다
    # 【판단】 10-12 저녁 1로: 멘토 "다수결 3번은 빼도 괜찮을 것 같아요 … 걸렸을 때만 확인".
    #        시험에서 1번도 3번과 같았고(100턴 99/100 · 짓궂은 20/20), 오판은 다수결이 아니라
    #        코드 대조(policy.desk_sanity)로 잡는다. 값이 약 1/3
    # 【판단】 10-12 저녁 되돌림(3으로): 1번만 묻게 바꿔 재 보니(r11 · 재생 242턴)
    #        '어느 동을 볼까요?'가
    #        12 → 23, 시험지 다섯에서 데스크 한 장 오판이 생기고(짓궂은 T10 · 청년 T39 · 떠보기 T2),
    #        평균 6.6 → 7.4초로 느려졌다(3장 같이 보내고 먼저 온 것을 쓰던 게 더 빨랐다).
    #        값은 한 턴 2.7 → 1.4원으로 줄었지만
    #        '나빠진 것이 있으면 되돌린다'(문제 목록 고치는 방법 5)
    desk_votes: int = 3
    # 【10-27 CLI 주석】 CLI 길에서는 한 장만 물었다(CLI는 한 번에 하나씩이라 3장이면 세 배 느림).
    #        CLI 길을 되살리면 desk.read 에서 다시 쓴다(llm.py 맨 아래 주석 블록)
    # cli_desk_votes: int = 1
    # 【기능】 True 면 먼저 1번만 묻고, 거절 · 막기 · 못 알아들음일 때만
    #        나머지를 더 묻는다(시간 · 값 절약).
    # 【판단】 10-12 팀장이 켬("품질이 그대로 1,2 <- 좋아 이걸 먼저 해보자"): 100턴 6차 100/100 ·
    #        짓궂은 20턴 19/20으로 3번 다수결과 같았고, 한 턴이 6.2초 → 5.5초
    desk_escalate: bool = True
    # 【기능】 escalate 일 때 3번을 처음부터 같이 보내고, 먼저 온 카드가 분명하면 그것으로.
    # 【판단】 10-12 켬: 40턴 따로 잰 시간 5.88초(늘 3번) · 6.22초(애매할 때만) → 4.94초(같이 보냄),
    #        정확도는 고정 시험지 다섯에서 같거나 나음(r8 · r10). 값은 늘 3번 값(한 턴 약 2원)
    # 【정함 10-27 팀장 "100달러를 기준으로 알뜰살뜰 써야해. 11월 3일까지"】 → 끔.
    #        같이 보내기는 분명한 질문에도 늘 3장 값(데스크가 한 턴 돈의 대부분)이고, 애매할 때만
    #        3장(escalate)은 100턴 $0.09 · 같이 보내기 $0.22(HANDOVER 8절)로 판단은 같고 돈은
    #        40%. 대가는 애매한 턴이 약 1.3초 느려지는 것. 시연 때 속도가 더 급하면
    #        DESK_RACE=true 로 켠다
    desk_race: bool = False

    # 【기능】 동 상황 문서(PDF · PPTX)를 쓰는 모델. 10-13 팀장 결정: Sonnet 5.5
    #        (10-12 동 10곳 시험: 자료에 없는 해석 · 단정 Haiku 6건 · Sonnet 0, 한 장 약 25원)
    doc_model: str = "claude-sonnet-5-5"
    # 【판단】 10-26 판단 층: 계산 계획은 데스크와 같은 Haiku로 짜고, 코드 검사(router.check)에 걸릴
    #        때만 이 모델로 다시 짠다(계단식, FrugalGPT 꼴). CALC_BIG_MODEL 로 바꿀 수 있다
    calc_big_model: str = "claude-sonnet-5-5"
    # 【기능】 계산 길을 끄려면 CALC_ON=false(그러면 10-25까지의 엔진과 같다)
    calc_on: bool = True
    # 【기능】 문서를 저장할 곳 · 나눔고딕 글꼴 폴더(비우면 흔한 위치를 찾는다 — doc.find_fonts)
    doc_dir: str = "outputs/dong_docs"
    doc_font_dir: str = ""
    # 【기능】 [했어요] 기록 파일(시험 화면용, 10-15). 운영은 팀 DB todo_done 표
    done_file: str = "outputs/todo_done.jsonl"
    # 【기능】 대화 상태(칸 · 기억) 파일 폴더(10-25) — 대화 묶음마다 JSON 하나.
    #        문답 기록은 chat_turn 표(history.py)
    state_dir: str = "outputs/chat_state"

    # 【기능】 대화 기록 — 최근 몇 턴을 원문 그대로 줄까.
    #        이음(e-EUM) 실측은 8턴. 우리는 슬롯 상태가 따로 있어 6턴
    # 【판단】 10-26 멘토 답 5 '최근 2턴만'을 재 봄: long_100 40턴 6턴 · 2턴 모두 40/40, 2턴이
    #        한 턴 약 500토큰(0.1원 남짓) 적음. 실제 대화는 3 ~ 5턴 앞을 자주 가리켜 6턴 그대로
    # 【판단】 10-27 밤 팀장 '최근 6턴을 15턴쯤으로 올려도 Haiku가 괜찮은가' → API로 잼:
    #        15턴 summary_recall_24 24/24 · long_100 100/100 · chuncheon_youth_60 60/60 ·
    #        long_recall_12 12/12(데스크 실패 0), 6턴은 summary_recall_24 23/24(T22 창 밖 첫 동,
    #        뒤에 engine.FIRST_DONGS 로도 받침). 기억 글은 약 2배
    #        (최대 1.9천 → 3.9천 자)지만 캐시로 돈은 거의 같음(24턴 $0.0235 → $0.0238) → 15턴
    history_turns: int = 15
    # 【기능】 같은 입력이면 그날 같은 답 — 데스크 카드 · 글쓴이 답을 몇 개까지 기억할까(0이면 끔,
    #        10-26 멘토 답 4, reply_cache.py)
    reply_cache: int = 500
    # 【기능】 사실 목록 — 앞쪽(담당 · 기관처럼 안 바뀌는 것)과 뒤쪽(지금 관심)을 몇 개씩 남길까
    facts_head: int = 12
    facts_tail: int = 18


def load_settings() -> AssistantSettings:
    return AssistantSettings()
