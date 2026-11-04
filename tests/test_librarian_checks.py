from src.assistant import checks
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather, trend
from src.assistant.slots import AgeRange, Slots

DATA = JsonDongData()


def test_trend_wording():
    assert trend(2316, 2471) == "2,316명 → 2,471명(155명 늘었음, 7%)"
    assert trend(77, 73) == "77명 → 73명(4명 줄었음, 5%)"


def test_solo_seniors_numbers_come_from_data():
    f = gather("solo_seniors", Slots(dongs=("수서동",), region="강남구"), DATA)
    # 10-19 자료 2026 최신 판: 2025-09 → 2026-09
    assert "2025-09 → 2026-09 2,462명 → 2,543명(81명 늘었음, 3%)" in f.text
    assert ("65세 이상 1인세대", 2462, 2543) in f.compares
    # 【기능】 서울시 현황이 주민등록보다 많은지 · 적은지는 동마다 계산한다(10-12 대치1동 교훈)
    assert "보다 많음" in f.text


def test_seoul_count_smaller_than_registry_is_said():
    f = gather("seoul_lonely", Slots(dongs=("대치1동",)), DATA)
    assert "보다 적음" in f.text


def test_rank_fix_sentence_is_single_meaning():
    f = gather("diagnosis", Slots(dongs=("북산면",)), DATA)
    assert "동 순위를 다시 매기면 7위" in f.text  # 혼자 사는 비율의 순위로 읽히지 않게


def test_priority_and_age_note():
    f = gather("priority", Slots(region="춘천시", ages=AgeRange(lo=70)), DATA)
    assert "1위 효자2동" in f.text  # 10-19 2026 최신 판(전에는 1위 북산면)
    assert "65세 이상" in f.text  # 자료에 없는 구간(70세 이상)을 물으면 자료의 나이 구간을 밝힌다


def test_youth_under10():
    f = gather("youth", Slots(dongs=("북산면",)), DATA)
    assert "10명 미만" in f.text


def test_checks_catch_extra_numbers_direction_banned():
    src = "65세 이상 1인세대: 2,316명 → 2,471명(155명 늘었음, 7%)"
    assert checks.problems("2,471명으로 155명 늘었어요.", src, [("x", 2316, 2471)]) == []
    assert "없는 숫자 3000" in checks.problems("3,000명이에요", src, [])
    assert checks.wrong_direction("2,471명으로 줄었어요", [("x", 2316, 2471)])
    # 【판단】 10-12: '없다' 말은 숫자 없이 끝날 때만 버린다(checks.none_only)
    assert checks.none_only("자료가 없어서 모르겠어요", src)


def test_direction_check_is_local_to_each_number():
    # 【기능】 한 줄에 두 동의 변화가 같이 있어도 오탐하지 않는다(100턴 2차 T36)
    line = "효자2동 1,659명→1,623명(36명 줄었음, 2%), 교동 348명→365명(17명 늘었음, 5%)"
    cmp = [("효자2동", 1659, 1623), ("교동", 348, 365)]
    assert checks.wrong_direction(line, cmp) == []
    assert checks.wrong_direction("교동 348명→365명으로 줄었어요", [("교동", 348, 365)])


def test_solo80_and_care_facility_mix():
    # 【기능】 80세 이상 1인세대 자료가 있다(공개 동 순위 표). 없다고 답하지 않는다(100턴 3차 T39)
    # 10-19 2026 최신 판: 북산면은 정원(17)이 80세 이상 1인세대(63)의 30%가 안 되어 조운동으로 봄
    f = gather("solo_seniors", Slots(dongs=("조운동",), ages=AgeRange(lo=80)), DATA)
    assert "80세 이상 1인세대(주민등록 2026-09): 166명" in f.text
    assert "시설 입소자가 섞여 있을 수 있음" in f.text
    assert not f.notes  # 80세 이상은 자료에 있는 구간이라 나이 안내를 붙이지 않는다
    assert checks.none_only("인원 수가 없어서 답할 수 없습니다", f.text)


def test_diagnosis_with_age_includes_counts():
    # 【기능】 '80세 이상 몇 명?'에 진단을 골라도 숫자가 들어간다(100턴 3 · 4차 T39)
    f = gather("diagnosis", Slots(dongs=("효자2동",), ages=AgeRange(lo=80)), DATA)
    assert "80세 이상 1인세대(주민등록 2026-09): 444명" in f.text
    assert checks.none_only("80세 이상 인구는 나와 있지 않습니다", f.text)
