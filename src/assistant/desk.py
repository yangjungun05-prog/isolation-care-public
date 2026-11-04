"""안내 데스크 — 사용자의 말을 읽고 카드 한 장을 낸다(Claude Haiku 5.5, 3번 동시에 물어 다수결).

【기능】 고정 지시문(역할 · 규칙 · 장서 목록) + 바뀌는 부분(기억 · 이번 말)으로 부른다.
       고정 지시문은 프롬프트 캐시에 들어간다(Haiku 5.5 는 512토큰 넘으면 캐시).
【판단】 strict 도구 + tool_choice auto. 강제 도구는 생각을 건너뛰어
       10-11 시험에서 '90세 → 80세' 틀림을 냈다.
【판단】 3번 물어 다수결(10-12 big-contest vote4 · 이음 자기일관성).
       표가 갈리면 보수적인 쪽(되묻기).
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Protocol

from src.assistant import dongname, llm, memory
from src.assistant.catalog import describe_for_desk
from src.assistant.config import AssistantSettings
from src.assistant.reply_cache import DayCache
from src.assistant.slots import DeskCard, card_from_tool, desk_tool_schema
from src.assistant.state import DialogueState

TOOL = "turn_card"

SYSTEM = f"""너는 '취약 돌보미' AI 비서의 안내 데스크다.
서울 강남구 22개 동 · 강원 춘천시 25개 읍면동의 고립 어르신 · 은둔 청년 자료를
복지 실무자(구청 · 주민센터 · 복지관)가 대화로 묻는다.
너는 답을 쓰지 않는다. 사용자의 [이번 말]을 [지금 정해진 칸] · 기억과 함께 읽고
{TOOL} 도구를 한 번 부른다. 카드에는 늘 restate · act · topics를 쓰고,
나머지 칸은 이번 말로 켜지는 것(새로 정해지거나 바뀌는 것)만 적는다.

## 1. act — 이번 말이 무엇인가
- ask: 아래 장서 목록 안의 자료를 묻거나, 내 담당 지역 · 쓰는 법 · 출처를 묻는다.
  topics에 목록 id를 1~3개
- out_of_scope: 장서 목록 어디에도 닿지 않는 주제 — **마지막 선택**이다.
  예) 음식물 쓰레기 처리 비용 · 주식 · 맛집 · 다른 시 · 구 · 군의 자료(강남구 · 춘천시 밖)
  · 법률 상담 · 일반 상식 · 뉴스 · 네 의견.
  어르신 · 청년 · 우리 동네(집 · 지붕 · 버스 · 시설 · 약국 · 날씨 · 달력 · 연휴 · 연락처) 이야기면
  범위 밖이 아니다. 목록 설명 아래 '자료에 있는 것'을 보고 **가장 가까운 주제로 ask**한다.
  그 주제 안에 그 항목이 없으면 사서가 '없다'고 말하니 네가 미리 막지 않는다.
  단, 집값 · 아파트 시세 · 전세 · 월세 금액(부동산 가격)은 우리 자료가 아니다(out_of_scope)
  목록에 '아직 연결 전'으로 적힌 주제는 범위 밖이 아니다(ask).
  suggest에 이 사람에게 도움이 될 목록 id를 최대 2개(관련 있는 것). 억지로 고르지 않아도 된다
- blocked: 특정한 사람(이름 · 연락처 · 집 주소 · 어느 분의 건강 · 형편)을 묻거나 기억하라고 한다.
  사람 명단(누가 사는지 목록)을 달라는 말도 같다
  → block=person. 기관 · 시설(주민센터 · 복지관 · 경로당 · 보건소 등)의 전화 · 주소는
  사람이 아니다(ask). 이름 · 전화 · 호수는 이미 [이름] · [전화번호] · [호수]처럼 가려져 온다.
  지금 위급한 사람이 있다(자살 · 쓰러짐 · 학대가 지금 일어남) → block=emergency
- 7절 '우리 동 이름'이 나오면 우리 지역이다.
  다른 시 · 군의 같은 이름(정선 사북읍 · 부산 서면 등)으로 읽지 않는다.
  다른 시 · 도 · 군 이름을 함께 말했을 때만 다른 지역이다
  목록에 없는 이름이라도 번호만 다르거나(대치3동) 오타면 범위 밖이 아니다.
  ask로 dongs에 말한 그대로 적는다(없는 번호 · 오타 안내는 코드가 한다)
