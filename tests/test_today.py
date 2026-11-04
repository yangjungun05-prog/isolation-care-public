"""오늘 챙길 일 카드(비서 설계 v3 4절, 10-14)."""

from src.assistant import today
from src.assistant.data_source import JsonDongData
from src.assistant.dongname import DONGS

DATA = JsonDongData()


def _cards(region=None, dong=None, on=None):
    return today.cards(today.Who(member_region=region, member_dong=dong), DATA, on)


def test_dong_member_gets_cold_card_on_basis_day():
    # 기준일 2025-12-31: 서울 관측소 최저 -8.9℃(한파 기준 -8℃ 이하)
    # 【10-16】 날짜를 안 주면 진짜 오늘(기상청 예보)이라, 지난 날짜를 주고 관측을 되짚는다
    r = _cards("강남구", "수서동", "2025-12-31")
    kinds = [c["kind"] for c in r["cards"]]
    assert "한파" in kinds
    c = next(c for c in r["cards"] if c["kind"] == "한파")
    # 10-19 자동 받기로 관측이 2026년까지 늘어 사흘 안(12-31 ~ 1-2)에서 가장 추운 날을 제목에 쓴다
    days = DATA.weather()["regions"]["강남구"]["days"]
    low = min(days[d]["tmin"] for d in ("2025-12-31", "2026-01-01", "2026-01-02") if d in days)
    assert c["where"] == "강남구 수서동" and f"{low:.1f}" in c["title"]
    assert c["focus"][-1].startswith("80세 이상 혼자 사시는 분")  # 늘 맨 뒤 한 줄(10-16)
    assert "동 상황 문서" in c["buttons"]
    assert all("검증됨" not in s and "참고" not in s for s in c["sources"])  # 딱지 없음


def test_region_member_card_names_big_dongs_not_a_rank():
    # 【정함 10-12 팀장】 먼저 볼 동 순위는 카드에 넣지 않는다 — 구 담당이면 챗봇으로 넘기는 단추.
    # 【정함 10-19 팀장이 맡김】 줄마다 값이 큰 동 세 곳까지는 적는다
    r = _cards("강남구", on="2025-12-31")
    c = r["cards"][0]
    for line in c["focus"]:
        assert sum(n in line for n in DONGS["강남구"]) <= 3, line
    assert "어느 동부터 볼지 묻기" in c["buttons"]


def test_rain_card_replays_observation():
    r = _cards("강남구", "수서동", "2025-07-15")
    c = next(c for c in r["cards"] if c["kind"] == "폭우")
    assert "16일" in c["title"] and "73.1" in c["why"]
    assert "due" not in c  # 10-19 팀장: 기한 문구는 뺌
    assert "되짚어" in c["why"]  # 예보가 아니라 관측을 되짚는다고 밝힘


def test_long_holiday_card_a_week_before():
    r = _cards("춘천시", "효자2동", "2025-09-29")
    c = next(c for c in r["cards"] if c["kind"] == "긴 연휴")
    assert "10월 3일" in c["title"] and "7일간" in c["title"]
    assert "추석" in c["why"]


def test_myeon_card_tells_pharmacy_and_bus():
    r = _cards("춘천시", "사북면", "2025-12-31")
    c = r["cards"][0]
    # 10-16: 면 한파는 수급자 · 약국 순(두 줄까지) + 80세 이상 한 줄
    s = " ".join(c["focus"])
    # 10-18: 면 한파는 그날(12-31 수) 문 연 약국이 먼 마을 수가 먼저(focus.json)
    assert "문 연 약국이 5km 넘게 먼 마을" in s and len(c["focus"]) <= 3
    assert "todo" not in c  # 10-19 팀장: 할 일은 적지 않는다


def test_no_region_asks_to_set_one():
    r = _cards()
    assert r["cards"] == [] and "담당 지역" in r["notice"]


def test_quiet_day_says_so():
    r = _cards("강남구", "수서동", "2025-11-20")
    assert r["cards"] == [] and r["notice"]
