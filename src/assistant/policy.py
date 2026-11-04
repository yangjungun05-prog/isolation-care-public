"""이륙 전 체크 — 답할지 · 되물을지 · 거절하고 권할지 · 막을지를 코드가 정한다.

【기능】 preflight(): 갱신된 상태 + 데스크 카드 → Plan.
       답이 아닌 경우의 문장은 여기서 코드가 만든다.
【판단】 정해진 문장(범위 밖 · 막기)은 AI가 쓰지 않는다 — 팀장이 정한 말을 그대로 지키려고.
       권유할 대안은 장서 목록(catalog) 안에서만 고른다. 목록 밖 정보를 권할 수 없다.
【판단】 되묻기는 한 번에 하나만(슬롯 채우기). 무엇이 비었는지는 코드가 안다.
       이음은 AI에게 되묻기를 맡겼다가 이미 답한 것을 또 물었다(조사 3절 4번).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from src.assistant import basis as B
from src.assistant import dongname, keyboard
from src.assistant.catalog import BY_ID, DATA_IDS, SHORT, covers
from src.assistant.data_source import DongData
from src.assistant.librarian import RANKABLE
from src.assistant.slots import DeskCard, Slots
from src.assistant.state import Applied, DialogueState

Kind = Literal[
    "answer",
    "ask_slot",
    "unknown_dong",
    "out_of_scope",
    "not_connected",
    "coverage",
    "blocked",
    "chitchat",
    "unclear",
    "settings",
    "recall",
    "too_long",
]

# 【판단】 10-12 팀장: "1000자까지만 일단 끊고". 넘는 글은 몰래 자르지 않고
#        (떠보기: 가운데 조건이 사라짐) 받지 않는다고 알린다.
#        긴 글을 나눠 읽는 방법은 멘토 답을 보고 정한다
MAX_INPUT = 1000
TOO_LONG = (
    "말씀이 {n:,}자라서 받지 못했어요. 한 번에 1,000자까지 받아요. "
    "공문은 통째로 붙이지 말고 대상 · 기간 같은 조건과 질문만 1,000자 안으로 적어 주세요."
)

# 【판단】 팀장 문장(10-12 03:57)을 그대로 쓴다
OUT_OF_SCOPE = "저희가 가지고 있는 데이터가 아니라 말씀드릴 수 없어요."
# 【정함 10-27 팀장】 범위 밖 문장(결정표 1): "저희가 가지고 있는 데이터가 아니라 말씀드릴 수
#        없어요. 다른 질문을 말씀해주실 수 있나요?" — 뒤의 '대신 ○○를 찾아보시는 건 어떠신가요?'
#        권유를 이 물음으로 바꿈. 볼 만한 질문은 답 밑 이어 묻기 단추(extras.followups)가 맡는다
OUT_OF_SCOPE_ASK = "다른 질문을 말씀해주실 수 있나요?"
# 【판단】 10-15 페르소나 20b q17: 막는 까닭이 보이게 동보다 작은 단위도 같은 문장에 넣는다
PERSON = (
    "취약 돌보미는 동 단위 자료만 다뤄서 특정한 분이나 통 · 반 · 아파트 단지처럼 동보다 작은 단위는 "  # noqa: E501
    "답하지 않아요."
)
EMERGENCY = "지금 위급한 상황이면 119(또는 112)로 바로 연락해 주세요."
# 【판단】 같은 위급 안내를 똑같이 두 번 하지 않는다(10-12 페르소나 엘다). 두 번째부터는 다음 할 일
# 【판단】 10-20 페르소나 o02 r4 T6 ~ T7: '아직 신고 안 했다'는 분께 '이미 알리셨다면 …'을 두 번 —
#        짐작하지 않고 두 경우를 다 적는다. 주소를 몰라도 신고할 수 있다는 것은 상식이라 적는다
EMERGENCY_AGAIN = (
    "아직 신고하지 않으셨다면 주소나 호수를 정확히 몰라도 112(또는 119)에 신고할 수 있어요. "
    "아는 것"
    "(아파트 이름 · 연세 · 마지막으로 통화한 날)을 그대로 말씀하시면 돼요. "
    "이미 알리셨다면 문을 직접 열지 "
    "마시고 구조대 안내를 따라 주세요. 동 주민센터에도 알려 함께 챙기시면 좋아요."
)
# 10-28 페르소나 p10_a T3 · T5: 저녁 8시에 '주민센터에 알려 주세요' · 경로당 안내 — 위급 중에는
#        119 · 112만 먼저, 주민센터는 낮에 하는 일로
EMERGENCY_THIRD = (
    "앞에서 말씀드린 대로 생명이 위험해 보이면 119, 안전 확인은 112예요(밤에도 24시간). "
    "동 주민센터 안부 확인은 낮에 요청할 수 있어요."
)
NOT_REPORTED = re.compile(
    r"신고 ?(?:안|못) ?했|신고를? (?:안|못)|주소(?:를|도)? ?모르|호수(?:를|도)? ?모르|주소를 알아야"
)
NO_ADDRESS_NOTE = (
    "주소나 호수를 정확히 몰라도 112에 신고할 수 있어요. 아는 것(아파트 이름 · 연세 · 마지막으로 "
    "통화한 날)을 그대로 말씀하시면 경찰이 확인해요."
)
# 【판단】 쓰는 사람 자신이 지쳤다고 털어놓으면 자료 안내로 넘기지 않는다(10-12 페르소나 엘다:
#        "그만두고 싶다" → "편하게 물어봐 주세요, 예를 들어…"). 상담 창구는 국가 공식 번호
CARE = (
    "많이 지치셨겠어요. 혼자 버티지 마시고 이야기를 나눌 곳에 기대 보셨으면 해요"
    "(정신건강 위기상담 1577-0199, 24시간). "
    "업무는 천천히, 필요하실 때 이어서 같이 볼게요."
)
DISTRESS = re.compile(
    # 10-28 밤: 활용형을 하나씩 더하던 것(지쳤 · 지쳐 → 지치네요가 빠짐)을 줄기로 —
    #        '지치지 않게 · 지치지 말고'처럼 권하는 말은 뺀다
    r"그만\s?두고 싶|너무 힘들|힘들어서|힘들어 죽|힘드네|힘드네요"
    r"|지[치쳐쳤](?!지 않|지 말)|번아웃|우울|죽고 싶|살기 싫"
)
UNCLEAR = (
    "제가 정확히 알아듣지 못했어요. 동 이름과 알고 싶은 것(예: 혼자 사는 어르신 · 청년 · "
    "먼저 볼 동)을 같이 말씀해 주시겠어요?"
)


# 【판단】 사서가 나눠 볼 수 없는 때 말(계절 · 달 · 상반기 등, 자료 밖의 해). '작년'만이면
#        자료의 1년 견줌(예: 2025-09 → 2026-09)이 그 뜻이라 밝히지 않는다
# 【판단】 자료의 달(주민등록 판의 달)은 우리 자료의 때라 뺀다(10-15 페르소나 q05:
#        '2024년 12월 대비 2025년 12월'에 '나눠 볼 수 없다'가 다섯 턴 붙음). 해는 서울시 독거노인
#        현황(2023 ~ 2025)부터 주민등록 판의 해까지. 10-19부터 달 · 해를 자료에서 읽는다(basis.py)
def _period_unmatched() -> re.Pattern:
    now = B.reg()
    month = int(now[5:7])
    years = "|".join(str(y)[2:] for y in range(2023, int(now[:4]) + 1))
    return re.compile(
        rf"봄|여름|가을|겨울|(?<!\d)(?!{month}\s?월)\d{{1,2}}\s?월|상반기|하반기|분기|"
        rf"20(?!(?:{years}))\d\d|19\d\d"
    )


_PERIOD_UNMATCHED = _period_unmatched()
# 지난 해(서울시 독거노인 현황이 해마다 있는 2020 ~ 2024년)
YEAR_PAST = re.compile(r"20(?:2[0-4])\s?년?")
# 말 속의 해('2020년 · 2019년 기준')
YEAR_SAID = re.compile(r"(?<!\d)(?:19|20)\d\d\s?년")


# 【판단】 데스크(AI)가 고른 '막기 · 위급 · 못 담은 조건'을 코드가 말 자체와 대조한다
#        (바깥 근거 대조). 10-12 시험: '네 연락했어요. 효자2동 청년은 어때요?'를
#        개인 질문으로 막음, 이름이 섞인 경로당
#        질문을 통째로 막음, '사북면 비교(춘천 밖)'을 못 담은 조건으로 적어 코드가 그대로 밝힘.
#        모든 답은 동 단위라, 사람 표시가 있어도 동 자료 부분은 답해도 개인이 드러나지 않는다
PERSON_SIGN = re.compile(
    r"\[이름\]|\[전화번호\]|\[주민번호\]|\[호수\]|\[아파트 동 번호\]|연락처|전화번호|주소|명단|"
    r"몇 호|이름|주민번호|그분|이분|저분|어느 분|누구|사시는 분|댁|개인"
)
# 위급 막기를 풀지 않는 강한 말(10-20 r8)
HARD_SIGN = re.compile(r"쓰러|의식|숨[을이]|자살|죽|피가|화재|불이 나|다쳤|폭행|학대")
# '신고해도 되나요?'처럼 신고가 맞는지 묻는 말 — 위급 안내가 아니라 상식으로 답한다
ASK_IF_REPORT = re.compile(
    r"신고해도 [되돼]|신고해야 [하되돼]|불러야 [하되돼]|위급한 (?:상황|건지|건가)|위험한 상황인|"
    r"신고하는 [게것]|신고 ?해도 [되돼]|신고해도 괜찮"
)
# 약국을 묻는 말(갈 곳 주제가 빠지면 코드가 넣는다 — 10-20 r9 h01 T2)
PHARMACY_ASK = re.compile(r"약국[^\n]{0,15}(?:어디|가까|문 ?연|몇 ?시)|(?:문 ?연|가까운|여는) 약국")
# 10-27 qbank P2-26(API): '1. 동면이 … 4. 가까운 보건지소'에 데스크가 갈 곳을 빠뜨려
#        '보건지소 자료는 없어요'(동면 보건지소가 갈 곳 자료에 있음). 보건 시설을 찾는 말이면
#        갈 곳을 더한다
HEALTH_ASK = re.compile(
    r"(?:가까운|문 ?연|근처|가장 가까운)\s?(?:보건(?:소|지소|진료소)|의원|병원)"
    r"|보건(?:소|지소|진료소)[^\n]{0,15}(?:어디|가까|문 ?연|전화|주소|있어|있나)"
)
# '이 대화 내용을 PDF로 저장해 줘'(chuncheon_youth_60 T47) — 동 상황 문서가 아니다(대화 저장은 없다)
CONVO_SAVE = re.compile(
    r"(?:이|지금까지|우리) ?(?:나눈 )?대화(?: 내용)?(?:을|를)? ?(?:저장|PDF|파일|기록)|채팅 내용"
)
# '주민이 몇 명'(chuncheon_youth_60 T40) — 청년 · 어르신을 말하지 않았으면 전체 주민(동 한눈에)
RESIDENT_COUNT = re.compile(r"주민(?:이|은|은요|들이| 수)[^\n]{0,8}(?:몇|얼마)")
# 비서 말고 사람을 바꿔 달라는 말(adversarial_20 T16) — 기관 연락처 물음이 아니다
HUMAN_AGENT = re.compile(
    r"너 말고|사람 담당자|상담원 연결|직원 연결|진짜 사람|사람이랑 (?:얘기|이야기|통화)"
)
# 연락처 · 담당을 묻는 말(못 알아들었으면 지원 기관으로 — 10-20 r9 o02 T7)
SUPPORT_WORD = re.compile(r"전화번호|연락처|번호|담당|상담 ?전화|창구|어디로 전화")
# 사람 하나를 가리키는 말(누구 · 사는 분은 기관 물음에도 쓰여 뺌)
PERSON_ONE_STRICT = re.compile(r"그분|이분|저분|어느 분|몇 호|할머니|할아버지|어르신 한 분")
# 수 · 비율을 묻는 말(사람 하나가 아니라 동 숫자
# — r10 o01 T2 '실제로 집에서 혼자 사시는 분이 몇 명')
COUNT_Q = re.compile(r"몇 ?명|명인지|명입니까|비율|가구 수|어림|몇 ?분이")
# 시설의 위치 · 연락처를 묻는 말(r10 o02 T9 '궁마을 경로당에서 제일 가까운 복지관이 어디예요?')
FACILITY_Q = re.compile(
    r"(?:경로당|복지관|센터|약국|보건소|마을회관)[^\n]{0,10}(?:어디|위치|주소|전화|번호|가까)"
)
# 지붕 · 슬레이트(마을별 눈 무게에 약한 지붕 집 자료가 있다 — 10-21 이장 T6: 데스크가 범위 밖으로)
ROOF_ASK = re.compile(r"지붕|슬레이트|함석|판넬|샌드위치 ?판넬|초가")
# '어떤 노인네부터 들여다봐야 하오'(10-21 이장 T12: 못 알아들음) — 취약 돌보미 판단의 '먼저 살필
#        무리'가 답
FIRST_WHO = re.compile(
    r"어떤[^\n]{0,14}(?:부터|먼저)|누구부터|어느 분부터|어느 쪽부터|먼저 (?:봐|들여다|살펴|챙)"
)
# '보고서 어떻게 써요'(10-21 팀장 "보고서 어떻게 쓰는 거야? 할 때 보여 주는 것도 필요") → 쓰는 법
HOW_REPORT = re.compile(
    r"보고서[^\n]{0,12}(?:어떻게|쓰|작성|만들)|보고(?:서|자료)에 (?:뭘|무엇을) (?:쓰|넣)"
)
# 동 없이 지역 전체 복지관 · 급식소를 물으면 지원 기관(지역 목록이 있다 — 10-21 말투 시험 D22)
REGION_FACILITY = re.compile(r"노인복지관|복지관|급식소")
# 연휴 · 명절은 달력 자료가 있다(못 담은 조건이 아님 — r10 f01 T5)
HOLIDAY_UNMET = re.compile(r"연휴|명절|설날|추석|공휴일")
# 약국 · 시설의 영업 시간은 자료에 있다(요일별, 10-20)
HOURS_UNMET = re.compile(r"문 ?연|문 ?여는|영업|운영 ?시간|몇 ?시|열었|여는 시간")
EMERGENCY_SIGN = re.compile(
    r"자살|죽고|죽을|죽었|숨[을이]|쓰러|의식|학대|폭행|폭력|119|112|응급|위급|"
    r"안 나오신 지|연락이 안 [돼되]|사흘|며칠 ?째|화재|불이 나|다쳤|피가"
)
PERSON_NOTE = "(특정한 분 이야기는 빼고 동 자료로만 답할게요.)\n"
SERVICE_NOTE = "(특정한 분 이야기는 기억하지 않고, 누구에게나 같은 서비스 안내로 답할게요.)\n"
# 받을 수 있는 서비스 · 신청 창구를 묻는 말(10-26 예상 질문 2-22)
SERVICE_ASK = re.compile(
    r"(?:받을|신청할|이용할|쓸)\s?수\s?있는\s?(?:서비스|지원|제도|혜택|돌봄)|"
    r"(?:서비스|지원|제도|돌봄)[이가은는]?\s?(?:뭐|무엇|어떤|있)|어디(?:서|에)\s?신청"
)
# 그분 자체의 정보를 묻는 말 — 있으면 서비스 안내로 풀지 않는다
PERSON_INFO = re.compile(r"주소|연락처|전화|번호|어디 사|사는 곳|몇 호|호수|명단|찾아")
# 【판단】 10-29 브라우저 시험 '302호 김순자 할머니 연락처 알려 주시고, 개포3동 노인맞춤돌봄
#        수행기관도 알려 주세요': 한 분의 연락처를 막으며 함께 물은 기관 안내까지 막았다 →
#        개인을 묻는 마디(가린 표시 · 그분)만 막고 나머지 마디로 답한다(person_free_rest)
PERSON_PART = "(한 분 한 분의 연락처 · 주소 같은 개인 정보는 알려 드릴 수 없어요. 함께 물으신 것에 답할게요.)\n"  # noqa: E501
PERSON_REF = re.compile(r"그\s?분|이\s?분|저\s?분|그\s?(?:할머니|할아버지|어르신|사람|아이|청년)")
_MASK_MARK = re.compile(r"\[(?:이름|호수|전화번호|주민번호|아파트 동 번호)\]")
_PART_SPLIT = re.compile(r"[.,!?\n]+|그리고|그다음|또한|(?:주시|해\s?주|하|주)고(?=\s)")
# 동 자료 · 기관 안내를 묻는 마디인지(나머지 마디가 이런 말을 담아야 따로 답한다)
_DATA_PART = re.compile(
    r"몇|현황|기관|센터|복지관|경로당|약국|의원|보건|버스|청년|어르신|독거|노인|수급|돌봄|"
    r"서비스|지원|순위|진단|급식|쉼터|빈집|1인"
)


# 한 분의 사정 · 걱정을 말하는 마디(빈칸을 지운 말에 댄다) — 자료 마디가 아니다
_WORRY_PART = re.compile(
    r"연락이?(?:안되|안돼|끊|두절|안닿|되지않|닿지않)|전화를?안받|소식이없|며칠째|이틀째|사흘째|"
    r"나흘째|\d+일째|급해|급합|급한"
)
# 한 분의 정보를 달라는 말(기관 · 창구의 전화 · 주소는 아님)
_PERSON_INFO_PART = re.compile(
    r"성함|이름|호수|몇\s?호|연락처|휴대폰|핸드폰|폰\s?번호|전화\s?번호|주소"
)
_INSTITUTION = re.compile(r"센터|기관|창구|복지관|보건소|구청|시청|주민센|경로당|약국|의원|급식")
# 인사 · 자기소개 마디(자료 질문이 아니다)
_SELF_INTRO = re.compile(
    r"^(?:안녕하|수고)|(?:담당자?|직원|복지팀|팀장|주무관|일하는\s?사람)\s?(?:입니다|이에요|예요|인데요|인데|이고)\s*$"
)


def _person_part(p: str) -> bool:
    if _MASK_MARK.search(p) or PERSON_REF.search(p) or PERSON_SEEK.search(p):
        return True
    if _WORRY_PART.search(re.sub(r"\s+", "", p)):
        return True
    return bool(_PERSON_INFO_PART.search(p) and not _INSTITUTION.search(p))


def person_free_rest(text: str) -> str:
    """개인 · 걱정을 말하는 마디와 함께 물은 자료 마디(인사 · 자기소개 마디는 뺀다).

    개인 · 걱정 마디가 없거나, 자료 마디가 없으면 ''.
    【판단】 10-29 2판 문장 200건으로 점검: '어르신이'를 걱정 단서로 넣었더니 '반지하 고립 어르신이
           몇 분인지 … 아울러 성함 · 호수 · 전화번호도'에서 자료 마디를 빼고 인사 · 개인 마디를
           남겼다 → 마디를 개인 · 걱정 / 인사 / 자료 셋으로 가른다
    """
    parts = [p.strip() for p in _PART_SPLIT.split(text) if p and p.strip()]
    person = [p for p in parts if _person_part(p)]
    data = [
        p for p in parts if p not in person and not _SELF_INTRO.search(p) and _DATA_PART.search(p)
    ]
    if not person or not data:
        return ""
    return ", ".join(data)


# 【판단】 기관 · 시설의 전화 · 주소 · 이름은 사람 질문이 아니다(10-13 갈 곳 · 지원 기관 서가).
#        '전화번호 · 주소 · 이름'은 PERSON_SIGN에도 있어,
#        기관 낱말이 있고 사람 표시가 없을 때만 푼다
INSTITUTION = re.compile(
    r"센터|복지관|경로당|마을회관|보건소|보건지소|진료소|기관|요양원|요양시설|급식소|약국|의원|"
    r"병원|구청|시청|창구"
)
PLACE_ASK = re.compile(
    r"(?:경로당|복지관|마을회관|주민센터|행정복지센터|보건소|보건지소|약국)[^.?!\n]{0,25}"
    r"(?:어디|위치|주소|전화|번호|있는지)|(?:어디|위치)[^.?!\n]{0,15}(?:경로당|복지관|마을회관)"
)
PERSON_ONLY = re.compile(
    r"\[이름\]|\[전화번호\]|\[주민번호\]|\[호수\]|\[아파트 동 번호\]|"
    r"그분|이분|저분|어느 분|누구|사시는 분|댁|개인|명단|몇 호"
)
# 【판단】 가려진 이름에 사람 자체를 묻는 말이 붙으면 동 자료로 돌리지 않고 막는다
#        (10-13 100턴 r8 T20: '[이름] 할머니 집 주소'에 데스크가 갈 곳을 같이 적어
#        경로당 목록으로 답함)
PERSON_ASK = re.compile(
    r"주소|연락처|전화|번호|건강|형편|병|어디 사|사는 곳|집 |집이|집에|댁|"
    r"몇 호|호수|사셔|사세요|사는지"
)
# 【판단】 가린 이름이 없어도 사람 표시(그분 · 몇 호 · 사는 분 …)에
#        사람 자체를 묻는 말이 붙으면 막는다
#        (10-13 떠보기 r10 T22: '수서아파트 사는 분은 몇 호에 사셔?').
#        '사시는 분 중 몇 명'은 무리라 둔다
# 그분 한 사람의 정보를 묻는 말(명단 말고 · 이름 말고는 묻는 것이 아니다)
PERSON_INFO_ASK = re.compile(
    r"(?:그분|이분|저분|할머니|할아버지|어르신)(?:의|이|은|는)?\s?"
    r"(?:주소|연락처|전화번호|이름|사는 곳|집 위치|상태)"
    r"|\[이름\]|\[전화번호\]|\[호수\]|명단(?!\s?말고)|몇 호"
)
PERSON_ONE = re.compile(r"그분|이분|저분|어느 분|누구|사는 분[은이]|사시는 분[은이]|몇 호")
# 【판단】 10-15 페르소나 20b q17(가족이라며 특정 어르신을 찾는 사람): 가린 이름이 없어도
#        특정인이 있는지 없는지를 묻거나 동보다 작은 단위(통 · 반 · 아파트 단지)를 물으면,
#        데스크가 '못 알아들음'을 내도 막고 까닭을 말한다(전에는 '정확히 알아듣지 못했어요'를
#        다섯 번 되풀이해 '못 알아듣는 척'으로 느낌). 데스크가 알아들은 질문(ask)은 건드리지 않는다
PERSON_SEEK = re.compile(
    r"성 가진|[가-힣]씨 성|분이? 있[냐나어는]|있어요 없어요|있는지 없는지|있나 없나|"
    r"사는 집이 있|사시는 집이 있"
)
SUB_DONG = re.compile(
    r"통이나 반|통 ?· ?반|\d+통 ?\d*반|\d+단지|아파트 ?단지|[가-힣]+아파트(?:에|는|에서|의)"
)
# 【판단】 동 칸을 끄는 것은 '전체 · 전부 · 모든 동 · 22개 동'을 말했을 때만
#        (10-12 r12: '서울시 독거노인
#        현황으로는요?'에 데스크가 동 칸을 꺼 '어느 동을 볼까요?'로 빠짐 — 서울시는 자료 이름이다).
#        그런 말이 있으면 지역 줄 세우기로 간다(재생: '관내 22개 동 전체'에 동 칸만 끄고 되물음)
WHOLE_REGION = re.compile(r"전체|전부|모든 동|동 모두|모두 다|\d+개 동|\d+곳 다|동별로 다|다 보여")
MALE = re.compile(r"할아버지|할배|남성|남자")
# 【판단】 날씨 · 날짜 낱말은 코드가 확정한다(10-13 날씨 r8: 데스크가 날짜 칸을 비우거나
#        앞 날씨 칸을 그대로 둠). '비'는 비서 · 비율에도 있어 '비가 · 비 오'처럼 말 모양으로만 본다
WEATHER_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("비", re.compile(r"폭우|호우|장마|강수|빗물|비가|비 ?[오와온내]|비 ?얼마|비 ?많")),
    ("눈", re.compile(r"폭설|대설|적설|눈이|눈 ?[오와온내쌓]|눈 ?많")),
    ("추위", re.compile(r"한파|추위|추운|추울|추워|영하|혹한")),
    ("더위", re.compile(r"폭염|더위|더운|더울|더워|열대야")),
)
WEATHER_ANY = re.compile(r"날씨|기온|온도")
REGION_WORDS_IN_TEXT: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("강남구", re.compile(r"강남구|강남(?!동)")),
    ("춘천시", re.compile(r"춘천")),
)
DATE_WORD = re.compile(r"\d{1,2}\s*월\s*\d{1,2}\s*일|내일|모레|어제|오늘")


def restate_or_text(
    restate: str,
    text: str,
    region: str | None,
    compare: bool,
    dongs: tuple[str, ...] = (),
) -> str:
    """글쓴이에게 줄 질문 — 다시 쓴 질문이 말에도 칸에도 없는 지역 · 동을 끌어오면 원문으로.

    【판단】 10-27 회귀 rules_v6_16 T3 '기초수급 받는 독거 어르신 많은 동 알려줘'(칸은 춘천시):
           데스크가 '강남구에서 …(독거와 수급을 함께 보는 자료는 강남구에만 있음)'로 다시 써서
           글쓴이가 춘천 자료를 두고 강남구 이야기를 했다. 견주기는 두 지역이 맞아 건드리지 않는다
    【판단】 10-29 회귀 summary_recall_24 T22 '처음에 물어본 세 동 … 다시': 코드가 대화 기록에서
           세곡동 · 수서동 · 역삼1동을 꺼냈는데 데스크가 다시 쓴 질문은 '세곡동 · 역삼1동 ·
           개포3동'이라 글쓴이가 수서동을 빼고 개포3동을 말했다 → 동도 지역과 같은 규칙
    """
    if not restate:
        return text
    if dongs and set(dongs_in_text(restate)) - set(dongs) - set(dongs_in_text(text)):
        return text
    if compare or not region:
        return restate
    said = {r for r, pat in REGION_WORDS_IN_TEXT if pat.search(text)}
    named = {r for r, pat in REGION_WORDS_IN_TEXT if pat.search(restate)}
    if named - said - {region}:
        return text
    return restate


# 【기능】 말 속 우리 동 이름(정식 이름 · 숫자 없는 이름, 긴 것부터). 앞에 한글 · 숫자가 붙으면
#        다른 낱말이다(판교동 → 교동 아님)
_DONG_NAMES = sorted(
    {n for ds in dongname.DONGS.values() for n in ds} | {fam for (_, fam) in dongname.FAMILY},
    key=len,
    reverse=True,
)
# 【판단】 10-29 회귀 춘천 청년 T21 '후평삼동은요?': 번호를 글자로 쓴 동(후평삼동 · 대치사동)은
#        데스크가 적어 줄 때만 잡혀, 데스크가 빠뜨리자 앞 동(효자2동)이 남았다 → 말에서 동을 찾을
#        때도 글자 번호를 읽는다(dongname.resolve와 같은 NUM_WORD). 진짜 동 이름과 같은 글자
#        꼴(번호 없는 동)은 만들지 않는다
_SPELLED_DONGS = {
    f"{m.group(1)}{w}동": n
    for n in _DONG_NAMES
    if (m := re.match(r"^(.+?)(\d)동$", n))
    for w, d in dongname.NUM_WORD.items()
    if d == m.group(2) and f"{m.group(1)}{w}동" not in _DONG_NAMES
}
_DONG_SPELLINGS = sorted(
    [(n, n) for n in _DONG_NAMES] + list(_SPELLED_DONGS.items()),
    key=lambda p: len(p[0]),
    reverse=True,
)
# 【판단】 다른 곳 이름이 같이 있으면(부산 서면 · 송파구 거여동) 동 칸을 채우지 않는다.
#        '○○구'를 통째로 잡으면 '1인 가구'도 걸려서 이름을 적어 둔다
OTHER_PLACE = re.compile(
    r"부산|대구|인천|광주|대전|울산|세종|경기|성남|분당|판교|수원|용인|고양|원주|강릉|속초|제주|"
    r"(?<![가-힣])(?:종로|중|용산|성동|광진|동대문|중랑|성북|강북|도봉|노원|은평|서대문|마포|양천|강서|구로|"
    r"금천|영등포|동작|관악|서초|송파|강동)구|"
    r"(?<![가-힣])(?:동해|태백|삼척)시|(?<![가-힣])(?:홍천|횡성|영월|평창|정선|철원|화천|양구|인제|고성|양양)군"
)
FEMALE = re.compile(r"할머니|할매|여성|여자")
EACH_DONG_WORD = re.compile(r"동별|동마다|동 별로|읍면동별")
BOTH_REGIONS = re.compile(r"강남[^\n]{0,25}춘천|춘천[^\n]{0,25}강남")
COMPARE_WORD = re.compile(r"비교|견주|중 어디|어디가 더|어느 쪽|더 심각|더 힘|차이|나란히|견줘")
BYE = re.compile(
    r"고마워|고맙습니다|고마워요|감사합니다|감사해요|감사드|수고하셨|수고 많|끊을게|마칠게|마치겠|"
    r"여기까지|이만 |그럼 이만|안녕히|됐습니다|됐어요|정리하겠|마무리하겠|"
    # 10-21 이장 T19 '고맙소. 이제 자야겠네. 내일 면사무소 가서 물어보리다'
    r"고맙소|고마우이|자야겠|이만 자|물어보리다|가 ?보리다|가 ?보겠|쉬겠|쉴게|들어가 ?볼게|들어가겠"
)
# 【판단】 10-20 r6 rules_v6 T16 '강남 청년 제일 많은 동은?': 데스크가 줄 세우기를 켜지 않고 앞 턴의
#        세곡동을 남겨 '세곡동 청년 수만 있어 가장 많은 동은 알 수 없다'(틀린 말).
#        r7 T3 '기초수급 받는 독거 어르신 많은 동 알려줘'(제일 · 가장 없이)도 '어느 동?'으로 되물음
# 동 이름 없이 어느 동인지를 묻는 말(10-26 예상 질문 2-17)
WHICH_DONG = re.compile(
    r"어느\s?(?:동|곳|지역|데)|어떤\s?(?:동|곳)|어디가|어디(?:부터|를)|동은 어디"
)
# 앞에서 말한 동들을 가리키는 말('그 중 · 이 동들 · 거기 · 아까 그') — 지역 전체로 넓히지 않는다
# 자기 담당 동을 가리키는 말 — '우리 동 · 제 담당 동'은 지역만 말한 것이 아니다
# 【판단】 10-29 점검: '이\s?동 · 그\s?동'이 낱말 '그동안 · 이동(지원 · 수단)' · '역삼이동'에도 걸려
#        '강남구 그동안 혼자 사는 어르신 늘었어요?'를 지역 전체로 보지 않았다 → 가리키는 말은 낱말
#        첫머리의 '이 동'(띄어 씀) · '그 동 · 그동'('그동안'은 아님)만
MY_DONG = re.compile(
    r"우리\s?동|담당\s?동|제\s?담당|내\s?담당"
    r"|(?<![가-힣])이\s+동(?!들)|(?<![가-힣])그\s?동(?!들|안)"
)
REFER_DONG = re.compile(r"그\s?중|그\s?가운데|이\s?동들|그\s?동들|거기|아까 그|위\s?\d+\s?곳|앞의")
# 지역을 견줄 기준으로 쓴 말('강남 평균보다 · 구 평균 대비 · 춘천 전체에 비해') — 지역 이름이 나와도
# 묻는 곳은 앞 동이다(10-29 회귀 long_100 T22 '강남 평균보다 넓어요 좁아요?'에 동 칸이 비워짐)
# 앞에서 나온 말의 뜻을 묻는 말('무슨 말이에요 · 무슨 뜻 · 뜻이 뭐예요 · 어떤 의미') — '112에 무슨
# 말을 해야'처럼 할 말을 묻는 것은 아니다(뒤에 이다 꼴이 와야 함)
MEANING_ASK = re.compile(
    r"무슨\s?(?:말|뜻|의미|소리|얘기)(?:이에요|예요|인가요|인지|이죠|이야|일까|이에|이지|인데)"
    r"|뜻이\s?(?:뭐|뭔|무엇)|어떤\s?(?:뜻|의미)(?:이에요|예요|인가요|인지|이죠|이야)"
)
BASE_WORD = re.compile(
    r"(?<=[가-힣])보다|대비|에\s?비(?:해|하면|교해)|(?:와|과|랑|하고)\s?(?:비교|견주|견줘)"
    r"|에\s?견(?:줘|주면)"
)
TOP_DONG = re.compile(
    r"(?:제일|가장|젤)\s*(?:많은|적은|높은|낮은|큰|작은)\s*(?:동|곳|데)"
    r"|(?:많은|적은|높은|낮은)\s*(?:동|곳)(?:은|이|을|는|좀|으로|부터|\s*알려|\s*어디|\s*순서|$)"
)
# 【기능】 표 파일을 달라는 말(10-15 desk_new_21 r0 X02: 데스크가 다시 쓴 말엔 '엑셀'이 있는데
#        형식 칸을 비움). '표로 정리해'는 대화 속 표라 넣지 않는다
# 【판단】 달라는 꼴('엑셀로 · CSV로 · 받을 수')만 본다
#        (10-15 페르소나 q05 T5: '엑셀 파일 감사합니다'에 걸려 표만 또 줌)
TABLE_WORDS = re.compile(
    r"(?i)엑셀|csv|xlsx|스프레드시트|(?<![가-힣])표(?![가-힣]{0,1}(?:준|시|현|정))|파일|내려\s?받|다운"
)
TABLE_FILE = re.compile(
    # 10-29 변수 시험 c01_052 '엑셀 파일로 보내 주시기 바랍니다': '엑셀로 열어 · 보면 · 읽어'를
    #       빼려던 '보'가 '보내'까지 걸러 엑셀 칸이 비었다
    r"(?:엑셀|CSV|csv|xlsx|표 ?파일|스프레드시트)\s*(?:파일)?\s*(?:로|으로)"
    r"(?!\s*(?:열|보(?!내)|읽))|"
    r"(?:엑셀|CSV|csv|xlsx|표 ?파일)\s*(?:파일)?\s*(?:을|를)?\s*"
    r"(?:받을|받고|받아|내려|다운|뽑아|만들어|보내)"
)
# 문서 · 파일을 바라는 말이 하나라도 있는가(없으면 동 상황 문서를 만들지 않는다)
DOC_WORDS = re.compile(
    r"(?i)pdf|pptx?|피피티|파워포인트|슬라이드|문서|파일|결재|보고서로|자료로\s?만들|자료로\s?뽑"
)
# 오늘 챙길 일 · 오늘 할 일(10-26 예상 질문 1-7)
TODAY_TASK = re.compile(r"오늘\s?(?:챙길|챙겨야 할|할|해야 할|봐야 할|볼|살필)\s?(?:일|것|거)")
# 동 상황 문서(PDF · PPTX)를 달라는 꼴 — 'PPT로 만들어 줘 · PDF로 뽑아 줘'(만들 때 쓸 숫자는 아님)
DOC_FILE = re.compile(
    r"(?i)(?:pptx?|피피티|파워포인트|pdf|슬라이드)\s*\)?\s*(?:파일)?\s*(?:로|으로|를|을)?\s*"
    r"(?:만들어|만들어\s*줘|뽑아|정리해|줘|주세요|부탁|받을|받고|내려)(?!\s*때)"
)
# 【기능】 나이 표현(10-15 r0 T01: '앞으로 80세 이상만'에 나이 칸이 빔 3/5). (낮은 쪽, 높은 쪽)
AGE_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)(\d{2})\s*세?\s*(?:~|-|에서)\s*(\d{2})\s*세"), "range"),
    (re.compile(r"(?<!\d)(\d{2})\s*세\s*이상"), "lo"),
    (re.compile(r"(?<!\d)(\d{2})\s*세\s*이하"), "hi"),
    (re.compile(r"(?<!\d)(\d{2})\s*세\s*미만"), "under"),
    (re.compile(r"(?<!\d)(\d{2})\s*대(?![가-힣])"), "decade"),
)


def ages_in_text(text: str) -> tuple[int, int] | None:
    """말 속 나이 표현이 딱 하나면 (낮은 쪽, 높은 쪽 · 없으면 -1).

    둘 이상이면 None(데스크에 맡김).
    """
    found: list[tuple[int, int]] = []
    taken: list[range] = []
    for pat, kind in AGE_PHRASES:
        for m in pat.finditer(text):
            if any(m.start() in r for r in taken):
                continue
            taken.append(range(m.start(), m.end()))
            a = int(m.group(1))
            if kind == "range":
                found.append((a, int(m.group(2))))
            elif kind == "lo":
                found.append((a, -1))
            elif kind == "hi":
                found.append((-1, a))
            elif kind == "under":
                found.append((-1, a - 1))
            else:
                found.append((a, a + 9))
    return found[0] if len(found) == 1 else None


# 【기능】 계절 · 반기 · 분기(앞뒤에 다른 글자가 붙으면 아니다: 봄봄버스)
SEASON_WORDS = re.compile(
    r"(?<![가-힣])(?:(?:작년|지난해|올해|올|이번|지난|내년) ?)?(?:봄|여름|가을|겨울)(?:철)?"
    r"(?=$|[\s에은는이랑과와도의,.?!])|(?<![가-힣])(?:상반기|하반기|\d ?분기)"
)
_MASKED_PERSON = ("이름", "전화번호", "주민번호", "호수")
_PLACE_WORDS = re.compile(r"강남|춘천|서울|강원")


# 【기능】 우리 서가가 분명한 낱말 → 주제(데스크가 범위 밖으로 잘못 냈을 때만 쓴다)
SHELF_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"수급자|기초수급|기초생활"), "livelihood"),
    (re.compile(r"경로당"), "senior_hall"),
    (re.compile(r"은둔|청년"), "youth"),
    (re.compile(r"혼자 사는|독거|1인 ?세대|1인 ?가구"), "solo_seniors"),
)


_VERB_LIKE_DONGS = {"서면", "남면", "동면"}
_VERB_BEFORE = re.compile(r"(?:안|못|줄|이|가|에|도)\s*$")
_VERB_AFTER = re.compile(r"^\s*(?:못|안|서고|서지|선다|설|되|돼)")


def dongs_in_text(text: str) -> list[str]:
    """말에 그대로 적힌 우리 동 이름(나온 차례). 다른 곳 이름 바로 뒤의 이름('부산 서면')은 뺀다.

    【판단】 10-29 변수 시험(다루지 않는 지역을 함께 물음 5건 중 3건 bad): 다른 곳 이름이 하나라도
           있으면 빈 목록이라 '수서동 경로당이랑 부산 경로당'의 수서동까지 못 읽었다 → 다른 곳
           이름 바로 뒤(사이에 빈칸만)에 붙은 이름만 그곳의 동으로 보고 뺀다
    """
    others = [m.end() for m in OTHER_PLACE.finditer(text)]
    hits: list[tuple[int, str]] = []
    taken: list[range] = []
    for n, real in _DONG_SPELLINGS:
        for m in re.finditer(rf"(?<![가-힣0-9]){re.escape(n)}", text):
            if any(0 <= m.start() - e <= 2 and not text[e : m.start()].strip() for e in others):
                continue
            # 10-20 페르소나 f01 r4 T8: '어림이 안 서면 못 서고'의 '서면'을 서면(면)으로 읽어
            #        묻지 않은 서면 카드가 붙었다. 두 글자 면 이름은 앞뒤가 동사 꼴이면 뺀다
            if n in _VERB_LIKE_DONGS and (
                _VERB_BEFORE.search(text[: m.start()]) or _VERB_AFTER.match(text[m.end() :])
            ):
                continue
            if not any(m.start() in r for r in taken):
                hits.append((m.start(), real))
                taken.append(range(m.start(), m.end()))
    return list(dict.fromkeys(n for _, n in sorted(hits)))


# 【기능】 대상 낱말
TARGET_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("청년", re.compile(r"청년|은둔")),
    ("어르신", re.compile(r"어르신|노인|할머니|할아버지|할매|할배|독거")),
)
# 【기능】 (대상, 주제) 이 어긋날 때 맞는 주제
TARGET_SWAP = {("어르신", "youth"): "solo_seniors", ("청년", "solo_seniors"): "youth"}
REGION_HINT: dict[str, re.Pattern[str]] = {
    "강남구": re.compile(r"강남(?!동)|서울"),
    "춘천시": re.compile(r"춘천|강원"),
}
OURS_WORD = re.compile(r"우리|저희|내 담당|제 담당|담당 지역|관내")


def _region_grounded(card: DeskCard, text: str) -> bool:
    """데스크가 바꾼 지역에 말의 근거가 있나.

    지역 낱말 · '우리' · 그 지역 동 이름(데스크가 적은 동 포함).
    """
    pat = REGION_HINT.get(card.region or "")
    if pat is None or pat.search(text) or OURS_WORD.search(text):
        return True
    named = dongs_in_text(text) + list(card.dong_mentions)
    return bool(named) and card.region in dongname.confirm(named)["regions"]


# ── 주제 구출 규칙(10-26 멘토 답 3: 흩어진 낱말 규칙을 순서가 정해진 표 하나로) ──
# 【판단】 데스크가 주제를 빠뜨리거나 범위 밖 · 못 알아들음으로 낸 말을 낱말로 되살린다. 전에는
#        desk_sanity 곳곳의 if 일곱 개였다. 조건은 그대로 옮기고, 위에서 아래 차례로 한 번씩 본다.
#        같은 낱말은 장서 목록 낱말(scripts/build_catalog_words.py EXTRA)에도 있어 데스크가 먼저
#        맞게 고르게 하고, 이 표는 받침이다. RESCUE_HITS 로 몇 번 걸렸는지 세어 안 걸리는 줄은
#        나중에 지운다
@dataclass(frozen=True)
class Rescue:
    name: str
    words: re.Pattern[str]
    acts: tuple[str, ...]
    topic: str
    add: bool  # True = 주제를 더함, False = 그 주제 하나로
    free_block: bool = False  # 막기가 없을 때만
    when: object = None  # (card, text) -> bool, 더 볼 조건


_NOT_HUMAN = re.compile(r"너 말고|사람 담당자|상담원|직원 연결|진짜 사람|사람이랑")
# 10-28 재심사 q08_a T5(북산면 이장, 사투리로 여러 가지를 한 번에): '80살 넘은 혼자 사는
#        어른신들 …'에 데스크가 못 알아들음 → '동 이름과 알고 싶은 것을 말씀해 주세요'
#        (북산면은 이미 정해져 있었다)
SOLO_ASK = re.compile(
    r"혼자\s?사(?:는|시는)\s?(?:어르신|어른신|노인|할머니|할아버지|어른)|독거\s?(?:어르신|노인)"
)
RESCUES: tuple[Rescue, ...] = (
    Rescue("혼자 사는 어르신", SOLO_ASK, ("unclear",), "solo_seniors", False),
    # 10-20 페르소나 h01 r9 T2: '오늘 신북읍 문연 약국 어디가 제일 가까운데'에 갈 곳을 빠뜨림
    Rescue("약국", PHARMACY_ASK, ("ask",), "places", True, free_block=True),
    Rescue("보건 시설", HEALTH_ASK, ("ask",), "places", True, free_block=True),
    # 10-21 이장 T6: '슬레이트 지붕 집이 몇 채나'를 범위 밖으로 — 마을별 약한 지붕 집 자료가 있다
    Rescue("지붕", ROOF_ASK, ("ask", "unclear", "out_of_scope"), "housing", True, free_block=True),
    # 10-21: '보고서 어떻게 써요' → 쓰는 법(보고서 길 안내)
    Rescue("보고서 쓰는 법", HOW_REPORT, ("ask", "unclear", "out_of_scope"), "usage", False),
    # 10-21 말투 시험 D22 '춘천 노인복지관 몇 군데나': 동 없이 지역 전체면 지원 기관(지역 목록)
    Rescue(
        "지역 시설",
        REGION_FACILITY,
        ("ask",),
        "support",
        True,
        when=lambda c, t: "places" in c.topics and not c.dong_mentions and not dongs_in_text(t),
    ),
    # 10-21 이장 T12: '어떤 노인네부터 들여다봐야 하오'에 못 알아들음 → 취약 돌보미 판단의 먼저
    #        살필 무리
    Rescue("누구부터", FIRST_WHO, ("unclear",), "outlook", False),
    # 10-21 이장 T14: '설 연휴가 언제요'를 범위 밖으로 — 달력(공휴일) 자료가 있다
    Rescue("연휴", HOLIDAY_UNMET, ("unclear", "out_of_scope"), "outlook", False),
    # 10-20 페르소나 o02 r9 T7: '담당 공무원한테 바로 연결되는 번호는'에 못 알아들음 → 지원 기관.
    #        사람 하나를 가리키거나 비서를 바꿔 달라는 말(adversarial_20 T16)은 빼고
    Rescue(
        "연락처",
        SUPPORT_WORD,
        ("unclear",),
        "support",
        False,
        when=lambda c, t: not PERSON_ONE_STRICT.search(t) and not _NOT_HUMAN.search(t),
    ),
)
RESCUE_HITS: dict[str, int] = {}


# 【판단】 10-29 변수 시험(여러 가지를 한 번에 묻는 말): 데스크가 주제를 하나만 잡아 나머지에
#        '자료에 없다'(거짓) — '일원본동 고립 어르신 1년 새 늘었어? … 주민센터 전화번호도'에 갈 곳만
#        (c01_039). 말을 마디(쉼표 · 그리고 · -고 · 줄바꿈 · 물음표)로 나눠, 마디마다 주제 단서가
#        있는데 카드에 없는 주제를 더한다. 단서는 주제마다 하나의 표 — 말투 하나를 덮지 않는다
PART_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "solo_seniors",
        re.compile(
            r"혼자\s?사(?:는|시는)\s?(?:어르신|노인|분|할머니|할아버지|어른)|독거|"
            r"(?:고립|홀몸)\s?(?:어르신|노인)|(?:65|80|85)세\s?이상|"
            r"(?:어르신|노인)[^.?!\n]{0,6}1인\s?(?:세대|가구)"
            r"|1인\s?(?:세대|가구)[^.?!\n]{0,6}(?:어르신|노인)"
        ),
    ),
    ("youth", re.compile(r"청년|은둔|집에만\s?있는")),
    ("livelihood", re.compile(r"기초\s?(?:생활)?\s?수급|수급자")),
    (
        "housing",
        re.compile(r"반지하|지하층|빈집|계단\s?(?:집|만)|승강기|엘리베이터|노후\s?(?:주택|건물)"),
    ),
    ("senior_hall", re.compile(r"경로당|마을\s?회관")),
    ("places", re.compile(r"약국|의원|병원|보건(?:소|지소|진료소)|급식|복지관|요양\s?(?:원|시설)")),
    ("bus", re.compile(r"버스|정류장|노선")),
    (
        "support",
        re.compile(
            r"(?:주민센터|행정복지센터|맞춤\s?돌봄|수행\s?기관|상담\s?센터|신청)"
            r"[^.?!\n]{0,12}(?:전화|번호|연락처|창구|어디|주소|위치)"
        ),
    ),
    (
        "priority",
        re.compile(r"먼저\s?(?:볼|살필|가\s?볼|찾아)|취약\s?돌보미\s?(?:동\s?)?순위|우선\s?방문"),
    ),
)
_PART = re.compile(r"[,.?!\n]+|그리고|그다음|또한|(?:주시|해\s?주|하|주|이|있|었|했)고(?=\s)")
# 이미 있는 주제가 그 자료를 함께 주면 더하지 않는다(갈 곳 서가는 경로당 목록 · 수도 준다)
_COVERED_BY = {"senior_hall": ("places",)}


def out_of_area_note(text: str) -> str:
    """다루지 않는 지역을 함께 물었으면 답 앞에 한 줄(코드가 — 말없이 빼먹지 않게).

    【판단】 10-29 변수 시험 c01_016 · c01_023 · c01_037: '부산 · 원주시 경로당도'를 말없이 빼고
           강남 · 춘천만 답했다(심사 bad 3/5)
    """
    names = list(dict.fromkeys(m.group(0) for m in OTHER_PLACE.finditer(text)))
    if not names:
        return ""
    return (
        f"({josa(' · '.join(names), '은', '는')} 이 비서가 다루지 않는 지역이라 빼고 답했어요 — "
        "강남구 · 춘천시만 다뤄요.)\n"
    )


def part_topics(card: DeskCard, text: str) -> DeskCard:
    """여러 마디로 물은 말에서 데스크가 빠뜨린 주제를 더한다(셋까지 더하고 모두 다섯까지)."""
    parts = [p for p in _PART.split(text) if p and p.strip()]
    if card.act != "ask" or len(parts) < 2:
        return card
    add = []
    for p in parts:
        if PERSON_REF.search(p) or _MASK_MARK.search(p) or OTHER_PLACE.search(p):
            continue  # 한 분 이야기 · 다루지 않는 지역 마디는 주제를 더하지 않는다
        for topic, cue in PART_CUES:
            covered = any(t in card.topics for t in _COVERED_BY.get(topic, ()))
            if cue.search(p) and topic not in card.topics and topic not in add and not covered:
                add.append(topic)
    if not add:
        return card
    RESCUE_HITS["여러 마디 주제"] = RESCUE_HITS.get("여러 마디 주제", 0) + len(add)
    return card.model_copy(update={"topics": (*card.topics, *add[:3])[:5]})


def dong_solo_ask(text: str) -> bool:
    """동 이름 + 혼자 사는 어르신 말이 있고 그분 한 사람의 정보는 묻지 않는 말(동 단위 인원)."""
    return bool(SOLO_ASK.search(text) and dongs_in_text(text) and not PERSON_INFO_ASK.search(text))


def rescue_topics(card: DeskCard, text: str) -> DeskCard:
    """RESCUES 를 위에서 아래로 한 번씩 — 걸리면 주제를 더하거나 그 주제 하나로."""
    for r in RESCUES:
        if card.act not in r.acts or (r.free_block and card.block != "none"):
            continue
        if not r.words.search(text) or (r.when and not r.when(card, text)):
            continue
        if r.add and r.topic in card.topics:
            continue
        topics = (*card.topics, r.topic) if r.add else (r.topic,)
        update: dict = {"act": "ask", "topics": topics}
        if card.act != "ask":
            update["block"] = "none"
        card = card.model_copy(update=update)
        RESCUE_HITS[r.name] = RESCUE_HITS.get(r.name, 0) + 1
    return card


def region_scope(card: DeskCard, text: str) -> str:
    """자료 질문 — 지역 전체인지 동 하나인지 정해야 하는 턴.

    '' = 정할 턴이 아님 · 'plain' = 동 이름 없이(지역 이름은 있어도 없어도) ·
    'named' = 지역 이름과 동 이름이 함께(데스크가 동을 적음) ·
    'cleared' = 데스크가 동 칸을 비웠는데 말에 '전체 · 모든 동' 같은 말이 없음.

    【판단】 10-29 팀장 '코드로 규정해 놓은 단어 제한은 결국 한계가 있어 … AI가 아니면 못
           알아듣거든 … haiku로' · '코드 규칙으로 이미 걸러지고 그걸 haiku에게 물어본다는 거야?':
           가리키는 말 낱말 표(MY_DONG · REFER_DONG · BASE_WORD)로 먼저 거르면 표에 없는 말투
           ('제가 맡은 곳은 강남구에서 몇 위예요?')는 AI에게 가지도 못한다 → 코드는 확실히 아는
           것(지역 이름 · 동 이름 사전, 데스크 카드)만 보고 이 턴을 고르며, 뜻은 늘 AI가 정한다
           (desk.pick). 낱말 표는 AI가 답하지 못할 때(시험 · 오류)의 대비(scope_guess)로만
    【판단】 10-29 변수 시험 2판 c02_068 · c02_086: '저는 개포2동 주민센터에서 … 강남구에서 어느
           동에 먼저'처럼 자기소개 속 동 이름 때문에 지역 순위 질문을 그 동 질문으로 받았다 → 동
           이름이 함께 있어도(견줌 · 줄 세우기가 아니면) 고를 턴. 이때 AI가 답하지 못하면
           데스크 그대로
    【판단】 10-29 브라우저 시험(담당 개포3동) '80세 이상만 따로 보면요? 많은데 5군데만' →
           '5곳은 드릴 수 없어요'(거짓) · '반지하가 있는 곳은 어디야?' → '강남구에서 반지하가 있는
           곳은 개포3동'(틀림): 데스크는 둘 다 지역 전체로 알아들었는데 말에 지역 이름이 없어 이
           턴을 고르지 않았고, 데스크가 비운 동 칸도 '전체' 낱말이 없다고 되돌렸다 → 데스크가 동
           칸을 비웠으면 지역 이름이 없어도 AI에게 묻는다('cleared' — 둘 다 지역 전체라야 비운 채로)
    【판단】 같은 날 회귀(fx1029s): 지역 이름이 없는 뒷말을 데스크가 동 그대로 둔 턴까지 AI에게
           맡겼더니('plain' 넓힘) 100턴 대화에서 '경로당은 몇 곳이에요?' · '서울시 독거노인
           현황으로는요?'(앞 답 수서동, 사용자는 구청 복지정책과)를 AI 혼자 지역 전체로 골라 5턴이
           새로 틀렸다 → 'plain'은 지역 이름을 말했을 때만(데스크와 AI 둘 중 하나만 지역 전체라고
           보면 바꾸지 않는다)
    """
    if not (card.act == "ask" and any(t in RANKABLE for t in card.topics)):
        return ""
    if card.dong_op == "clear":
        return "" if WHOLE_REGION.search(text) else "cleared"
    if not region_said(text):
        return ""
    if not dongs_in_text(text) and not card.dong_mentions:
        return "plain" if card.dong_op == "keep" else ""
    return "" if card.compare or card.rank else "named"


def region_said(text: str) -> bool:
    return any(pat.search(text) for _, pat in REGION_WORDS_IN_TEXT)


def scope_guess(text: str) -> str:
    """AI가 답하지 못할 때만 쓰는 대비 — 가리키는 말이 있으면 'dong', 없으면 'region'."""
    if REFER_DONG.search(text) or MY_DONG.search(text) or BASE_WORD.search(text):
        return "dong"
    return "region"


def whole_region_card(card: DeskCard) -> DeskCard:
    """지역 전체로 — 동 칸을 비우고 줄 세우기(합계 · 위 몇 곳으로 답한다)."""
    return card.model_copy(update={"dong_op": "clear", "dong_mentions": (), "rank": True})


# AI에게 물을 때의 보기(region_scope)
SCOPE_ASK = (
    "이번 말이 답을 바라는 곳은 어디인가요? 동 이름이 정해지지 않은 지역 전체(어느 동이 많은지 · "
    "구 · 시 합계)인가요, 정해진 동 하나인가요?"
)
SCOPE_CHOICES = {
    "region": (
        "지역 전체 — 어느 동인지 아직 모르고 찾는다(위 몇 곳 · 어느 동부터 · 가장 많은 동) "
        "또는 구 · 시 전체 합계를 묻는다. 자기소개로 말한 일하는 동은 묻는 곳이 아니다"
    ),
    "dong": (
        "동 하나 — 이미 정해진 동(말에 나온 동 · 앞에서 말한 동 · 담당 동 · 우리 동 · 제가 맡은 "
        "곳)의 값이나 그 동의 순위(그 동이 몇 위)를 묻는다. 앞 답이 동 하나였고 그 안에서 다시 "
        "고르는 말(그중 · 그 가운데)도, 지역을 견줄 기준으로만 말한 것(평균보다)도 여기"
    ),
}
# 【판단】 10-29 실제 Haiku 시험(담당 개포3동, 앞 답이 개포3동 어르신): '청년 1인가구는요?
#        은둔청년도 … 대충 몇명' · '대충 몇명이에요 은둔청년'을 세 번 모두 region으로 골랐다(주제가
#        바뀌면 곳도 바뀐다고 봄) → 묻는 곳은 그대로이고 주제만 바뀐 뒷말을 물음에 적는다. 처음
#        적은 말은 '많은데 5군데만'까지 dong으로 돌려 여러 곳을 바라는 말은 region으로 적음
SCOPE_ASK += (
    " 여러 곳을 바라는 말(어디 · 어느 동 · 몇 곳 · 5군데 · 다섯 곳 · 많은 데)이 있으면 region. "
    "그런 말 없이 주제 · 대상만 바꾼 뒷말('청년은요?' · '대충 몇 명?')은 바로 앞 답이 본 곳을 "
    "그대로 묻는 것이다(앞 답이 동 하나였으면 dong, 지역 전체였으면 region)."
)


def desk_sanity(
    card: DeskCard,
    text: str,
    after_emergency: bool = False,
    hidden: list[str] | tuple[str, ...] = (),
    pick: Callable[[str, dict[str, str]], str | None] | None = None,
) -> tuple[DeskCard, str]:
    """데스크 카드를 말과 대조해 고친 카드와 답 앞에 붙일 말.

    after_emergency: 바로 앞 답이 위급 안내였으면 이어지는 말('문이 잠겨 있으면요?')도
    위급으로 둔다.
    """
    data = tuple(
        t for t in card.topics if t in BY_ID and BY_ID[t].ready and BY_ID[t].needs != "none"
    )
    note = ""
    if card.block == "emergency" and not after_emergency and not EMERGENCY_SIGN.search(text):
        card = card.model_copy(update={"block": "none"})
        if card.act == "blocked":
            card = card.model_copy(update={"act": "ask" if data else "unclear"})
    # 10-20 페르소나 o02 r8 T6 · T10: '112에 신고해도 되는 건가요?' · '신고하고 … 감사합니다'에
    #        위급 안내만 나가고 물은 것(경로당 위치)은 건너뜀 → 묻는 말 · 마무리는 위급 막기가 아님
    if card.block == "emergency" and not HARD_SIGN.search(text):
        if ASK_IF_REPORT.search(text):
            topics = card.topics if "support" in card.topics else (*card.topics, "support")
            card = card.model_copy(update={"block": "none", "act": "ask", "topics": topics})
        elif BYE.search(text) and "?" not in text:
            card = card.model_copy(update={"block": "none", "act": "chitchat"})
    if card.block == "person" or (card.act == "blocked" and card.block != "emergency"):
        asks_place = bool(INSTITUTION.search(text)) and not PERSON_ONLY.search(text)
        if not PERSON_SIGN.search(text) or asks_place:
            card = card.model_copy(update={"act": "ask" if data else "unclear", "block": "none"})
        elif data and not (
            (any(k in hidden for k in _MASKED_PERSON) or PERSON_ONE.search(text))
            and PERSON_ASK.search(text)
        ):
            card = card.model_copy(update={"act": "ask", "block": "none"})
            note = PERSON_NOTE
    # 【판단】 10-28 재심사 C2 p10_c(밤 11시 통장): '개포3동 혼자 사는 어르신 현황 좀 ·
    #        대략 몇 분인지'
    #        (동 단위)를 연락이 끊긴 할머니 걱정과 함께 말하자 개인 막기로 세 턴 내내 거절했다 →
    #        동 이름과 혼자 사는 어르신 말이 있고 그분 정보(주소 · 연락처 · 이름 · 명단)를 묻지
    #        않으면 동 단위로 답한다(급한 사정 안내는 답 길이 붙인다)
    if card.act == "blocked" and card.block == "person" and dong_solo_ask(text):
        card = card.model_copy(update={"act": "ask", "block": "none", "topics": ("solo_seniors",)})
        note = PERSON_NOTE
    # 【판단】 10-20 페르소나 o02 r3: '경로당이나 복지관 어디 있는지 알려 주세요 … 80대 명단 같은
    #        거'를 통째로 막아 위치도 못 받았다. 막는 말에 시설 위치 · 연락처 묻기가 섞이면
    #        그 부분은 갈 곳 서가로 답한다(명단 같은 개인 정보는 여전히 답하지 않는다고 밝힘)
    if card.act == "blocked" and card.block == "person" and not data and PLACE_ASK.search(text):
        card = card.model_copy(update={"act": "ask", "block": "none", "topics": ("places",)})
        note = PERSON_NOTE
    # 【판단】 10-26 예상 질문 2-22 '… 김○○ 할머니가 무릎이 안 좋으신데, 이분이 받을 수 있는
    #        서비스가 뭐예요?': 그분 이야기가 섞였다고 통째로 막아 누구에게나 같은 안내(받을 수 있는
    #        서비스 · 신청 창구)도 못 받았다. 위 시설 위치처럼, 그분 정보(주소 · 연락처 · 사는 곳 ·
    #        명단)를 묻지 않고 서비스 안내를 물으면 지원 기관 서가로 답한다(그분 이야기는
    #        기억하지 않음)
    if (
        card.act == "blocked"
        and card.block == "person"
        and SERVICE_ASK.search(text)
        and not PERSON_INFO.search(text)
    ):
        said = dongs_in_text(text)
        update: dict = {
            "act": "ask",
            "block": "none",
            "topics": ("support",),
            "new_facts": (),
        }
        if said:
            update |= {"dong_op": "set", "dong_mentions": tuple(said[:2])}
        card = card.model_copy(update=update)
        note = SERVICE_NOTE
    # 【판단】 (10-12 r16 되돌림) 데스크의 '범위 밖'을 서가 낱말로 뒤집던 규칙은
    #        '원주시 독거노인' · '부산 해운대구 청년'까지 답으로 끌어들여 뺐다(문제 목록 2-1)
    # 【판단】 가려진 개인정보(이름 · 전화 · 주민번호 · 호수)가 든 말을
    #        데스크가 '못 알아들음'으로 내면
    #        막기로 본다(10-12 r12: '대치1동 사는 [이름] 씨 건강 상태 알려줘' → 못 알아들음)
    # 【판단】 동 주제가 같이 적혀도 막는다(10-12 r13: 데스크가 대치1동 주제를 같이 적어 빠져나감)
    if card.act == "unclear" and any(k in hidden for k in _MASKED_PERSON):
        card = card.model_copy(update={"act": "blocked", "block": "person"})
    if card.act == "unclear" and (PERSON_SEEK.search(text) or SUB_DONG.search(text)):
        card = card.model_copy(update={"act": "blocked", "block": "person"})
    # 【판단】 대상 낱말이 하나만 있는데 대상 칸이 비면 코드가 적는다(10-15 desk_new_21 r1 T02).
    #        대상 · 주제 맞추기보다 먼저
    said = {t for t, pat in TARGET_WORDS if pat.search(text)}
    if card.act in ("ask", "chitchat") and card.target_op == "keep" and len(said) == 1:
        card = card.model_copy(update={"target_op": "set", "target": said.pop()})
    # 【판단】 대상과 주제가 어긋나면 코드가 맞춘다(10-14 r3_1014 춘천 청년 T44 '동내면만 어르신':
    #        데스크가 대상은 어르신, 주제는 앞의 청년 그대로 → '어르신 숫자는 이 자료에 없어요')
    swap = TARGET_SWAP.get((card.target, card.topics[0])) if len(card.topics) == 1 else None
    if card.target_op == "set" and swap:
        card = card.model_copy(update={"topics": (swap,)})
    # 【판단】 10-29 회귀 춘천 청년 T22 '거기 갈 곳이 적다던데 무슨 말이에요?': 뜻을 묻는 말에
    #        데스크가 갈 곳 주제만 적어 갈 곳 목록으로 답했다(뜻은 말하지 않음, 여섯 판 중 한 번).
    #        데스크 지시도 '뜻을 물으면 sources'라, 말에 뜻 묻기가 있으면 코드가 sources를
    #        앞에 붙인다
    if card.act == "ask" and MEANING_ASK.search(text) and "sources" not in card.topics:
        card = card.model_copy(update={"topics": ("sources", *card.topics)})
    # 【판단】 초성만 쓴 동 이름이 여러 동에 맞는데(ㅅㅅㄷ → 수서동 · 신사동 · 삼성동) 데스크가 말에
    #        없는 동을 적었거나 못 알아들었으면, 초성을 그대로 두어 코드가 되묻는다
    #        (10-14 데스크 시험 r0 A13: 5번 중 2번 말없이 수서동으로 짐작)
    cho = keyboard.ambiguous_chosung(text)
    flat = re.sub(r"\s", "", text)
    guessed = not any(re.sub(r"\s", "", m) in flat for m in card.dong_mentions)
    if cho and card.act in ("ask", "unclear") and (card.dong_op != "set" or guessed):
        card = card.model_copy(update={"act": "ask", "dong_op": "set", "dong_mentions": tuple(cho)})
    # 【판단】 말에 우리 동 이름이 그대로 있는데 데스크가 동 칸을 안 건드렸으면 코드가 적는다
    #        (10-14 데스크 시험 r3 B10 · 100턴 T3: '저는 주로 수서동을 챙겨요'에 동 칸이 빔)
    named = dongs_in_text(text)
    # 10-29 브라우저 시험: 개인 질문을 막는 답의 권유('대신 ○○동 동 상황 …')가 말에 나온
    #       개포3동이 아니라 앞 턴의 효자2동이었다 → 막는 말에도 말에 나온 동을 적는다
    if (
        named
        and (card.act in ("ask", "chitchat") or card.block == "person")
        and card.dong_op == "keep"
        and not card.dong_mentions
    ):
        card = card.model_copy(update={"dong_op": "set", "dong_mentions": tuple(named)})
    # 【판단】 10-29 회귀 춘천 청년 T57 '마지막으로 우리 동 한눈에 정리': 데스크가 다시 쓴 질문에는
    #        '효자2동'(처음에 말한 일하는 곳, 기억에서 풂)을 적고 동 칸은 그대로 둬 앞 턴 소양동으로
    #        답했다 → 말에 동 이름은 없고 '우리 동 · 제 담당'만 있으면 다시 쓴 질문의 동을
    #        칸에 적는다
    meant = dongs_in_text(card.restate or "")
    if (
        card.act == "ask"
        and card.dong_op == "keep"
        and not card.dong_mentions
        and not named
        and meant
        and MY_DONG.search(text)
    ):
        card = card.model_copy(update={"dong_op": "set", "dong_mentions": tuple(meant)})
    # 【판단】 10-29 브라우저 시험 '제 담당 개포3동이랑 효자2동 … 표로 나란히 비교': 데스크가 줄
    #        세우기를 켜, 지역 하나를 되묻거나 춘천 위 5곳 표가 나갔다 → 동을 둘 넘게 적고 견주는
    #        말이면 줄 세우기가 아니라 그 동들의 견줌('제일 · 가장 많은 동 · 동별'은 줄 세우기)
    if (
        card.act == "ask"
        and card.rank
        and len(named) >= 2
        and COMPARE_WORD.search(text)
        and not TOP_DONG.search(text)
        and not EACH_DONG_WORD.search(text)
    ):
        card = card.model_copy(update={"rank": False, "compare": True})
    # 지역 전체냐 동 하나냐는 AI가(region_scope · pick). 'cleared'(데스크가 동 칸을 비움)는 AI가
    # 지역 전체라고 해야 비운 채로 둔다 — AI가 답하지 못하면 예전처럼 '전체' 낱말로
    scope = region_scope(card, text)
    whole = bool(WHOLE_REGION.search(text))
    if scope == "cleared":
        whole = (pick(SCOPE_ASK, SCOPE_CHOICES) if pick is not None else None) == "region"
        scope = ""
    if card.dong_op == "clear" and not whole:
        card = card.model_copy(update={"dong_op": "keep"})
    elif card.dong_op == "clear" and any(t in RANKABLE for t in card.topics):
        card = card.model_copy(update={"rank": True})
    # 【판단】 성별 낱말이 한쪽만 있는데 데스크가 성별 칸을 놓치면 채운다(10-12 r12: '혼자 사는
    #        할아버지'에 성별 칸이 비어 남녀 합친 숫자라는 밝힘이 빠짐)
    if card.sex_op == "keep" and card.act == "ask":
        m, f = bool(MALE.search(text)), bool(FEMALE.search(text))
        if m != f:
            card = card.model_copy(update={"sex_op": "set", "sex": "남" if m else "여"})
    # 【판단】 지역 이름도 말에 하나만 분명히 있으면 코드가 확정한다(10-14 데스크 시험 r2 C05:
    #        '강남구 경로당 많은 동'에서 5번 중 1번 지역 칸을 비워 '어느 지역?'으로 되물음).
    #        춘천 강남동은 강남구가 아니다(REGION_WORDS_IN_TEXT). 동 이름이 있으면 동으로 맞춘다
    regs = {r for r, pat in REGION_WORDS_IN_TEXT if pat.search(text)}
    if card.act == "ask" and card.region_op == "keep" and len(regs) == 1 and not card.dong_mentions:
        card = card.model_copy(update={"region_op": "set", "region": next(iter(regs))})
    # 【판단】 10-28 밤 브라우저 시험(로그인 회원 · 담당 동 개포3동): '강남구 독거 어르신 … 몇 명쯤'
    #        (지역만 말함)에 담당 동이 남아 개포3동 숫자로 답하고 '강남구 합계는 자료에 없다'(거짓).
    #        동을 말하지 않고 지역 이름을 말했으면 지역 전체인지 동 하나인지(앞 동 · 우리 동 ·
    #        견줄 기준) 정한다(줄 세울 수 있는 주제만: 합계 · 위 몇 곳으로 답한다).
    #        10-29부터 정하는 것은 AI(pick — 엔진이 desk.pick을 넘김), 낱말 표는 대비(scope_guess)
    if scope:
        got = pick(SCOPE_ASK, SCOPE_CHOICES) if pick is not None else None
        fallback = scope_guess(text) if scope == "plain" else "dong"
        if (got or fallback) == "region":
            card = whole_region_card(card)
            if card.region_op == "keep" and len(regs) == 1:  # 동 칸 때문에 위에서 못 적은 지역
                card = card.model_copy(update={"region_op": "set", "region": next(iter(regs))})
    # 【판단】 지역 칸은 말에 근거(지역 낱말 · 그 지역 동 이름 · '우리')가 있을 때만 바꾼다
    #        (10-14 r2_1014 rules_v6 T3: 춘천 질문 다음 '기초수급 받는 독거 어르신 많은 동'에
    #        데스크가 말에 없는 강남구로 바꿈 — 강남에 수급권자 독거노인 자료가 생겨 끌려감)
    if card.region_op == "set" and card.region and not _region_grounded(card, text):
        card = card.model_copy(update={"region_op": "keep", "region": None})
    # 【판단】 10-20 페르소나 f02 r4 T5: '강남구와 춘천시 중 어디가 더 심각합니까?'에 데스크가
    #        견줌을
    #        켜지 않아 '춘천시 값이 없다'(틀린 말). 두 지역 이름이 함께 있고 견주는 말이면 켠다
    if (
        card.act == "ask"
        and not card.compare
        and BOTH_REGIONS.search(text)
        and COMPARE_WORD.search(text)
    ):
        card = card.model_copy(update={"compare": True})
    # 10-20 페르소나 f02 r8 · r9 T4: 앞 턴의 개포3동이 남아 동끼리 견줌으로 가 '춘천시는 자료에
    #        없다' → 지역 이름만 말했으면(데스크가 견줌을 켰어도) 동 칸을 비워 지역끼리 견준다
    if (
        card.compare
        and BOTH_REGIONS.search(text)
        and not dongs_in_text(text)
        and not card.dong_mentions
    ):
        card = card.model_copy(update={"dong_op": "clear"})
    found = [w for w, pat in WEATHER_WORDS if pat.search(text)]
    if card.act == "ask" and len(found) == 1 and card.weather != found[0]:
        card = card.model_copy(update={"weather_op": "set", "weather": found[0]})
    elif card.act == "ask" and not found and card.weather_op == "keep" and WEATHER_ANY.search(text):
        card = card.model_copy(update={"weather_op": "set", "weather": "날씨"})
    # 【판단】 계절 · 반기 · 분기 낱말은 코드가 때 칸에 적는다(10-14 r1_1014 probe_weak T6: '작년
    #        겨울이랑 올여름 수서동 비교'에 데스크가 때 칸을 비워
    #        '나눠 볼 수 없다'는 밝힘이 없었다).
    #        날씨를 물었으면 날씨 쪽이 때를 정한다
    if card.act == "ask" and card.period_op == "keep" and card.weather_op != "set" and not found:
        seasons = [m.group(0).strip() for m in SEASON_WORDS.finditer(text)]
        # 10-29 변수 시험 c01_088 '춘천시 전체의 2020년 기준 65세 이상 1인세대': 해도 때 칸에
        #       적어야 '때를 나눠 볼 수 없어서 이 자료의 때로'가 붙는다(데스크가 비움)
        seasons += [m.group(0).strip() for m in YEAR_SAID.finditer(text)]
        if seasons:
            card = card.model_copy(update={"period_op": "set", "period": " · ".join(seasons)})
    # 【판단】 10-26 예상 질문 2-17 '작년 여름 폭우 때는 어느 동이 위험했어요?': 회원 담당
    #        동(수서동)이 칸에 있어 그 동 하나만 판단하고 '다른 동은 자료에 없다'고 했다.
    #        동을 말하지 않고 어느 동인지를 묻는 판단 질문이면 지역 판단(동 칸을 비움 — 지역
    #        판단은 지난 날도 본다)
    if (
        card.act == "ask"
        and "outlook" in card.topics
        and WHICH_DONG.search(text)
        and not card.dong_mentions
        and not dongs_in_text(text)
    ):
        card = card.model_copy(update={"dong_op": "clear"})
    # 【판단】 동을 말하지 않고 '동별로 · 동마다'면 지역 줄 세우기(10-15 페르소나 q04 T3:
    #        '동별로 집에만 있는 청년 어림'에 '어느 동?'을 되물음)
    if (
        card.act == "ask"
        and not card.rank
        and EACH_DONG_WORD.search(text)
        and not card.dong_mentions
        and not dongs_in_text(text)
        and any(t in RANKABLE for t in card.topics)
    ):
        card = card.model_copy(update={"rank": True})
    if (
        card.act == "ask"
        and not card.rank
        and TOP_DONG.search(text)
        and "outlook" not in card.topics  # '겹친 동 중 경로당 적은 곳'은 겹친 동들로(librarian)
        and not card.dong_mentions
        and not dongs_in_text(text)
        and any(t in RANKABLE for t in card.topics)
    ):
        card = card.model_copy(update={"rank": True})
    # 【판단】 10-27 qbank P1-19(api9): '독거노인 1,000명당 공공 자원이 적은 동은 어디예요?'에 계산
    #        계획이 그 판만 실패해 보통 길로 떨어졌고, 먼저 볼 동(줄 세우기 그 자체라 RANKABLE 밖)이
    #        앞 턴의 북산면 하나만 봐 '동별 순서는 만들 수 없어요'가 나갔다. 동 이름 없이 '적은 ·
    #        많은 동'을 물으면 앞 턴의 동을 풀어 지역 전체로 본다
    if (
        card.act == "ask"
        and TOP_DONG.search(text)
        and "priority" in card.topics
        and card.dong_op == "keep"
        and not card.dong_mentions
        and not dongs_in_text(text)
        and not REFER_DONG.search(text)
    ):
        card = card.model_copy(update={"dong_op": "clear"})
    # 【판단】 표 파일 낱말 · 나이 표현은 말에 그대로 있으면 코드가 적는다(10-15 desk_new_21 r0)
    if card.act == "ask" and card.fmt == "답" and TABLE_FILE.search(text):
        card = card.model_copy(update={"fmt": "엑셀"})
    # 【판단】 10-27 qbank P2-26(API): 앞 턴 '…csv로'에 끌려 데스크가 표 · 파일 말이 없는 번호
    #        질문에도 엑셀 칸을 적어, 묻지 않은 표 파일을 만들고 동 하나짜리 표 안의 '1위'를 답에
    #        썼다(실제 25곳 중 11위). 형식 칸은 이번 말만 보므로 표 · 파일 낱말이 없으면 답으로
    if card.fmt == "엑셀" and not TABLE_WORDS.search(text):
        card = card.model_copy(update={"fmt": "답"})
    # 【판단】 10-26 예상 질문 2-4 '…둘 다 넣어서 PPT로 만들어 줘요': 데스크가 문서 칸을 적지 않아
    #        'PPT 파일은 제가 만들 수 없어요'(거짓)가 나갔다. PDF · PPTX를 만들어 달라는 말이 그대로
    #        있으면 코드가 동 상황 문서로 잇는다(표 파일 낱말과 같은 방식, 표 · 대화 저장은 빼고)
    if (
        card.act == "ask"
        and "dong_doc" not in card.topics
        and DOC_FILE.search(text)
        and not TABLE_FILE.search(text)
        and not CONVO_SAVE.search(text)
    ):
        fmt = (
            "PDF"
            if re.search(r"(?i)pdf", text) and not re.search(r"(?i)ppt|피피티", text)
            else "PPTX"
        )
        rest = tuple(t for t in card.topics if t != "dong_doc")[:2]
        card = card.model_copy(update={"topics": ("dong_doc", *rest), "fmt": fmt})
    # 【판단】 10-26 예상 질문 q2 1-23 '구청장 보고에 쓸 문장으로 한 줄 요약해 줄래요?'
    #        (문서 다음 턴): 데스크가 동 상황 문서를 골라 같은 문서 요약이 또 나갔다
    #        (q1에서는 동 한눈에). 문서 · 파일을 달라는 말이 없으면 동 한눈에로 답한다
    if card.act == "ask" and "dong_doc" in card.topics and not DOC_WORDS.search(text):
        topics = tuple(
            dict.fromkeys("dong_overview" if t == "dong_doc" else t for t in card.topics)
        )
        card = card.model_copy(update={"topics": topics, "fmt": "답"})
    # 【판단】 10-26 예상 질문 q2 1-7 '오늘 챙길 일이 뭐예요?': 데스크가 순위를 골라 '오늘 할 일은
    #        자료에 없어요'(q1에서는 판단). 오늘 챙길 일은 그날의 취약 돌보미 판단(날씨 · 달력 포함)
    if card.act == "ask" and TODAY_TASK.search(text) and "outlook" not in card.topics:
        card = card.model_copy(update={"topics": ("outlook",)})
    age = ages_in_text(text) if card.act in ("ask", "chitchat") and card.ages_op == "keep" else None
    if age:
        card = card.model_copy(update={"ages_op": "set", "age_lo": age[0], "age_hi": age[1]})
    if card.weather_op == "set" and card.period_op != "set":
        m_date = DATE_WORD.search(text)
        if m_date:
            card = card.model_copy(update={"period_op": "set", "period": m_date.group(0)})
    if card.unmet:
        # 【판단】 우리 동 이름 · 지역 말이 든 것은 '못 담은 조건'이 아니라
        #        데스크가 잘못 읽은 것이다
        keep = tuple(
            u
            for u in card.unmet
            if not _PLACE_WORDS.search(u)
            and not dongname.confirm([w for w in u.split() if w])["dongs"]
        )
        card = card.model_copy(update={"unmet": keep})
    # 10-20 페르소나 h01 r8 T2: '지금 문 연 시간'을 못 담은 조건으로 적고는 바로 아래에서
    #        영업 시간을 답함 — 약국 요일별 시간은 자료에 있다
    # 10-20 페르소나 h01 r9 T2: '결론만 … 그럼 오늘 신북읍 문연 약국 어디가 제일 가까운데'에
    #        데스크가 갈 곳 주제를 빠뜨려 '약국은 이 자료로 확인할 수 없어요'(자료는 있다)
    card = rescue_topics(card, text)
    card = part_topics(card, text)
    # 10-21 범위 시험 S20 '강남구 22개 동 위험 구간이랑 자원 공백 표로': 진단(동 하나)으로 가 동을 되물음  # noqa: E501
    #        → 지역 전체를 말했으면 순위 표(priority)로
    if (
        card.act == "ask"
        and "diagnosis" in card.topics
        and "priority" not in card.topics
        and not card.dong_mentions
        and WHOLE_REGION.search(text)
        and not dongs_in_text(text)
    ):
        card = card.model_copy(update={"topics": ("priority", *card.topics), "rank": True})
    # 10-21 말의 꼴: 데스크가 급하다고 보고(urgent) 위급한 말(쓰러짐 · 며칠째 안 나오심)이 있으면
    #        지원 기관으로 보내지 않고 위급 안내(desk_only_60 D09가 2/3로 흔들림)
    #        단, '연락이 끊기는 청년'처럼 동 단위로 말하는 것(r14 세라핀 T5)은 아니다 — 특정한 사람
    #        표시(그분 · 할머니 · 가린 이름)가 있을 때만
    if (
        card.act == "ask"
        and card.block == "none"
        and card.urgent
        and EMERGENCY_SIGN.search(text)
        and (
            PERSON_ONE_STRICT.search(text)
            or "[이름]" in text
            or any("이름" in k for k in hidden)
            or re.search(r"어르신이 |분이 |양반", text)
        )
        and not re.search(r"청년들|어르신들|분들|청년이|사람들", text)
    ):
        card = card.model_copy(update={"act": "blocked", "block": "emergency"})
    # 10-20 페르소나 o02 r9 T3: '그분 주소나 보호자 연락처 정도는 확인할 수 있는 거 아닌가요?'에
    #        데스크가 갈 곳 주제로 답해 경로당 목록이 나감 → 사람 표시 + 사람 정보 물음은 막는다
    if (
        card.act == "ask"
        and card.block == "none"
        and PERSON_ONE_STRICT.search(text)
        and PERSON_ASK.search(text)
        and not (INSTITUTION.search(text) and not PERSON_ONLY.search(text))
        and not PHARMACY_ASK.search(text)
        and not COUNT_Q.search(text)
        and not FACILITY_Q.search(text)
        and not dong_solo_ask(text)  # 10-28 재심사 C2 p10_c '전화를 안 받으세요'의 '전화'
    ):
        card = card.model_copy(update={"act": "blocked", "block": "person"})
    # 10-21 r21 chuncheon_youth_60 T47: '이 대화 내용 PDF로 저장'을 동 상황 문서로 만듦
    if card.act == "ask" and "dong_doc" in card.topics and CONVO_SAVE.search(text):
        card = card.model_copy(update={"act": "out_of_scope", "topics": ()})
    # 10-21 r21 chuncheon_youth_60 T40: 청년 이야기 뒤 '주민이 몇 명인데요?'를 청년 수로 — 전체 주민
    if (
        card.act == "ask"
        and RESIDENT_COUNT.search(text)
        and not re.search(r"청년|어르신|노인|독거|혼자", text)
        and set(card.topics) <= {"youth", "solo_seniors"}
    ):
        card = card.model_copy(update={"topics": ("dong_overview",), "target_op": "clear"})
    # 데스크가 '너 말고 사람 담당자 연결해 줘'를 지원 기관으로 읽음(장서 낱말에 '연결 창구'가 들어간 뒤)  # noqa: E501
    #        → 비서를 바꿔 달라는 말은 범위 밖(기관 연락처가 아니다)
    if card.act == "ask" and HUMAN_AGENT.search(text) and not dongs_in_text(text):
        card = card.model_copy(update={"act": "out_of_scope", "topics": ()})
    if card.unmet:
        keep = tuple(
            u
            for u in card.unmet
            if not ("places" in card.topics and HOURS_UNMET.search(u))
            and not ("housing" in card.topics and ROOF_ASK.search(u))
            and not HOLIDAY_UNMET.search(u)
        )
        if keep != card.unmet:
            card = card.model_copy(update={"unmet": keep})
    # 【판단】 10-26 팀장 '긍정 · 부정 칸 — AI가 판단하고 코드가 대조'(polarity.reconcile)
    from src.assistant.polarity import reconcile

    card, pnote = reconcile(card, text)
    note += pnote
    return card, note


# 【판단】 거절 까닭을 나눠 말한다(10-12 페르소나: 지시문 요청 · 숫자 바꾸기 · 원본 자료 요청에
#        모두 '저희가 가지고 있는 데이터가 아니라'가 나가 왜 안 되는지 몰랐다). 범위 밖 일반 문장은
#        팀장 결정 전이라 그대로 둔다(문제 목록 1-5)
REFUSAL_REASONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"지시문|프롬프트|시스템 (메시지|설정|프롬프트)|규칙을? 무시|지시[는를]? (다 )?무시|"
            r"제한 없는|개발자 모드|디버그|[Ii]gnore|[Ss]ystem prompt"
        ),
        "제 지시문이나 내부 설정은 알려 드릴 수 없어요. "
        "강남구 · 춘천시 동 자료는 물어봐 주시면 찾아 드릴게요.",
    ),
    (
        re.compile(
            r"부풀|두 배로|2배로|배로 (말|써|늘)|순위를 바꿔|1위로 (해|만들|바꿔)|맞다고만|대충 \d|"
            r"숫자를 (바꿔|올려|키워)"
        ),
        "숫자나 순위를 바꾸거나 맞다고만 해 드릴 수는 없어요. 자료에 있는 그대로 말씀드릴게요.",
    ),
    # 【판단】 10-15: 원문 자료 서가 · 표 내려받기가 생겨 '원본은 못 건넨다'만은 사실과 어긋난다.
    #        대회 제공 자료 이름(SKT · 신한카드)은 공개 자료가 아니라고 따로 말한다(먼저 본다)
    (
        re.compile(r"SKT|신한|카드 결제|유동인구"),
        "그 자료는 취약 돌보미가 쓰는 공개 자료가 아니라 원본 자료를 건넬 수 없어요. "
        "취약 돌보미가 쓰는 공개 자료는 '자료 목록 보여 줘'로 물어봐 주세요.",
    ),
    (
        re.compile(r"원본|원자료|csv|CSV|[Rr]aw"),
        "원본 자료 파일은 취약 돌보미가 직접 건네지 않고, 받는 곳(기관 · 주소)과 이용 조건을 "
        "'자료 목록'으로 알려 드려요. "
        "취약 돌보미가 정리한 동별 숫자는 표 파일(엑셀 · CSV)로 드릴 수 있어요.",
    ),
)


def refusal_reason(text: str) -> str | None:
    for pat, msg in REFUSAL_REASONS:
        if pat.search(text):
            return msg
    return None


def not_connected_note(topics: tuple[str, ...]) -> str:
    """답할 수 있는 주제와 함께 물은, 아직 연결 전인 주제를 밝힌다(10-12 페르소나: 두 가지를 물으면
    하나만 답하고 나머지는 말이 없었다 — '합계 돼? 엑셀 · PDF 돼?')."""
    missing = [BY_ID[t].title for t in topics if t in BY_ID and not BY_ID[t].ready]
    if not missing:
        return ""
    # 【기능】 받침에 맞는 조사(10-13 재생: '춘천 버스은(는)')
    names = josa(" · ".join(missing), "은", "는")
    return f"({names} 취약 돌보미에 있는 자료지만 이 대화에는 아직 연결하지 않았어요.)\n"


# 【기능】 사람 수가 아니라 시설 · 집을 세는 주제 — 성별 · 때 안내가 뜻이 없다(10-13 places_30 T19)
FACILITY_TOPICS = frozenset({"places", "support", "senior_hall", "housing"})


def disclose(
    card: DeskCard,
    slots: Slots,
    kinds: list[str] | None = None,
    topics: tuple[str, ...] = (),
    repeat_period: bool = False,
) -> str:
    """답 앞에 코드가 붙이는 밝힘 — 조용히 빼거나 바꾼 조건을 말한다.

    【판단】 떠보기(10-12): 칸에 없는 조건(기초수급 · 장애 · 부부)을 조용히 버리고, '작년 겨울 ·
           올여름'을 말없이 12월 숫자로 바꾸고, '남자'를 말없이 뺐다. 밝히는 말은 정해진 사실이라
           AI가 아니라 코드가 쓴다(빠뜨릴 수 없게).
           '자료가 없어서'로 끝내지 않고 무엇으로 보여 주는지
           함께 말한다(10-12 팀장).
    """
    parts = []
    if kinds:
        parts.append(f"개인 정보로 보이는 부분({' · '.join(kinds)})은 가리고 받았어요.")
    if card.unmet:
        said = ", ".join(f"'{u}'" for u in card.unmet)
        parts.append(f"말씀하신 조건 중 {said}은(는) 이 자료로 나눠 볼 수 없어서 빼고 보여 드려요.")
    people = not topics or not set(topics) <= FACILITY_TOPICS
    # 【판단】 춘천 수급자 숫자는 나이 · 혼자 사는지로 못 나눈다. 데스크가 그 조건을 못 담은 조건이
    #        아니라 칸(어르신 · 혼자 · 나이)으로 적으면 조용히 빠졌다(10-14 시험지 여덟 rules_v6
    #        T3). 강남은 '수급권자 독거노인'(65세 이상 혼자)이라 그 조건 그대로다
    chuncheon = slots.region == "춘천시" or any(
        dongname.region_of(d) == "춘천시" for d in slots.dongs
    )
    filtered = slots.alone or slots.ages or slots.target == "어르신"
    if "livelihood" in topics and chuncheon and filtered and not card.unmet:
        parts.append(
            "춘천 기초생활수급자 숫자는 나이 · 혼자 사는지로 나눠 볼 수 없어서 "
            "전체 수급자 수로 보여 드려요."
        )
    # 【판단】 강남 혼자 사는 어르신 · 서울시 독거노인 현황은 성별 숫자가 있다(서울시 현황, 10-14)
    gangnam = slots.region == "강남구" or (
        bool(slots.dongs) and all(dongname.region_of(d) == "강남구" for d in slots.dongs)
    )
    # 10-29 변수 시험 c01_051 '개포2동과 후평1동의 혼자 사는 할머니': 두 지역이 섞이면 '성별
    #       숫자가 없다'로 갔다(개포2동은 서울시 현황에 여성 수가 있음) → 지역마다 따로 밝힌다
    mixed = len({dongname.region_of(d) for d in slots.dongs} - {None}) > 1
    solo = set(topics) & {"solo_seniors", "seoul_lonely"}
    if slots.sex and people and mixed and solo:
        parts.append(
            "강남 동의 할아버지 · 할머니 숫자는 서울시 독거노인 현황으로 답하고, 춘천 동은 성별로 "
            "나눈 숫자가 없어 남녀를 합친 숫자로 보여 드려요."
        )
    elif slots.sex and people and gangnam and solo:
        parts.append(
            # 10-26: '성별로 나뉘어 있지 않아'가 '성별 숫자는 없다'로 읽혀 AI가 '드릴 수 없다'
            "할아버지 · 할머니 숫자는 서울시 독거노인 현황으로 답해요"
            "(주민등록 1인세대는 남녀를 합친 숫자예요)."
        )
    elif slots.sex and people:
        parts.append("이 자료는 성별로 나눈 숫자가 없어서 남녀를 합친 숫자로 보여 드려요.")
    # 【판단】 날씨 칸이 있으면 때는 날씨 기록의 날짜라 '나눠 볼 수 없다'고 밝히지 않는다(10-13)
    # 10-20 페르소나 f01 r8: 같은 때 알림이 턴마다 되풀이(네 번) → 앞 턴과 같은 때면 숨긴다
    # 10-29 c01_085: 서울시 독거노인 현황은 해마다(2020 ~ 2025) 있어 지난 해를 물으면 그 해로 답한다
    yearly = "seoul_lonely" in topics and bool(YEAR_PAST.search(slots.period or ""))
    if (
        slots.period
        and not repeat_period
        and _PERIOD_UNMATCHED.search(slots.period)
        and people
        and not slots.weather
        and not yearly
        and not (topics and set(topics) <= {"usage", "sources", "datasets"})
    ):
        parts.append(
            f"'{slots.period}'처럼 때를 나눠 볼 수 없어서 이 자료의 때로 보여 드려요"
            f"(주민등록 숫자는 {B.ko(B.reg())}, 늘고 줄음은 {B.ko(B.reg_prev())}과 견줌)."
        )
    return "(" + " ".join(parts) + ")\n" if parts else ""


@dataclass
class Plan:
    kind: Kind
    topics: tuple[str, ...] = ()
    message: str = ""
    # 【기능】 되묻는 칸("dong" · "region"). 다음 턴 데스크가 '방금 내가 물은 것'으로 본다
    pending: str | None = None
    suggest: tuple[str, ...] = field(default_factory=tuple)
    # 【기능】 답 앞에 붙일 밝힘(예: 지역에 없는 주제를 빼고 답할 때)
    note: str = ""


def has_batchim(word: str) -> bool:
    # 【판단】 끝의 괄호 설명은 빼고 본다: '먼저 볼 동(취약 돌보미 동 순위)' → '동'
    word = re.sub(r"\s*\([^)]*\)$", "", word.strip())
    ch = word[-1:]
    if not ch:
        return False
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3:
        return (o - 0xAC00) % 28 != 0
    return ch in "013678LMNlmn"  # 숫자 · 영어 끝소리 어림


def josa(word: str, with_b: str, without_b: str) -> str:
    return word + (with_b if has_batchim(word) else without_b)


def _label(topic_id: str, state: DialogueState) -> str:
    t = BY_ID[topic_id]
    name = SHORT.get(topic_id, t.title)
    s = state.slots
    if t.needs == "dong" and s.dongs:
        return f"{s.dongs[0]} {name}"
    if t.needs == "region" and s.region:
        return f"{s.region} {name}"
    return name


def pick_alternatives(state: DialogueState, wanted: tuple[str, ...] = ()) -> tuple[str, ...]:
    """권할 대안 2개 — 데스크가 고른 것(목록 안) 먼저, 모자라면 지금 상태로 코드가 고른다."""
    region = state.slots.region
    # 【판단】 같은 주제 두 번 → '○○ 현황이나 ○○ 현황'(10-12 페르소나). 한 번만 담는다
    out = list(dict.fromkeys(t for t in wanted if t in DATA_IDS and covers(t, region)))
    if state.slots.dongs:
        fallback = ["dong_overview", "solo_seniors", "youth", "diagnosis"]
    else:
        fallback = ["priority", "dong_overview", "solo_seniors"]
    for t in fallback:
        if len(out) >= 2:
            break
        if t not in out and covers(t, region):
            out.append(t)
    return tuple(out[:2])


def suggestion_sentence(state: DialogueState, alts: tuple[str, ...]) -> str:
    labels = [_label(t, state) for t in alts]
    if not labels:
        return ""
    if len(labels) == 1:
        body = josa(labels[0], "을", "를")
    else:
        body = f"{josa(labels[0], '이나', '나')} {josa(labels[1], '을', '를')}"
    return f" 대신 {body} 찾아보시는 건 어떠신가요?"


def _uncovered_note(off: list[str]) -> str:
    """지역에 없는 주제를 빼고 답할 때 앞에 붙이는 밝힘."""
    if not off:
        return ""
    t = BY_ID[off[0]]
    names = " · ".join(BY_ID[x].title for x in off)
    return f"({josa(names, '은', '는')} {t.coverage} 자료만 있어서 빼고 보여 드려요.)\n"


def _ask_dong(state: DialogueState, data: DongData) -> str:
    region = state.slots.region
    if region:
        top = [n for _, n in data.ranked(region)[:3]]
        return (
            f"어느 동을 볼까요? {region}에서는 예를 들어 {', '.join(top)}처럼 "
            "동 이름으로 말씀해 주세요."
        )
    return "어느 동을 볼까요? 강남구나 춘천시의 동 이름으로 말씀해 주세요(예: 수서동, 북산면)."


# 못 알아들음이어도 동을 말했으면 주제를 낱말로(10-28 p03_c)
YOUTH_WORD = re.compile(r"청년|은둔")
SENIOR_WORD = re.compile(r"어르신|노인|독거|홀몸")


def preflight(applied: Applied, card: DeskCard, data: DongData) -> Plan:
    state = applied.state
    if card.block == "emergency":
        return Plan(
            "blocked", message=EMERGENCY + " 동 단위 상황은 이어서 물어봐 주시면 찾아 드릴게요."
        )
    if card.block == "person" or card.act == "blocked":
        alts = pick_alternatives(state)
        return Plan("blocked", message=PERSON + suggestion_sentence(state, alts), suggest=alts)
    if card.act == "out_of_scope":
        alts = pick_alternatives(state, card.suggest)
        return Plan("out_of_scope", message=f"{OUT_OF_SCOPE} {OUT_OF_SCOPE_ASK}", suggest=alts)
    if card.act == "chitchat":
        # 【판단】 10-20 페르소나 o06(춘천 담당)에게 '수서동 청년' 예가 나갔다 → 지역에 맞는 예
        here = "효자2동" if state.slots.region == "춘천시" else "수서동"
        # 【판단】 10-20 페르소나 o03 r6: 청년 이야기를 하던 상담사에게 '효자2동 혼자 사는 어르신'
        #        예가 나갔다 → 지금 대상(청년 · 어르신)에 맞는 예
        who = "청년" if state.slots.target == "청년" else "혼자 사는 어르신"
        example = f"{state.slots.dongs[0]} {who}" if state.slots.dongs else f"{here} 청년"
        # 【판단】 새로 알게 된 일 맥락 · 계속 쓸 조건은 기억했다고 말한다(10-14 r1_1014 probe_weak
        #        T7: '앞으로 80세 이상 어르신만 볼 거예요'에 '편하게 물어봐 주세요'만 나감)
        if card.new_facts:
            return Plan(
                "chitchat",
                message=f"알겠어요. 기억해 둘게요({' · '.join(card.new_facts[:2])}). "
                f"이어서 '{example}'처럼 물어봐 주세요.",
            )
        return Plan(
            "chitchat",
            message=(
                f"네, 편하게 물어봐 주세요. 예를 들어 '{example}'처럼 물어보시면 바로 찾아 드려요."
            ),
        )
    # 【판단】 10-27 desk_correct_18(-pending 6문제 중 5개 0/3): 비서가 '어느 동?'을 되묻는 중에
    #        동만 말하면('대치4동요' · '개포3동 말고요, 개포4동이요') 데스크가 주제가 없다며
    #        unclear 를 낸다. 되묻기에 답한 동이 칸에 들어갔으면 코드가 되묻던 주제로 잇는다
    #        (이음 교훈: 빈 칸이 무엇인지 코드가 안다 — 되묻기는 코드가 정한다)
    answered_dong = (
        state.pending == "dong" and "dongs" in applied.changed and bool(state.slots.dongs)
    )
    # 【판단】 10-27 팀장 "싹 다 고치자": 앞 맥락 없이 동만 말하거나 고쳐 말하면('역삼1동 아닌
    #        역삼2동 얘기야' · '대치4동요', desk_correct_18 -bare 6문제 중 5개 0/3) 데스크가 '무엇을
    #        볼지 모른다'며 unclear → '무엇을 볼까요?'만 나갔다. 동은 분명히 정해졌으니 앞에서 보던
    #        주제가 있으면 그것으로, 없으면 그 동의 상황 한눈에로 답한다
    named_dong = (
        card.act == "unclear"
        and "dongs" in applied.changed
        and bool(state.slots.dongs)
        and not applied.unknown_dongs
    )
    # 【판단】 10-28 페르소나 p03_c T1: 담당 동(역삼1동)을 그대로 말한 긴 질문('역삼1동의 은둔
    #        청년이 몇 명쯤')에 데스크가 unclear — 칸은 이미 역삼1동이라 '바뀐 칸'이 없어 위 규칙이
    #        안 걸렸다 → 말에 지금 칸의 동 이름이 있으면 같은 것으로 본다(주제 낱말이 있으면
    #        그 주제로)
    if (
        card.act == "unclear"
        and not named_dong
        and state.slots.dongs
        and not applied.unknown_dongs
        and set(dongs_in_text(applied.said)) & set(state.slots.dongs)
    ):
        named_dong = True
    said = applied.said
    word_topic = (
        ("youth",)
        if YOUTH_WORD.search(said)
        else ("solo_seniors",)
        if SENIOR_WORD.search(said)
        else ()
    )
    if card.act == "unclear" and not (answered_dong or named_dong):
        return Plan("unclear", message=UNCLEAR)

    # ── 자료 질문(act == ask) ──
    if applied.unknown_dongs:
        said, near = applied.unknown_dongs[0]
        hint = f" 혹시 {', '.join(near[:4])} 중 하나인가요?" if near else ""
        return Plan(
            "unknown_dong",
            topics=state.topics,
            message=f"말씀하신 '{said}'은(는) 강남구 · 춘천시 동 목록에서 찾지 못했어요.{hint}",
            pending="dong",
        )
    topics = (
        state.topics
        or (state.pending_topics if answered_dong else ())
        or ((word_topic or ("dong_overview",)) if named_dong else ())
    )
    if not topics:
        return Plan("unclear", message=UNCLEAR)
    if "my_region" in topics:
        return Plan("settings", topics=("my_region",))
    if "recall" in topics:
        return Plan("recall", topics=("recall",))
    ready = tuple(t for t in topics if BY_ID[t].ready)
    if not ready:
        alts = pick_alternatives(state)
        name = BY_ID[topics[0]].title
        msg = (
            f"{josa(name, '은', '는')} 취약 돌보미에 있는 자료지만 이 대화에는 아직 연결하지 않았어요."  # noqa: E501
            + suggestion_sentence(state, alts)
        )
        return Plan("not_connected", topics=topics, message=msg, suggest=alts)
    # 【판단】 10-20 r5 강남 T9 '걱정이 겹친 동 중에 경로당이 적은 곳은요?': 데스크가 senior_hall을
    #        앞에 적자 동이 없다고 '어느 동?'을 되물었다. 취약 돌보미 판단(지역)이 함께 있고 동이
    #        없으면
    #        판단을 앞에 둔다(동 주제는 겹친 걱정이 많은 동들로 꺼낸다, librarian.gather_all)
    if "outlook" in ready and not state.slots.dongs and state.slots.region:
        ready = ("outlook",) + tuple(t for t in ready if t != "outlook")
    main = BY_ID[ready[0]]
    s = state.slots
    # 【판단】 10-27: 강남 버스처럼 지역 전체에 없는 자료는 동을 알아도 답할 수 없다.
    #        동 되묻기 · 엑셀 표 만들기보다 먼저 알린다. 함께 물은 자료가 있으면 기존 길로 간다.
    if s.region and not s.dongs and not any(covers(t, s.region) for t in ready):
        alts = pick_alternatives(state)
        msg = (
            f"{josa(main.title, '은', '는')} {main.coverage} 자료만 있어서 "
            f"{s.region} 자료는 이 비서에서 제공하지 않아요." + suggestion_sentence(state, alts)
        )
        return Plan("coverage", topics=ready, message=msg, suggest=alts)
    if s.rank and any(t in RANKABLE for t in ready):
        # 【판단】 조합 규칙(10-12 팀장 "○번 ○번이 On되면 이걸로"): 주제 + 줄 세우기 + 지역이 켜지면
        #        동이 없어도 '많은 동' 서가로 간다. 그 지역에 자료가 있는 주제를 먼저 고른다
        if not s.region:
            return Plan(
                "ask_slot",
                topics=ready,
                message="강남구와 춘천시 중 어느 지역을 볼까요?",
                pending="region",
            )
        ranked = [t for t in ready if t in RANKABLE and covers(t, s.region)]
        if ranked:
            off = [t for t in ready if t in RANKABLE and not covers(t, s.region)]
            # 【판단】 10-29 변수 시험 c01_052 '고립 어르신과 고립 청년 자료를 동별로 엑셀로':
            #        첫 주제 하나만 남겨 '청년 자료는 없다'(거짓) → 대상이 다른 주제(어르신 ·
            #        청년 · 동 순위)는 하나씩 같이 줄 세운다. 한 무리를 두 주제로 적은 말('기초수급
            #        독거 어르신')은 예전처럼 그 지역에 있는 첫 주제 하나(10-14)
            keep, groups = [], set()
            for t in ranked:
                g = (
                    "청년"
                    if t == "youth"
                    else "순위"
                    if t in ("priority", "diagnosis")
                    else "어르신"
                )
                if g not in groups:
                    keep.append(t)
                    groups.add(g)
            rest = tuple(t for t in ready if t not in RANKABLE)
            return Plan("answer", topics=(*keep, *rest)[:4], note=_uncovered_note(off))
        first = BY_ID[next(t for t in ready if t in RANKABLE)]
        alts = pick_alternatives(state)
        msg = (
            f"{josa(first.title, '은', '는')} {first.coverage} 자료만 있어서 {s.region}의 동들은 "
            "이 자료로 줄 세울 수 없어요." + suggestion_sentence(state, alts)
        )
        return Plan("coverage", topics=ready, message=msg, suggest=alts)
    # 【판단】 표 파일은 동이 없으면 그 지역 모든 동(10-15 desk_new_21 r0 X01 · X03 · X05:
    #        엑셀 칸은 켜졌는데 '어느 동?'을 되물음)
    if s.fmt == "엑셀" and main.needs == "dong" and not s.dongs and s.region:
        return Plan("answer", topics=ready[:2])
    if main.needs == "dong" and not s.dongs:
        # 【판단】 날씨만 물으면(오늘 날씨 · 7월 16일 비) 동 없이
        #        그 지역 관측 기록으로 답한다(10-13)
        if s.weather and main.id == "dong_overview" and s.region:
            return Plan("answer", topics=(main.id,))
        # 【판단】 갈 곳을 지역 전체로 물으면(동 칸을 끔) 지역 단위 지원 기관 서가로 답한다
        #        (10-13 places_30 r8 T20: '춘천 노인복지관은 전부 몇 곳?'에 '어느 동?'만 물음)
        if main.id == "places" and card.dong_op == "clear" and s.region:
            return Plan("answer", topics=("support",))
        return Plan("ask_slot", topics=ready, message=_ask_dong(state, data), pending="dong")
    # 【판단】 10-21 r14 오린 T6: '강남 1위 개포3동이랑 춘천 1위 효자2동을 나란히'에 두 지역 동이
    #        들어 지역 칸이 비자 '어느 지역을 볼까요?' → 견줌이면 동끼리 답한다(지역을 되묻지 않음)
    if main.needs == "region" and not s.region and not (s.compare and s.dongs):
        return Plan(
            "ask_slot",
            topics=ready,
            message="강남구와 춘천시 중 어느 지역을 볼까요?",
            pending="region",
        )
    if main.needs == "dong":
        regions = {data.dong(d)["region"] for d in s.dongs if data.dong(d)}
        fits = [t for t in ready if BY_ID[t].coverage == "both" or BY_ID[t].coverage in regions]
        if main.coverage != "both" and main.coverage not in regions and fits:
            # 【판단】 10-13 떠보기 r7 T2: 지역에 맞는 주제가 같이 있으면
            #        거절하지 않고 그것으로 답한다
            off = [t for t in ready if t not in fits]
            return Plan("answer", topics=tuple(fits[:3]), note=_uncovered_note(off))
        if main.coverage != "both" and main.coverage not in regions:
            alts = pick_alternatives(state)
            msg = (
                f"{josa(main.title, '은', '는')} {main.coverage} 자료만 있어요. "
                # 【기능】 받침에 맞는 조사(10-13 r6: '수서동은(는) 강남구이라')
                f"{josa(', '.join(s.dongs), '은', '는')} "
                f"{josa('·'.join(sorted(regions)), '이라', '라')} "
                "이 자료로는 볼 수 없어요." + suggestion_sentence(state, alts)
            )
            return Plan("coverage", topics=ready, message=msg, suggest=alts)
    # 【판단】 10-26 예상 질문 2-25 · 2-26: 데스크는 주제를 3개까지 고르는데(약국 · 보건지소가 셋째)
    #        여기서 2개로 잘려 '약국 · 보건지소는 알 수 없다'고 답했다. 답 쓰는 AI에게 보낼 자료가
    #        크면 budget.fit 이 덜어 내므로 3개까지 둔다
    # 【판단】 10-27 qbank P2-26(api11): 데스크가 셋을 고른 말에 코드가 넷째(보건 시설 → 갈 곳,
    #        RESCUES)를 더하면 여기서 잘려 '보건지소 자료는 없어요'가 다시 나갔다. 데스크는 셋까지만
    #        내므로 넷째는 코드가 말에서 확인해 더한 것뿐 — 넷까지 둔다
    # 【판단】 10-29 변수 시험 c01_085 '논현1동 2020년 기준 고립 어르신': 주민등록 숫자는 2025 ·
    #        2026년뿐이라 '자료에 없다'고 했다(서울시 독거노인 현황에 2020년 606명) → 지난 해를 물은
    #        강남 혼자 사는 어르신이면 해마다 있는 서울시 현황도 같이
    gang = any(dongname.region_of(d) == "강남구" for d in s.dongs) or s.region == "강남구"
    if (
        s.period
        and YEAR_PAST.search(s.period)
        and gang
        and "solo_seniors" in ready
        and "seoul_lonely" not in ready
    ):
        ready = (*ready, "seoul_lonely")
    return Plan("answer", topics=ready[:4])