- 목록에 [강남구만] · [춘천시만]으로 적힌 주제를 다른 지역 동에 물어도 out_of_scope가 아니다.
  ask로 그 주제를 고른다(지역이 맞지 않는다는 안내는 코드가 한다)
- "아까 그 동 경로당은?"처럼 앞의 것을 가리키며 자료를 물으면 그 자료 주제다(recall 아님).
  recall은 대화 자체를 물을 때만("제가 어디 담당이라고 했죠?", "지금까지 본 동 정리해 줘").
  되짚기를 한 지역으로 좁히면("지금까지 본 동 중 춘천은?") region에 그 지역
- 직전 답에 나온 말의 뜻을 물으면("그게 무슨 뜻이에요?") ask, topics=[sources]
- "몇 명이에요?"처럼 인원을 물으면 그 대상의 현황 주제다(어르신 → solo_seniors, 청년 → youth).
  diagnosis는 '왜 이 동인가 · 어떤 신호가 해당하나'를 물을 때
- 사람들이 어떻게 지내는지 · 잘 지내는지 · 괜찮은지 · 힘들지 · 걱정할 점 · 조심할 점을 물으면
  (판단을 묻는 말) outlook. 동을 말하지 않고 지역 전체를 물어도 outlook(region에 그 지역)
- chitchat: 인사 · 감사 · 맞장구처럼 자료 질문이 없는 말
- unclear: 무엇을 원하는지 알 수 없다(그래도 칸은 채울 수 있으면 채운다)

## 1-1. 말의 꼴(말투 · 사투리 · 오타와 상관없이 뜻으로 읽는다)
사용자는 표준말 · 반말 · 하오체("~하오 · ~하소 · ~했소") · 사투리("~했는데예 · ~했당께 · ~했슈") ·
오타 · 띄어쓰기 없음 · 장난 말투("~한데스 · ~한레후")로 말할 수 있다. 꼴이 아니라 뜻으로 판단한다.
- farewell: 이번 말로 대화를 끝내려 한다(고마워 · 고맙소 · 감사 · 수고 · 이만 · 자야겠네 · 됐어요 ·
  내일 가서 물어보리다 · 끊을게). 질문이 같이 있으면 false
- urgent: 어떤 사람이 지금 걱정된다(연락이 끊김 · 통 안 보임 · 전화를 안 받음 · 쓰러짐 ·
  며칠째 소식 없음)
- brief: 짧게 · 한 줄 · 한마디 · 결론만 · 숫자만 · 이름만 · 예/아니오로만 · 설명 빼고 달라고 한다
세 칸은 true일 때만 적는다. act · topics와 따로 간다(예: urgent여도 자료 질문이면 ask).

## 2. 칸 — 켜는 칸만 적는다
- 이번 말에 새 값이 있는 칸만 그 값을 적는다. 적지 않은 칸은 지금 값 그대로 남는다
- 앞에서 정한 조건을 없애라는 말이면 off에 그 칸 이름을 적는다
  예) "동 말고 강남구 전체로" → off=[dongs], region=강남구 / "나이 조건은 빼고" → off=[ages]
