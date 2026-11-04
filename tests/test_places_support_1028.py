"""10-27 밤: 강남 주민센터 주소 · 노인복지관 · 두 지역 사회복지관 · 정신건강복지센터.

팀장(10-27 밤): '고칠거, 해결해야할거. 추가할거. 등등'.

전에는 강남 주민센터가 이름만, 노인복지관은 '이용 조건이 적힌 파일을 못 찾았다'고 답했다.
"""

from src.assistant import librarian
from src.assistant.data_source import JsonDongData
from src.assistant.slots import Slots

DATA = JsonDongData()


def _lines(topic: str, **slots) -> str:
    return "\n".join(librarian.gather(topic, Slots(**slots), DATA).lines)


def test_gangnam_office_has_address_and_120():
    text = _lines("places", region="강남구", dongs=("수서동",))
    assert "수서동 주민센터(서울특별시 강남구 광평로 301-4" in text or "광평로 301-4" in text
    assert "다산콜센터 120" in text
    support = _lines("support", region="강남구", dongs=("수서동",))
    assert "수서동 주민센터: 수서동 주민센터(" in support and "광평로 301-4" in support


def test_gangnam_senior_centers_are_listed():
    support = _lines("support", region="강남구")
    assert "강남구 노인복지관 7곳" in support and "대치노인복지관" in support
    text = _lines("places", region="강남구", dongs=("대치4동",))
    assert "노인복지관: 강남구립 대치노인복지관" in text
    # 동 안에 없으면 가장 가까운 곳과 직선거리
    near = _lines("places", region="강남구", dongs=("수서동",))
    assert "노인복지관" in near and "km" in near
    assert "아직 찾지 못해" not in near


def test_chuncheon_office_keeps_phone():
    text = _lines("places", region="춘천시", dongs=("신북읍",))
    assert "행정복지센터: 신북읍행정복지센터(" in text and "033-250-3601" in text
    assert "다산콜센터" not in text


def test_gangnam_support_lists_welfare_and_mental_health():
    support = _lines("support", region="강남구")
    assert "강남구 사회복지관 6곳" in support and "수서명화종합사회복지관" in support
    assert "정신건강복지센터" in support and "강남구중독관리통합지원센터" in support
    assert "노인일자리 지원기관 2곳" in support
    # 춘천은 강원도 사회복지관 · 춘천시 정신건강센터 현황(10-27 밤 받음)으로 — 전화까지 있다
    cc = _lines("support", region="춘천시")
    assert "춘천시 사회복지관 3곳(이름 · 주소)" in cc and "033-261-1790" in cc
    assert "춘천시정신건강복지센터" in cc and "033-244-7574" in cc
    assert "노인일자리 지원기관" not in cc


def test_dong_places_show_welfare_center_in_that_dong():
    # 10-27 밤 페르소나 s01 T5: 개포3동에 강남종합사회복지관이 있는데 '복지관 없음'만
    text = _lines("places", region="강남구", dongs=("개포3동",))
    assert "사회복지관: 강남종합사회복지관(개포로109길 5" in text
    cc = _lines("places", region="춘천시", dongs=("효자2동",))
    assert "사회복지관: 춘천효자종합사회복지관(" in cc and "033-261-1790" in cc
    assert "정신건강복지센터 · 중독관리통합지원센터: 춘천시정신건강복지센터" in _lines(
        "places", region="춘천시", dongs=("약사명동",)
    )
