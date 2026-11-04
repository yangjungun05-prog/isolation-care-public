from src.assistant import catalog
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.policy import PERSON_NOTE, desk_sanity
from src.assistant.slots import DeskCard, Slots

DATA = JsonDongData()


def test_places_and_support_are_connected():
    # 【기능】 10-13: 갈 곳 · 지원 기관 서가를 이었다(페르소나 20명이 '연결 전'만 들은 곳)
    assert "places" in catalog.READY_IDS and "support" in catalog.READY_IDS
    assert catalog.BY_ID["support"].needs == "region"  # 신청 창구는 동 없이 지역만으로 답한다


def test_rural_places_give_nearest_instead_of_none():
    # 【기능】 면 안에 없으면 '없다'로 끝내지 않고 가장 가까운 곳과 직선거리(10-12 팀장 원칙)
    f = gather("places", Slots(dongs=("북산면",), region="춘천시"), DATA)
    assert "북산면 보건지소(보건지소, 033-251-0555)" in f.text
    # 10-20: 약국은 요일별 운영 시간이 있는 국립중앙의료원 자료로(가까운 약국 · 그날 문 여는지)
    assert "약국: 면 안에 없음(국립중앙의료원 약국 정보" in f.text and "직선" in f.text
    assert "샘밭소양댐약국(신북읍, 직선" in f.text and "요일별 월~토" in f.text
    assert "북산면행정복지센터(북산면 북산로 493, 033-250-3610)" in f.text
    assert "평강요양원" in f.text and "(개정법)" not in f.text
    assert "북산면 보건지소" in f.memo  # '아까 그 보건지소'를 되짚을 수 있게 기억에 남긴다


def test_gangnam_hall_counts_name_both_years():
    # 【판단】 경로당 이름(서울시 2025-06)과 넓이 자료(강남구 2022)의 수가 다르면 해와 함께 둘 다
    f = gather("places", Slots(dongs=("개포3동",), region="강남구"), DATA)
    assert "경로당 7곳(서울시 경로당 현황 2025-06)" in f.text
    assert "강남구 경로당 현황(2022)에는 4곳" in f.text
    assert "강남구청 어르신복지과" in f.text
    f = gather("places", Slots(dongs=("수서동",), region="강남구"), DATA)
    assert "2022" not in f.text  # 수가 같으면 덧붙이지 않는다


def test_support_gangnam_and_chuncheon():
    g = gather("support", Slots(region="강남구"), DATA).text
    assert "동 주민센터에 신청" in g and "강남구노인통합지원센터 02-557-8091" in g
    assert "보건복지상담센터 129" in g
    c = gather("support", Slots(dongs=("효자2동",), region="춘천시"), DATA).text
    assert "춘천동부노인복지관(033-255-8866" in c
    assert "효자2동 행정복지센터: 효자2동행정복지센터(돌담길10번길 8, 033-250-3620)" in c


def test_support_puts_youth_desk_first_for_youth():
    f = gather("support", Slots(dongs=("효자2동",), region="춘천시", target="청년"), DATA)
    assert f.lines[1].startswith("- 청년 연결:") and "청년ON" in f.lines[1]


def test_institution_contact_is_not_a_person_question():
    # 【기능】 '전화번호 · 주소'는 사람 표시 낱말이기도 해서, 기관 질문이 막히지 않게 한다
    card = DeskCard(act="blocked", block="person", topics=("support",))
    fixed, note = desk_sanity(card, "북산면 행정복지센터 전화번호요")
    assert fixed.act == "ask" and fixed.block == "none" and note == ""
    # 가려진 이름이 섞이면 그대로 사람 질문이다
    card = DeskCard(act="blocked", block="person", topics=("places",))
    fixed, note = desk_sanity(card, "[이름] 할머니가 다니는 경로당 알려줘", hidden=["이름"])
    assert note == PERSON_NOTE or fixed.act == "blocked"