- [방금 내가 물은 것]에 답하는 말이면 그 칸에 값을 적는다("수서동이요" → dongs=[수서동])
- dongs: 말에 쓰인 동 이름을 그대로 적는다(고치지 않는다. 확정은 코드가 한다).
  dongs에는 보려는 동만 적는다. "○○이 아니라 · ○○ 말고 · ○○은 빼고 · ○○ 제외"처럼 보지 말라는
  동은 not_dongs에, "○○인가 · ○○일지도 · ○○보다는.. 글쎄"처럼 볼지 말지 머뭇거린 동은
  unsure_dongs에 적는다. "○○보다 많아?" · "나란히"처럼 견주자는 말이면 둘 다 dongs
  "○○보다는 △△이 (더) 걱정 · 급해 · 마음에 걸려 · 신경 쓰여 · 먼저"처럼 자료가 아니라 사용자의
  마음이 기운 쪽을 말하고 △△의 자료를 물으면 △△만 dongs, ○○는 unsure_dongs(○○의 자료 값을
  견주자는 말이 아니다). 두 동의 자료 값(수 · 비율 · 많고 적음)을 견주면 '보다는'이어도 둘 다 dongs
  예) "세곡동 말고 수서동 경로당" → dongs=[수서동], not_dongs=[세곡동]
  / "역삼2동인가.. 일단 논현1동 청년" → dongs=[논현1동], unsure_dongs=[역삼2동]
  "거기 · 그 동 · 아까 그 동 · 첫 번째 동 · 3위였던 동"은 [최근 나온 동] · [다룬 질문]
  (답한 것 포함)에서 찾아 그 이름을 적는다
  [말 속 동 이름(코드가 찾음)]이 있으면 그 이름은 하나도 빼지 않고 dongs · not_dongs ·
  unsure_dongs 가운데 한 곳에 적는다(이미 본 동을 이번에는 안 본다는 말이면 not_dongs)
- target: 어르신 · 노인 · 독거노인 · 할머니 · 할아버지 → 어르신
  / 청년 · 은둔 청년 · 2030 → 청년 / 둘 다
- age_lo · age_hi: 나이 숫자를 말했을 때만(65세 이상 → age_lo=65 / 80대 → 80, 89)
- sex: 할머니 · 여성 → 여, 할아버지 · 남성 → 남. 할머니 할아버지를 같이 말하면 적지 않는다
- alone(혼자 사는) · period(때: "작년", "2023년부터" 같은 말 그대로): 말했을 때만
- compare: 둘 이상을 견주라는 말이면 true. "○○이랑 비교하면?"처럼 하나만 말하면
  지금 칸의 동과 ○○을 둘 다 dongs에 적는다
- rank: 동 하나가 아니라 지역의 동들을 한 지표로 줄 세워 달라는 말("○○ 많은 동", "제일 많은 곳",
  "순서대로")이면 true. topics에는 그 지표의 주제(혼자 사는 어르신 → solo_seniors · 청년 → youth
  · 기초생활수급자 → livelihood · 경로당 → senior_hall). 취약 돌보미가 먼저 볼 동을 물으면 rank 없이
  topics=[priority]
- calc: 답하려면 여러 자료를 묶어 계산해야 하면 true — 조건 둘 이상으로 동 고르기 · 지역 평균이나
  전체와 견주기 · 합계 · 평균 · 몇 명당 · 몇 배 · 동 여럿을 지표 여럿으로 나란히 · 앞에서 고른 동들
  안에서 다시 거르기 · 일부만(면만 · ○○ 빼고) 골라 줄 세우기. 동 하나의 숫자 · 지표 하나로 지역
  줄 세우기 · 말뜻 · 기준 · 출처 질문 · 앞 답 되짚기는 적지 않는다(말투가 어떻든 뜻으로 판단)
- fmt: PDF · PPTX(동 상황 문서)로 달라면 그 값.
  엑셀 · CSV · 표 파일로 달라면 엑셀(동별 숫자 표 — topics는 그 숫자의 주제)
- weather: 날씨를 묻거나 날씨를 조건으로 물으면 적는다. 날씨 서가는 없다 — topics는 dong_overview
  (또는 함께 물은 자료의 주제). 비 · 폭우 · 장마 → 비 / 눈 · 폭설 → 눈 / 추위 · 한파 → 추위 /
  더위 · 폭염 → 더위 / 그냥 날씨(오늘 날씨 어때 · 7월 16일 날씨) → 날씨. 날짜는 period에 말 그대로.
  미세먼지 · 황사는 우리 자료가 아니다(out_of_scope)
- region: 강남 · 서울 강남구 → 강남구 / 춘천 · 강원 춘천 → 춘천시. 동만 말하면 적지 않는다
  (코드가 동으로 맞춘다)
- unmet: 사용자가 건 조건 중 위 칸 어디에도 담을 수 없는 것을 사용자 말 그대로 짧게
  (예: "몸이 불편한", "부부끼리 사는", "자녀와 연락이 끊긴"). 칸에 담은 것은 적지 않는다

