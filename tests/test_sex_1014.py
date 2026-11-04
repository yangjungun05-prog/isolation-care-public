"""강남 성별 — 서울시 독거노인 현황 성별동별(DT_201004_F030011, 공공누리 1유형, 10-14).

【기능】 전에는 '할머니 · 할아버지'를 물으면 늘 '성별로 나눈 숫자가 없어
       남녀 합친 숫자로'라고만 했다.
       강남은 서울시 현황에 동별 남 · 여가 있다(문제 목록 3-3, 빅콘 3d86491로 내보냄).
"""

from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.policy import disclose
from src.assistant.slots import DeskCard, Slots

DATA = JsonDongData()


def test_dong_answer_has_sex_numbers_first():
    f = gather("solo_seniors", Slots(region="강남구", dongs=("수서동",), sex="여"), DATA)
    text = "\n".join(f.lines)
    assert "여성(할머니): 2024년 → 2025년 2,816명 → 2,958명" in text
    assert "남성(할아버지)은 1,548명" in text and "기초생활수급권자 1,125명" in text
    assert f.lines[1].startswith("- 서울시 독거노인 현황 여성")  # 성별 줄이 맨 앞


def test_rank_by_sex_in_gangnam_only():
    f = gather("solo_seniors", Slots(region="강남구", sex="남", rank=True), DATA)
    assert "남성(할아버지)" in f.lines[0] and "1위 수서동 1,548" in f.lines[0]
    cc = gather("solo_seniors", Slots(region="춘천시", sex="남", rank=True), DATA)
    assert "성별" not in cc.lines[0] and "65세 이상 1인세대" in cc.lines[0]


def test_disclose_says_where_sex_numbers_come_from():
    gn = disclose(DeskCard(), Slots(region="강남구", sex="여"), None, ("solo_seniors",))
    # 10-26: 문장을 '서울시 독거노인 현황으로 답해요'로(전 문장은 '성별 숫자는 없다'로 읽힘)
    assert "서울시 독거노인 현황으로 답해요" in gn
    cc = disclose(DeskCard(), Slots(region="춘천시", sex="여"), None, ("solo_seniors",))
    assert "성별로 나눈 숫자가 없어서" in cc
    yt = disclose(DeskCard(), Slots(region="강남구", sex="여"), None, ("youth",))
    assert "성별로 나눈 숫자가 없어서" in yt
