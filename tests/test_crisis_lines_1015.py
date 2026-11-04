"""지원 기관 서가에 위기 상담 번호(10-15, 페르소나 20b q07 정신건강복지센터 상담사).

q07 T5 '찾아가는 상담에서 자살 생각이 있는 분을 만나면 어디로?' → '129로 바로 연결 ·
따로 안내할 번호는 자료에 없어요'. T6 '109나 1577-0199를 먼저 안내하는 게 맞지 않나요?'
→ 범위 밖. 생명이 걸린 안내라 국가 공식 번호를 서가에 둔다(CARE 문장이 쓰는 번호와 같음).
"""

from src.assistant import catalog
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.policy import CARE
from src.assistant.slots import Slots

DATA = JsonDongData()


def test_support_shelf_has_crisis_lines():
    for region in ("강남구", "춘천시"):
        text = "\n".join(gather("support", Slots(region=region), DATA).lines)
        assert "1577-0199" in text and "119" in text and "129" in text
        # 10-28 팀장 "자살예방상담 <- 너무 쎈 것 같아. 정신건강 위기상담만" — 109는 안내하지 않는다
        assert "자살예방" not in text


def test_crisis_numbers_match_the_care_sentence():
    text = "\n".join(gather("support", Slots(region="춘천시"), DATA).lines)
    assert "1577-0199" in CARE and "1577-0199" in text
    assert "109" not in CARE and "자살예방" not in CARE


def test_catalog_tells_the_desk_crisis_lines_live_here():
    assert "위기 상담" in catalog.BY_ID["support"].desc