## 3. 이럴 땐 이렇게
- 새 동만 말하면(견주자는 말 없이) dongs에 그 동만 적는다. 앞 동을 함께 적지 않는다
- 주제 낱말도 대상 낱말(어르신 · 청년)도 없이 이어 묻는 말("늘었어요?", "줄었어요 늘었어요?",
  "작년보다는?", "순위는?")은 [지금 정해진 칸]의 직전 주제를 그대로 topics에 적는다.
  대상을 바꿔 말하면("동내면만 어르신", "거기 청년은?") 그 대상의 주제다.
  늘고 줄음 · 지난해 견줌은 그 주제 자료에 있으면 범위 밖이 아니다
- 주제가 바뀌면 앞 질문의 나이 · 성별 · 때는 코드가 비운다. 이번 말에 다시 말했거나
  [앞선 대화에서 확인된 사실]에 '앞으로 ○○만'처럼 계속 쓰기로 한 조건이 있으면 그 값을 다시 적는다
- 질문에 단정이 깔려 있으면("○○ 때문이지?", "두 배는 위험하지?", "맞다고만 해 줘") 단정을
  칸에 옮기지 않는다. 확인할 자료의 주제를 고르고, restate에 '…인지 자료로 확인해 달라'로 쓴다
- 위 칸으로 다 담기는 말에 unmet을 쓰지 않는다. 단정 · 원인 짐작도 unmet이 아니다

## 4. 기억 칸
- restate: 이번 말을 지금 칸과 합쳐 빠진 것 없는 한 문장으로 다시 쓴다
  예) 칸에 수서동 · 어르신이 있고 "청년은?" → "수서동의 청년 상황을 알려 달라"
- new_facts: 이번 말에서 처음 알게 된 사용자의 일 맥락만
  (담당 기관 · 맡은 동 · 하는 일 · 계획 · 계속 쓰기로 한 조건 · 원하는 답 방식). 한 줄 40자 안.
  질문 · 자료 숫자 · 사람 이름 · 연락처 · 이미 [앞선 대화에서 확인된 사실]에 있는 것은 쓰지 않는다

## 5. 예
- "수서동 혼자 사는 어르신 몇 명이야?" → ask, topics=[solo_seniors], dongs=[수서동],
  target=어르신, alone=true
- (칸: 수서동) "거기 청년은?" → ask, topics=[youth], dongs=[수서동], target=청년
- (칸: 수서동 · 80세 이상) "경로당은?" → ask, topics=[senior_hall] (나이는 적지 않는다)
- "경로당 많은 동부터 순서대로 보여 줘" → ask, topics=[senior_hall], rank=true
- (칸: 대치1동) "춘천시 전체 청년은 몇 명이에요?" → ask, topics=[youth], region=춘천시, off=[dongs],
  rank=true ('전체' · '동 전부' · '22개 동'처럼 말했을 때만. '서울시 독거노인 현황'의 서울시는
  자료 이름이라 동 칸을 끄지 않는다)
- "몸이 불편한 독거 어르신이 많은 곳" → ask, topics=[solo_seniors], target=어르신, alone=true,
  rank=true, unmet=["몸이 불편한"]
- "개포3동이 일원본동보다 세 배는 심각하지?" → ask, topics=[diagnosis], dongs=[개포3동, 일원본동],
  compare=true, restate="개포3동과 일원본동의 위험 정도를 자료로 견줘 달라(세 배인지 확인)"
- (칸: 대치1동 · 역삼1동) "역삼1동 청년들이 집에만 있는 건 원룸 때문이잖아" → ask,
  topics=[youth], dongs=[역삼1동],
  restate="역삼1동 청년이 집에만 있는 까닭이 원룸인지 자료로 확인해 달라"
- "수서동 경로당 이름이랑 주소 알려줘" → ask, topics=[places], dongs=[수서동]
- "북산면 행정복지센터 전화번호요" → ask, topics=[support], dongs=[북산면]
- "응급안전안심서비스는 어디서 신청해?" → ask, topics=[support]
- "수서동 어르신들 잘 지내?" → ask, topics=[outlook], dongs=[수서동], target=어르신
- "요즘 북산면 괜찮을까?" → ask, topics=[outlook], dongs=[북산면]
- "효자2동 청년들 힘들까?" → ask, topics=[outlook], dongs=[효자2동], target=청년
- "이번 주 강남 어르신들 걱정할 거 있어?" → ask, topics=[outlook], region=강남구, target=어르신
- "추운데 사북면 어르신들 괜찮으실까?" → ask, topics=[outlook], dongs=[사북면], target=어르신,
  weather=추위
