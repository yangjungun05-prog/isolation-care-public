"""장서 목록 — 비서가 가진 자료의 닫힌 목록.

【기능】 범위 판단의 기준. 안내 데스크는 이 목록의 id 중에서만 고른다(strict 도구의 enum).
       목록에 없는 주제는 고를 수 없으니 지어낼 수 없다.
【판단】 데스크 지시문 · 범위 밖 권유 문장 · 이륙 전 체크(필요한 칸)를 모두 여기서 만든다.
       서가를 늘릴 때는 여기에 한 줄 + 사서 함수 하나. 지시문은 손대지 않는다
       (Schema-Guided Dialogue 방식).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Need = Literal["dong", "region", "none"]
Coverage = Literal["both", "강남구", "춘천시"]


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    # 【기능】 데스크가 읽는 설명 — 무엇을 물으면 이 주제인가
    desc: str
    needs: Need
    coverage: Coverage = "both"
    # 【판단】 ready=False 는 '우리 자료지만 이 대화에는 아직 연결 전'. 범위 밖과 다르다
    ready: bool = True
    examples: tuple[str, ...] = ()


TOPICS: tuple[Topic, ...] = (
    Topic(
        "dong_overview",
        "동 상황 한눈에",
        "한 동의 순위 · 진단 · 혼자 사는 어르신 · 청년 · 주민 수(춘천시)를 한꺼번에. "
        "날씨(오늘 · 그날 관측 기록)와 '비 · 눈 · 추위 · 더위일 때 이 동은?'도 "
        "이 주제에 날씨 칸으로",
        "dong",
        examples=("수서동 어때?", "북산면 상황 알려줘"),
    ),
    # 【정함 10-20 팀장】 "수서동의 노인분들이 잘 지내니?"에 단답이 아니라 근거로 — 여러 겹의
    #        조건을 겹쳐 판단한다(conditions.py)
    Topic(
        "outlook",
        "어떻게 지내나(취약 돌보미 판단)",
        "한 동(또는 지역 전체)의 어르신 · 청년이 요즘 잘 지내는지 · 괜찮은지 · 힘들지 · "
        "걱정할 점 · 조심할 점을 묻는 판단 질문. 사람 · 집 · 동네 · 안전망 · 지난 날씨 · "
        "앞으로 날씨 · 달력 · 땅의 조건을 겹쳐 '겹친 걱정'과 그 근거를 준다. "
        "숫자 하나를 물으면 그 현황 주제, 한눈에 보는 현황은 dong_overview",
        "region",
        examples=(
            "수서동 어르신들 잘 지내?",
            "요즘 북산면 괜찮을까?",
            "효자2동 청년들 힘들까?",
            "이번 주 강남 어르신들 걱정할 거 있어?",
        ),
    ),
    Topic(
        "priority",
        "먼저 볼 동(취약 돌보미 동 순위)",
        "지역 안에서 어느 동을 먼저 볼지, 순위 · 위쪽 몇 곳",
        "region",
        examples=("강남에서 먼저 볼 동은?", "춘천 1위는 어디야"),
    ),
    Topic(
        "diagnosis",
        "진단 · 왜 이 동인가",
        "그 동이 왜 위에 있나, 고립 가능성 신호 몇 가지가 해당하나. "
        "신호: 외출 · 연락이 적은 어르신 · "
        "독거노인 중 기초수급 · 저소득 명단에 없는 비율 · 혼자 사는 비율 · 갈 곳 적음 · 계단 집 · "
        "80세 이상 비율 · 약국까지 거리 · 버스가 드묾 · 독거노인이 빠르게 늘어남",
        "dong",
        examples=("개포3동은 왜 1위야?",),
    ),
    Topic(
        "solo_seniors",
        "혼자 사는 어르신",
        "65세 이상 · 80세 이상 1인세대(주민등록) · 실제로 혼자 사는 분 어림 · 1년 변화 · "
        "노인복지시설(요양원) 정원",
        "dong",
        examples=("수서동 혼자 사는 어르신 몇 명?", "작년보다 늘었어?"),
    ),
    Topic(
        "seoul_lonely",
        "서울시 독거노인 현황",
        "서울시가 세는 독거노인 수와 해마다 변화(강남구만)",
        "dong",
        coverage="강남구",
        examples=("서울시 독거노인 현황으로는 몇 명이야?",),
    ),
    Topic(
        "youth",
        "청년",
        "19~34세 청년 인구 · 나이 구간 · 1인세대 · 거의 집에만 있는 청년 어림",
        "dong",
        examples=("역삼1동 청년은?", "은둔 청년 얼마나 돼?"),
    ),
    Topic(
        "housing",
        "사는 집",
        "주거 가구, 30년 넘은 계단 집(승강기 없는 3~5층), 지하층이 있는 오래된 저층 건물",
        "dong",
        examples=("계단만 있는 오래된 집 많아?",),
    ),
    Topic(
        "senior_hall",
        "경로당",
        "경로당 · 마을회관 수와 이름(두 지역), "
        "넓이 · 65세 이상 100명당 넓이(넓이는 강남구만, 2022 현황)",
        "dong",
        examples=("경로당 몇 곳이야?",),
    ),
    Topic(
        "livelihood",
        "기초생활수급자 · 빈집",
        "춘천: 기초생활수급자 수 · 주민 수 · 주민 100명당 · 춘천 안 순서 · 지난해와 견줌 · "
        "빈집 수. "
        "강남: 서울시 독거노인 현황의 기초생활수급권자 · 저소득 · 일반 독거노인과 해마다 변화",
        "dong",
        # 【판단】 10-14: 강남도 '수급권자 독거노인'(서울시 독거노인 현황)으로 답한다(두 지역)
        examples=("교동 수급자 몇 명?", "빈집 있어?", "수서동 수급 받는 독거노인 늘었어?"),
    ),
    Topic(
        "places",
        "갈 곳(동 안 시설)",
        "그 동의 경로당 · 마을회관 이름 · 주소, 무료급식소(요일 · 시간 · 대상), "
        "보건소 · 보건지소 · 보건진료소, 노인복지관, 약국 · 의원 수와 이름, "
        "장기요양기관(방문요양 · 방문목욕 · 주야간보호 같은 재가 기관, 요양원 같은 입소 시설의 "
        "정원 · 현원 · 대기), 주민센터(행정복지센터). 동 안에 없으면 가장 가까운 곳과 직선거리",
        "dong",
        examples=("수서동 경로당 이름이랑 주소 알려줘", "북산면에 보건소나 약국 있어?"),
    ),
    Topic(
        "support",
        "지원 기관 · 신청 창구",
        "응급안전안심서비스(응급 · 안부 장비) · 노인맞춤돌봄 · 안부살핌 우편을 어디에 신청하나와 "
        "맡은 기관 · 전화, 고립 · 은둔 청년을 연결할 곳(청년ON · 행정복지센터 · 청년미래센터), "
        "주민센터(행정복지센터) 주소(두 지역) · 전화(춘천시), 보건소, 노인복지관 · 사회복지관 · "
        "정신건강복지센터 목록(두 지역), 노인일자리 지원기관(강남), 보건복지상담센터, "
        "위기 상담 전화(정신건강 위기상담 1577-0199 · 급할 때 112 · 119)를 어디로 "
        "안내하나. 기관의 전화 · 주소를 묻는 것은 사람 질문이 아니다",
        "region",
        examples=("응급안전안심서비스 신청은 어디서 해?", "청년을 연결할 기관은 어디야?"),
    ),
    Topic(
        "sources",
        "자료 설명 · 출처",
        "숫자가 어디서 왔나 · 기준일 · 어림을 어떻게 만들었나 · 답에 나온 말의 뜻"
        "(다시 매긴 순위 · 진단 · 어림 · 계단 집 등이 무슨 뜻인지)",
        "none",
        examples=("이 숫자 어디서 나온 거야?",),
    ),
    Topic(
        "datasets",
        "원문 자료 · 자료 목록",
        "취약 돌보미가 쓰는 공개 자료의 목록 — 자료 이름 · 만든 기관 · 기준 시점 · 이용 조건 · "
        "받는 곳(주소) · "
        "취약 돌보미에서 어디에 쓰나. '○○ 자료 뭐 있어?', '원본은 어디서 받아?', '이용 조건은?', "
        "'홍보 자료에 써도 돼?'. 숫자 하나가 어디서 왔는지는 sources",
        "none",
        # 【판단】 10-08 팀장 장면 ②(원문 자료) · 설계 v3 서가 표 · 문제 목록 3-4(10-14)
        examples=(
            "우리가 쓰는 자료 목록 보여 줘",
            "보건복지부 자료 뭐 있어?",
            "수급자 원본 어디서 받아?",
        ),
    ),
    Topic(
        "usage",
        "쓰는 법",
        # 10-26 멘토 답 3: 구출 규칙(policy.RESCUES '보고서 쓰는 법')의 말을 장서 목록에도 —
        #        데스크가 먼저 맞게 고르고, 코드 규칙은 받침
        "이 비서로 무엇을 물을 수 있나 · 보고서는 어떻게 쓰나(보고서 길 안내)",
        "none",
        examples=("뭘 물어볼 수 있어?", "보고서 어떻게 써요?"),
    ),
    Topic(
        "my_region",
        "내 담당 지역",
        "내 담당 지역 보기 · 바꾸기",
        "none",
        examples=("내 담당 지역을 춘천 효자2동으로 바꿔줘",),
    ),
    Topic(
        "recall",
        "앞선 대화 되짚기",
        "이 대화 자체를 묻는다(내가 앞서 뭐라고 했나, 지금까지 무엇을 봤나). "
        "앞의 동을 가리키며 그 동의 자료를 물으면 이 주제가 아니다",
        "none",
        examples=("제가 처음에 어디 담당이라고 했죠?", "아까 물어본 동들 정리해 줘"),
    ),
    Topic(
        "bus",
        "춘천 버스",
        "그 동 · 읍면의 정류장 수, 지나는 노선(마을버스는 하루 횟수 어림, 시내버스는 횟수 모름), "
        "노선이 많이 서는 정류장, 하루 3번 이하 마을버스, "
        "마을(경로당)에서 가장 가까운 정류장까지 거리, "
        "춘천에서 하루 3번 이하 마을버스가 지나는 면",
        "dong",
        coverage="춘천시",
        examples=("북산면 버스는 하루 몇 번 다녀?", "퇴계동은 어느 정류장에 버스가 많이 서?"),
    ),
    Topic(
        "dong_doc",
        "동 상황 문서(PDF · PPTX)",
        "한 동의 상황(순위 · 진단 · 어르신 · 청년 · 집 · 갈 곳 · 버스)을 "
        "결재 문서에 옮겨 적을 수 있게 "
        "PDF · PPTX 파일로 만들어 줌(한 곳에 40초쯤). 이 대화 내용을 저장하는 기능은 아니다",
        "dong",
        examples=("수서동 동 상황 PDF로 만들어 줘", "북산면 상황 PPT로 정리해 줘"),
    ),
)

BY_ID: dict[str, Topic] = {t.id: t for t in TOPICS}
# 【기능】 권유 문장에 쓰는 짧은 이름("대신 수서동 청년 현황을 찾아보시는 건 …")
SHORT: dict[str, str] = {
    "dong_overview": "동 상황",
    "outlook": "취약 돌보미 판단(어떻게 지내나)",
    "priority": "먼저 볼 동",
    "diagnosis": "진단",
    "solo_seniors": "혼자 사는 어르신 현황",
    "seoul_lonely": "서울시 독거노인 현황",
    "youth": "청년 현황",
    "housing": "집 상황",
    "senior_hall": "경로당 현황",
    "livelihood": "기초생활수급자 현황",
    "places": "갈 곳",
    "support": "지원 기관 · 신청 창구",
    "bus": "버스",
    "datasets": "자료 목록",
}
TOPIC_IDS: tuple[str, ...] = tuple(t.id for t in TOPICS)
READY_IDS: tuple[str, ...] = tuple(t.id for t in TOPICS if t.ready)
# 【판단】 데이터 주제(동 · 지역 자료). 쓰는 법 · 출처 · 내 설정은 대화 기능이라 권유 대상에서 뺀다
DATA_IDS: tuple[str, ...] = tuple(t.id for t in TOPICS if t.ready and t.needs != "none")


def covers(topic_id: str, region: str | None) -> bool:
    t = BY_ID[topic_id]
    return t.coverage == "both" or region is None or t.coverage == region


def _words() -> dict[str, list[str]]:
    """주제마다 '자료에 있는 것' 낱말.

    scripts/build_catalog_words.py가 사서 줄에서 뽑은 것 + 손으로 더한 말(EXTRA).

    【판단】 10-21 새벽 팀장 "범위 바깥이다(있는데 없다고 대화함) 이게 왜 생기는 걸까": 손으로 적은
           desc 한 줄이 사서보다 좁아(지붕 · 첫차 · 연휴가 없음) 데스크가 범위 밖으로 보냈다.
           자료를 더하면 스크립트를 다시 돌려 이 파일을 새로 만든다
    """
    import json
    from pathlib import Path

    p = Path(__file__).with_name("catalog_words.json")
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def describe_for_desk() -> str:
    """데스크 지시문에 넣는 목록. 순서 · 글자가 늘 같아야 캐시가 된다(정렬하지 않은 원래 순서)."""
    words = _words()
    lines = []
    for t in TOPICS:
        area = "" if t.coverage == "both" else f" [{t.coverage}만]"
        state = "" if t.ready else " [우리 자료지만 이 대화에는 아직 연결 전]"
        ex = f" 예: {' / '.join(t.examples)}" if t.examples else ""
        have = f"\n  자료에 있는 것: {' · '.join(words[t.id])}" if words.get(t.id) else ""
        lines.append(f"- {t.id}: {t.title} — {t.desc}{area}{state}{ex}{have}")
    return "\n".join(lines)
