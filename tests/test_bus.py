from src.assistant import catalog
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots

DATA = JsonDongData()


def test_bus_is_connected_for_chuncheon_only():
    # 【기능】 10-13: 춘천 버스 서가를 이었다(페르소나 20명이 '연결 전'을 가장 많이 들은 곳, 8번)
    t = catalog.BY_ID["bus"]
    assert t.ready and t.coverage == "춘천시"


def test_rural_bus_routes_and_village_distance():
    f = gather("bus", Slots(dongs=("북산면",)), DATA)
    assert "북산1(하루 약 7번, 이 면 정류장 23곳)" in f.text
    assert "이 면을 지나는 하루 3번 이하 마을버스: 북산2(하루 약 2번)" in f.text
    assert "물로리 경로당 → 떡갈매기 8.21km" in f.text
    assert "북산면 버스" in f.memo  # '아까 하루 두 번 다니는 노선'을 되짚을 수 있게


def test_city_dong_busy_stops_and_unknown_city_bus_count():
    # 【판단】 시내버스는 배차 간격 자료가 없어 하루 횟수를 모른다 — 지어내지 않고 모른다고 적는다
    f = gather("bus", Slots(dongs=("퇴계동",)), DATA)
    assert "남춘천역(29개 노선)" in f.text
    assert "시내버스 31개(하루 횟수 모름)" in f.text
    # 면에 붙은 드문 노선도 시내 동을 지나가면 그 동에서 센다(원자료 계산은 '면'에만 붙임)
    assert "이 동을 지나는 하루 3번 이하 마을버스:" in f.text and "남면2-1(하루 약 2번)" in f.text


def test_total_routes_is_given_so_writer_need_not_add():
    # 【기능】 10-13 버스 r6 T11: '효자2동은 노선이 몇 개?'에 글쓴이가 11 + 30 = 41을 직접 더해
    #        '없는 숫자 41'로 버려졌다. 합계는 사서가 미리 센다(사서 원칙: 계산은 코드)
    f = gather("bus", Slots(dongs=("효자2동",)), DATA)
    b = DATA.bus("효자2동")
    town = sum(r["per_day"] is not None for r in b["routes"])
    assert f"지나는 노선 {len(b['routes'])}개(마을버스 {town}개 · 시내버스 " in f.text


def test_none_only_counts_bus_units():
    # 【기능】 10-13 버스 r6 T12: '시내버스 하루 횟수는 알 수 없어요'에
    #        마을버스 횟수(○번)를 같이 줘도
    #        '없다고만 함'으로 걸렸다 — 검사가 아는 단위에 번 · 개 · km를 더한다
    from src.assistant import checks

    src = "- 마을버스 11개: 동내1(하루 약 9번)\n- 시내버스 30개(하루 횟수 모름)"
    ans = "시내버스는 하루 횟수를 알 수 없어요. 마을버스는 동내1이 하루 약 9번이에요."
    assert checks.none_only(ans, src) == []
    assert checks.none_only("시내버스 횟수는 알 수 없어요.", src)  # 숫자 없이 끝나면 그대로 실패