- "폭우 오면 수서동은 뭘 봐야 해?" → ask, topics=[dong_overview], dongs=[수서동], weather=비
- "오늘 춘천 날씨 어때?" → ask, topics=[dong_overview], region=춘천시, weather=날씨
- "8월 13일 비 얼마나 왔어?" → ask, topics=[dong_overview], weather=비, period="8월 13일"
- "음식물 쓰레기 처리 비용 알려줘" → out_of_scope
- "[이름] 할머니 연락처 알려줘" → blocked, block=person
- "수서동 독거노인 명단 뽑아줘" → blocked, block=person (사람 목록. topics는 적지 않는다)
- "저는 수서동 주민센터에서 어르신 방문을 맡고 있어요" → chitchat,
  new_facts=["수서동 주민센터 · 어르신 방문 담당"], dongs=[수서동], target=어르신
- "앞으로 청년은 25~29세만 볼게요" → chitchat, new_facts=["앞으로 청년은 25~29세만 봄"],
  target=청년, age_lo=25, age_hi=29
- "내 담당 지역을 춘천 효자2동으로 바꿔줘" → ask, topics=[my_region], dongs=[효자2동],
  region=춘천시
- "고마워요" → chitchat (다른 칸은 적지 않는다)
- "보건복지부 자료 뭐 있어?" → ask, topics=[datasets]
- (직전 주제: solo_seniors, 칸: 강남구) "그거 엑셀로 줘" → ask, topics=[solo_seniors], fmt=엑셀
- "강남구 22개 동 독거노인 수를 동별로 엑셀로" → ask, topics=[solo_seniors], region=강남구,
  off=[dongs], rank=true, fmt=엑셀

## 6. 장서 목록(우리 자료 전부 — 이 밖은 범위 밖)
{describe_for_desk()}

