"""개인정보 가림 — AI에 보내기 전, 기억에 남기기 전에 코드가 먼저 가린다.

【판단】 10-12 멘토: "민감한 정보는 로컬에서 먼저 걸러내고 답변 생성은 Haiku에".
       떠보기 28턴(10-12): "302호 김순자 할머니예요. 기억해 둬"는 답은 막았지만
       원문이 최근 대화 6턴에 남아 매 턴 AI로 다시 갔고 저장소에도 남았다.
【판단】 모양이 정해진 것만 코드로 가린다(주민번호 · 전화 · 호수 · 아파트 동 번호 · 이름+호칭).
       이름은 성씨 + 두 글자 + 호칭일 때만 — 넓게 잡으면 '정말 어르신' 같은 말까지 가린다.
       나머지(이름만 말한 것 등)는 데스크가 막는다.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.assistant import dongname

SURNAMES = (
    "김이박최정강조윤장임한오서신권황안송류홍전고문양손배백"
    "허유남심노하곽성차주우구민진나엄채원천방공현함변염"
)
# 【판단】 성씨로 시작하지만 사람 이름이 아닌 세 글자 말
#        (big-contest chat.py NOT_NAMES에서 세 글자만 + 더함)
NOT_NAMES = {
    "우리동",
    "장애인",
    "저소득",
    "이번주",
    "정말로",
    "주민들",
    "고령자",
    "이웃들",
    "이웃집",
    "전체적",
    # 【판단】 10-12 페르소나: 직함 · 기관 말이 '이름 + 님'으로 잡혔다(주무관님 · 구청장님)
    "주무관",
    "구청장",
    "센터장",
    "사무관",
    "복지사",
    "상담사",
    "관리사",
    "지원사",
    "조사관",
    "구의원",
    "시의원",
    "보좌관",
    "공무원",
    "위원장",
    "협의체",
    # 【판단】 10-15 호칭 없는 이름(아래 BARE_NAME)과 부딪히는 무리 말
    "노년층",
    "고령층",
    "장년층",
    "중년층",
    "청년층",
    "취약층",
    "저소득층",
    "차상위",
    "한부모",
    # 【판단】 10-26 예상 질문 2-13: 공고문의 '2026년 하반기 어르신 …'에서 '하반기'를 이름(하씨)으로
    #        가리고 '(이름)은 가리고 받았어요'가 붙었다 → 때를 부르는 세 글자 말
    "하반기",
    "상반기",
    "전반기",
    "후반기",
    "내년도",
    "금년도",
    "전년도",
}
# 【판단】 10-20 페르소나 f01 r8: '순위와 진단이 어르신 쪽 자료' · '보건지소의 주소와 전화'에서
#        '진단이' · '주소와'를 이름으로 가렸다(성씨 '진' · '주'로 시작하는 낱말 + 조사).
#        두 글자 낱말 + 조사이면 이름으로 보지 않는다.
#        낱말은 비서 대화에 자주 나오는 것(성씨 글자로 시작)
NOUN2 = frozenset(
    """진단 진료 진짜 주소 주민 주거 주택 주말 주변 주의 전화 전체 전국 전문
    전달 전입 조사 조건 조례 조치 정보 정책 정도 정신 정리 정원 신호 신청
    신고 신규 한파 한계 한번 장애 장소 장기 고립 고령 고독 고민 고객 문의
    문제 문서 안부 안전 안내 성별 성인 성과 차이 차량 구청 구성 구역 구분
    민간 민원 나이 원래 원인 원본 방문 방법 방향 공공 공식 공간 현황 현장
    현재 변화 변경 노인 노년 노후 순위 서울 서류 서비 상담 상황 상태 배달
    허가 유형 유지 남성 남자 남편 심리 심사 하루 우편 우리 홍보 홍수 함께
    엄마 채널 천천 백신 양식 기준 기록 기관 기간 마을 반지 오늘 오후 오전
    손님 송파 강원 강남 황사 권역 표준 경로 용도
    이웃 이장 이분 이모 고모 조카 손자 손녀 이사 이용 이유 이후 이전 이상""".split()
)
# 【판단】 10-25 페르소나 cli2 세라핀 T6: '청년 가족이나 이웃이 전화를 해 올 때'의 '이웃이'를
#        이름으로 가리고 '(이름)은 가리고 받았어요'라고 해, 사용자가 '무엇을 가렸느냐'를 세 번
#        물었다 → 사람을 가리키는 흔한 말(이웃 · 이장 · 조카 · 손자 …)을 위 낱말에 더함
# 【판단】 10-28 페르소나 p01_a T3 '사회복지관 이름과 연락처도'에서 '이름과'를 사람 이름
#        (이 + 름과)으로 가리고 '개인 정보(이름)를 가렸다'고 알렸다 → 성씨 '이'로 시작하는 흔한
#        낱말을 명사로 둔다
NOUN2 = NOUN2 | frozenset("이름 이웃 이용 이유 이사 이번 이상 이하 이전 이후".split())
PARTICLES = "이가은는을를와과도만의에로"


def _noun_particle(word: str) -> bool:
    return word[:2] in NOUN2 and word[2] in PARTICLES


TITLES = "할머니|할아버지|어르신|씨|님"

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("주민번호", re.compile(r"(?<!\d)\d{6}\s?-?\s?[1-8]\d{6}(?!\d)")),
    ("전화번호", re.compile(r"(?<!\d)(?:01[016789]|0\d{1,2})[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")),
    # 【판단】 '3호선' · '1호점' 같은 말은 빼고, '302호예요'처럼 조사가 붙은 것은 잡는다
    # 【판단】 공문 번호('제2025-복지-0412호')는 앞에 '-'가 붙어 있어 빼낸다(10-12 페르소나)
    ("호수", re.compile(r"(?<![\d가-힣-])\d{1,4}\s?호(?![선점실차기])")),
    # 【판단】 아파트 동 번호(101동). 행정동(역삼1동)은 앞에 한글이 붙어 걸리지 않는다
    # 10-20 페르소나 o01 r4: '2026-09-30 동 자료'의 '30 동'을 아파트 동 번호로 가렸다 → 날짜 뒤는 뺌
    ("아파트 동 번호", re.compile(r"(?<![\d가-힣.-])\d{2,4}\s?동(?![가-힣])")),
)
# 【판단】 우리 동 · 면 이름(수서동 · 사북면 · 삼성동)과 구 · 시 이름만 이름 후보에서 뺀다.
#        전에는 끝 글자(동 · 면 …)로 뺐는데, '홍길동 씨'가 '동'으로 끝나 가려지지 않았다(10-12 r13)
PLACES = (
    {d for ds in dongname.DONGS.values() for d in ds}
    | {fam for (_, fam) in dongname.FAMILY}
    | {"강남구", "춘천시", "서울시", "강원도"}
)
NAME = re.compile(rf"(?<![가-힣])([{SURNAMES}][가-힣]{{2}})(\s?)({TITLES})")
# 【판단】 호칭 없이 이름만 쓴 말(문제 목록 5-2, 10-15): 바로 뒤에 개인을 묻는 말이 올 때만 가린다
#        ('김순자 주소', '박영희는 어디 사셔'). 넓게 잡으면 '노년층 건강'까지 가린다
PERSONAL_ASK = r"주소|연락처|전화|번호|집 |집이|집에|사는 곳|어디 사|건강|형편|몇 호|호수"
BARE_NAME = re.compile(
    rf"(?<![가-힣\[])([{SURNAMES}][가-힣]{{2}})(?=(?:씨|님)?(?:은|는|이|가|의|을|를)?\s?(?:{PERSONAL_ASK}))"
)


_DIGITS = re.compile(r"\D")
_PUBLIC = ("places.json", "pharmacies.json")


@lru_cache(maxsize=1)
def public_numbers() -> frozenset[str]:
    """우리 시설 자료에 실린 기관 전화번호(숫자만) — 가리지 않는다.

    【판단】 10-20 페르소나 f01 r8: 사용자가 비서에게서 받은 행정복지센터 · 보건소 번호를 되읽자
           '개인 정보(전화번호)를 가렸어요'가 붙었다. 공공기관 · 약국 번호는 개인정보가 아니다
    """
    pat = PATTERNS[1][1]
    out: set[str] = set()
    root = Path(__file__).resolve().parents[2] / "data" / "public"

    def walk(v: object) -> None:
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            for m in pat.finditer(v):
                out.add(_DIGITS.sub("", m.group(0)))

    for name in _PUBLIC:
        f = root / name
        if f.exists():
            walk(json.loads(f.read_text(encoding="utf-8")))
    return frozenset(out)


# 【판단】 10-28 재심사 q06_b '엄마가 이틀째 전화를 안 받아요'에서 '이틀째'를 이름(이씨)으로 가렸다.
#        낱말을 하나씩 예외로 더하면(이름과 · 이웃이 · 이틀째 …) 다음 낱말에서 또 걸린다 →
#        원인 둘을 고친다
#        ① 세 글자의 끝이 조사 · 꼬리(째 · 과 · 와 · 를 · 을 · 의 · 에 · 들 …)면
#           '두 글자 낱말 + 꼬리'다
#           (사람 이름은 이런 글자로 거의 끝나지 않는다. '은 · 이'는 이름에도 흔해 넣지 않음)
#        ② '전화를 안 받 · 연락이 안 돼'는 그분 정보를 묻는 말이 아니다
#           (호칭 없는 이름은 정보를 물을 때만)
NOT_NAME_END = frozenset("째과와를을의에들쯤씩께로")
_NOT_ASKING_INFO = re.compile(
    r"\s?(?:씨|님)?(?:은|는|이|가|의|을|를|도)?\s?(?:전화|연락)(?:를|가|도|이)?\s?"
    r"(?:안|못|잘 안|통 안)\s?(?:받|되|돼|닿)"
)


# 【판단】 꾸미는 말 끝(…는 · …던 · …된 · …될 · …할)은 이름 끝 글자가 아니다. 10-12에 '나오는
#        어르신'으로 '는 · 던'만 넣었다가 10-29 브라우저 시험 '계단만 있는 오래된 집이 많음'의
#        '오래된'(+ 집이)을 이름으로 가렸다 → 꾸밈 · 때 꼴 끝을 한 묶음으로
MODIFIER_END = frozenset("는던된될할")


def _not_a_name(word: str) -> bool:
    return word[-1] in NOT_NAME_END or word[-1] in MODIFIER_END


def mask(text: str) -> tuple[str, list[str]]:
    """가린 글과 가린 종류(중복 없이, 나온 순서)."""
    kinds: list[str] = []
    for kind, pat in PATTERNS:
        if kind == "전화번호":

            def phone(m: re.Match[str]) -> str:
                if _DIGITS.sub("", m.group(0)) in public_numbers():
                    return m.group(0)
                if "전화번호" not in kinds:
                    kinds.append("전화번호")
                return "[전화번호]"

            text = pat.sub(phone, text)
            continue
        text, n = pat.subn(f"[{kind}]", text)
        if n and kind not in kinds:
            kinds.append(kind)

    def name(m: re.Match[str]) -> str:
        # 【판단】 '나오는 어르신'처럼 꾸미는 말(MODIFIER_END)은 이름이 아니다(10-12 페르소나)
        if (
            m.group(1) in NOT_NAMES
            or m.group(1)[-1] in MODIFIER_END
            or m.group(1) in PLACES
            or _noun_particle(m.group(1))
        ):
            return m.group(0)
        if "이름" not in kinds:
            kinds.append("이름")
        return f"[이름]{m.group(2)}{m.group(3)}"

    text = NAME.sub(name, text)

    def bare(m: re.Match[str]) -> str:
        if (
            _not_a_name(m.group(1))
            or _NOT_ASKING_INFO.match(m.string, m.end())
            or m.group(1) in NOT_NAMES
            or m.group(1) in PLACES
            or _noun_particle(m.group(1))
        ):
            return m.group(0)
        if "이름" not in kinds:
            kinds.append("이름")
        return "[이름]"

    text = BARE_NAME.sub(bare, text)
    return text, kinds
