"""엔진 — 한 턴을 처음부터 끝까지 잇는다.

    데스크(AI) → 상태 갱신(코드) → 이륙 전 체크(코드) → 사서(코드)
    → 답 쓰기(AI) · 검사(코드) → 기억 · 저장(코드)

【판단】 AI가 하는 일은 말 알아듣기와 글쓰기 둘뿐. 나머지는 코드라 같은 입력이면 같은 결과다.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from src.assistant import (
    arith,
    budget,
    checks,
    dongname,
    keyboard,
    librarian,
    llm,
    pii,
    query,
    router,
    table,
    table_edit,
)
from src.assistant import basis as B
from src.assistant import conditions as C
from src.assistant import doc as dongdoc
from src.assistant.catalog import BY_ID
from src.assistant.config import AssistantSettings
from src.assistant.data_source import DongData
from src.assistant.desk import Desk
from src.assistant.librarian import RANKABLE, Facts, gather_all
from src.assistant.librarian import _office_line as office_line
from src.assistant.memory import add_log, add_recent, fold_facts, note_dongs
from src.assistant.outlook_text import BRIEF_TAIL
from src.assistant.policy import (
    BOTH_REGIONS,
    BYE,
    CARE,
    DISTRESS,
    EMERGENCY,
    EMERGENCY_AGAIN,
    EMERGENCY_THIRD,
    FACILITY_TOPICS,
    MAX_INPUT,
    NO_ADDRESS_NOTE,
    NOT_REPORTED,
    PERSON,
    PERSON_PART,
    REGION_WORDS_IN_TEXT,
    SCOPE_ASK,
    SCOPE_CHOICES,
    SUB_DONG,
    TOO_LONG,
    Plan,
    desk_sanity,
    disclose,
    dongs_in_text,
    josa,
    not_connected_note,
    out_of_area_note,
    person_free_rest,
    preflight,
    refusal_reason,
    restate_or_text,
)
from src.assistant.slots import DeskCard, Slots
from src.assistant.state import DialogueState, LogEntry, Profile, TurnText, apply_card, new_state
from src.assistant.store import Store
from src.assistant.writer import Writer

# 【기능】 되짚기에서 무엇을 물었나(코드가 확정할 수 있는 말만)
_ASK_FACTS = re.compile(r"담당|무슨 일|하는 일|맡(은|고|아)|기관|어디서 일")
_ASK_DONGS = re.compile(r"본 동|동들|어디였|어느 동|무슨 동")
# 【판단】 10-27 밤 창 시험 T23 '물어본 동을 숫자와 함께 정리해 줘'가 동 이름 목록만 받았다 —
#        숫자를 함께 달라는 말이면 동 목록(되짚기)이 아니라 앞 답 숫자로 정리한다
_WITH_NUM = re.compile(r"숫자|수치|몇 명|인원|명수")
# 【판단】 10-27 밤 페르소나 h01 T5 '오늘 신북읍에서 어디부터 들르면 좋냐? 한곳만'에 자료에
#        없는 '행정복지센터부터 들러 보세요'를 지어냄 → 방문 순서를 물으면 마을 단위 자료와 글쓴이
#        안내를 준다
VISIT_ORDER = re.compile(
    r"어디(?:부터|먼저|를 먼저)\s*(?:들르|들러|들를|가|방문|돌|챙기)"
    r"|먼저\s*(?:들를|갈|방문할|돌)\s*(?:곳|데|마을)|방문\s*순서|어느 마을부터"
)
VISIT_NOTE = (
    "사용자가 오늘 어디부터 들를지(방문 순서)를 물었다. 비서는 어르신 한 분 한 분의 사정을 몰라 "
    "방문 순서를 정해 주지 않는다고 짧게 밝히고, 위 마을 단위 자료에서 두드러진 마을"
    "(눈 무게에 약한 지붕 · 오래된 집이 많은 마을, 버스가 드문 마을)을 까닭과 함께 "
    "'먼저 살펴볼 만한 마을'로 말한다. "
    "행정복지센터 · 경로당 같은 시설에 들르라고 권하지 않는다"
)
# 쓰는 사람 자신이 지쳤다는 말(10-28 p03_c · p10_c) — '어르신이 힘들어서'처럼 남 이야기는 빼고
SELF_DISTRESS = re.compile(
    r"(?:저도|나도|제가|내가|저는|나는|저 요즘|저 너무|저 진짜|저 정말)[^.?!\n]{0,20}"
    r"(?:그만\s?두고 싶|너무 힘들|힘들어|힘드|지[치쳐쳤](?!지 않|지 말)|번아웃|우울|버겁|버거)"
    # 10-28 p10_c '진짜 다 그만두고 싶어요'(저도 · 나도 없이) — 이런 말은 거의 늘 말하는 사람 자신
    r"|다 그만두고 싶|다 그만 두고 싶|죽고 싶|살기 싫|사라지고 싶|그만 살고"
)
# 위급 중 '119가 맞아요? · 호수 몰라도 돼요?'(10-28 p10_a)
EMERGENCY_119_OK = re.compile(r"119[^\n?]{0,12}(?:맞|되죠|될까|괜찮|걸면|부르면)")
NO_ADDRESS_ASK = re.compile(r"(?:주소|호수|몇 호)[^\n?]{0,10}(?:몰라|모르)")
# 표 요청 속 순서 · 지역 전체 말(10-28 p01_c)
ORDER_OR_ALL = re.compile(
    r"많은 ?순|적은 ?순|순서대로|내림차순|오름차순|순위대로|\d+\s?개 ?동|\d+곳|동별|전체 동|모든 동"
)
# 동보다 작은 단위를 줄 세우거나 찾는 말(10-28 p07_a)과 동을 묻는 말
SUBDONG_ASK = re.compile(
    r"(?:아파트|단지|골목|빌라)[^\n]{0,15}(?:많은 ?(?:곳|데)|어디|제일|가장|순위|명단)"
    r"|(?:가장|제일|어느|무슨|많은)[^\n.?]{0,8}(?:아파트|단지|골목|빌라)"
)
SUBDONG_NOTE = "아파트 단지 · 골목처럼 동보다 작은 단위 자료는 없어 단지별로는 답할 수 없어요."
DONG_LEVEL_ASK = re.compile(r"많은 ?(?:동|읍|면)|(?:동|읍|면)(?:은|이|을)? ?(?:어디|어느)")
# 비서가 사람인지 묻는 말(10-28 p02_c)
AI_ASK = re.compile(
    r"사람(?:이에요|이세요|인가요|이야|이니|이냐|이신가|이십니까|맞[아나죠])|진짜 사람|"
    r"기계(?:예요|야|인가|냐|에요)|로봇(?:이|인가|이야|이에요)|"
    r"(?:AI|에이아이|인공지능)(?:예요|야|인가|냐|이에요)|"
    r"누구(?:세요|야|니|신가요)"
)
AI_SELF = (
    "저는 사람이 아니라 AI 비서예요. 공개 자료로 강남구 · 춘천시의 동 단위 숫자와 기관을 "
    "찾아 드려요. 사람과 이야기하고 싶으시면 동 주민센터나 보건복지상담센터(129)에 전화해 보세요."
)
# 담당 지역을 바꾸라는 말(10-28 p01_b — 묻기만 한 말은 바꾸지 않는다)
CHANGE_REGION = re.compile(
    r"바꿔|바꾸|바꿀|변경|설정해|옮겨|으로 해|로 해"
    r"|담당(?:이|은|는)?\s*\S+?(?:이야|이에요|예요|에요|입니다|이고|이라)"
)
# 취약 돌보미 판단의 말(겹친 걱정 · 구조 걱정 · 겹침)
OVERLAP_WORD = re.compile(r"겹친 ?걱정|겹침|구조 ?걱정|닥친 ?걱정")
# 10-28 재심사 q05_b: '22개 동의 평균보다 높음' — 비율 지표도 지역 전체 값이 아니라
#        동 평균으로 견준다
DONG_MEAN = re.compile(
    # 10-28 밤 브라우저 시험 '강남 동들 평균보다'를 놓침 → 동 · 동들 · 동별 다음 평균이면 모두
    r"동(?:들|별)?(?:의)?\s?평균|\d+\s?개\s?동(?:의)?\s?(?:단순\s?)?평균|단순\s?평균"
)
# 10-28 재심사 p06_b(기자) '고독사 위험군이 전체 몇 명': 그런 무리의 수는 자료에 없다
RISK_GROUP = re.compile(r"고독사\s?위험|위험군")
RISK_GROUP_NOTE = (
    "'고독사 위험군' 같은 무리의 수는 이 자료에 없다 — 먼저 그렇다고 한 문장으로 밝히고, "
    "1인세대 · 독거노인 수를 위험군이라 부르지 않고 자료 이름 그대로 말한다"
)
# 앞 계산을 가리키는 말(10-28 재심사 q05_a) — 이 세션의 계산 기록을 함께 건넨다
PAST_CALC = re.compile(r"처음|아까|앞에서|앞서|첫\s?답|골랐|고른|정했|어떤 기준|무슨 기준|기준으로")
CALC_LOG_NOTE = (
    "이 대화에서 한 계산들의 기준이다(차례대로). '처음 · 앞에서 고른 곳'의 기준을 물으면 그 턴의 "
    "기준을 그대로 말하고, 다른 계산의 기준과 섞지 않는다"
)


def calc_log_entry(turn: int, res: query.Result) -> tuple[str, ...]:
    """계산 기록 한 줄 — 조건으로 고른 계산만(조건 없는 표 · 줄 세우기는 고른 기준이 아니다)."""
    if not res.conds:
        return ()
    names = " · ".join(res.matched[:8]) + (" …" if len(res.matched) > 8 else "")
    return (
        f"{turn}번째 질문의 계산({res.region}): "
        + " / ".join(s for _, s in res.conds)
        + (" → 모두 맞는 곳" if res.mode == "모두" else f" → {res.mode} 방식으로 고른 곳")
        + f" {len(res.matched)}곳({names})",
    )


# 자료가 0줄이라 글쓴이 답이 빈 턴(10-28 재심사 p06_b) — 코드가 한 문장
EMPTY_ANSWER = (
    "그 질문에 맞는 자료를 찾지 못했어요. 동 이름이나 대상(어르신 · 청년)을 함께 말씀해 주시면 "
    "다시 찾아볼게요."
)
# 【기능】 앞 답을 되짚는 말: 앞 답의 숫자(세 자리 이상 · ○위)를 다시 말하거나 '아까 · 앞에서'
# 【판단】 10-20 페르소나 o06 r5 T8 · T9 '처음에 강남이 41%, 춘천이 28%라고 하신 숫자 자체는
#        맞는 건가요?': 몇 턴 앞(T1) 답의 숫자라 직전 답의 자료에 없어 '자료에 없다'고 했다.
#        '처음 · 하신' 같은 말과 몫(%)도 되짚는 말로 보고, 그 전 답들의 자료(older_facts)도 준다
_BACK = re.compile(
    r"아까|앞에서|앞 답|방금|지난번|위에서|그 숫자|그 순위|말씀하신|처음에|처음 답|하신 숫자|"
    r"라고 하신|라고 했|말씀해 주신|알려 주신|해 주셨|하셨잖|처음엔|아까는"
)
# 10-20 페르소나 s02 r8: '25곳 중 7곳 · 2가지'를 되짚었는데 두 자리 수라 잇지 않아 '자료에 없다'
# 10-25 페르소나 cli4 오린 T9: '강남 8/22, 춘천 14/25'처럼 나눗셈 꼴로 되짚으면 숫자로 못 읽었다
_NUM_BACK = re.compile(
    r"\d+\s*/\s*\d+|\d[\d,]{2,}|\d+위|\d+(?:\.\d+)?%|\d+(?:곳|가지|명|채|세대|가구)"
)
# 【판단】 날짜(기준일 2026-09-30 · 2025년)의 숫자는 앞 답 숫자로 보지 않는다(거의 모든 줄에 있다)
_DATE = re.compile(r"\d{4}[-./]\d{1,2}(?:[-./]\d{1,2})?|\d{4}년")
_HEAD_ONLY = re.compile(r"^\[[^\]]+\]$")
# 【판단】 10-20 페르소나 s02 r8: '지금까지 말씀해 주신 내용 세 줄로 요약'이 되짚기(recall)로 가
#        '아직 춘천시의 동은 함께 보지 않았어요'(두 번). 요약을 달라면 앞 답들의 자료로
#        글쓴이가 쓴다
URGENT = re.compile(
    r"연락이 (?:끊|안 ?되|없)|연락 두절|전화를? 안 받|꺼져|걱정돼|걱정이 돼|쓰러|위급|급해|급한|"
    r"문(?:이라도)? ?(?:두드|열)|찾아 ?(?:가|뵙)|통 ?안 ?보|안 보여|안 보이|보이지 않|소식이 없"
)
# 【정함 10-26 설계 문서 6-2 결정 거리 3】 예산을 어디에 더 줄지 같은 판단은 비서가 정하지 않고 근거
#        숫자만. 예상 질문 1-29 '그래서 예산을 어느 동에 더 줘야 하는지 결론만 내려 줘요'에 '예산을
#        우선 볼 동은 … 개포3동'이 나갔다 → 코드가 알아보고 머리말 · 글쓴이 안내를 붙인다
DECIDE_ASK = re.compile(
    r"(?:예산|지원금|사업비|인력|돈)[^.?!\n]{0,20}(?:어느|어디|누구|몇)[^.?!\n]{0,20}"
    r"(?:줘야|주어야|써야|배정|몰아|나눠|보내야|투입|더 ?줘|더 ?주)|"
    r"(?:어느|어디)[^.?!\n]{0,15}(?:예산|지원금|사업비)[^.?!\n]{0,15}(?:줘야|써야|배정|몰아|더)"
)
DECIDE_HEAD = "(예산을 어느 동에 줄지는 비서가 정하지 않아요. 정하실 때 쓸 근거만 보여 드려요.)\n"
DECIDE_NOTE = (
    "예산 · 인력을 어느 동에 줄지 정해 달라는 말이다. 어느 동에 주라고 결론 내지 않는다"
    "('예산을 우선 볼 동은 ○○' 같은 말도 쓰지 않는다). 순위 · 숫자 같은 근거만 그대로 쓴다"
)
# 빈칸을 지운 말에 대는 꼴(띄어쓰기 없이 빨리 친 말 — 10-29)
URGENT_SQ = re.compile(
    r"연락이?(?:끊|안되|안돼|없|두절)|전화를?안받|꺼져|걱정(?:돼|이돼|됩)|쓰러|위급|급해|급한|급합|"
    r"문(?:이라도)?(?:두드|열)|찾아(?:가|뵙)|통안보|안보여|안보이|보이지않|소식이없"
)
LOST_CONTACT_SQ = re.compile(
    r"(?:이틀|사흘|나흘|며칠|일주일|여러날|\d+일)째?[^.?!]{0,12}"
    r"(?:연락이?(?:안되|안돼|끊|두절|안닿|되지않|닿지않)|전화를?안받|소식이없|안보이|안보여)"
    r"|(?:연락이?(?:안되|안돼|끊|두절|되지않)|전화를?안받)[^.?!]{0,6}(?:이틀|사흘|나흘|며칠|일주일)"
)
# 글쓴이가 다시 쓴 '○○(으)로 알아들었어요. 아니면 말씀해 주세요.'(코드가 이미 머리말로 붙임)
HEARD_AGAIN = re.compile(
    r"(?m)^[ㄱ-ㅎ]?[^\n.]{0,40}?(?:으)?로 알아들었어요\.?(?:\s*아니면 말씀해 주세요\.?)?[ \t]*\n?"
)
# 목숨이 걸린 말(이때는 자료 마디를 나눠 답하지 않고 위기 안내만)
SEVERE_SQ = re.compile(r"자살|죽고|죽을|죽었|쓰러|의식|학대|폭행|폭력|피가|불이나|화재|숨을|숨이")
URGENT_NOTE = (
    "연락이 끊긴 분이 걱정되시면 동 주민센터에 안부 확인을 요청하시고, 생명이 위험해 보이면 "
    "바로 112나 119에 신고해 주세요."
)
# 【정함 10-26 팀장 "너가 추천하는대로 일단 다 해봐"】 예상 질문 2-21 '그 판단이 틀렸던 적은 없어요?
#        틀리면 책임은 누가 져요?'에 '자료로 가릴 수 없어요'만 나가 질문을 피하는 것처럼 들렸다.
#        법적 면책이 아니라 설계(결정 거리 3 — 비서는 근거만, 결정은 담당자)를 그대로 한 문장으로
ROLE_ASK = re.compile(
    r"책임[은이을]?\s?(?:누가|누구|어디)|틀리면|틀렸던|틀린 적|잘못되면|잘못된 (?:판단|결과|숫자)|"
    r"오류가? (?:나면|있으면)"
)
ROLE_NOTE = (
    "비서는 공개 자료로 근거를 보여 주는 참고 도구예요. 어느 동을 먼저 볼지, 예산을 어떻게 쓸지는 "
    "담당자와 기관이 정하고, 숫자마다 출처와 기준일을 드리니 원자료로 확인하실 수 있어요."
)
CAN_INSTEAD = (
    " 대신 {where} 경로당 · 복지관 위치와 연락처, 안부 확인 창구는 바로 알려 드릴 수 있어요."
)
CAN_INSTEAD_NO_DONG = (
    " 대신 동 이름을 말씀해 주시면 그 동 경로당 · 복지관과 안부 확인 창구를 알려 드릴게요."
)
SAID_BEFORE = (
    "앞에서 말씀드린 것처럼 한 분 한 분의 정보(이름 · 주소 · 연락처 · 명단)는 찾아 드릴 수 없어요."
)
# 【판단】 10-25 페르소나 cli2 세라핀 T8 · T9: 앞 답 머리의 '개인 정보로 보이는 부분(이름)은
#        가리고 받았어요'에 '무엇을 가렸느냐'를 세 번 물었는데, 데스크가 자료 설명 주제로 보내
#        묻지 않은 긴 자료 설명(기본 답)만 나갔다. 가린 자리는 대화 기록에 '[이름]'으로 남아 있어
#        코드가 답한다. 가린 말 자체는 AI에 보내지 않고 기록(chat_turn)에도 가린 뒤 글만 남는다
# '가리키다'(무엇을 가리키나요)는 가림이 아니다
MASK_ASK = re.compile(
    r"(?:무엇|뭘|뭐|무슨|어떤 ?(?:것|말|부분)|어느 ?부분)[^.?!\n]{0,12}가리(?![키켜킨킬])|"
    r"가리(?:신|셨)|가린 (?:것|게|거|부분|말)"
)
NOTHING_MASKED = (
    "이 대화에서는 가린 말이 없어요. 이름 · 전화번호 · 주민번호 · 호수로 보이는 말이 있으면 "
    "AI에 보내기 전에 가리고, 가렸다는 것을 답 머리에 알려 드려요."
)
MASKED = re.compile(r"\[(이름|전화번호|주민번호|호수|아파트 동 번호)\]")


def mask_spots(text: str) -> tuple[str, ...]:
    """가린 글에서 가린 자리마다 앞뒤 몇 글자(가린 말은 '[이름]'처럼 이미 빠져 있다)."""
    return tuple(
        text[max(0, m.start() - 10) : m.end() + 8].replace("\n", " ").strip()
        for m in MASKED.finditer(text)
    )


def mask_answer(spots: tuple[str, ...]) -> str:
    """가장 최근에 가린 글의 가린 자리와 종류(state.masked). 가린 적이 없으면 없다고.

    【판단】 대화 기억(recent)은 글의 앞 200자만 남겨 세라핀 T6의 '[이름]'(520자째)이 잘렸다
           → 가릴 때 가린 자리를 따로 남긴다
    """
    if not spots:
        return NOTHING_MASKED
    kinds = Counter(m.group(1) for s in spots for m in MASKED.finditer(s))
    what = " · ".join(f"{k} {n}곳" for k, n in kinds.items())
    where = " · ".join(f"'…{s}…'" for s in spots[:3])
    return (
        f"앞서 받은 글에서 {what}을 가렸어요. 가린 자리는 {where}예요. "
        "가린 말은 AI에 보내지 않고 대화 기록에도 가린 뒤의 글만 남겨서, "
        "무엇이었는지는 저도 알 수 없어요. "
        "이름 · 전화번호 · 주민번호 · 호수로 보이는 말은 늘 이렇게 가리고 받아요."
    )


SUMMARY_ASK = re.compile(
    r"요약|정리해|정리 해|세 ?줄|두 ?줄|한 ?장|한 문장으로|"
    r"지금까지 (?:말|알려|얘기)|앞에서 (?:말|알려)"
)
OLDER_FACTS_MAX = 120
# 【기능 10-27】 세션 — 첫 질문을 제목으로 쓸 때 글자 수 · 이어서 만든 세션에 옮기는 목록 크기
FIRST_MAX = 60
CARRY_LOG = 15
CARRY_RECENT = 2
TABLE_EDIT_TURNS = 3  # 표를 그린 뒤 몇 턴까지 '정렬 · 열 더해 줘'를 그 표로 받나
# 계산 길을 타는 답 형식 — 10-28: 엑셀도(한 말에 '계산 + 엑셀'이면 계산 표로 파일, p09_c).
# PDF · PPTX(동 상황 문서)는 계산 길이 아니다
CALC_FMTS = ("답", "엑셀")
# 파일만 달라는 말('엑셀로 주세요 · 엑셀 파일로 받을 수 있어요?') — 다른 물음이 없으면 글쓴이 없이
EXCEL_ONLY = re.compile(
    r"(?:그\s*)?(?:표|결과|그거|이거)?\s*(?:를|을)?\s*(?:엑셀|xlsx|csv|CSV|파일)(?:\s*파일)?"
    r"\s*(?:로|으로)?\s*(?:좀\s*)?(?:주세요|줘요?|주실\s*수\s*있나요|받을\s*수\s*있(?:어|나)요?"
    r"|부탁(?:해|드려)요?|내려\s*주세요|뽑아\s*주세요)?[.!?\s]*"
)
LONG_SESSION_TURNS = 50  # 이 수를 넘으면 화면이 새 세션을 '추천'(강요하지 않음)


def session_title(st: DialogueState | None, fallback: str = "") -> str:
    """세션 제목 — 사용자가 정한 것, 없으면 첫 질문, 그것도 없으면 fallback."""
    if st is None:
        return fallback
    return st.title or st.first or fallback


def session_turns(st: DialogueState) -> int:
    """이 세션의 대화 수(앞 세션을 이어 만든 세션은 이어 온 턴을 빼고 센다)."""
    return max(0, st.turn - st.since)


LAST_FACTS_MAX = 60
SAID_FACTS_MAX = 80
CARRY_TITLE = "앞서 답할 때 본 자료(다시 확인용)"
CARRY_NOTE = (
    "앞서 답할 때 본 자료 줄이다. 그때 말한 숫자의 근거이니 뒤집지 않는다. "
    "출처를 물으면 이 줄의 자료 이름 · 기준을 말하고, 이 묶음 이름은 답에 쓰지 않는다"
)


def num_keys(s: str) -> set[str]:
    """글 속 숫자를 견줄 열쇠로('22곳 중 8곳(36%)' ↔ '8/22' · '36%').

    단위가 붙은 꼴('8곳' · '36%')은 그대로, 두 자리 이상 숫자는 숫자만으로도 둔다.
    나눗셈 꼴('8/22')은 두 숫자를 다 둔다.
    """
    keys: set[str] = set()
    for m in _NUM_BACK.findall(_DATE.sub(" ", s)):
        m = m.replace(",", "").replace(" ", "")
        vals = re.findall(r"\d+(?:\.\d+)?", m)
        if "/" in m:
            keys |= set(vals)
            continue
        keys.add(m)
        keys |= {v for v in vals if len(v) >= 2}
    return keys


# 앞 답 숫자를 되짚은 것이 아닌 숫자 — 나이 조건(80세 이상 · 19~34세)과 번호(1. · 2))
_NOT_RECALL_NUM = re.compile(
    r"\d{1,3}\s?(?:~|-)\s?\d{1,3}\s?세|\d{1,3}\s?세(?:\s?(?:이상|이하|미만|넘은))?|"
    r"(?:(?<=\s)|^)\d{1,2}\s?[.)](?=\s)"
)


def _bare(keys: set[str]) -> set[str]:
    """숫자만인 열쇠(두 자리 이상 · 소수) — '1곳 · 2위' 같은 흔한 작은 수로 잇지 않는다."""
    return {k for k in keys if re.fullmatch(r"\d{2,}(?:\.\d+)?|\d+\.\d+", k)}


def said_lines(message: str, facts: list[Facts]) -> list[str]:
    """답에 실제로 말한 숫자가 든 자료 줄 — 몇 턴 뒤에 되짚어도 근거를 잃지 않게 따로 둔다."""
    spoken = _bare(num_keys(message))
    if not spoken:
        return []
    out: list[str] = []
    for f in facts:
        head = ""
        for ln in f.lines:
            if _HEAD_ONLY.match(ln):
                head = ln
            elif spoken & num_keys(ln):
                # 동 머리줄('[강남구 수서동]')을 붙여 둔다 — 몇 턴 뒤에 이어 줘도 어느 동인지 알게
                out.append(f"{head} {ln}" if head and not ln.startswith("[") else ln)
    return out


def doc_facts(recent: tuple, carried: tuple[str, ...] = ()) -> Facts | None:
    """앞서 만든 동 상황 문서의 글(문서 줄이 자료에 남아 있으면 전부, 아니면 답에 보인 요약)."""
    body = [x for x in carried if x.startswith("문서 ")]
    if body:
        return Facts(
            title="앞서 만든 동 상황 문서(글 전체 — 요약과 절마다 글머리)",
            lines=body,
            notes=[DOC_Q_NOTE, "어떤 문구가 문서에 있는지는 위 줄에 그 말이 있는지로 답한다"],
        )
    for r in reversed(recent):
        if DOC_MADE in r.bot:
            lines = [x.strip() for x in r.bot.split("\n") if x.strip().startswith("·")]
            return Facts(title="앞서 만든 동 상황 문서(요약)", lines=lines, notes=[DOC_Q_NOTE])
    return None


def carry_facts(
    text: str,
    last_answer: str,
    last_facts: tuple[str, ...],
    facts: list[Facts],
    older: tuple[str, ...] = (),
    earlier: str = "",
    kept: tuple[str, ...] = (),
) -> Facts | None:
    """앞 답을 되짚는 말이면 앞 답에 쓴 자료 줄 중 이번 묶음에 없는 것을 하나로 묶는다.

    【판단】 10-15 페르소나 20b 재생: '앞 답 숫자를 없다고 함'이 원본 18 · 중간 9 · 마지막 19로
           흔들렸다. 뒤집힌 턴은 데스크가 그 턴에 다른 주제를 골라 앞 답의 숫자(순위 · 진단)가
           사실 묶음에서 빠진 경우였다(q01 T13 '12위 맞죠?' → 버스 주제 → '12위는 확인되지 않아요').
           데스크를 고치는 대신 앞 답의 자료를 글쓴이에게 함께 준다(숫자는 그대로 허용 글에)
    【판단】 10-25 페르소나 cli4 오린 T7: 되짚는 말 · 숫자가 없는 질문에서 글쓴이가 [직전 답]의
           '22곳 중 8곳(36%)'을 보고도 그 근거 줄을 못 받아 '제가 가진 자료에서 확인되지 않으니'
           → 직전 답에 나온 숫자의 근거가 이번 묶음에 없으면 그 줄만은 늘 함께 준다.
           kept = 지난 답들에서 실제로 말한 숫자의 근거 줄(state.said_facts, 오래 둔다)
    """
    if not last_facts and not older and not kept:
        return None
    have = {line for f in facts for line in f.lines}
    pool = [
        x
        for x in dict.fromkeys(last_facts + kept + older)
        if not x.startswith("## ") and x not in have
    ]
    # 10-21 r14 노엘 T8: 다섯 턴 전 표의 '합계 31,845명'을 되물었는데 그 줄이 60줄 밖으로 밀려
    #        '자료에 없는 숫자' → 사용자가 말한 숫자가 든 앞 자료 줄이 있으면 되짚는 말이 없어도
    #        그 줄을 맨 앞에 꼭 넣는다
    # 10-26 예상 질문 q5 2-26 '1. 동면이 … 2. 80세 이상 혼자 사는 분 … 4. 가까운 보건지소': 나이
    #       조건(80세)과 번호(1. 2.)를 앞 답 숫자를 되짚은 것으로 읽어 앞 동(신북읍) 자료가 통째로
    #       따라왔고 글쓴이가 신북읍 보건지소를 답했다 → 나이 · 번호는 빼고 센다
    said = num_keys(_NOT_RECALL_NUM.sub(" ", text))
    first = [x for x in pool if said and said & num_keys(x)]
    gap = _bare(num_keys(last_answer)) - num_keys("\n".join(have))
    backing = [x for x in pool if x not in first and gap & num_keys(x)]
    if not (first or _BACK.search(text) or said & num_keys(f"{last_answer} {earlier}")):
        if not backing:
            return None
        # 되짚는 말이 아니면 직전 답 숫자의 근거 줄만(다른 앞 자료는 붙이지 않는다)
        return Facts(title=CARRY_TITLE, lines=backing[:LAST_FACTS_MAX], notes=[CARRY_NOTE])
    rest = [x for x in pool if x not in first and x not in backing]
    lines = (first + backing + rest)[:LAST_FACTS_MAX]
    return Facts(title=CARRY_TITLE, lines=lines, notes=[CARRY_NOTE]) if lines else None


def facts_lines(facts: list[Facts]) -> tuple[str, ...]:
    """다음 턴에 이어 줄 이번 답의 자료 줄(묶음 이름 + 줄, 60줄까지)."""
    out: list[str] = []
    for f in facts:
        out += [f"## {f.title}", *f.lines]
    return tuple(out[:LAST_FACTS_MAX])


def dedupe_facts(facts: list[Facts]) -> list[Facts]:
    """앞 묶음에 이미 나온 줄 · 참고는 뒤 묶음에서 뺀다.

    【판단】 10-15 페르소나 q02 T1: 먼저 볼 동 + 동 상황이 둘 다 날씨 줄을 붙여 같은 줄이 두 번 나감
    """
    seen: set[str] = set()
    for f in facts:
        # 【판단】 동 머리줄('[강남구 수서동]')은 묶음마다 둔다(뒤 줄이 어느 동인지 알게)
        f.lines = [ln for ln in f.lines if ln.startswith("[") or ln not in seen]
        f.notes = [n for n in f.notes if n not in seen]
        seen.update(f.lines, f.notes)
    return facts


# 【기능】 표를 그 지역 모든 동으로 만들라는 말(10-14)
EACH_DONG = re.compile(r"동별|동마다|전체|모든 동|\d+개 동")
RECALL_NOT = re.compile(r"\d|써도|적어도|맞습니까|맞나요|맞죠|맞아요|되겠습니까|맞는 겁니까")
# '처음에 물어본 세 동' · '처음 본 두 곳'(10-27 밤 창 시험 T22)
FIRST_DONGS = re.compile(
    r"처음(?:에)?\s*(?:물어본|물었던|본|봤던|말한|얘기한)\s*(한|두|세|네|다섯|[1-9])\s*(?:개\s*)?(?:동|곳)"
)
COUNT_WORD = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}
TOP_RANK = re.compile(
    r"(?<![\d가-힣])(?:순위\s*)?([1-9]|1\d|2[0-5])\s?위(?:인|의)?\s*동"
    r"|먼저 볼 동\s*([1-9]|1\d|2[0-5])\s?위"
)
RANK_WORD = re.compile(r"순위|먼저 볼")
# 주제 → 그 주제를 줄 세우는 대표 지표('○○ 순위에서 N위 동', 10-29)
TOPIC_METRIC = {
    "solo_seniors": "solo65",
    "youth": "youth_solo",
    "livelihood": "livelihood",
    "senior_hall": "halls",
    "housing": "old_walkup",
    "seoul_lonely": "lonely_total",
}
METRIC_NAME = {
    "solo65": "65세 이상 1인세대",
    "youth_solo": "청년 1인세대",
    "livelihood": "기초생활수급자",
    "halls": "경로당 · 마을회관",
    "old_walkup": "30년 넘은 계단 집",
    "lonely_total": "서울시 독거노인",
}
# 읍 · 면 가운데만을 말함('읍면 중에 · 면 가운데')
TOWN_ONLY = re.compile(r"읍\s?[·・,]?\s?면|면\s?(?:중|가운데|에서)|읍\s?(?:중|가운데)")
# 지표로 줄 세운 순위를 가리키는 말('많은 순 · 순위에서 · 많은 동 중')
METRIC_RANK = re.compile(r"(?:많은|적은|높은|낮은)\s?(?:순|동|곳)|순위\s?(?:에서|로|상|중)|순\s?\d")
# 취약 돌보미 동 순위를 분명히 가리키는 말(그냥 '순위'는 앞 답의 순위일 수 있다)
PRIORITY_RANK_WORD = re.compile(r"취약\s?돌보미|먼저\s?볼|동\s?순위")
_RANK_SEEN = re.compile(
    r"(\d{1,2})\s?위\s*[:)]?\s*([가-힣0-9]+(?:동|읍|면))"
    r"|([가-힣0-9]+(?:동|읍|면))(?:[^\n·,]|(?<=\d),(?=\d)){0,40}?(?<![\d,])(\d{1,2})\s?위"
)


def ranks_in(answer: str) -> dict[int, str]:
    """앞 답에 적힌 'N위 ○○동' · '○○동 …(N위)' → {N: 동}. 우리 동 이름만, 처음 나온 것."""
    out: dict[int, str] = {}
    for m in _RANK_SEEN.finditer(answer or ""):
        n, name = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        got = dongs_in_text(name)
        if got and int(n) not in out:
            out[int(n)] = got[0]
    return out


# 글을 다듬어 달라는 말(써 둔 글 고치기인지, 우리 자료로 보고 문장을 만들어 달라는지 두 뜻 — 10-27)
POLISH = re.compile(
    r"(?:문장|글|보고서|공문|문구|초안|보고)[^\n]{0,10}(?:다듬|매끄럽|손\s?봐|손\s?보|윤문)"
)
POLISH_NO = "써 두신 글을 고치거나 다듬는 일은 제가 할 수 없어요."
POLISH_PASTED = 80  # 이보다 긴 말이면 다듬을 글을 붙여 넣은 것으로 본다
# 1위가 어느 동인지를 묻는 말('1위가 어디예요?' · '어느 동이 1위')
TOP_WHERE = re.compile(
    r"\d{1,2}\s?위[가는은]?\s*(?:어디|어느|무슨|뭐)|(?:어디|어느 ?동)[가이]?\s*\d{1,2}\s?위"
)
DOC_DONG = re.compile(r"([가-힣0-9]+(?:동|읍|면))\s*(?:의\s*)?(?:동\s*)?상황\s*문서")
SORT_COLS = (
    "청년 1인세대 {reg}",
    "청년 1인세대 1년 새 증감률(%)",
    "65세 이상 1인세대 1년 새 증감률(%)",
    "청년 중 1인세대 몫(%)",
    "65세 이상 1인세대 {reg}",
    "65세 이상 중 혼자 사는 몫(%)",
    "지하층이 있는 30년 넘은 저층 주거 건물",
    "30년 넘은 계단 집 가구",
    "기초생활수급자(명)",
    "경로당 수",
)
# 【기능】 표를 달라는 말(채팅 표 포함) — 표의 줄을 글쓴이에게 준다(_table_facts, 10-20)
# 앞서 만든 동 상황 문서에 대해 묻는 말(10-20 페르소나 s01 r12 T8 ~ T10: '문서에 그 한계 문구가
#        있는지' · '겨울 증가는 작년 자료인지'에 같은 요약을 세 번 다시 만듦)
#        — 다시 만들지 않고 답한다
# 10-26 웹 점검: '수서동 동 상황 문서'처럼 동이 겹쳐 '수서동 상황 문서'로 씀(옛 말에도 걸림)
DOC_MADE = "상황 문서를 만들었어요"
# 10-28 재심사 p05_b T3 '요약만 보이고 PDF 다운로드 버튼이 안 보여요 … 어떻게 받는지':
#        세 판 모두 'PDF는 이 대화 창에서 만들 수 없어요' · '받는 방법은 자료에 없어요'(거짓 —
#        문서를 만든 답 아래 'PDF 내려받기' · 'PPTX 내려받기' 단추, src/api/chat.html)
DOC_DOWNLOAD_NOTE = (
    "문서 파일(PDF · PPTX)은 문서를 만든 그 답 아래의 'PDF 내려받기' · 'PPTX 내려받기' 단추로 "
    "받는다. "
    "단추가 안 보이면 '○○동 상황 PDF로 만들어 줘'라고 하면 다시 만든다. 'PDF를 만들 수 없다' · "
    "'받는 방법은 자료에 없다'고 하지 않는다"
)
DOC_QUESTION = re.compile(
    r"문서(?:에|를|가|의| 안에| 어디에)?[^\n]{0,60}"
    r"(?:있는지|적혀|들어 ?있|들어갔는지|들어갔|있나요|나오나요|있습니까|어디에 있)|"
    r"문서[^\n]{0,30}(?:어느 해|작년|기준인|무슨 뜻|뜻인가)|"
    r"다시 만들지 말|다시 만들어 달라는 게 아니|요약만으로는"
)
DOC_Q_NOTE = (
    "사용자가 앞서 만든 동 상황 문서에 대해 묻는다(문서를 다시 만들지 않는다). "
    "문서 요약은 위 줄이고, "
    "그 밖의 문구가 문서에 있는지는 요약만으로 알 수 없으면 '요약에는 없다'고 답한다. "
    "'겨울(11·12월)' 비교는 서울 시민생활 데이터 2025년 7·8월 대 11·12월(작년 자료)이다"
)
# 막힌 말 속 '경찰에 신고하면 어떻게 되나 · 밤에는 어디로'(10-20 페르소나 o02 r13 T8 ~ T10) — 상식
POLICE_Q = re.compile(
    r"경찰이[^\n]{0,20}(?:가 ?봐|찾아가|출동|확인)|신고하면[^\n]{0,20}(?:어떻게|경찰)|실종 ?신고|"
    r"밤에[^\n]{0,16}(?:번호|연락|전화)|24시간[^\n]{0,10}(?:번호|연락)"
)
POLICE_LINE = (
    "112에 신고하면 경찰이 안전 확인(집 방문)을 나갈 수 있어요(출동은 신고 내용에 따라 정해요). "
    "밤에도 112 · 119로 신고할 수 있어요."
)
SAME_ANSWER = "같은 답을 드릴 수밖에 없어요. "
# 누구 · 어디부터 볼지 묻는 말(10-25 세라핀 — 연휴 답에 '먼저 살필 무리'는 이때만)
WHO_FIRST = re.compile(
    r"누구(?:부터|를 먼저|를 챙|에게 먼저)|어디(?:부터|를 먼저)|"
    r"먼저 (?:볼|살필|챙길|연락할)|우선(?:순위|으로)"
)
# 막기 답 속 곁물음(10-25 레아나) — 개인 정보가 아닌 물음
SERVICE_Q = re.compile(r"1566\s*-?\s*3232|응급\s*안전\s*안심")
TELL_112 = re.compile(
    r"112[^\n]{0,24}(?:뭐라고|무엇을|뭘|무슨 말|어떻게 말)|"
    r"신고(?:할 때|하려면)[^\n]{0,12}(?:뭐라고|무엇을|뭘|무슨 말)"
)
ROSTER_Q = re.compile(
    r"명단[^\n]{0,20}(?:볼 수|보는|기능|권한)|(?:권한|기관 회원)[^\n]{0,30}(?:명단|대상자)"
)
FAMILY_Q = re.compile(r"(?:가족|친척|보호자|자녀)(?:이면|이라도|이라고 하면|인데|라면|이니까)")
# 출처: 복지로(보건복지부 정보제공, 2025-05-29) '112 신고 내용: 이름, 장소(위치), 신고하는 이유'
TELL_112_LINE = (
    "112에 신고할 때는 이름 · 장소(위치) · 신고하는 이유를 말하라고 안내돼 있어요"
    "(복지로 · 보건복지부). 예를 들어 장소는 그분이 사시는 곳을 아는 만큼, 이유는 언제부터 연락이 "
    "안 되는지를 말씀하시면 돼요."
)
ROSTER_LINE = (
    "취약 돌보미에는 회원 종류나 권한과 상관없이 개인 명단 · 대상자 목록이 없어요"
    "(동 단위 공개 자료만 있어요)."
)
FAMILY_LINE = "가족이어도 취약 돌보미에는 개인 주소 · 연락처 자료가 없어 찾아 드릴 수 없어요."


def side_answers(text: str, data: DongData) -> list[str]:
    """막기 답 속에서도 답할 수 있는 곁물음의 답 — 개인 정보가 아닌 것만(10-25).

    1566-3232는 갈 곳 자료의 응급안전안심서비스(공공데이터 15098764 · 복지로)로, 112에 말할 것은
    복지로 안내로만 답한다. 전화하면 무엇을 해 주는지처럼 자료에 없는 것은 없다고 밝힌다
    """
    out = []
    if SERVICE_Q.search(text):
        common = data.places_common() if hasattr(data, "places_common") else {}
        s = (common or {}).get("safety") or {}
        num = s.get("중앙모니터링센터") or "1566-3232"
        line = f"{num}는 응급안전안심서비스 중앙모니터링센터 번호예요"
        if s.get("장비") or s.get("신청"):
            line += f"(서비스: {s.get('장비', '')}. 신청: {s.get('신청', '')})"
        out.append(
            line
            + ". 전화하면 무엇을 해 주는지 · 그분이 이 서비스를 쓰시는지는 취약 돌보미 자료에 없어요."  # noqa: E501
        )
    if TELL_112.search(text):
        out.append(TELL_112_LINE)
    if ROSTER_Q.search(text):
        out.append(ROSTER_LINE)
    if FAMILY_Q.search(text):
        out.append(FAMILY_LINE)
    return out


# 아파트 · 단지에서 가까운 곳(10-20 페르소나 o02 r12 T6 ~ T8): 그 위치 자료가 없어 못 잰다고 말한다
APT_NEAR = re.compile(
    r"([가-힣0-9]+(?:아파트|빌라|단지))[^\n]{0,14}(?:가까운|가장 가까|제일 가까|근처)"
)
# 채팅에 표를 달라는 말(파일 말고) — 코드가 그린 표를 붙인다(10-21)
# 10-28 페르소나 p01_c T1 '많은 순으로 표 좀 급하게 부탁드립니다'를 놓쳐 '엑셀 표로 만들어
#        드리는 기능은 없어요'(거짓)가 나갔다 → '표 좀 · 표 하나 · 표로 좀'도 표 요청으로
CHAT_TABLE = re.compile(
    r"(?<![가-힣])표(?:로|를|만|도|좀|\s*(?:좀|형태|주|만들|정리|부탁|하나|뽑|그려))|마크다운"
)
# 취약 돌보미 자료에 없는 동 단위 물음(고독사 · 사망 · 신고 건수) — 막기 답에 한 줄 덧붙인다(10-20
#        r11 o02)
NO_DATA_ASK = re.compile(
    r"고독사|돌아가신 분|사망|신고(?:된 게|가|는|된 것이)? ?몇|신고 ?건수|몇 건"
)
NO_DATA_LINE = (
    "동 단위 고독사 · 사망 · 신고 건수는 취약 돌보미 자료에 없어요(경찰 · 구청이 가진 자료예요)."
)
# '통·반을 묻지 않았다' 같은 말 — 그 낱말이 있어도 묻는 것이 아니다(10-20 r10 o01)
NOT_ASKING = re.compile(r"묻지 않|안 물|필요 없|빼 주|붙이지 마|말고요")
TABLE_ASK = re.compile(
    r"(?<![가-힣])표(?:로|를|만|에|좀|\s*(?:좀|형태|주|만들|정리|부탁|하나|뽑|그려))|마크다운|엑셀|CSV|csv"
)


def prepare_input(text: str) -> tuple[str, list[str], list[tuple[str, str]]]:
    """데스크 · 기억 · 저장소에 닿기 전에 코드가 손보는 것 → (고친 말, 가린 종류, 바꾼 글자).

    【판단】 개인정보는 코드가 먼저 가린다(10-12 멘토 · 떠보기).
           데스크만 재는 시험(evals/run_desk.py)도 이 함수를 거쳐 엔진과 같은 말을 보낸다.
    【판단】 영어 자판으로 친 한글 · 초성 동 이름은 코드가 먼저 바꾼다(10-14, keyboard.py).
           가림보다 먼저 한다(영어 자판으로 친 이름 · 호칭도 가려지게)
    """
    text, typed = keyboard.fix(text)
    text, hidden = pii.mask(text)
    return text, hidden, typed


def typed_note(typed: list[tuple[str, str]]) -> str:
    """바꾼 글자를 답 앞에 밝힌다.

    【판단】 짐작은 틀릴 수 있어 조용히 쓰지 않는다(오타 짐작과 같은 까닭).
    """
    if not typed:
        return ""
    heard = ", ".join(f"'{said}'을(를) '{word}'(으)로" for said, word in typed)
    return f"({heard} 읽었어요. 아니면 말씀해 주세요.)\n"


# 【기능】 여러 조건 계산이 다루는 주제(이 주제 줄은 계산 사실 묶음으로 갈음한다)
CALC_TOPICS = frozenset(
    {
        "solo_seniors",
        "youth",
        "housing",
        "livelihood",
        "diagnosis",
        "priority",
        "senior_hall",
        "seoul_lonely",
        "places",
    }
)
# 【기능】 계산 지표(query.METRICS 키의 앞부분) → 그 자료를 가진 서가 주제. 계산 길에서도 그
#        주제의 밝힘 · 서가 자료를 붙이려고(10-29). 마을 지표(v_…)는 동 서가가 없어 뺀다
METRIC_TOPIC: tuple[tuple[str, str], ...] = (
    ("solo65", "solo_seniors"),
    ("solo80", "solo_seniors"),
    ("pop65", "solo_seniors"),
    ("pop80", "solo_seniors"),
    ("lonely", "seoul_lonely"),
    ("livelihood", "livelihood"),
    ("youth", "youth"),
    ("solo_all", "livelihood"),  # 서가는 수급 묶음 끝에 1인 가구(모든 나이)를 붙인다
    ("empty_houses", "housing"),
    ("old_walkup", "housing"),
    ("res_units", "housing"),
    ("basement_old", "housing"),
    ("halls", "senior_hall"),
    ("hall_area", "senior_hall"),
    ("meals", "places"),
    ("pharmac", "places"),
    ("clinics", "places"),
    ("ltc_", "places"),
    ("diag", "diagnosis"),
    ("gap", "priority"),
    ("risk_band", "priority"),
    ("priority", "priority"),
)


_ROW_BULLET = re.compile(r"^\s*(?:[·•\-]|\d+\.)\s*(\S+?)[\s:：(]")


def drop_row_bullets(body: str, names: list[str]) -> str:
    """표에 줄로 있는 동(이름)으로 시작하는 목록 줄을 뗀다 — 표와 같은 숫자를 두 번 쓰지 않게."""
    want = set(names)
    keep = []
    for line in body.split("\n"):
        m = _ROW_BULLET.match(line)
        if m and m.group(1).rstrip(":：") in want:
            continue
        keep.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def _in_background(fn: Callable[..., str | None], *args: object) -> Future[str | None]:
    """fn(*args)를 따로 돌린다(기다리지 않음) — 데스크와 동시에 부르는 말뜻 고르기."""
    pool = ThreadPoolExecutor(max_workers=1)
    job = pool.submit(fn, *args)
    pool.shutdown(wait=False)
    return job


def _two_region_dongs(text: str) -> bool:
    """말에 강남 동과 춘천 동을 함께 적었나.

    【판단】 10-29 브라우저 시험 '제 담당 개포3동이랑 효자2동 … 표로 나란히 비교': 계산 도구는 한
           지역씩 세어, 계획 AI가 춘천 위 5곳 줄 세우기로 바꿔 계산했다 → 두 지역 동을 견주는
           말은 계산 길이 아니라 동마다 서가 · 표 길로(지역 둘의 합계 · 평균은 계산 길이 따로 한다)
    """
    return len({dongname.region_of(d) for d in dongs_in_text(text)} - {None}) > 1


def metric_topics(refs) -> list[str]:
    """계산이 쓴 지표들의 서가 주제(나온 차례, 겹침 없이)."""
    out: list[str] = []
    for r in refs:
        for head, topic in METRIC_TOPIC:
            if r.metric.startswith(head) and topic not in out:
                out.append(topic)
    return out


# 갈 곳의 이름 · 주소 · 전화를 묻는 말이면 갈 곳 서가도 같이 꺼낸다
# 10-26 예상 질문 q6 2-26 '4. 가까운 보건지소': 계산 통로로 가며 갈 곳 서가를 빼 '보건지소 위치는
#        자료에 없어요'(동면 보건지소가 있음) → 가까운 곳 · 보건기관 · 여는 시간도
PLACE_DETAIL = re.compile(
    r"이름|주소|전화|연락처|어디\s?있|위치|가까운|보건지소|보건소|보건진료소|문\s?(?:연|여는)|운영\s?시간"
)
ARITH_NOTE = (
    "사용자가 적은 숫자를 코드가 그대로 셈한 결과다. '맞다 · 아니다'를 이 결과로 답하고, 그 숫자가"
    " 자료 값과 같은지는 다른 사실 줄로 확인해 함께 말한다"
)
PASTED_NOTE = (
    "사용자가 붙여 넣은 동별 숫자를 코드가 취약 돌보미 값과 대조한 결과다. 다른 동은 두 숫자를 "
    "그대로 쓴다. 왜 다른지는 이 자료로 확인할 수 없다고 하고, 취약 돌보미 숫자의 "
    "출처 · 기준일([기준] "
    "줄)을 밝혀 기준일이 다르면 그사이 생기거나 없어진 곳이 있을 수 있다는 것만 덧붙인다"
)
# 답 쓰는 AI 지시문(가장 긴 것)의 몫 — 크기 어림에만 쓴다
WRITER_HEAD = "가" * 2300
CALC_NOTES = (
    # 10-26 multi_hard H5: '첫 문장에서 … 밝힙니다'가 답에 그대로 나갔다 → 보일 말의 꼴로 준다
    "[알아들은 것]이 있으면 답을 '○○로 알아들었어요.'로 시작한다(이 안내문 자체는 쓰지 않는다)",
    "'모두 N곳 — 그중 위 5곳만 적음'이면 맞는 곳은 N곳이다 — 'N곳'이라고 먼저 쓰고, 적힌 곳은 "
    "'그중 위 5곳'이라고 쓴다(5곳이 전부라고 쓰지 않는다)",
    "'제일 · 가장'을 물었으면 1위 동을 먼저 말하고, 조건에 맞는 곳이 몇 곳인지 함께 쓴다",
    # 10-26 calc_flow_8 r2 T5: 맞는 6곳 중 셋만 쓰고, 맞지 않은 두 동을 '자료가 없어 확인되지
    #       않는다'고 씀
    "[모두 맞는 동]에 이름이 나온 동은 빠짐없이 쓴다. 거기에 없는 동은 조건에 맞지 않은 동이다"
    "('자료가 없다'고 쓰지 않는다 — 자료가 없으면 [자료 없는 동] 줄이 따로 있다)",
    "앞 결과 안에서 다시 거른 것이면 '앞의 N곳 중'이라고 몇 곳에서 골랐는지 밝힌다",
    "조건 · 계산 방식을 한 줄로 밝히고, 모두 맞는 동(또는 조건에 많이 맞는 동)과 숫자를 적는다",
    # 10-27 multi_hard H5: '[모두 맞는 마을] 없음'인데 먼저 거른 읍 · 면을 맞는 곳처럼 씀
    "'[모두 맞는 동] 없음' · '[모두 맞는 마을] 없음'이면 첫 문장에서 '조건을 모두 맞는 곳은 "
    "없어요'라고 먼저 말하고 하나만 못 맞춘 곳을 적는다([결론] 줄이 있으면 그 뜻대로 — 먼저 "
    "거른 읍 · 면을 맞는 곳처럼 쓰지 않는다)",
    "평균 · 지역 전체 값 · 배수 · 합계는 위 줄의 숫자만 쓴다(직접 더하거나 나누지 않는다)",
    "계산하지 못한 조건 · 자료 목록에 없는 조건은 그대로 밝힌다(다른 자료로 지어내지 않는다)",
    "동마다 ○ · × 표가 있으면 코드가 글 아래에 붙인다 — 글에서 표를 다시 그리지 않는다",
    # 10-26 예외 점검
    "[다른 곳에 있는 자료]가 있으면 '자료 없음'으로 끝내지 말고 어디서 볼 수 있는지 한 줄로 알린다",
    "[자료 없는 동]은 0이 아니라 자료가 없는 곳이다. [사람 단위로 겹쳐 세기]가 있으면 그 수는 셀 수"
    " 없다고 먼저 말한다",
    # 10-28 페르소나 p09_c: 80세 이상 독거의 '분모는 22곳 동 평균(300명)'이라고 지어냈다
    "'많음 · 적음'의 ○는 그 지역 동들 사이 등수(위 · 아래 3분의 1)로 정했다. 동 평균 · 가운데값은"
    " 견주어 보라고 준 값이지 ○ 기준도 분모도 아니다. 분모를 물으면 '1,000명당'처럼 나눈 지표만"
    " 그 사람 수가 분모이고, 나머지는 사람 · 채 · 곳 수를 그대로 센 값이라고 말한다",
)
# 【정함 10-27 팀장】 묻는 것만 — 계산 길이 표를 붙이는 답(동마다 표 · 많이 맞는 순)에서
#        글쓴이가 표의 값을 동마다 줄줄이 옮겼다(qbank 1-5 '개포3동이랑 개포1동 견주면?'
#        줄글 13줄 + 같은 값 12칸 표, 1,320자 · multi_16 C8 938자). 표가 붙을 때만 이 안내를 더한다
CALC_TABLE_NOTE = (
    "이 답에는 코드가 동마다 표를 글 아래에 붙인다(모든 동 · 모든 값). "
    "너는 표의 값을 동마다 줄줄이 "
    "옮기지 말고, 물은 것에 대한 결론과 눈에 띄는 차이 두세 가지만 쓴다"
)


def calc_missing(res: query.Result, plan: query.Plan, body: str) -> str:
    """모두 맞는 동 가운데 답 글에 없는 동이 있으면 맞은 동 전부를 한 줄로(없으면 '').

    【판단】 10-26 calc_flow_8 r2 T5: 맞는 6곳 중 글쓴이가 3곳만 썼다. 안내(CALC_NOTES)를 더해도
           글쓴이는 AI라 다시 생길 수 있어 코드가 대조한다(표가 붙는 방식은 표가 대신한다)
    """
    if res.mode != "모두" or not res.conds or not res.matched:
        return ""
    top = res.matched[: query.shown_limit(res, plan)]
    word = "마을" if any(" " in n for n in top) else "동"  # 마을 이름은 '사북면 지암리' 꼴
    # 마을은 리 이름만 써도 쓴 것으로 센다('사북면 원평리' → '원평리')
    gone = [
        n
        for n in top
        if not re.search(rf"(?<![가-힣]){re.escape(n.split()[-1] if ' ' in n else n)}", body)
    ]
    n = len(res.matched)
    if not gone:
        # 【판단】 10-27 village_6 c1 T3: '10곳(위 5곳만)'을 글쓴이가 '5곳 모두'로 씀 → 맞는 곳
        #        수가 글에 없으면 한 줄로 알린다
        if n > len(top) and not re.search(rf"(?<![0-9,]){n}\s?곳", body):
            return f"\n\n조건에 모두 맞는 {word}은 모두 {n}곳이에요(위 {len(top)}곳만 보였어요)."
        return ""
    more = f"(위 {len(top)}곳만)" if n > len(top) else ""
    return f"\n\n조건에 모두 맞는 {word} {n}곳{more}: " + " · ".join(top)


@dataclass
class Reply:
    text: str
    kind: str
    topics: tuple[str, ...]
    state: DialogueState
    card: DeskCard
    facts: list[Facts] = field(default_factory=list)
    # 【기능】 동 상황 문서처럼 파일을 만들었으면 그 경로(화면이 내려받기 단추로 보인다)
    files: list[str] = field(default_factory=list)


class Engine:
    def __init__(
        self,
        desk: Desk,
        writer: Writer,
        data: DongData,
        store: Store,
        settings: AssistantSettings,
        doc_writer: dongdoc.DocWriter | None = None,
        planner: query.ClaudePlanner | None = None,
        planner_big: query.ClaudePlanner | None = None,
    ) -> None:
        self.desk = desk
        # 【기능】 10-26 판단 층 · 여러 조건 계산. 넣어 줄 때만 쓴다(단위 시험은 지금 길 그대로)
        self.planner = planner
        self.planner_big = planner_big
        self.writer = writer
        self.data = data
        self.store = store
        # 【판단】 10-27 제목 바꾸기 · 이어서 새 세션이 답을 쓰는 중인 턴과 같은 상태 파일을 고친다
        #        — 턴은 시작에 읽고 끝에 저장하므로, 저장 · 제목 고치기를 이 잠금 안에서 한다
        self._save_lock = threading.Lock()
        self.s = settings
        # 【기능】 챗봇 날씨의 되감기(카드의 AS_OF와 같은 값, 10-19)
        librarian.AS_OF = settings.as_of
        # 【판단】 따로 주지 않으면 키가 있을 때만 Claude 문서 글쓴이(Sonnet 5.5)를 만든다
        # 【10-27 CLI 주석】 … and (settings.anthropic_api_key or cli.backend() == "cli")
        if doc_writer is None and settings.anthropic_api_key:
            doc_writer = dongdoc.ClaudeDocWriter(settings)
        self.doc_writer = doc_writer

    # 【10-27 CLI 주석】 CLI 미리 띄우기(서버가 켜질 때) — API 길에는 띄울 것이 없다
    # def warm(self) -> None:
    #     for part in (self.desk, self.writer):
    #         fn = getattr(part, "warm", None)
    #         if fn is not None:
    #             fn()

    def start(self, session_id: str, profile: Profile | None = None) -> DialogueState:
        st = new_state(profile)
        self.store.save(session_id, st)
        return st

    def carry_over(self, old_id: str, new_id: str, title: str = "") -> DialogueState | None:
        """앞 세션을 이어 새 세션을 연다(10-27 팀장 '새 세션에서 지금의 채팅이 이어진채 시작').

        【판단】 기억(동 · 조건 · 사실 · 앞 답의 숫자)은 그대로 옮기고, 매 턴 데스크에게 그려 주는
               목록(다룬 질문 · 최근 원문)은 줄여서 옮긴다 — 새 세션의 지시문이 짧아져 토큰이 준다.
               되묻던 것은 비운다(새 세션 첫 말은 새 질문). 턴 번호는 이어 쓴다(since)
        """
        with self._save_lock:
            old = self.store.load(old_id)
            if old is None:
                return None
            st = old.model_copy(
                update={
                    "title": title,
                    "first": "",
                    "since": old.turn,
                    "log": old.log[-CARRY_LOG:],
                    "recent": old.recent[-CARRY_RECENT:],
                    "pending": None,
                    "pending_topics": (),
                    "last_question": None,
                    "masked": (),
                }
            )
            self.store.save(new_id, st)
        return st

    def set_title(self, session_id: str, title: str) -> DialogueState | None:
        """세션 제목 바꾸기(빈 글이면 첫 질문으로 돌아간다). 세션이 없으면 None."""
        with self._save_lock:
            st = self.store.load(session_id)
            if st is None:
                return None
            st = st.model_copy(update={"title": title})
            self.store.save(session_id, st)
        return st

    def turn(self, session_id: str, text: str) -> Reply:
        """한 턴 — 답이 다 만들어진 뒤 한 번에 돌려준다(turn_stream 을 끝까지 돈 것과 같다)."""
        for event, value in self.turn_stream(session_id, text):
            if event == "done":
                return value
        raise RuntimeError("turn_stream 이 done 없이 끝났다")

    def turn_stream(
        self, session_id: str, text: str, split: bool = True
    ) -> Iterator[tuple[str, object]]:
        """한 턴을 흘려 보이며 — ("text", 조각) … ("replace", 바꿀 글 전체) … ("done", Reply).

        【판단】 10-12 팀장 "대답이 8초나 걸린다고? 기다리다가 지치겠는데" → 글쓴이가 다 쓸 때까지
               기다리지 않고 문장마다 보인다. 화면은 text 를 이어 붙이고, replace 를 받으면 그 글로
               통째로 바꾼다(검사에 걸려 코드 기본 답으로 바뀐 경우).
               마지막 Reply.text 가 진짜 답이다.
        """
        state = self.store.load(session_id) or new_state()
        text = (text or "").strip()
        if len(text) > MAX_INPUT:
            # 【판단】 데스크를 부르지 않고(값 0), 기억도 바꾸지 않는다. 긴 글을 최근 대화에 남기면
            #        다음 턴마다 다시 보내고, 공문 속 이름 · 주소도 저장소에 남는다
            msg = TOO_LONG.format(n=len(text))
            yield ("text", msg)
            yield ("done", Reply(msg, "too_long", (), state, DeskCard(act="unclear")))
            return
        if not text:
            card = DeskCard(act="unclear")
            plan = Plan("unclear", message="무엇을 볼까요? 동 이름과 알고 싶은 것을 말씀해 주세요.")
            yield ("text", plan.message)
            yield ("done", self._finish(session_id, state, state, card, plan, text, []))
            return
        text, hidden, typed = prepare_input(text)
        if MASK_ASK.search(text):
            card = DeskCard(act="ask", topics=("recall",))
            plan = Plan("recall", topics=("recall",), message=mask_answer(state.masked))
            if hidden:
                plan.message = disclose(DeskCard(), Slots(), hidden) + plan.message
            yield ("text", plan.message)
            yield ("done", self._finish(session_id, state, state, card, plan, text, []))
            return
        # 【판단】 10-27 멘토(팀장 전달): 대기 시간은 '오래 걸립니다'보다 진행 단계를 보여 주면
        #        덜 답답하다 → 걸리는 단계 앞에 ('status', 말)을 낸다(화면은 글이 오기 전까지만
        #        보인다, API · 시험 도구는 모르는 이벤트를 넘긴다). 여러 조건 질문은 가운데 13초
        #        (multi_16 e1)
        yield ("status", "질문을 알아듣는 중")
        # 【판단】 10-29 팀장 '단어 제한은 한계가 있어 … AI도 섞어도 괜찮아, haiku로': 말뜻을
        #        정해야 하는 턴(동 이름을 말하지 않은 자료 질문 등)은 데스크 모델이 보기를 고른다
        #        (policy가 그 턴에만 답을 쓴다 — desk.pick). 지역 전체냐 동 하나냐(SCOPE_ASK)는
        #        데스크와 동시에 물어 기다림이 늘지 않고, 계산 길(_calc)도 그 답을 쓴다(10-29
        #        브라우저 시험 뒤 팀장 '고치고 머지'). 한 번에 약 $0.0001
        desk_pick = getattr(self.desk, "pick", None)
        scope_job = (
            _in_background(desk_pick, state, text, SCOPE_ASK, SCOPE_CHOICES) if desk_pick else None
        )
        card = self.desk.read(state, text)
        after_em = any(
            r.bot.startswith(EMERGENCY) or r.bot == EMERGENCY_AGAIN for r in state.recent[-1:]
        )

        def pick(ask: str, choices: dict[str, str]) -> str | None:
            if scope_job is not None and ask == SCOPE_ASK:
                return scope_job.result()
            return desk_pick(state, text, ask, choices) if desk_pick else None

        card, sanity_note = desk_sanity(card, text, after_em, hidden, pick if desk_pick else None)
        # 【판단】 10-28 페르소나 p07_a T5 '혼자 사는 어르신이 가장 많은 아파트'를 데스크가
        #        못 알아들음으로 내 말을 바꿔 다시 캐게 했다 → 동보다 작은 단위(아파트 · 단지 ·
        #        골목)를 줄 세우거나 찾는 말은 코드가 막기로(동을 묻는 말 · 가까운 곳은 그대로)
        subdong = bool(
            SUBDONG_ASK.search(text)
            and not DONG_LEVEL_ASK.search(text)
            and not APT_NEAR.search(text)
        )
        if subdong:
            card = card.model_copy(update={"act": "blocked", "block": "person", "topics": ()})
        # 개인을 묻는 마디와 동 자료 · 기관을 묻는 마디가 함께면, 개인 마디는 한 줄로 막고 나머지
        # 마디로 이 턴을 다시 한다(policy.PERSON_PART). 급한 일(112)은 그대로 막기 길. 나머지가
        # 우리 자료에 없는 것(고독사 · 신고 건수)이면 막기 답에 '자료에 없다' 한 줄(NO_DATA_LINE)
        # 【판단】 10-29 변수 시험 c01_110 '대치2동 기초수급자 몇 명이에요? 거기 수급자 한 분이
        #        며칠째 연락이 안 돼서 … 일단 숫자부터': 긴급으로 막고 숫자는 '이어서 물어봐 달라'
        #        → 며칠째 연락이 끊긴 걱정(목숨이 걸린 말은 아님)이면 안부 확인 안내 한 줄을 먼저
        #        주고 함께 물은 자료 마디에 답한다. 한 번만 나눈다(split)
        sq = re.sub(r"\s+", "", text)
        lost = card.block == "emergency" and LOST_CONTACT_SQ.search(sq) and not SEVERE_SQ.search(sq)
        person = card.act == "blocked" and card.block == "person" and not card.urgent
        rest = person_free_rest(text) if split and (person or lost) else ""
        if rest and not NO_DATA_ASK.search(rest):
            lead = PERSON_PART if person else URGENT_NOTE + "\n\n"
            yield ("text", lead)
            for kind, value in self.turn_stream(session_id, rest, split=False):
                if kind == "replace":
                    value = lead + str(value)
                elif kind == "done" and isinstance(value, Reply):
                    value.text = lead + value.text
                yield (kind, value)
            return
        # 【판단】 10-28 페르소나 p01_c r2 T2: '22개 동 … 많은 순으로 표'에 데스크가 줄 세우기를
        #        켜지 않아 '어느 동?'을 묻거나 동 순서 표를 '많은 순'이라 했다 → 표 요청에 순서 ·
        #        지역 전체 말이 있고 동을 말하지 않았으면 코드가 줄 세우기를 켠다
        if (
            card.act == "ask"
            and not card.rank
            and not card.dong_mentions
            and CHAT_TABLE.search(text)
            and ORDER_OR_ALL.search(text)
        ):
            card = card.model_copy(update={"rank": True})
        # 【판단】 10-20 페르소나 o01 r4 T5: '아까 300명이라고 하셨지요? 보고서에 적어도
        #        되겠습니까'를
        #        데스크가 되짚기로 내 대화 요약이 나갔다. 숫자 · '써도 되나'가 든 말은 자료 질문이다
        if "recall" in card.topics and RECALL_NOT.search(text):
            prev = tuple(t for t in state.topics if t in BY_ID and t != "recall")
            card = card.model_copy(update={"act": "ask", "topics": prev or ("solo_seniors",)})
        # 【판단】 10-27 밤 창 시험 T22 '처음에 물어본 세 동 … 숫자 다시 알려줘': 최근 원문 창
        #        밖으로 밀린 첫 동들을 데스크가 잘못 골랐다(6턴에서 두 번 다 수서동을 빼고
        #        세곡동부터)
        #        → '처음 물어본 N 동'이면 코드가 다룬 질문 목록(먼저 본 순)에서 꺼낸다
        first_n = FIRST_DONGS.search(text)
        seen = list(dict.fromkeys(d for e in state.log for d in e.dongs))
        if first_n and card.act in ("ask", "unclear"):
            n = COUNT_WORD.get(first_n.group(1)) or int(first_n.group(1))
            if len(seen) >= n:
                prev = tuple(t for t in state.topics if t in BY_ID and t != "recall")
                topics = tuple(t for t in card.topics if t != "recall") or prev
                card = card.model_copy(
                    update={
                        "act": "ask",
                        "topics": topics or ("solo_seniors",),
                        "dong_op": "set",
                        "dong_mentions": tuple(seen[:n]),
                    }
                )
        # 【판단】 10-20 페르소나 f02 r4 T8: '춘천시 취약 돌보미 동 순위 1위 동의 독거 수'에 '어느
        #        동을
        #        볼까요?'. '1위 동'은 코드가 순위에서 꺼낸다
        # 【판단】 10-29 회귀 long_100 T18 '3위 동은 상황이 어때요?'(앞 턴 먼저 볼 동): 1위만 꺼내서
        #        3위는 데스크에 맡겨졌고, 데스크가 앞 동을 남기자 '논현2동 세부 자료는 없다'(거짓,
        #        10-28 f판에서도 같음) → N위도 꺼낸다. 앞 턴이 여러 조건 계산이면 그 결과의 N번째,
        #        '순위 · 먼저 볼'을 말했거나 앞 턴이 동 순위면 동 순위의 N위(1위는 예전처럼 늘)
        top = TOP_RANK.search(text)
        if card.act == "ask" and top and not card.dong_mentions:
            nth = int(top.group(1) or top.group(2))
            region = (
                (card.region if card.region_op == "set" and card.region else None)
                or state.slots.region
                or state.profile.member_region
                or "강남구"
            )
            # 10-20 페르소나 f02 r11 T5 ~ T10: '강남 1위 개포3동이랑 춘천 1위 동을 나란히'에 지금
            #        지역 하나만 꺼내 '춘천 1위는 자료에 없다' → 견줌이면 두 지역 1위를 다 꺼낸다
            both = card.compare or bool(BOTH_REGIONS.search(text))
            regions = ["강남구", "춘천시"] if both else [region]
            # 【판단】 10-29 변수 시험 c01_028 · c01_102: '65세 이상 1인세대 3위 · 그 순위 3위'를
            #        취약 돌보미 순위 3위(논현2동)로 잡았다 — 사용자는 바로 앞 답에서 본 순위를
            #        가리킨다 → 순위 이름을 분명히 말하지 않았으면 앞 답의 'N위 ○○동'이 먼저
            explicit = PRIORITY_RANK_WORD.search(text)
            seen = {} if explicit else ranks_in(state.last_answer)
            after_calc = state.calc_turn == state.turn and state.last_calc and not explicit
            by_rank = nth == 1 or explicit or "priority" in state.topics
            firsts: list[tuple[str, str]] = []
            # 【판단】 10-29 변수 시험 c01_077 '춘천시 고립 어르신 순위에서 2위 동': 지표를 말한
            #        순위면 그 지표로 줄 세운 N번째(말한 지역에서) — 회원 담당 동으로 답했다
            metric = next((TOPIC_METRIC[t] for t in card.topics if t in TOPIC_METRIC), None)
            said_region = next((r for r, p in REGION_WORDS_IN_TEXT if p.search(text)), region)
            by_metric = bool(metric and METRIC_RANK.search(text) and not explicit)
            if nth in seen:
                firsts = [(dongname.region_of(seen[nth]) or region, seen[nth])]
            elif after_calc:
                calc_n = state.last_calc[nth - 1 : nth]
                firsts = [(state.calc_region or region, d) for d in calc_n]
            elif by_metric:
                try:
                    order = query.run(
                        query.Plan(region=said_region, sort=query.Ref(metric=metric), limit=25),
                        self.data,
                    ).matched
                except Exception:  # noqa: BLE001 — 그 지역에 없는 지표면 넘어간다
                    order = []
                # 10-29 변수 시험 c01_038 '춘천 읍면 중에 고립 어르신 많은 순위 3위 동네': 읍 · 면만
                if TOWN_ONLY.search(text):
                    order = [d for d in order if d.endswith(("읍", "면"))]
                if len(order) >= nth:
                    firsts = [(said_region, order[nth - 1])]
            elif by_rank:
                firsts = [
                    (r, self.data.ranked(r)[nth - 1][1])
                    for r in regions
                    if len(self.data.ranked(r)) >= nth
                ]
            if firsts and not dongs_in_text(text):
                card = card.model_copy(
                    update={
                        "dong_op": "set",
                        "dong_mentions": tuple(f for _, f in firsts),
                        "rank": False,
                        "compare": card.compare or len(firsts) > 1,
                    }
                )
                said = " · ".join(
                    f"앞 답의 {nth}위는 {f}"
                    if nth in seen
                    else f"앞 계산 결과 {nth}번째는 {f}"
                    if after_calc
                    else f"{r} {METRIC_NAME.get(metric or '', '')} 많은 순 {nth}위는 {f}"
                    if by_metric
                    else f"{r} 취약 돌보미 동 순위 {nth}위는 {f}"
                    for r, f in firsts
                )
                # 【정함 10-27 팀장】 묻는 것만 — '1위가 어디예요?'처럼 1위를 묻는 말이면
                #        글쓴이 첫 문장이 같은 말이다(qbank 2-2b T1: 머리말과 첫 문장이
                #        같은 말 두 번). 1위 동의 다른 것을 물을 때만('1위 동의 독거 수')
                #        머리말로 알린다
                if not TOP_WHERE.search(text):
                    sanity_note += f"({said}이에요. 그 동으로 볼게요.)\n"
        applied = apply_card(state, card, text)
        plan = preflight(applied, card, self.data)
        # 10-29 변수 시험 c01_025: 두 지역 이름을 다 말한 줄 세우기는 '어느 지역?'을 되묻지 않고
        #       지역마다 줄 세운다(librarian._gather_all)
        if (
            plan.kind == "ask_slot"
            and plan.pending == "region"
            and applied.state.slots.rank
            and BOTH_REGIONS.search(text)
        ):
            plan = Plan("answer", topics=plan.topics)
        # 【판단】 10-26 판단 층: 동이 없어 '어느 동?'을 되물을 말이라도 계산 길이면 되묻지 않는다
        #        (지역 전체 · 앞 계산의 동들 안에서 거른다 — '그 중에 약국 10곳 넘는 데는?')
        if (
            plan.kind == "ask_slot"
            and plan.pending == "dong"
            and self.planner is not None
            and (dec := self._decide(state, card, text)).route == "깊은 고민"
        ):
            sig = dec.sig
            # 【판단】 10-28 재심사 p06_b '강남구 독거노인 고독사 위험군이 전체 몇 명':
            #        데스크만 계산이라 보고(계산 낱말 · 두 번째 지표 · 앞 결과를 가리키는 말 없음)
            #        되묻기를 건너뛰었는데 계획기가 계산이 아니라고 봐 동 없이 서가로 갔다 →
            #        자료 0줄에 빈 답 · 영어 답 · '자료에 없다'(거짓). 이런 말은 줄 세울 수 있는
            #        주제면 지역 전체(합계 · 위 몇 곳)로, 아니면 그대로 동을 되묻는다
            lone = len(sig.concepts) <= 1 and not (
                sig.calc or sig.refer or sig.subset or sig.carried or sig.items
            )
            if not lone:
                plan = Plan("answer", topics=plan.topics)
            elif any(t in RANKABLE for t in plan.topics) and applied.state.slots.region:
                plan = Plan("answer", topics=plan.topics)
                slots = applied.state.slots.model_copy(update={"rank": True})
                applied.state = applied.state.model_copy(update={"slots": slots})
        # 【정함 10-27 팀장】 '보고서 문장 좀 다듬어 줘'는 두 뜻(써 둔 글 고치기 · 우리 자료로
        #        보고 문장 만들기)이라 되묻는다. 우리는 동 자료로 보고용 문장 · 상황 문서를 만들지만
        #        써 둔 글을 고치는 기능은 없다(desk_new_21 O03: 데스크가 '쓰는 법'으로 봄, 3/3).
        #        글을 붙여 넣었으면(길면) 고치지 못한다고 밝히고 만들 수 있는 것을 알린다
        if POLISH.search(text) and not dongs_in_text(text):
            here = "효자2동" if applied.state.slots.region == "춘천시" else "개포3동"
            can = (
                "우리 자료로 보고 문장을 만들어 드릴 수는 있어요"
                f"(예: '{here} 상황을 보고용 한 줄로' · "
                f"'{here} 상황 문서')."
            )
            if len(text) > POLISH_PASTED:
                plan = Plan("out_of_scope", message=POLISH_NO + " " + can)
            else:
                plan = Plan("unclear", message=can + " 어느 동으로 만들까요? " + POLISH_NO)
        # 【판단】 10-20 페르소나 8명 r8: '고마워 끊을게' · '수고하셨습니다'에 '편하게 물어봐
        #        주세요. 예를 들어 …'가 나갔다(다섯 명). 마무리 인사에는 마무리로 답한다
        # 【판단】 10-20 페르소나 o02 r8: 연락이 끊긴 어르신을 찾아 달라는 말에 같은 막기 문장만
        #        세 번 나갔고, 급한 사정에 바로 할 일(주민센터 · 112)을 먼저 말하지 않았다
        if plan.kind == "blocked" and plan.message.startswith(PERSON):
            if (card.urgent or URGENT.search(text)) and URGENT_NOTE not in plan.message:
                plan.message = plan.message.rstrip() + " " + URGENT_NOTE
            # 앞 막기 답에는 가림 알림이 앞에 붙었을 수 있어 '들어 있나'로 본다
            if any(SAID_BEFORE in r.bot for r in state.recent[-3:]):
                # 10-20 페르소나 o02 r7: 같은 거절을 서너 번 — 세 번째부터는 할 수 있는 일을 번호로
                dongs = applied.state.slots.dongs
                where = f"{dongs[0]} " if dongs else ""
                plan.message = SAME_ANSWER + (
                    "지금 바로 할 수 있는 일은 ① 112에 아는 것만으로 신고 "
                    f"② {where}주민센터에 안부 확인 요청 ③ {where}복지관 · 경로당에 전화예요. "
                    "연락처가 필요하시면 '지원 기관'이라고 말씀해 주세요."
                )
            elif any(PERSON in r.bot for r in state.recent[-3:]):
                # 10-20 페르소나 o02 r3: '앞에서 말씀드린 것처럼 …'만 되풀이
                #        → 대신 할 수 있는 것을 붙인다
                dongs = applied.state.slots.dongs
                can = CAN_INSTEAD.format(where=dongs[0]) if dongs else CAN_INSTEAD_NO_DONG
                urgent = " " + URGENT_NOTE if (card.urgent or URGENT.search(text)) else ""
                plan.message = SAID_BEFORE + can + urgent
        # 10-20 페르소나 o02 r11 T8 ~ T9: 막힌 말 속에 '수서동 전체 고독사 신고 몇 건' 같은 동 단위
        #        물음이 섞여 있었는데 같은 막기 문장만 → 그 자료는 없다고 한 줄 덧붙인다
        if plan.kind == "blocked" and NO_DATA_ASK.search(text) and NO_DATA_LINE not in plan.message:
            plan.message = plan.message.rstrip() + " " + NO_DATA_LINE
        if (
            plan.kind == "blocked"
            and (apt := APT_NEAR.search(text))
            and "위치는 취약 돌보미 자료에 없어" not in plan.message
        ):
            where = f"{applied.state.slots.dongs[0]} " if applied.state.slots.dongs else ""
            plan.message = (
                plan.message.rstrip()
                + f" '{apt.group(1)}' 위치는 취약 돌보미 자료에 없어 거기서 가까운 경로당 · 복지관을 "  # noqa: E501
                + "잴 수 없어요. "
                + f"{where}경로당 · 복지관 주소와 연락처는 '갈 곳'이라고 말씀하시면 드려요."
            )
        # 10-28 재심사 C3 p07_a · p10_c: 막기 답에 코드가 붙인 안내(주민센터 · 112 · 동 전체 수)는
        #        출처가 있는 문장인데 그 턴 자료 줄이 비어 심사관이 '지어냈다'고 봤다 →
        #        자료 줄로도 남긴다
        #        (화면의 '이 답의 자료'에도 보인다)
        code_lines: list[str] = []
        # 10-28 밤 브라우저 시험 '옆집 할머니가 사흘째 전화를 안 받으세요 … 뭐부터 해야 하죠?'에
        #        위급 틀 문장만(119 · 112) — 연락이 끊긴 걱정이면 112 안전 확인을 늘 함께
        if (
            plan.kind == "blocked"
            and (POLICE_Q.search(text) or URGENT.search(text))
            and "안전 확인(집 방문)" not in plan.message
        ):
            plan.message = plan.message.rstrip() + " " + POLICE_LINE
            code_lines.append(POLICE_LINE)
        # 10-28 재심사 p07_a T7 '개포3동 아파트 중 혼자 사시는 어르신이 제일 많은 단지': 앞 턴이
        #        개인 막기라 '한 분 한 분의 정보는 …'(물음과 안 맞는 거절)이 나갔다(고치기 전에는
        #        '단지별 자료는 없어요. 개포3동 전체로는 1,262명') → 단지 물음은 단지 자료가 없다고
        #        하고 동 전체로
        if subdong and plan.kind == "blocked":
            named = list(applied.state.slots.dongs) or dongs_in_text(text)
            total = self._dong_total(named[0]) if named else ""
            plan.message = SUBDONG_NOTE + total
            # 10-28 재심사 C1 p07_a T4: 코드가 쓴 동 전체 수인데 그 턴 자료 줄이 비어 심사관이
            #        '근거 없는 숫자'로 봤다 → 그 문장을 자료 줄로도 남긴다(화면의 '이 답의 자료')
            if total:
                code_lines.append(total.strip())
        # 10-28 재심사 q06_b(서울 사는 딸 '엄마가 이틀째 전화를 안 받아요 … 춘천 사북면'): 동을
        #        말했는데 막기 답이 두 번이나 '동 이름을 말씀해 주시면'이었고 주민센터 번호는 셋째
        #        턴에야 나왔다 → 연락이 끊긴 걱정이면 말한 동의 주민센터를 막기 답에 바로 붙인다
        if (
            plan.kind == "blocked"
            and plan.message.startswith(
                (PERSON, SAID_BEFORE, SAME_ANSWER, EMERGENCY, EMERGENCY_AGAIN[:12])
            )
            and (card.urgent or URGENT.search(text))
            and (named := list(applied.state.slots.dongs) or dongs_in_text(text))
            and (office := self._office_for(named[0]))
            and office not in plan.message
        ):
            plan.message = (
                plan.message.replace(CAN_INSTEAD_NO_DONG, "").rstrip()
                + f" 안부 확인을 요청할 곳: {office.split(': ', 1)[-1]}."
            )
            code_lines.append(office)
        # 【판단】 10-25 페르소나 cli1 레아나 T6 ~ T9: 막을 말(개인 연락처 · 단지) 사이에 답할
        #        수 있는 곁물음('1566-3232에 전화하면 어떻게 돼요' · '112에 뭐라고 말해요' ·
        #        '기관 회원은 명단을 볼 수 있나요' · '가족이면 되나요')이 섞였는데 같은 막기 문장만
        #        나갔다 → 곁물음의 답을
        #        앞에 붙이고, '같은 답을 드릴 수밖에 없어요'는 부드럽게
        if plan.kind == "blocked" and (side := side_answers(text, self.data)):
            body = plan.message
            if body.startswith(SAME_ANSWER):
                body = "다만 한 분 한 분의 정보는 찾아 드릴 수 없어요. " + body[len(SAME_ANSWER) :]
            plan.message = " ".join(side) + "\n\n" + body
            code_lines += side
        doc_q = False
        if (
            plan.kind == "answer"
            and "dong_doc" in plan.topics
            and DOC_QUESTION.search(text)
            and any(DOC_MADE in r.bot for r in state.recent[-4:])
        ):
            plan.topics = tuple(t for t in plan.topics if t != "dong_doc") or (
                "diagnosis",
                "sources",
            )
            doc_q = True
        # 【판단】 10-28 페르소나 p02_c T2 · T3 '사람이세요, 기계인가요?'에 AI라고 밝히지 않고
        #        '네, 편하게 물어봐 주세요' — 공공 챗봇은 사람이 아님을 밝혀야 한다(투명성)
        if AI_ASK.search(text) and plan.kind in ("chitchat", "unclear", "out_of_scope"):
            plan.kind, plan.topics, plan.message = "chitchat", (), AI_SELF
        if plan.kind == "chitchat" and (card.farewell or BYE.search(text)) and "?" not in text:
            kept = f"기억해 둘게요({' · '.join(card.new_facts[:2])}). " if card.new_facts else ""
            plan.message = f"네, {kept}필요하실 때 또 물어봐 주세요."
        st = applied.state
        facts: list[Facts] = (
            [Facts(title="막기 답에 붙인 안내(코드)", lines=code_lines)]
            if code_lines and plan.kind == "blocked"
            else []
        )
        if self._table_edit_ok(state, st, card, plan, text):
            yield from self._table_edit_turn(session_id, state, st, card, plan, text)
            return
        if plan.kind == "settings":
            st, plan.message = self._settings(st, card, text)
        elif (
            plan.kind == "recall"
            and SUMMARY_ASK.search(text)
            # r11 100턴 T89 '아까 물어본 동들 정리해 줘'는 본 동 목록(되짚기) — 요약이 아니다
            and (not _ASK_DONGS.search(text) or _WITH_NUM.search(text))
            and (state.last_facts or state.older_facts or state.said_facts)
        ):
            yield from self._summary_turn(session_id, state, card, plan, text)
            return
        elif plan.kind == "recall":
            # 【판단】 되짚기는 칸을 바꾸지 않는다('춘천은?'으로 좁혀도 지금 지역 · 동은 그대로)
            st = state
            region = card.region if card.region_op == "set" else None
            plan.message = self._recall(st, region, text)
        elif plan.kind == "answer" and "dong_doc" in plan.topics:
            yield from self._doc_turn(session_id, state, st, card, plan, text)
            return
        elif plan.kind == "answer":
            # 【판단】 표 파일을 달라면 파일을 만들고 머리말로 알린 뒤, 같은 말 속 다른 질문에도
            #        보통 답을 이어 쓴다(10-15 페르소나 q05: 표만 주고 묻는 말에 답하지 않음)
            files: list[str] = []
            table_note = ""
            sheet_facts: Facts | None = None
            if st.slots.fmt == "엑셀" and self._calc_sheet_ok(state, text):
                # 10-28 p09_c: 앞 턴이 여러 조건 계산이면 '엑셀로'는 그 계산 표(후보 동 모두)
                files, table_note = self._save_calc_sheet(state)
                sheet_facts = self._calc_sheet_facts(state)
            elif st.slots.fmt == "엑셀" and any(t in table.COLS for t in plan.topics):
                files, table_note = self._make_table(st, plan, text)
            if self._calc_likely(state, st, card, plan, text):
                yield ("status", "여러 조건을 묶어 계산 방법을 짜는 중")
            scope = scope_job.result() if scope_job is not None else None
            calc = self._calc(state, st, card, plan, text, scope)
            yield (
                "status",
                f"자료 {len(calc[1].refs) or 1}가지로 계산했어요 · 답을 쓰는 중"
                if calc is not None
                else "자료를 찾아 답을 쓰는 중",
            )
            if calc is not None:
                cf, cres, cplan = calc
                # 계산이 다루지 않는 주제(전화번호 · 버스 · 출처 따위)는 서가에서 같이 꺼낸다
                # 【판단】 동 셋까지를 묻는 계산이면 그 동의 서가 자료를 늘 같이 준다. 계산은
                #        고른 지표의 줄 세우기 · 견줌만 해서, 같은 말에 함께 물은 것(1년 변화 ·
                #        어떤 진단 신호 · 갈 곳 이름)이 빠지면 글쓴이가 '자료에 없다'(거짓)고
                #        썼다 — 10-26 예상 질문 1-5(진단 신호), 10-29 브라우저 시험 '거기는 춘천
                #        평균보다 몇 배? 그리고 1년 전보다는?'(퇴계동 수급자 2023년 값이 있는데
                #        '1년 전 자료가 없다')
                few = 0 < len(st.slots.dongs) <= 3
                keep = tuple(
                    dict.fromkeys(
                        t
                        for t in [*plan.topics, *(metric_topics(cres.refs) if few else [])]
                        if t not in CALC_TOPICS
                        or (t == "places" and PLACE_DETAIL.search(text))
                        or few
                    )
                )
                more = dedupe_facts(gather_all(keep, st.slots, self.data, text)) if keep else []
                facts = [cf] + more
                # 앞 결과: 조건으로 거른 것이면 맞은 동 모두(차례대로, 25곳까지 — '그 중에'는 보인
                # 5곳이 아니라 맞은 동 전체), 줄 세우기만이면 보인 동('세 곳' 그 중에)
                n = 25 if (cres.conds and cres.mode == "모두") else query.shown_limit(cres, cplan)
                sheet = query.sheet(cres) if cres.candidates else ()
                st = st.model_copy(
                    update={
                        "last_calc": tuple(cres.matched[:n]),
                        "last_calc_conds": tuple(s for _, s in cres.conds)[:8],
                        "calc_sheet": sheet,
                        "calc_turn": state.turn + 1,
                        "calc_region": cres.region,
                        "calc_rules": tuple(s for _, s in cres.conds)[:8],
                        "calc_log": (st.calc_log + calc_log_entry(state.turn + 1, cres))[-4:],
                    }
                )
                # 10-28 p09_c: 이번 턴에 엑셀을 달라면 이 계산의 전체 표로 파일을 만든다
                if st.slots.fmt == "엑셀" and len(sheet) > 1:
                    files, table_note = self._save_calc_sheet(st, now=True)
            elif sheet_facts is not None:
                # 10-28 p09_c: 앞 계산 표로 엑셀을 만든 턴 — 글쓴이도 그 표만 본다(보통 서가 자료를
                #        주면 앞 계산과 어긋나는 말(여성 구분 없음 · 반지하 없음)과 다른 표를 썼다)
                facts = [sheet_facts]
            else:
                facts = dedupe_facts(gather_all(plan.topics, st.slots, self.data, text))
                st = st.model_copy(update={"last_calc": ()})
            # 【판단】 10-26 페르소나 c01 · c04: 사용자가 적은 셈('2,543 + 1,285 + 1,262 = ?')은
            #        코드가 계산해 건넨다(글쓴이는 셈하지 않으므로 '자료에 합계가 없다'고만 했다)
            if sums := arith.lines(text):
                facts.insert(0, Facts(title="사용자가 적은 셈", lines=sums, notes=[ARITH_NOTE]))
            if cmp := arith.pasted(text, self.data, st.slots.region):
                facts.insert(0, Facts(title="붙여 넣은 숫자 대조", lines=cmp, notes=[PASTED_NOTE]))
            if doc_q and (df := doc_facts(state.recent, state.last_facts + state.older_facts)):
                df.notes.append(DOC_DOWNLOAD_NOTE)
                facts.insert(0, df)
            # 10-27 밤 페르소나 s01 T2: '왜 겹친 걱정은 없다고 하나요?'를 순위 주제로 받아 판단 기준
            #        줄이 없자 '겹친 걱정으로 본 기준은 자료에 없다' → 그 말을 물으면 기준 줄을 함께
            if (
                facts
                and OVERLAP_WORD.search(text)
                and not any(C.OVERLAP_RULE in x for f in facts for x in f.lines + f.notes)
            ):
                facts.append(Facts(title="취약 돌보미 판단의 뜻", lines=[C.RULE_LINE]))
            if facts and VISIT_ORDER.search(text) and (vf := self._visit_facts(st)):
                facts.append(vf)
            if facts and RISK_GROUP.search(text) and RISK_GROUP_NOTE not in facts[0].notes:
                facts[0].notes.append(RISK_GROUP_NOTE)
            # 10-28 재심사 q05_a: 뒤 계산(1,000명당)이 앞 계산 기준(경로당 곳수)을 덮어써
            #        '처음 고른 곳은 어떤 기준?'에 뒤 기준으로 답했다 → 앞 계산을 가리키면
            #        이 세션의 계산 기록을 함께
            if facts and st.calc_log and (len(st.calc_log) >= 2 or PAST_CALC.search(text)):
                log = Facts(title="이 대화의 계산 기록", lines=list(st.calc_log))
                log.notes.append(CALC_LOG_NOTE)
                facts.append(log)
            # 10-20 페르소나 h01 r8: '짧게'를 네 번 말했는데 그 턴에만 짧고 다음 턴은 다시 길었다
            #        → 앞 세 턴 안에 짧게 달라는 말이 있었으면 이번에도 짧게
            from src.assistant.librarian import HOLIDAY_ASK, calendar_facts
            from src.assistant.writer import BRIEF, BRIEF_NOTE, BRIEF_PREV

            if facts and card.brief and not BRIEF.search(text):
                # 10-21 말의 꼴: 데스크가 '짧게'라고 판정했으면(어떤 말투든) 정규식과 같게
                facts[0].brief = True
                facts[0].notes.append(BRIEF_NOTE)
            if facts and any(BRIEF_PREV.search(r.user) for r in state.recent[-3:]):
                facts[0].brief = True
                if not BRIEF.search(text):
                    facts[0].notes.append(BRIEF_NOTE + "(앞 턴에서 짧게 달라고 했음)")
            # 10-27 밤 페르소나 h01: 판단 답마다 '근거 보여 줘' 안내가 붙었다 → 세션에서 한 번만
            if facts and state.tail_shown:
                for f in facts:
                    f.tail_shown = True
            # 10-20 페르소나 f01 r9: 청년 주제에서 '다음 긴 연휴가 언제'를 세 번 물어야 답이 나옴
            if HOLIDAY_ASK.search(text):
                cal = calendar_facts(self.data)
                cal.notes.append("연휴 날짜를 물었으면 위 달력 줄의 날짜를 그대로 적는다")
                # 【판단】 10-25 페르소나 cli1 세라핀 T4 ~ T5: 연휴를 물을 때마다 '먼저 살필
                #        무리는 혼자
                #        사는 청년 3,638명'이 붙어 1인 청년 전체를 위험군처럼 불렀다(1인세대는 세대
                #        구성일 뿐). 누구부터 볼지 물었을 때만 취약 돌보미 판단의 조건으로 한 줄
                #        붙인다
                if WHO_FIRST.search(text):
                    cal.notes.append(
                        "연휴 전에 누구 · 어디부터 볼지 물었으면 취약 돌보미 판단에 해당한 조건을 "
                        "한 줄로 붙인다. 1인세대 수 전체를 '먼저 살필 무리' · 위험군처럼 부르지 "
                        "않는다(1인세대는 세대 "
                        "구성일 뿐 고립을 뜻하지 않는다)"
                    )
                else:
                    cal.notes.append(
                        "누구부터 볼지는 묻지 않았다 — '먼저 살필 무리'나 대상 인원을 붙이지 않는다"
                    )
                facts.append(cal)
            # 10-20 페르소나 h01 r9 T6 ~ T8: '천전1리 어때'에 '마을 자료 없음', 다음 턴엔 '버스가
            #        드문 마을' — 마을에 대해 있는 자료가 무엇인지 사서가 밝힌다
            if applied.villages and facts:
                names = " · ".join(v for v, _ in applied.villages)
                facts[0].notes.append(
                    f"{names}은(는) 마을이라 마을 단위 자료는 가장 가까운 정류장 · 거리 · 잦은 노선"
                    "(버스 주제) · 마을별 집(읍면 집 주제) · 마을에서 요일별 문 연 약국 · 의원 · "
                    "공공기관까지 거리(약국 주제, 10-27)이고 나머지는 읍면 전체 값이다. "
                    "'마을 자료가 없다'고 뭉뚱그리지 않고 무엇이 있고 없는지 적는다"
                )
            # 【판단】 10-26 페르소나 c01: 계산 길 답에 묻지 않은 22곳 일반 표가 또 붙었다
            #        → 계산 길이면 계산이 만든 표만(엑셀 파일을 달라고 했으면 그대로 만든다)
            # 10-28 재심사 q05_a T2: 앞 계산 표로 엑셀을 만든 턴에 일반 동 표(순위 열이 있음)까지
            #        붙어, 글쓴이가 '파일에 각 순위 열이 있어요'(파일에는 없음)라고 썼다 → 그 턴은
            #        계산 표만
            tf = (
                None
                if (calc is not None and not files) or sheet_facts is not None
                else self._table_facts(st, plan, text, bool(files), files)
            )
            if tf:
                facts.append(tf)
            head = typed_note(typed) + sanity_note + not_connected_note(st.topics) + plan.note
            head += out_of_area_note(text) + table_note
            if DECIDE_ASK.search(text) and facts:
                head += DECIDE_HEAD
                facts[0].notes.append(DECIDE_NOTE)
            if facts:
                pool = "\n".join(x for f in facts for x in f.lines)
                facts[0].notes += checks.claim_notes(text, pool, st.slots.dongs)
            # 때 알림은 앞 턴과 같은 때면 다시 붙이지 않는다(10-20 페르소나 f01 r8: 네 번 되풀이)
            same_period = bool(state.slots.period) and state.slots.period == st.slots.period
            # 【판단】 10-26 calc_flow_8 T6: 계산 길이 '약국 없는'을 조건으로 셌는데도 데스크의
            #        '나눠 볼 수 없어서 빼고' 알림이 앞에 붙었다 → 계산 길이면 계산 줄이 스스로
            #        밝힌다
            shown = card.model_copy(update={"unmet": ()}) if calc is not None else card
            # 【판단】 10-29 회귀 rules_v6_16 T3: 데스크가 주제를 혼자 사는 어르신만 적었는데 계산은
            #        기초생활수급자 지표를 써서, 그 자료에 늘 붙는 밝힘(춘천 수급자는 나이 · 혼자로
            #        못 나눔)이 빠졌다 → 밝힘은 데스크가 적은 주제에 더해 계산이 실제로 쓴 지표의
            #        주제로도 본다(지표 키가 주제 이름이거나 '주제_…')
            note_topics = plan.topics
            if calc is not None:
                note_topics = tuple(dict.fromkeys([*plan.topics, *metric_topics(calc[1].refs)]))
            head += disclose(shown, st.slots, hidden, note_topics, repeat_period=same_period)
            # 【판단】 시설 주제(경로당 · 갈 곳 등)는 나이와 상관없어 밝히지 않는다
            if applied.standing_used and not set(plan.topics) <= FACILITY_TOPICS:
                said = " · ".join(applied.standing_used)
                head += (
                    f"(앞으로 {said}만 보기로 하셔서 그 기준으로 봤어요. "
                    "바꾸시려면 말씀해 주세요.)\n"
                )
            # 【판단】 10-20 엔진 시도 '수서동 3단지 어르신들 괜찮아?': 단지 · 통 · 반은 자료가 없어
            #        동 전체로 답하면서 밝히지 않았다
            sub = SUB_DONG.search(text)
            # 10-20 페르소나 o01 r10: '저는 통·반을 묻지 않았으니 그 안내는 필요 없다'는 말에도
            #        '통·반'이 들어 있어 같은 알림이 일곱 번
            #        → 묻지 않았다는 말 · 앞 턴에 보인 알림은 뺌
            shown = state.recent[-1].bot if state.recent else ""
            if (
                sub
                and st.slots.dongs
                and not NOT_ASKING.search(text)
                and "동보다 작은 단위는 자료가 없어" not in shown
            ):
                apt = APT_NEAR.search(text)
                if apt:
                    # 10-20 페르소나 o02 r12 T6 ~ T8: '신동아아파트에서 제일 가까운 경로당'
                    head += (
                        f"('{apt.group(1)}' 위치는 취약 돌보미 자료에 없어 "
                        "거기서 가까운 곳은 잴 수 없어요. "
                        f"{', '.join(st.slots.dongs[:3])} 전체 목록으로 보여 드려요.)\n"
                    )
                else:
                    head += (
                        f"('{sub.group(0).strip()}'처럼 동보다 작은 단위는 자료가 없어 "
                        f"{', '.join(st.slots.dongs[:3])} 전체로 봤어요.)\n"
                    )
            for said, dong in applied.villages:
                head += f"({josa(said, '은', '는')} {dong}의 마을이라 {dong}으로 볼게요.)\n"
            for old, new in applied.renamed:
                head += f"({old}은(는) 지금 {new}이에요. {new}으로 볼게요.)\n"
            if applied.guessed:
                heard = ", ".join(
                    f"'{said}'을(를) '{dong}'(으)로" for said, dong in applied.guessed
                )
                head += f"({heard} 알아들었어요. 아니면 말씀해 주세요.)\n"
            if head:
                yield ("text", head)
            question = restate_or_text(
                card.restate, text, st.slots.region, st.slots.compare, st.slots.dongs
            )
            # 10-29 변수 시험 c01_073 '일원2동 약국은?': 옛 이름 · 오타를 코드가 개포3동으로 잡고도
            #       글쓴이에게는 그 말 그대로 가 '일원2동은 자료에 없다'고 썼다 → 고친 이름으로 준다
            olds = [(o, n[1]) for o, n in dongname.OLD_NAMES.items()]
            for said, word in [*typed, *applied.guessed, *olds]:
                if said in question and word in st.slots.dongs:
                    question = question.replace(said, f"{word}(사용자 말 '{said}')")
            stream = getattr(self.writer, "write_stream", None)
            before = state.last_answer
            carry = carry_facts(
                text,
                before,
                state.last_facts,
                facts,
                state.older_facts,
                " ".join(t.bot for t in state.recent),
                state.said_facts,
            )
            # 10-28 p09 k3: 앞 계산 표로 엑셀을 만든 턴에 앞 턴 자료까지 주면 표에 없는 열(2025-09
            #        1인세대 · 수급 2024)을 '들어 있다'고 썼다 → 그 턴은 계산 표만
            if sheet_facts is not None:
                carry = None
            wfacts = facts + [carry] if carry else facts
            # 【판단】 10-26 팀장 '억지로 막지 말고 필요 없는 것만': 너무 크면 덜어 낸다(budget)
            wfacts, _ = budget.fit(wfacts, (question, text, before, WRITER_HEAD), CARRY_TITLE)
            if sheet_facts is not None and EXCEL_ONLY.fullmatch(text.strip()):
                # 10-28 p09 m3: '엑셀로 주세요'만인데 글쓴이가 표로 새 결론('앞 답에서 논현1동을
                #        빠뜨렸어요')을 지어냈다 → 파일만 달라는 말이면 코드가 한 문장으로
                body = self._calc_sheet_sentence(state)
                yield ("text", body)
            elif stream is None:
                body = self.writer.write(question, wfacts, said=text, before=before)
                yield ("text", body)
            else:
                body = ""
                for event, chunk in stream(question, wfacts, said=text, before=before):
                    body = chunk if event == "replace" else body + chunk
                    yield (event, head + chunk if event == "replace" else chunk)
                body = self.writer.last.text if getattr(self.writer, "last", None) else body
            # 10-28 재심사 p06_b: 자료가 0줄이라 글쓴이 답이 비면(검사에 두 번 걸리면 고른 줄도
            #        없음) 빈 말풍선이 나갔다 → 코드가 한 문장
            if not body.strip():
                body = EMPTY_ANSWER
                yield ("text", body)
            # 10-21: 채팅에 표를 달라면 코드가 그린 표를 글 아래에 붙인다(글쓴이는 한두 문장만)
            # 파일(엑셀)을 같이 만들어도 채팅에 표를 달라면 붙인다(r15 노엘 T3 '표가 답변에 안 보여요')  # noqa: E501
            if tf is not None and CHAT_TABLE.search(text):
                t_region, t_dongs, tbl = self._table_rows(st, plan, text)
                if tbl.rows:
                    view, n_cols = table.chat_view(tbl, st.slots.alone)
                    md = "\n\n" + table.markdown(view, max_cols=n_cols)
                    # 【정함 10-29 팀장 '그 아래 … 너무 길어'】 표가 붙으면 글쓴이가 표의 동마다
                    #        다시 늘어놓은 목록 줄은 뗀다(요약 문장 · 표 밖의 말은 그대로)
                    short = drop_row_bullets(body, [str(r[1]) for r in tbl.rows])
                    if short != body:
                        body = short + md
                        yield ("replace", head + body)
                    else:
                        body += md
                        yield ("text", md)
                    # 10-28 표 모양을 남긴다 — 다음 '정렬 · 열 더해 줘'가 이 표를 고친다
                    spec = table_edit.spec_from(
                        t_region, table.with_named_topics(plan.topics, text), t_dongs, tbl, text
                    )
                    st = st.model_copy(update={"table_spec": spec, "table_turn": state.turn + 1})
            if calc is not None and calc[1].table:
                md = "\n\n" + calc[1].table
                body += md
                yield ("text", md)
            elif calc is not None and (miss := calc_missing(calc[1], calc[2], body)):
                body += miss
                yield ("text", miss)
            # 【판단】 10-26 예상 질문 2-23 '지난주부터 연락이 끊긴 어르신이 … 몇 분인지만이라도':
            #        동 자료로 답한 길에는 급한 사정에 할 일(주민센터 · 112)이 빠졌다(막기 답에만).
            #        데스크가 지금 걱정되는 분으로 보고 말에도 그 꼴이 있을 때만
            # 10-29 변수 시험 c01_015 '이틀째 연락이안돼서 맘이 급합니다': 띄어쓰기가 없어 꼴을 못
            #       봤다 → 빈칸을 지운 말로 보고, 며칠째 연락이 끊긴 말은 데스크 표시가 없어도
            sq = re.sub(r"\s+", "", text)
            urgent_now = (card.urgent and URGENT_SQ.search(sq)) or LOST_CONTACT_SQ.search(sq)
            if urgent_now and URGENT_NOTE not in body:
                body += "\n\n" + URGENT_NOTE
                yield ("text", "\n\n" + URGENT_NOTE)
            if ROLE_ASK.search(text) and ROLE_NOTE not in body:
                body += "\n\n" + ROLE_NOTE
                yield ("text", "\n\n" + ROLE_NOTE)
            # 【판단】 10-28 페르소나 p03_c T3 '숫자 … 솔직히 저도 요즘 너무 지쳐서'에 숫자만 답하고
            #        위기 상담 번호가 없었다(지친 말 규칙은 범위 밖 · 못 알아들음 길에만 있었다)
            #        → 쓰는 사람 자신이 지쳤다는 말이면 자료 답에도 상담 안내를 붙인다
            if SELF_DISTRESS.search(text) and CARE not in body:
                body += "\n\n" + CARE
                yield ("text", "\n\n" + CARE)
            # 10-29 변수 시험 c01_006: 코드가 '○○로 알아들었어요'를 붙였는데 글쓴이가 같은 말을 또
            #       쓰고 앞에 자음 하나('ㅇ')까지 붙었다 → 글쓴이 쪽 같은 줄은 뗀다
            if "알아들었어요" in head and HEARD_AGAIN.search(body):
                body = HEARD_AGAIN.sub("", body).strip()
                yield ("replace", head + body)
            plan.message = head + body
            # 이어 준 앞 자료도 이번 답의 근거라 다음 턴 기억에 남긴다(10-25 오린 T9)
            reply = self._finish(session_id, state, st, card, plan, text, wfacts)
            reply.files = files
            yield ("done", reply)
            return
        # 【판단】 데스크가 못 알아들음으로 내도 까닭이 분명하면 그 까닭(10-15 desk_only_60 r6 D05)
        if plan.kind in ("out_of_scope", "unclear") and refusal_reason(text):
            plan.message = refusal_reason(text) or plan.message
        # 【판단】 쓰는 사람이 지쳤다는 말은 데스크가 범위 밖 · 못 알아들음으로 내도 상담 창구로
        #        (10-14 데스크 시험 r0 D10: 5번 중 1번 범위 밖 → 거절 문장이 나갈 뻔함)
        care_after = False
        if plan.kind in ("chitchat", "out_of_scope", "unclear") and DISTRESS.search(text):
            plan.message = CARE
        elif SELF_DISTRESS.search(text) and CARE not in plan.message:
            # 10-28 페르소나 p10_c T2 · T4: 위급 · 막기 길 답에 '다 그만두고 싶네요'가 섞이면
            #        위기 상담 번호가 빠졌다(critical) → 어떤 길의 답이든 끝에 붙인다(아래, 위급
            #        되풀이 문장으로 바꾼 뒤 — 10-28 재심사 C1 p10_c T4에서 바꾸며 덮어써 빠졌다)
            care_after = True
        elif typed and plan.kind != "blocked":
            plan.message = typed_note(typed) + plan.message
        if plan.message.startswith(EMERGENCY) and any(
            r.bot.startswith(EMERGENCY) for r in state.recent[-2:]
        ):
            plan.message = (
                EMERGENCY_THIRD
                if any(r.bot.startswith(EMERGENCY_AGAIN) for r in state.recent[-3:])
                else EMERGENCY_AGAIN
            )
        # 【판단】 10-28 페르소나 p10_a T3 ~ T5: 위급 중 '119가 맞아요? · 호수 몰라도 돼요?'에 같은
        #        틀 문장만 되풀이하고, 저녁 8시에 '주민센터에 알려 주세요' · 경로당 안내까지 했다
        #        → 위급 길 답이면 그 물음에 먼저 답하는 한 줄을 앞에 둔다
        if plan.message.startswith((EMERGENCY, EMERGENCY_AGAIN[:12], EMERGENCY_THIRD[:12])):
            if EMERGENCY_119_OK.search(text):
                plan.message = "네, 생명이 위험해 보이면 119가 맞아요. " + plan.message
            if NO_ADDRESS_ASK.search(text) and "몰라도" not in plan.message:
                plan.message = NO_ADDRESS_NOTE + " " + plan.message
        if (
            plan.kind == "blocked"
            and NOT_REPORTED.search(text)
            and NO_ADDRESS_NOTE not in plan.message
            and not plan.message.startswith(EMERGENCY_AGAIN)
        ):
            plan.message = NO_ADDRESS_NOTE + " " + plan.message
        if care_after and CARE not in plan.message:
            plan.message += "\n\n" + CARE
        if hidden:
            plan.message = disclose(DeskCard(), Slots(), hidden) + plan.message
        yield ("text", plan.message)
        yield ("done", self._finish(session_id, state, st, card, plan, text, facts))

    def _doc_turn(
        self,
        session_id: str,
        before: DialogueState,
        st: DialogueState,
        card: DeskCard,
        plan: Plan,
        text: str,
    ) -> Iterator[tuple[str, object]]:
        """동 상황 문서 — 동마다 PDF · PPTX를 만들고(같은 자료면 저장해 둔 것)
        요약 몇 줄과 파일을 준다.

        【판단】 만드는 데 한 곳에 40초쯤(10-26 웹 점검 37.5초, CLI) 걸려 먼저 '만드는 중'을
               보이고, 다 되면 그 글을 바꾼다.
               한 번에 두 곳까지(값 · 시간). 크레딧 바닥은 그대로 올려 보낸다(사람에게 알림)
        """
        dongs = list(st.slots.dongs[:2])
        # 【판단】 10-20 페르소나 s01 r4 T4: '개포1동 반지하도 찾아 주시고 … 개포3동 동 상황
        #        문서로'에
        #        개포1동 문서를 만들었다. '○○동 (동) 상황 문서'라고 이름을 댔으면 그 동
        m = DOC_DONG.search(text)
        if m and m.group(1) in dongs_in_text(text):
            dongs = [m.group(1)]
        yield ("text", f"{', '.join(dongs)} 상황 문서를 만드는 중이에요(한 곳에 40초쯤 걸려요).")
        files: list[str] = []
        lines: list[str] = []
        memo: list[str] = []
        doc_lines: list[str] = []
        for d in dongs:
            if self.doc_writer is None:
                lines.append("동 상황 문서를 쓸 AI가 설정되지 않아 만들지 못했어요.")
                break
            try:
                res = dongdoc.build(
                    d, self.data, self.doc_writer, Path(self.s.doc_dir), self.s.doc_font_dir
                )
            except llm.CreditExhausted:
                raise
            except FileNotFoundError:
                # 10-27: 글꼴이 없으면 AI를 부르기 전에 멈춘다(doc.build) — 무엇이 없는지 알린다
                lines.append(
                    f"{d} 동 상황 문서는 만들지 못했어요. 문서에 쓰는 글꼴(나눔고딕)이 이 컴퓨터에 "
                    "없어요 — 관리자에게 알려 주세요(.env 의 DOC_FONT_DIR)."
                )
                break
            except (llm.LLMError, KeyError) as e:
                lines.append(f"{d} 동 상황 문서는 만들지 못했어요({type(e).__name__}).")
                continue
            files += [str(res.pdf), str(res.pptx)]
            memo.append(f"{d} 동 상황 문서")
            lines.append(f"{d} {DOC_MADE}(PDF · PPTX). 요약:")
            lines += [f"· {x}" for x in res.doc["summary"][:5]]
            # 10-20 페르소나 s01 r13 T8 ~ T10: '문서에 그 문구가 들어갔는지'에 답하려면 문서 글이
            #        자료로 남아 있어야 한다(요약 다섯 줄만으로는 모른다)
            doc_lines += [f"문서 {d} · 요약: {x}" for x in res.doc["summary"]]
            doc_lines += [
                f"문서 {d} · {s['heading']}: {b}"
                for s in res.doc.get("sections", [])
                for b in s.get("bullets", [])
            ]
        if len(st.slots.dongs) > 2:
            lines.append("한 번에 두 곳까지 만들어요. 나머지는 이어서 말씀해 주세요.")
        plan.message = "\n".join(lines)
        yield ("replace", plan.message)
        title = BY_ID["dong_doc"].title
        facts = [Facts(title=title, lines=doc_lines, memo=" · ".join(memo))]
        reply = self._finish(session_id, before, st, card, plan, text, facts)
        reply.files = files
        yield ("done", reply)

    def _table_edit_ok(
        self, state: DialogueState, st: DialogueState, card: DeskCard, plan: Plan, text: str
    ) -> bool:
        """앞 표를 고치는 말인가(10-28 table_edit) — 표를 그린 지 세 턴 안 · 새 동을 말하지 않음."""
        spec = state.table_spec
        if spec is None or state.turn - state.table_turn > TABLE_EDIT_TURNS:
            return False
        if plan.kind not in ("answer", "unclear", "recall") or st.slots.fmt == "엑셀":
            return False
        if dongs_in_text(text) or not table_edit.is_edit(text):
            return False
        # 10-28 밤 브라우저 시험 '비율이 동들 평균보다 높으면서 경로당은 적은 동만 골라 주세요'
        #        (여러 조건 계산)를 '…동만'이 위 N곳 말로 잡혀 표 다듬기가 가로챘다 →
        #        판단 층이 계산으로 보면 표 다듬기가 아니다
        # 단, 칸 · 열을 직접 말하면 표 다듬기다('늘어난 비율 칸 붙여 주시고 …'는 계산 낱말(비율 ·
        #     늘어난)이 있어도 표의 열 이야기 — 10-28 밤 브라우저 다시 시험)
        # 10-29 회귀 table_noel_10 T7 '위에서 다섯 곳만 보여 줘': 지표 말이 하나도 없는 위 N곳 ·
        #       정렬 말까지 계산으로 가 표 대신 목록 → 계산으로 보더라도 지표(조건) 말이 있을 때만
        if not re.search(r"칸|열|컬럼|항목", text) and self.planner is not None:
            dec = self._decide(state, card, text)
            if dec.route == "깊은 고민" and dec.sig.concepts:
                return False
        # 다른 주제를 물으면('청년 많은 순으로 알려 줘') 표 · 열 말이 없을 때 표 고치기가 아니다
        new_topic = (
            plan.kind == "answer" and plan.topics and not set(plan.topics) & set(spec.topics)
        )
        if new_topic and not re.search(r"표|열|칸|컬럼", text):
            return False
        return True

    def _table_edit_turn(
        self,
        session_id: str,
        state: DialogueState,
        st: DialogueState,
        card: DeskCard,
        plan: Plan,
        text: str,
    ) -> Iterator[tuple[str, object]]:
        """앞 표를 코드가 고쳐 다시 그린다(글쓴이 없음 — 앞뒤가 다른 말이 나오지 않게)."""
        spec = state.table_spec
        assert spec is not None
        region = st.slots.region if st.slots.region in ("강남구", "춘천시") else spec.region
        header = table.build(spec.topics, region, [], self.data).header
        new, notes = table_edit.apply(spec, header, text, region)
        md, n, _ = table_edit.render(new, self.data)
        what = " · ".join(n for n in notes if not n.startswith("지역:")) or (
            "열 · 정렬 같음" if region != spec.region else "앞 표 그대로"
        )
        if region != spec.region:
            msg = f"앞의 {spec.region} 표와 같은 열로 {region} 표를 그렸어요({what}). {n}곳이에요."
        else:
            msg = f"앞의 {region} 표를 고쳤어요({what}). {n}곳이에요."
        if not new.cols:
            msg += " 남은 열이 없어 동 이름만 보여요 — 보실 열을 말씀해 주세요."
        plan.kind, plan.topics, plan.pending = "answer", new.topics, None
        plan.message = msg + "\n\n" + md
        st = st.model_copy(update={"table_spec": new, "table_turn": state.turn + 1})
        yield ("text", plan.message)
        yield ("done", self._finish(session_id, state, st, card, plan, text, []))

    def _table_rows(
        self, st: DialogueState, plan: Plan, text: str
    ) -> tuple[str, list[str], object]:
        s = st.slots
        region = (
            s.region
            or (dongname.region_of(s.dongs[0]) if s.dongs else None)
            or st.profile.member_region
            or "강남구"
        )
        # 10-29 브라우저 시험 '제 담당 개포3동이랑 효자2동 … 표로 나란히': 한 지역 동만 남겨
        #       효자2동이 빠지거나(1차), 데스크가 줄 세우기를 켜 춘천 위 5곳 표가 나갔다(2차) →
        #       이번 말에 동을 둘 넘게 적었으면 그 동들로(지역이 달라도), 줄 세우기여도
        said = dongs_in_text(text)
        every = bool(EACH_DONG.search(text)) or not s.dongs or (s.rank and len(said) < 2)
        both = len({dongname.region_of(d) for d in said}) > 1 or (
            s.compare and len({dongname.region_of(d) for d in s.dongs}) > 1
        )
        if every:
            dongs = []
        elif len(said) >= 2:
            dongs = said
            if not both:
                region = dongname.region_of(said[0]) or region
        elif both:
            dongs = list(s.dongs)
        else:
            dongs = [d for d in s.dongs if dongname.region_of(d) == region]
        topics = table.with_named_topics(plan.topics, text)
        t = table.pick(table.build(topics, region, dongs, self.data), text)
        return region, dongs, table.order_top(t, topics, text)

    def _table_facts(
        self, st: DialogueState, plan: Plan, text: str, made: bool, files: list[str] = ()
    ) -> Facts | None:
        """표를 달라는 말이면 표의 줄을 글쓴이에게도 준다(코드가 옮긴 숫자).

        【판단】 10-20 페르소나 h02 r8: 표 파일을 만들었다는 머리말 아래에 글쓴이가 '엑셀 파일은
               만들 수 없어요' · '22개 동 열을 모두 채울 수 없어요'라고 썼다(글쓴이는 파일도 표의
               숫자도 몰랐다). 채팅에 표를 달라는 말('마크다운 표로')에도 같은 줄을 준다
        """
        if not (made or TABLE_ASK.search(text)) or not any(t in table.COLS for t in plan.topics):
            return None
        region, dongs, t = self._table_rows(st, plan, text)
        if not t.rows:
            return None
        cols = t.header[1:]
        lines = ["표의 열: " + " | ".join(cols)]
        # 10-25 페르소나 cli1 오린 T6 ~ T7: 채팅 표는 앞 8열만 그리는데 글쓴이는 모든 열을 알고
        #        '순위 · 진단이 들어 있다'고 썼다 → 채팅에 보이는 열을 따로 알린다
        shown = table.shown_header(*table.chat_view(t, st.slots.alone))
        if CHAT_TABLE.search(text) and len(shown) < len(cols):
            lines.append(
                f"채팅에 붙는 표에 보이는 열({len(shown)}열): "
                + " | ".join(shown)
                + " — 나머지 열은 채팅 표에 보이지 않는다(그 열이 채팅 표에 있다고 쓰지 않는다)"
            )
        # 'name' 많은 순 줄은 값이 큰 쪽부터(증감률은 늘어난 쪽부터 — 줄어든 쪽은 뒤)
        for r in t.rows:
            lines.append(
                " | ".join(
                    "" if v is None else f"{v:,}" if isinstance(v, int) else str(v) for v in r[1:]
                )
            )
        lines += t.footer[:1] + [x for x in t.footer if x.startswith("합계(")]
        # 【판단】 10-20 페르소나 h02 r2: 글쓴이가 표 줄을 스스로 줄 세우다 '정정하면 … 6위
        #        논현1동 411곳'처럼 순서를 틀렸다. 핵심 열은 많은 순 줄을 코드가 만들어 준다
        # 10-28 재심사 q01_b T7: 동 하나짜리 표에 '많은 순: 1위 역삼1동 8.4'를 줘 글쓴이가
        #        '증감률은 1위'라고 썼다(22곳 중 6위). 한 곳이면 순서 줄을 주지 않고, 일부 동이면
        #        그 안의 순서라고 밝힌다
        whole = len(self.data.region_dongs(region)) if region else 0
        some = f"이 표 {len(t.rows)}곳 안에서 많은 순({region} 전체 순위 아님)"
        for col in SORT_COLS if len(t.rows) >= 2 else ():
            name = col.format(reg=B.reg())
            if name not in t.header:
                continue
            k = t.header.index(name)
            got = sorted(
                ((r[1], r[k]) for r in t.rows if isinstance(r[k], int | float)),
                key=lambda x: -x[1],
            )
            if got:
                lines.append(
                    f"'{name}' {'많은 순' if len(t.rows) >= whole else some}: "
                    + " · ".join(f"{i}위 {n} {v:,}" for i, (n, v) in enumerate(got, 1))
                )
        f = Facts(title=f"{region} 표({len(t.rows)}곳, 코드가 동 자료에서 옮김)", lines=lines)
        if made:
            f.notes.append(
                "표 파일(엑셀 · CSV)을 만들어 이 답과 함께 건넸다. "
                "'파일을 만들 수 없다'고 하지 않는다"
            )
            # 10-20 페르소나 h02 r9 T8 ~ T9: '파일 이름과 열 구성'을 물었는데 '자료에 없다'
            if files:
                f.lines.insert(
                    0, f"표 파일 이름: {Path(files[0]).name}(엑셀) — 열은 아래 '표의 열' 그대로"
                )
        f.notes.append(
            "표의 숫자는 위 줄 그대로 옮기고, 빈 칸은 그 동에 그 자료가 없는 것이다. "
            "순서를 매길 때는 '많은 순' 줄을 그대로 쓰고 스스로 다시 줄 세우지 않는다"
        )
        # 10-20 페르소나 f02 r7 T5: 22곳 표 줄을 다 주었는데 '전체 표는 여기서 드리기 어려워요'
        # 【정함 10-27 팀장】 묻는 것만 — 채팅 표는 '표로' 같은 말이 있을 때만 붙는다(CHAT_TABLE).
        #        파일만 만든 답에도 '표를 글 아래에 붙인다'고 알려, 글쓴이가 파일 · 열을 다시
        #        설명했다(qbank 1-5 T2 · 2-2a T4 · 2-8 T1: 머리말의 열 16개 목록 + 글의 파일 설명)
        if CHAT_TABLE.search(text):
            f.notes.append(
                "사용자가 표를 달라고 했다. "
                "표 자체는 코드가 네 글 아래에 붙인다(모든 줄 · 모든 숫자). "
                "너는 표를 그리지 말고, 표가 무엇을 보여 주는지와 눈에 띄는 것 한두 문장만 쓴다. "
                "'여기서 드리기 어렵다' · '동을 하나씩 말해 달라' · '-로 둔다'고 하지 않는다"
            )
        elif made:
            f.notes.append(
                "파일 이름 · 열 · 받는 곳은 코드가 답 맨 앞에 이미 알렸다. "
                "파일을 다시 설명하지 말고 "
                "물은 숫자 · 결론만 쓴다(열 구성을 물을 때만 '표의 열' 줄로 답한다)"
            )
        return f

    def _calc_sheet_ok(self, state: DialogueState, text: str) -> bool:
        """앞 계산 표로 엑셀을 줄까 — 계산한 지 세 턴 안 · 새 동을 말하지 않음."""
        return (
            len(state.calc_sheet) > 1
            and state.turn - state.calc_turn <= TABLE_EDIT_TURNS
            and not dongs_in_text(text)
        )

    def _calc_sheet_facts(self, st: DialogueState) -> Facts:
        """앞 계산 표를 글쓴이에게(엑셀로 만든 턴) — 줄은 코드가 옮긴 그대로."""
        head, *rows = st.calc_sheet
        lines = [" | ".join(head)] + [" | ".join(r) for r in rows]
        notes = [
            "이 표 전체를 엑셀 · CSV 파일로 만들었다(파일 이름은 답 앞 괄호에 이미 있다).",
            "표를 글로 다시 그리지 않는다. 한두 문장으로 무엇이 들어 있는지만 말한다",
            "앞 계산에서 쓴 자료를 '없다' · '구분이 없다'고 하지 않는다(표의 열이 그 자료다)",
            "표에 무엇이 들어 있는지는 맨 위 머리 줄의 열 이름만으로 말한다(다른 열 · 연도를 더하지"
            " 않는다). 빈 칸 · 대신 넣은 값 · 가까운 값 이야기를 지어내지 않는다",
        ]
        notes += [f"조건 {i}) {r}" for i, r in enumerate(st.calc_rules, 1)]
        return Facts(title="앞 여러 조건 계산의 전체 표(엑셀로 만든 것)", lines=lines, notes=notes)

    def _calc_sheet_sentence(self, st: DialogueState) -> str:
        """계산 표 파일에 든 것 — 코드가 머리 줄로 쓴 한 문장(글쓴이 없음)."""
        head, *rows = st.calc_sheet
        cols = [re.sub(r"^\d+\)\s*", "", h) for h in head[1:] if h != "맞은 수"]
        tail = " · 조건마다 ○ × · 맞은 수" if st.calc_rules else ""
        return f"파일에는 {len(rows)}곳마다 {' · '.join(cols)}{tail}가 들어 있어요."

    def _save_calc_sheet(self, st: DialogueState, now: bool = False) -> tuple[list[str], str]:
        """앞 여러 조건 계산의 전체 표 → 엑셀 · CSV(코드가 만든다)."""
        head, *rows = st.calc_sheet
        region = st.calc_region or st.slots.region or "강남구"
        foot = [f"조건 {i}) {r}" for i, r in enumerate(st.calc_rules, 1)]
        if st.calc_rules:
            foot.append("○ · × 와 맞은 수는 취약 돌보미가 조건마다 코드로 셈(AI가 쓰지 않음)")
        foot.append(f"기준 자료: {self.data.basis}")
        t = table.Table(
            title="여러 조건 계산",
            header=["지역", *head],
            rows=[[region, *r] for r in rows],
            footer=foot,
        )
        files = table.save(t, region, self.data.basis, Path(self.s.doc_dir))
        n_cond = len(head) - 2 if st.calc_rules else len(head) - 1
        what = f"조건 {n_cond}가지 · 맞은 수" if st.calc_rules else f"지표 {n_cond}가지"
        # 【정함 10-29 팀장 '가독성이 별로야'】 안내는 한 문장 — 파일 이름은 내려받기 단추 옆에
        #        보이고(화면), 조건 기준은 파일 맨 아래에 있다
        note = (
            f"({'이' if now else '앞'} 계산 표({region} {len(rows)}곳 전부 · {what})를 "
            "엑셀 · CSV로 만들었어요 — 아래 '엑셀 내려받기'로 받아요.)\n"
        )
        return [str(p) for p in files], note

    def _make_table(self, st: DialogueState, plan: Plan, text: str) -> tuple[list[str], str]:
        """동별 표 파일(엑셀 · CSV)과 답 앞에 붙일 알림.

        숫자는 사서와 같은 동 자료에서 코드가 옮긴다(AI가 표를 쓰지 않는다).

        【판단】 동을 정했으면 그 동만, 줄 세우기 · '동별로 · 전체'면 그 지역 모든 동(10-14)
        """
        region, dongs, t = self._table_rows(st, plan, text)
        every = not dongs
        files = table.save(t, region, self.data.basis, Path(self.s.doc_dir))
        where = f"{region} {len(t.rows)}개 동" if every else f"{region} {' · '.join(dongs)}"
        note = (
            # 10-27: 열 이름을 다 늘어놓지 않는다(열 16개면 머리말만 300자 — 열은 파일 첫 줄에 있다)
            # 10-20 페르소나 h02 r6 '엑셀 링크가 안 보인다 · 파일명이라도' → 10-29부터 파일 이름은
            #       화면의 내려받기 단추 옆에 보인다(팀장 '가독성') — 글은 한 문장
            f"({where} {t.title} 표를 엑셀 · CSV로 만들었어요(열 {len(t.header) - 2}개) — "
            "아래 '엑셀 내려받기'로 받아요."
        )
        if t.skipped:
            names = josa(" · ".join(t.skipped), "은", "는")
            note += f" {names} 표로 만들지 않아요."
        return [str(p) for p in files], note + ")\n"

    def _dong_total(self, name: str) -> str:
        """동 전체 65세 이상 1인세대 한 문장(가장 새 판) — 단지 물음의 대신 답(재심사 p07_a)."""
        solo = (self.data.dong(name) or {}).get("solo65") or {}
        if not solo:
            return ""
        k = max(solo)
        return f" {name} 전체로는 65세 이상 1인세대(주민등록 {k})가 {solo[k]:,}명이에요."

    def _office_for(self, name: str) -> str:
        """그 동 주민센터(행정복지센터) 한 줄 — 주소가 있을 때만(10-28 재심사 q06_b)."""
        o = (self.data.places(name) or {}).get("office") or {}
        return office_line(name, o) if o.get("addr") else ""

    def _visit_facts(self, st: DialogueState) -> Facts | None:
        """방문 순서를 물을 때 — 그 동의 마을(리) 단위 자료 줄(집 · 버스). 없으면 안내만."""
        lines: list[str] = []
        for d in st.slots.dongs[:2]:
            sl = Slots(region=dongname.region_of(d), dongs=(d,))
            for topic, key in (("housing", "마을(리)별"), ("bus", "버스가 드문 마을")):
                try:
                    got = librarian.gather(topic, sl, self.data).lines
                except Exception:  # noqa: BLE001 — 그 지역에 없는 서가(강남 버스)는 건너뛴다
                    continue
                lines += [f"[{d}] {x}" for x in got if key in x]
        return Facts(title="방문 순서를 물음 — 마을 단위 자료", lines=lines, notes=[VISIT_NOTE])

    def _summary_turn(
        self, session_id: str, state: DialogueState, card: DeskCard, plan: Plan, text: str
    ) -> Iterator[tuple[str, object]]:
        """앞 답들의 자료로 요약(SUMMARY_ASK 위 판단). 칸은 바꾸지 않는다.

        【판단】 10-27 밤 창 시험 T11 '지금까지 얘기한 거 세 줄로': 앞 답 숫자 줄이 최근 것부터라
               글쓴이가 마지막 두 동만 요약하고 처음 본 수서동을 빠뜨렸다(6턴 · 15턴 한 번씩)
               → 앞 답 숫자 줄을 동을 처음 본 순서로 놓고, 본 동 목록을 함께 준다
        """
        seen = list(dict.fromkeys(d for e in state.log for d in e.dongs))

        def first_seen(x: str) -> int:
            head = re.match(r"\[[^\]]*?(\S+)\]", x)
            return seen.index(head.group(1)) if head and head.group(1) in seen else len(seen)

        said = sorted(state.said_facts, key=first_seen)
        lines = [
            x
            for x in dict.fromkeys(said + list(state.last_facts + state.older_facts))
            if not x.startswith("## ")
        ]
        f = Facts(title="앞 답들에 쓴 자료(요약할 것)", lines=lines[:OLDER_FACTS_MAX])
        f.notes.append(
            "사용자가 앞에서 나눈 이야기를 요약 · 정리해 달라고 했다. "
            "위 자료의 숫자 · 사실만 쓰고, "
            "사용자가 말한 줄 수(예: 세 줄)를 지킨다. '아직 함께 보지 않았다'고 하지 않는다"
        )
        if len(seen) > 1:
            f.notes.append(
                f"이 대화에서 본 동(먼저 본 순): {', '.join(seen[:12])}. "
                "줄 수가 적으면 여러 동을 한 줄에 묶어서라도 이 동들을 빠뜨리지 않는다"
            )
        facts = [f]
        plan.kind, plan.topics = "answer", ("recall",)
        question = card.restate or text
        before = state.last_answer
        facts, _ = budget.fit(facts, (question, text, before, WRITER_HEAD), CARRY_TITLE)
        stream = getattr(self.writer, "write_stream", None)
        if stream is None:
            body = self.writer.write(question, facts, said=text, before=before)
            yield ("text", body)
        else:
            body = ""
            for event, chunk in stream(question, facts, said=text, before=before):
                body = chunk if event == "replace" else body + chunk
                yield (event, chunk)
            body = self.writer.last.text if getattr(self.writer, "last", None) else body
        plan.message = body
        yield ("done", self._finish(session_id, state, state, card, plan, text, facts))

    def _recall(self, st: DialogueState, region: str | None = None, asked: str = "") -> str:
        """앞선 대화 되짚기 — 코드가 쌓은 사실 목록 · 다룬 질문 목록으로만 답한다.

        【판단】 AI가 지어내지 않게, 저장된 기억을 그대로 보여 준다.
        【판단】 지역으로 좁혀 물으면('지금까지 본 동 중 춘천은?') 그 지역 동만 답한다
               (떠보기 10-12: 기억 목록을 통째로 내놓았다).
        """
        seen: list[str] = []
        for e in st.log:
            for d in e.dongs:
                if d not in seen:
                    seen.append(d)
        if region:
            mine = [d for d in seen if dongname.region_of(d) == region]
            whole = list(
                dict.fromkeys(
                    BY_ID[e.topic].title for e in st.log if not e.dongs and e.topic in BY_ID
                )
            )
            if not mine and whole:
                # 10-20 페르소나 s02 r8: 지역 전체로 본 것이 있는데 '아직 함께 보지 않았어요'
                return (
                    f"이 대화에서 {region}의 동을 하나씩 정해 본 것은 없고, 지역 전체로 "
                    f"{' / '.join(whole)}을(를) 봤어요."
                )
            if not mine:
                return f"이 대화에서 아직 {region}의 동은 함께 보지 않았어요."
            return f"지금까지 함께 본 {region}의 동(먼저 본 순): {', '.join(mine)}"
        # 【판단】 10-12 페르소나: '제가 어디 담당이라고 했죠?'에도 동 15곳 · 최근 질문까지 통째로
        #        내놓았고 'T3' 같은 내부 번호가 보였다.
        #        물은 것만(담당 · 일 → 사실, 본 동 → 동) 답한다
        want_facts = bool(_ASK_FACTS.search(asked)) and not _ASK_DONGS.search(asked)
        want_dongs = bool(_ASK_DONGS.search(asked)) and not _ASK_FACTS.search(asked)
        rows = []
        if st.facts and not want_dongs:
            rows.append("앞에서 말씀하신 것:")
            rows += [f"· {f}" for f in st.facts[:12]]
        if st.log and not want_facts:
            rows.append(f"지금까지 함께 본 동(먼저 본 순): {', '.join(seen) or '없음'}")
            if not want_dongs:
                last = list(
                    dict.fromkeys(BY_ID[e.topic].title for e in st.log[-5:] if e.topic in BY_ID)
                )
                rows.append(f"최근 다룬 질문: {' / '.join(last)}")
        if not rows:
            return "아직 이 대화에서 함께 본 것이 없어요. 동 이름과 알고 싶은 것을 말씀해 주세요."
        return "\n".join(rows)

    def _settings(
        self, st: DialogueState, card: DeskCard, text: str = ""
    ) -> tuple[DialogueState, str]:
        """내 담당 지역 바꾸기 — 바꾸라는 말과 정한 동 · 지역이 있을 때만 바꾼다.

        【판단】 10-28 페르소나 p01_b T3 '수서동은 어떻게 정하신 건가요?'에 '담당 지역을
               수서동으로 바꿨어요' — 묻기만 했는데 데스크가 동을 칸에 넣어 바꾸기로 갔다 → 말에
               바꾸라는 뜻이 있을 때만 바꾸고, 아니면 지금 담당 지역과 기준으로 보는 것을 알린다
        """
        s = st.slots
        wants_change = (card.dong_op == "set" or card.region_op == "set") and (
            not text or CHANGE_REGION.search(text)
        )
        if wants_change and (s.dongs or s.region):
            dong = s.dongs[0] if len(s.dongs) == 1 else None
            region = (dongname.region_of(dong) if dong else None) or s.region
            p = Profile(member_region=region, member_dong=dong)
            where = f"{region} {dong}" if dong else f"{region}"
            msg = (
                f"담당 지역을 {josa(where, '으로', '로')} 바꿨어요. "
                "앞으로 지역을 말씀하지 않으시면 여기를 기준으로 볼게요."
            )
            return st.model_copy(update={"profile": p}), msg
        p = st.profile
        now = f"{p.member_region or '정하지 않음'}{' ' + p.member_dong if p.member_dong else ''}"
        return st, (
            f"지금 담당 지역은 {now}이에요. 지역 · 동을 말씀하지 않으시면 "
            "담당 지역(화면 위에서 고른 지역 · 동)을 기준으로 봐요. "
            "바꾸시려면 '담당 지역을 ○○동으로 바꿔 줘'처럼 말씀해 주세요."
        )

    @staticmethod
    def _prev_dongs(before: DialogueState) -> tuple[str, ...]:
        """'그 중에서'가 가리킬 앞 결과 — 앞 계산에서 고른 동, 없으면 바로 앞 답에 나온 동들.

        【판단】 10-26: 앞 턴이 보통 길(지표 하나 줄 세우기)로 답했으면 last_calc 가 비어 '그 중에서
               반지하 많은 데만'이 지역 전체로 계산됐다. 앞 답에 동이 둘 넘게 나왔으면 그 동들로
               본다
        """
        last = before.recent[-1].bot if before.recent else ""
        got = tuple(dongs_in_text(last))
        if before.last_calc:
            # 【판단】 10-26 페르소나 c02 T4: '그 5곳 합치면'에 앞 계산의 7곳에서 5곳을 골라
            #        남산면이 섞임. 사용자가 본 것은 앞 답에 나온 5곳 → 앞 답의 동이 앞 결과 안에
            #        다 있고 더 적으면 그것을 앞 결과로 본다
            if 2 <= len(got) < len(before.last_calc) and set(got) <= set(before.last_calc):
                return got
            return before.last_calc
        return got if len(got) >= 2 else ()

    def _decide(self, before: DialogueState, card: DeskCard, text: str) -> router.Decision:
        """판단 층(코드 신호 + 데스크 카드 + 바로 앞 턴)."""
        last = before.recent[-1] if before.recent else None
        return router.decide(
            text,
            card,
            has_prev_calc=bool(self._prev_dongs(before)),
            prev_user=last.user if last else "",
            prev_bot=last.bot if last else "",
        )

    def _calc_likely(
        self, before: DialogueState, st: DialogueState, card: DeskCard, plan: Plan, text: str
    ) -> bool:
        """계산 방법을 짜는 AI를 부를 말인가(진행 단계 알림용 — _calc의 앞 조건과 같다)."""
        if self.planner is None or "dong_doc" in plan.topics or st.slots.fmt not in CALC_FMTS:
            return False
        if _two_region_dongs(text):
            return False
        return self._decide(before, card, text).route == "깊은 고민"

    def _calc(
        self,
        before: DialogueState,
        st: DialogueState,
        card: DeskCard,
        plan: Plan,
        text: str,
        scope: str | None = None,
    ) -> tuple[Facts, query.Result, query.Plan] | None:
        """판단 층이 '깊은 고민'으로 보면 계산 계획을 짜고(Haiku → 검사 → 필요하면 큰 모델)
        코드로 계산한 사실 묶음을 돌려준다. 아니면 None(지금 길).

        scope: 지역 전체냐 동 하나냐를 AI가 고른 것('region' · 'dong', 모르면 None — SCOPE_ASK).

        【판단】 10-26 팀장 "더 집중적으로 고민을 해 봐야 하는 건지 … 치밀하게 조직해서" →
               ① 코드 신호 + 데스크 카드로 길(router.decide) ② Haiku 계획
               ③ 코드 검사(router.check)에 걸리면 큰 모델(calc_big_model)로 다시
               ④ 계산은 전부 코드(query.run)
        """
        if self.planner is None or "dong_doc" in plan.topics or st.slots.fmt not in CALC_FMTS:
            return None
        if _two_region_dongs(text):
            return None
        dec = self._decide(before, card, text)
        if dec.route != "깊은 고민":
            return None
        prev_user = before.recent[-1].user if before.recent else ""
        region = st.slots.region or st.profile.member_region
        ctx = prev_user[:300]
        if before.last_calc_conds:
            # 앞 계산과 같은 기준을 다시 말하면 같은 지표 · 연산으로(10-26 페르소나 c01: 턴마다
            # '경로당 부족'을 아래 3분의 1 · 평균보다 낮음으로 번갈아 옮겨 ○ · ×가 바뀜)
            ctx += "\n앞 계산 조건: " + " / ".join(before.last_calc_conds)
        if prev := self._prev_dongs(before):
            # 앞 결과가 있다는 것을 계획기도 알게('그 중에' → use_prev)
            ctx += f"\n앞 결과 동 {len(prev)}곳: {' · '.join(prev[:12])}"
        try:
            p = self.planner.plan(text, region, ctx)
            if p is None or p.need != "계산":
                return None  # 계획기가 계산이 아니라고 봄 → 지금 길
            issues = router.check(p, dec.sig)
            if issues and self.planner_big is not None:
                p2 = self.planner_big.plan(text, region, ctx)
                if (
                    p2 is not None
                    and p2.need == "계산"
                    and len(router.check(p2, dec.sig)) <= len(issues)
                ):
                    p = p2
        except llm.CreditExhausted:
            raise
        except llm.LLMError:
            return None
        if p is None or not (p.conds or p.sort or p.show or p.agg):
            return None
        # 【판단】 10-29 브라우저 시험(담당 개포3동) '우리동 혼자사는 어르신이랑 혼자사는 청년 둘다
        #        작년꺼랑 같이 표로': 지표가 둘이라 판단 층이 계산 길로 보냈고 계획기가 지역 전체
        #        줄 세우기를 짜 강남 위 5곳 표가 붙었다(글은 개포3동으로 맞음). AI가 정해진 동
        #        하나를 묻는 말이라고 했으면 계산이 그 동을 다루거나(동 목록에 그 동 · 사람 겹쳐
        #        세기) 지역과 견줄 때만(조건 · 평균 · 범위) 계산 길. 지역 전체를 늘어놓거나 합계만
        #        내거나 그 동이 빠진 동 목록이면 지금 길로(그 동의 표)
        # 【판단】 같은 날 다시: '청년 1인가구는요?'(개포3동)에 계획기가 강남 합계를 짜 계산 길로
        #        갔고, 그 결과(청년 많은 5곳)가 남아 다음 턴 '둘다 … 표로'가 앞 결과 5곳 표
        #        (use_prev)로 — 합계만 · 그 동이 빠진 동 목록도 지금 길로
        mine = st.slots.dongs[0] if len(st.slots.dongs) == 1 else None
        about_mine = mine in p.dongs or bool(p.conds) or p.cross or bool(set(p.agg) - {"합계"})
        if scope == "dong" and mine and not about_mine:
            return None
        if card.dong_not:
            # 빼라는 동은 계획에 들어 있어도 빼고, 지역 계산에서도 뺀다(10-26 긍정 · 부정 칸)
            p = p.model_copy(
                update={
                    "dongs": tuple(d for d in p.dongs if d not in card.dong_not),
                    "exclude": tuple(dict.fromkeys(p.exclude + card.dong_not)),
                }
            )
        # 【판단】 10-27 qbank 2-8 c1 T3('1. 동면이 … 3. 버스 드문 마을'): 계획기가 마을 지표를
        #        쓰면서 동면을 빼 춘천 읍면 10곳 마을 전체를 봤다 → 말에 읍 · 면이 나왔고 계획에
        #        동이 없으면 그 읍 · 면 안의 마을만 본다(앞 결과 안에서 거르는 말은 그대로)
        towns = [d for d in dec.sig.dongs if d.endswith(("읍", "면"))]
        refs = list(p.conds) + list(p.show) + [p.sort]
        if towns and not p.dongs and not p.use_prev and any(map(query._is_village, refs)):
            p = p.model_copy(update={"dongs": tuple(towns)})
        if p.region is None:
            if region is None:
                return None  # 지역을 모르면 강남으로 셈하지 않고 지금 길(지역을 되묻는다)
            p = p.model_copy(update={"region": region})
        if DONG_MEAN.search(text):
            p = p.model_copy(update={"dong_mean": True})
        res = query.run(p, self.data, prev=list(self._prev_dongs(before)))
        # 【판단】 두 지역에 평균 · 합계를 바라면 지역마다 따로 계산해 잇는다(계산 도구는 한 지역씩,
        #        route_50 r1 P11 '평균 자원 공백 강남 · 춘천')
        # 10-29 변수 시험 c01_056 '개포2동 담당인데 춘천 읍면 중에 …': 자기소개의 강남 동이 지역
        #       신호로 세어져 묻지 않은 강남 계산표가 붙었다 → 지역 이름을 둘 다 말했을 때만
        named = {r for r, pat in REGION_WORDS_IN_TEXT if pat.search(text)}
        others = [r for r in named if r != p.region] if len(named) >= 2 else []
        for r in others:
            more = query.run(p.model_copy(update={"region": r, "dongs": ()}), self.data)
            res.lines += more.lines
            res.matched += more.matched
            if more.table:
                res.table = (res.table + "\n\n" + more.table).strip()
        # 【판단】 10-26 페르소나 c01 T3: '수서동 · 개포3동 …'을 물었는데 위 5곳에 없어 글쓴이가
        #        '자료에 없다'고 씀 → 말에 나온 동은 위 몇 곳에 없어도 그 동 줄을 덧붙인다
        named = [d for d in dict.fromkeys(dec.sig.dongs) if d in res.values]
        res.lines += query.focus_lines(res, p, named)
        f = Facts(title="여러 조건 계산", lines=res.lines, notes=list(CALC_NOTES))
        if res.table:
            f.notes.append(CALC_TABLE_NOTE)
        f.memo = (p.restate or "여러 조건 계산")[:80]
        return f, res, p

    def _finish(
        self,
        session_id: str,
        before: DialogueState,
        st: DialogueState,
        card: DeskCard,
        plan: Plan,
        text: str,
        facts: list[Facts],
    ) -> Reply:
        # 【판단】 답 검문소 — 어떤 길로 만든 답이든 화면에 나가기 전에 속말 꼬리표를 뗀다(10-12)
        plan.message = checks.tidy(plan.message)
        turn = before.turn + 1
        log = st.log
        if plan.kind == "answer":
            memos = {f.title: f.memo for f in facts}
            for t in plan.topics:
                entry = LogEntry(
                    turn=turn,
                    topic=t,
                    dongs=st.slots.dongs[:4],
                    target=st.slots.target,
                    note=memos.get(BY_ID[t].title, ""),
                )
                log = add_log(log, entry)
        seen = st.dong_seen
        if st.slots.dongs and (plan.kind == "answer" or st.slots.dongs != before.slots.dongs):
            seen = note_dongs(seen, st.slots.dongs, turn)
        st = st.model_copy(
            update={
                "turn": turn,
                "log": log,
                "dong_seen": seen,
                "facts": fold_facts(st.facts, card.new_facts, self.s.facts_head, self.s.facts_tail),
                "last_question": plan.message if plan.pending else None,
                "pending": plan.pending,
                "pending_topics": plan.topics if plan.pending else (),
                # 【판단】 맞장구 · 되묻기는 직전 자료 답을 바꾸지 않는다(10-15)
                "last_answer": plan.message[:800] if plan.kind == "answer" else st.last_answer,
                "last_facts": facts_lines(facts) if plan.kind == "answer" else st.last_facts,
                "older_facts": tuple(dict.fromkeys(st.last_facts + st.older_facts))[
                    :OLDER_FACTS_MAX
                ]
                if plan.kind == "answer"
                else st.older_facts,
                "said_facts": tuple(
                    dict.fromkeys(said_lines(plan.message, facts) + list(st.said_facts))
                )[:SAID_FACTS_MAX]
                if plan.kind == "answer"
                else st.said_facts,
                "masked": mask_spots(text) or st.masked,
                # 10-27 세션 제목이 없을 때 쓰는 첫 질문(막은 질문 · 너무 긴 글은 넣지 않음)
                "first": st.first
                or ("" if plan.kind in ("blocked", "too_long") else text.strip()[:FIRST_MAX]),
                "tail_shown": st.tail_shown or BRIEF_TAIL in plan.message,
                "recent": add_recent(
                    st.recent,
                    TurnText(turn=turn, user=text, bot=plan.message),
                    self.s.history_turns,
                ),
            }
        )
        with self._save_lock:
            # 턴은 제목을 바꾸지 않는다 — 답을 쓰는 동안 사용자가 바꾼 제목(set_title)을 살린다
            now = self.store.load(session_id)
            if now is not None and now.title != st.title:
                st = st.model_copy(update={"title": now.title})
            self.store.save(session_id, st)
        return Reply(plan.message, plan.kind, plan.topics, st, card, facts)