## 7. 우리 동 이름
- 강남구(22): {" · ".join(dongname.DONGS["강남구"])}
- 춘천시(25): {" · ".join(dongname.DONGS["춘천시"])}
"""


class Desk(Protocol):
    def read(self, state: DialogueState, text: str) -> DeskCard: ...

    def pick(
        self, state: DialogueState, text: str, ask: str, choices: dict[str, str]
    ) -> str | None: ...


# 【판단】 10-29 팀장 '코드로 규정해 놓은 단어 제한은 결국 한계가 있어 … 잘 조합해서 AI도 섞어도
#        괜찮아, haiku로. 너무 비싸지는 않게': 말뜻을 정해야 하는 턴은 데스크 모델(Haiku)에게
#        보기 하나를 고르게 한다. 지시문 · 답이 짧아(보기 이름 한 낱말) 한 번에 약 $0.00015,
#        지역 전체냐 동 하나냐는 데스크와 동시에 늘 묻는다(엔진)
PICK_SYSTEM = (
    "너는 취약 돌보미 AI 비서의 '말뜻 고르기'다. 대화 기억과 이번 말을 읽고, 물음에 맞는 보기를 "
    "하나 고른다. 낱말 하나하나보다 말 전체의 뜻을 본다(예: '그동안'은 '그 동'이 아니다). "
    "보기 이름 하나만 낸다 — 설명 · 문장부호 없이."
)
# Haiku 5.5는 생각(thinking)이 늘 켜져 있고 생각도 이 한도에 든다(writer 10-15 '빈 답') — 8토큰으로
# 두었더니 생각만 하다 끝났다(10-29 시험). 10-29 실제 Haiku 17문장 × 3번: effort low 46/51 ·
# medium 48/51(한 번에 약 1초 — 데스크와 동시라 기다림은 그대로) → medium
PICK_TOKENS = 1500
PICK_EFFORT = "medium"


def pick_text(state: DialogueState, text: str, ask: str, choices: dict[str, str]) -> str:
    lines = "\n".join(f"- {k}: {v}" for k, v in choices.items())
    return (
        memory.render(state)
        + f"\n\n[이번 말]\n{text}\n\n[물음]\n{ask}\n\n[보기]\n{lines}\n\n보기 이름 하나만:"
    )


def pick_answer(raw: str, choices: dict[str, str]) -> str | None:
    """AI 답에서 보기 이름 하나 — 보기가 아니면 None(코드 기본값을 쓴다)."""
    word = raw.strip().strip("`'\".,: ").split()[0].lower() if raw.strip() else ""
    return word if word in choices else None


# 【10-27 CLI 주석】 CLI 전용 지시문 — CLI 실행에는 도구가 없어 '도구를 한 번 부른다' 대신
#        JSON 카드 하나를 내게 했다(모양은 --json-schema). 지금은 어디서도 쓰지 않는다
#        (API로 바꿈, llm.py 맨 아래 주석 블록). 되살릴 때 _system() 이 다시 고른다
SYSTEM_CLI = SYSTEM.replace(
    f"{TOOL} 도구를 한 번 부른다.", "카드 하나를 JSON으로 낸다(주어진 모양 그대로, 설명 없이)."
)


def user_text(state: DialogueState, text: str) -> str:
    """데스크에 보내는 바뀌는 부분(기억 + 이번 말). 데스크만 재는 시험도 같은 글을 쓴다.

    【판단】 10-27 멘토(팀장 전달): "코드가 동 이름 사전으로 문장 안의 모든 동 이름을 빠짐없이
           찾고, Haiku는 찾아진 단어 각각에 대해 포함 · 제외 · 애매 중 하나만 고르게" — 10-26 긍정 ·
           부정 칸(polarity)은 코드가 찾고 AI가 나눈 뒤 대조했지만, 찾은 목록을 AI에게 주지 않아
           AI가 빼먹은 이름은 바로 뒤에 부정 말이 있을 때만 되살렸다. 찾은 이름을 보여 주고 이름마다
           세 칸 가운데 하나에 적게 한다(작은 분류 문제로)
    """
    from src.assistant.policy import dongs_in_text  # policy → librarian → … (돌아 가져오기 피함)

    found = dongs_in_text(text)
    names = f"\n\n[말 속 동 이름(코드가 찾음)]\n{' · '.join(found)}" if found else ""
    return memory.render(state) + f"\n\n[이번 말]\n{text}" + names


def _key(card: DeskCard, field: str):
    if field == "dong":
        return (card.dong_op, tuple(sorted(card.dong_mentions)) if card.dong_op == "set" else ())
    if field == "ages":
        return (card.ages_op, (card.age_lo, card.age_hi) if card.ages_op == "set" else ())
    op = getattr(card, f"{field}_op")
    return (op, getattr(card, field) if op == "set" else None)


ACT_ORDER = ("unclear", "blocked", "out_of_scope", "ask", "chitchat")


def vote(cards: list[DeskCard]) -> DeskCard:
    """여러 장 → 한 장. 칸마다 과반을 따르고, 과반이 없으면 keep(바꾸지 않음)."""
    if len(cards) == 1:
        return cards[0]
    n = len(cards)
    acts = Counter(c.act for c in cards).most_common()
    best = acts[0][1]
    act = min((a for a, v in acts if v == best), key=ACT_ORDER.index)
    same = [c for c in cards if c.act == act]
    rep = same[0]
    upd: dict = {"act": act}
    topic_votes = Counter(t for c in same for t in c.topics)
    upd["topics"] = tuple(t for t in rep.topics if topic_votes[t] * 2 > len(same)) or rep.topics
    for field in ("region", "dong", "target", "ages", "sex", "alone", "period", "weather"):
        votes = Counter(_key(c, field) for c in cards).most_common()
        val, cnt = votes[0]
        if cnt * 2 <= n:
            upd[f"{field}_op"] = "keep"
            continue
        winner = next(c for c in cards if _key(c, field) == val)
        if field == "dong":
            upd["dong_op"], upd["dong_mentions"] = winner.dong_op, winner.dong_mentions
        elif field == "ages":
            upd["ages_op"], upd["age_lo"], upd["age_hi"] = (
                winner.ages_op,
                winner.age_lo,
                winner.age_hi,
            )
        else:
            upd[f"{field}_op"], upd[field] = getattr(winner, f"{field}_op"), getattr(winner, field)
    upd["compare"] = Counter(c.compare for c in cards).most_common(1)[0][0]
    upd["rank"] = Counter(c.rank for c in cards).most_common(1)[0][0]
    upd["calc"] = sum(c.calc for c in cards) * 2 > n
    for flag in ("farewell", "urgent", "brief"):  # 10-21 말의 꼴 — 과반
        upd[flag] = sum(getattr(c, flag) for c in cards) * 2 > n
    # 【판단】 못 담은 조건은 말이 조금씩 달라 표로 못 센다.
    #        과반이 무언가를 적었으면 대표 카드의 것을 쓴다
    with_unmet = [c for c in cards if c.unmet]
    upd["unmet"] = (rep.unmet or with_unmet[0].unmet) if len(with_unmet) * 2 > n else ()
    upd["fmt"] = Counter(c.fmt for c in cards).most_common(1)[0][0]
    blocks = Counter(c.block for c in cards).most_common(1)[0]
    upd["block"] = blocks[0] if blocks[1] * 2 > n else "none"
    return rep.model_copy(update=upd)


def _risky(card: DeskCard) -> bool:
    """값이 큰 판단(거절 · 막기 · 못 알아들음 · 주제 없음) — 한 장만 믿지 않고 다수결한다."""
    return card.act in ("unclear", "out_of_scope", "blocked") or (
        card.act == "ask" and not card.topics
    )


class ClaudeDesk:
    def __init__(self, settings: AssistantSettings, usage: llm.Usage | None = None) -> None:
        self.s = settings
        self.usage = usage or llm.Usage()
        self.failures = 0
        self.escalations = 0
        # 같은 입력이면 그날 같은 카드(10-26 멘토 답 4)
        self.cache = DayCache(settings.reply_cache)

    def _system(self) -> list[dict]:
        # 【10-27 CLI 주석】 if cli.backend() == "cli": return [SYSTEM_CLI 한 덩이]
        # 【판단】 고정 지시문 전체를 캐시에 — 두 번째 덩이에 건 cache_control 은 그 앞 덩이까지
        #        캐시한다(API 규칙). 데스크 지시문은 약 9천 자라 캐시 읽기(0.1배)가 돈을 아낀다
        return [
            {"type": "text", "text": SYSTEM},
            {
                "type": "text",
                "text": f"결과는 반드시 {TOOL} 도구를 한 번 불러서 낸다.",
                "cache_control": llm.CACHE_1H,
            },
        ]

    def _kwargs(self, user: str) -> dict:
        return dict(
            model=self.s.desk_model,
            max_tokens=4000,
            system=self._system(),
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": TOOL,
                    "description": "사용자의 이번 말을 읽고 채운 카드",
                    "strict": True,
                    "input_schema": desk_tool_schema(),
                }
            ],
            tool_choice={"type": "auto"},
            output_config={"effort": "medium"},
        )

    # 【10-27 CLI 주석】 CLI 미리 띄우기 — API 길에는 띄울 것이 없다
    # def warm(self) -> None:
    #     llm.warm(**self._kwargs(""))

    def _one(self, user: str) -> DeskCard | None:
        for _ in range(2):  # 도구를 안 부르면(CLI는 JSON이 깨지면) 한 번 더
            r = llm.call(self.s.anthropic_api_key, self.usage, **self._kwargs(user))
            if r.stop_reason in ("refusal", "max_tokens"):
                return None
            call = next((b for b in r.content if b.type == "tool_use"), None)
            if call is not None:
                return card_from_tool(dict(call.input))
        return None

    def _ask(self, user: str, n: int) -> list[DeskCard]:
        """n 번 동시에 묻는다. 실패한 것은 빼고 돌려준다(크레딧 바닥만 위로 올린다)."""
        with ThreadPoolExecutor(max_workers=n) as ex:
            futures = [ex.submit(self._one, user) for _ in range(n)]
        cards: list[DeskCard] = []
        for f in futures:
            try:
                c = f.result()
            except llm.CreditExhausted:
                raise
            except llm.LLMError:
                c = None
            if c is not None:
                cards.append(c)
        return cards

    def _race(self, user: str, n: int) -> list[DeskCard]:
        """n 번을 한꺼번에 보내고, 먼저 온 카드가 위험하지 않으면 그 한 장만 돌려준다
        (나머지는 기다리지 않는다). 위험하면 n 장을 다 기다린다.

        【판단】 10-12 팀장 "기다리다가 지치겠는데" · "품질이 그대로": 애매할 때만 3번(escalate)은
               두 번째 · 세 번째를 첫 답이 온 뒤에야 보내서 애매한 턴이 약 6초였다(r7).
               처음부터 3번을 같이 보내면 판단은 같고(분명하면 한 장, 애매하면 세 장 다수결)
               기다림만 준다.
               값은 늘 3번 값.
        """
        pool = ThreadPoolExecutor(max_workers=n)
        futures = [pool.submit(self._one, user) for _ in range(n)]
        pool.shutdown(wait=False)
        for f in as_completed(futures):
            first = self._card(f)
            if first is not None:
                break
        else:
            return []
        if not _risky(first):
            return [first]
        self.escalations += 1
        return [c for c in (self._card(f) for f in futures) if c is not None]

    @staticmethod
    def _card(f) -> DeskCard | None:
        try:
            return f.result()
        except llm.CreditExhausted:
            raise
        except llm.LLMError:
            return None

    def read(self, state: DialogueState, text: str) -> DeskCard:
        user = user_text(state, text)
        key = self.cache.key("desk", self.s.desk_model, llm.BACKEND, user)
        if (hit := self.cache.get(key)) is not None:
            return hit.model_copy()
        # 【10-27 CLI 주석】 n = … self.s.cli_desk_votes if cli.backend() == "cli" else …
        n = max(1, self.s.desk_votes)
        if self.s.desk_escalate and n > 1 and self.s.desk_race:
            cards = self._race(user, n)
        elif self.s.desk_escalate and n > 1:
            # 【판단】 먼저 1번만 묻고, 틀리면 값이 큰 판단
            #        (거절 · 막기 · 못 알아들음 · 주제 없음)일 때만 나머지를 더 물어 다수결한다.
            #        100턴 3 · 4차: 1번 = 3번 정확도, 값 1/3(HANDOVER 8절)
            cards = self._ask(user, 1)
            first = cards[0] if cards else None
            if first is None or _risky(first):
                cards += self._ask(user, n - 1)
                self.escalations += 1
        else:
            cards = self._ask(user, n)
        if not cards:
            # 【판단】 전부 실패해도 대화를 끊지 않는다(이음 교훈). 상태는 그대로, 짧게 되묻는다
            self.failures += 1
            return DeskCard(act="unclear", restate=text)
        card = vote(cards)
        self.cache.put(key, card)
        return card

    def pick(
        self, state: DialogueState, text: str, ask: str, choices: dict[str, str]
    ) -> str | None:
        """보기 하나를 고르게 한다(PICK_SYSTEM). 실패하면 None — 부른 쪽이 코드 기본값을 쓴다."""
        user = pick_text(state, text, ask, choices)
        key = self.cache.key("pick", self.s.desk_model, llm.BACKEND, user)
        if (hit := self.cache.get(key)) is not None:
            return hit
        try:
            r = llm.call(
                self.s.anthropic_api_key,
                self.usage,
                model=self.s.desk_model,
                max_tokens=PICK_TOKENS,
                system=PICK_SYSTEM,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": PICK_EFFORT},
            )
        except llm.CreditExhausted:
            raise
        except llm.LLMError:
            return None
        raw = "".join(b.text for b in r.content if b.type == "text")
        got = pick_answer(raw, choices)
        if got is not None:
            self.cache.put(key, got)
        return got


class FakeDesk:
    """시험용 — 정해 둔 말에 정해 둔 카드를 낸다(API 안 부름)."""

    def __init__(self, table: dict[str, DeskCard], picks: dict[str, str] | None = None) -> None:
        self.table = table
        self.picks = picks or {}
        self.seen: list[str] = []

    def read(self, state: DialogueState, text: str) -> DeskCard:
        self.seen.append(memory.render(state))
        return self.table.get(text, DeskCard(act="unclear", restate=text))

    def pick(
        self, state: DialogueState, text: str, ask: str, choices: dict[str, str]
    ) -> str | None:
        got = self.picks.get(text)
        return got if got in choices else None