def test_home_care_lists_every_agency_with_its_services():
    # 【기능】 10-13 places_30 T9 · T25: 이름을 5곳만 건네 '방문요양 9곳 전체 목록은 자료에 없어요',
    #        '주야간보호 하는 곳 이름은 자료에 없어요'라고 답했다.
    #        우리 자료에 있으니 전부 종류와 함께
    for dong in ("수서동", "효자2동", "석사동"):
        home = DATA.places(dong)["ltc"]["home"]
        assert len(home["list"]) == home["n"]
        text = gather("places", Slots(dongs=(dong,)), DATA).text
        for org in home["list"]:
            assert f"{org['name']}({' · '.join(org['kinds'])})" in text


def test_sex_note_is_not_added_to_facility_answers():
    # 【기능】 10-13 places_30 T19: '퇴계동 할매들 모이는 데'에
    #        '성별로 나눈 숫자가 없어서 …'가 붙었다.
    #        시설 · 집 주제만 답할 때는 사람 수의 성별 · 때 안내가 뜻이 없다
    from src.assistant.policy import disclose

    s = Slots(dongs=("퇴계동",), sex="여", period="작년 겨울")
    assert disclose(DeskCard(), s, None, ("places",)) == ""
    assert "성별" in disclose(DeskCard(), s, None, ("solo_seniors",))
    assert "성별" in disclose(DeskCard(), s)  # 주제를 모르면 예전처럼 밝힌다


def test_desk_knows_our_dong_names():
    # 【기능】 10-13 places_30 T24: '사북면 근처 무료급식소 있어?'를 범위 밖으로 냈다(페르소나 p03도
    #        '사북면(춘천 밖)'). 데스크가 우리 동 이름을 몰랐다 → 지시문에 47곳 이름을 넣는다
    from src.assistant import desk, dongname

    for names in dongname.DONGS.values():
        for n in names:
            assert n in desk.SYSTEM


def test_senior_hall_covers_both_regions_with_years():
    # 【기능】 10-13: 춘천 경로당 수도 답한다
    #        (페르소나 p07 '경로당이 강남만 있다고? 춘천은 왜 없어').
    #        강남은 지금 수(2025-06)와 넓이 자료의 그때 수(2022)를 해와 함께
    f = gather("senior_hall", Slots(dongs=("북산면",)), DATA)
    assert "경로당 9곳 · 마을회관 2곳(전국마을회관및경로당 표준데이터 2025-07)" in f.text
    f = gather("senior_hall", Slots(dongs=("세곡동",)), DATA)
    assert "경로당 25곳(서울시 경로당 현황 2025-06)" in f.text and "그때 24곳 기준" in f.text
    f = gather("senior_hall", Slots(region="춘천시", rank=True), DATA)
    assert "춘천시 경로당 · 마을회관 수(전국마을회관및경로당 표준데이터 2025-07) 많은 동" in f.text
    assert "1위 동내면 32곳 · 2위 퇴계동 30곳" in f.text


def test_places_carries_village_pharmacy_distance_from_diagnosis():
    # 【기능】 10-13 청년 60턴 r3 T30: 남산면 '약국까지 얼마나 멀어요?'가 갈 곳 서가로 가서
    #        '거리는 자료에 없어요'라고 답했다(전에는 진단 서가로 가서 '가운데값 6.1km').
    #        같은 사실은 어느 서가로 가도 같게 — 진단의 약국 · 버스 신호를 갈 곳에도 같은 문장으로
    data = DATA
    # 10-19 2026 최신 판으로 다시 세니 남산면은 가운데값 4.4km라 진단의 '멀다' 신호에서 빠졌다
    #        (10-16 약국 요일별 자료도 화요일 10곳 중 3곳만 5km 넘음과 맞음).
    #        신호가 남은 사북면으로 본다
    text = gather("places", Slots(dongs=("사북면",)), data).text
    assert "마을에서 약국까지 가운데값 13.5km" in text
    # 두 거리를 어디서 쟀는지 밝힌다(북산면: 경로당 가운데에서 직선 9.7km · 마을 가운데값 10.7km)
    text = gather("places", Slots(dongs=("북산면",)), data).text
    assert "마을에서 약국까지 가운데값 10.7km" in text and "경로당들의 가운데에서 잰 직선" in text
