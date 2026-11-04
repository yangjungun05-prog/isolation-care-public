"""10-18 카드 '먼저 볼 곳'을 날씨마다 — focus.json(big-contest scripts/build_weather_focus.py).

【정함 10-16 팀장】 "비가 오면 … 반지하 + 지하에 살고 있는 사람들", "눈이나 우박이 오면 … 집의
       형태가 눈에 잘 막히는 곳", "약국으로부터 거리가 5KM이상 된 곳". 담당 구역 안에서.
【정함 10-19 팀장】 읍면 카드는 두드러진 마을(리) 이름을 적는다(세 곳까지, 집 20채 넘는 마을만).
"""

from datetime import date

from src.assistant import today
from src.assistant.data_source import JsonDongData
from src.assistant.dongname import DONGS

DATA = JsonDongData()


def _focus(region, dong, kind, day, data=DATA):
    lines, sources = today._focus(kind, region, dong, data, day)
    return " ".join(lines), sources


def test_focus_file_covers_every_dong():
    for names in DONGS.values():
        for n in names:
            fv = DATA.focus(n)
            assert fv, n
            assert fv["unit"] == ("면" if n.endswith(("읍", "면")) else "동")


def test_myeon_pharmacy_line_follows_the_weekday():
    # 남산면은 수요일에만 약국이 먼 마을이 늘어난다(강촌동아약국이 수요일 쉼, 10-16)
    tue, _ = _focus("춘천시", "남산면", "한파", date(2025, 12, 30))
    wed, src = _focus("춘천시", "남산면", "한파", date(2025, 12, 31))
    assert "화요일에 문 연 약국" in tue and "수요일에 문 연 약국" in wed

    def n(s):
        return int(s.split("먼 마을 ")[1].split("곳")[0])

    assert n(wed) > n(tue)
    assert any("요일별 운영 시간" in s for s in src)


def test_holiday_uses_holiday_hours():
    s, _ = _focus("춘천시", "북산면", "폭설", date(2025, 12, 25))
    assert "공휴일에 문 연 약국" in s


def test_myeon_rain_names_the_villages():
    # 10-19 팀장: "동 안에 있는 마을들 중에서 취약점이 눈에 보이는게 있으면 거기를 적어줘"
    lines, src = today._focus("폭우", "춘천시", "북산면", DATA, date(2025, 7, 16))
    s = " ".join(lines)
    assert "산사태취약지역 28곳" in s and "급경사지 80곳" in s and "마을 8곳에 걸침" in s
    assert "청평리 32곳" in s
    villages = [v["name"] for v in DATA.focus("북산면")["villages"]]
    for line in lines:  # 줄마다 마을 이름은 세 곳까지
        assert sum(1 for v in villages if f"{v} " in line) <= today.VILLAGE_MAX
    assert any("산사태" in x for x in src) and any("급경사지" in x for x in src)


def test_village_names_skip_tiny_villages():
    vs = DATA.focus("북산면")["villages"]
    tiny = [v["name"] for v in vs if (v.get("homes") or 0) < today.MIN_HOMES]
    s, _ = _focus("춘천시", "북산면", "폭우", date(2025, 7, 16))
    assert not any(f"{n} " in s for n in tiny)


def test_myeon_pharmacy_and_roof_lines_name_villages():
    s, _ = _focus("춘천시", "사북면", "폭설", date(2025, 12, 30))
    assert "먼 곳 원평리" in s and "km" in s.split("먼 곳")[1]
    assert "오탄리" in s  # 약한 지붕이 가장 많은 마을


def test_region_card_names_no_village_or_dong():
    s, _ = _focus("춘천시", None, "폭설", date(2025, 12, 30))
    villages = {
        v["name"] for n in DONGS["춘천시"] for v in (DATA.focus(n) or {}).get("villages") or []
    }
    assert not any(v in s for v in villages)


def test_basement_home_replaces_old_estimate_when_fetched():
    # 층별개요를 다 받은 동은 '지하층에 집' 줄, 표제부 어림('반지하가 있을 수 있는') 줄은 뺀다.
    # 10-19 층별개요를 두 지역 모두 다 받음(춘천 5,990 · 강남 6,754 지번)
    for region, dong in (("춘천시", "효자2동"), ("춘천시", "석사동"), ("강남구", "개포4동")):
        fv = DATA.focus(dong)
        assert fv["basement_lots_fetched"] >= today.COVER * fv["basement_lots_need"]
        s, _ = _focus(region, dong, "폭우", date(2025, 7, 16))
        assert "지하층에 집이 있는 건물" in s and "반지하가 있을 수 있는" not in s


def test_old_estimate_when_floors_not_fetched():
    # 층별개요를 덜 받은 동은 표제부 어림 줄을 그대로 쓴다(받은 몫 < COVER)
    class Half(type(DATA)):
        def focus(self, name):
            fv = dict(super().focus(name))
            fv["basement_lots_fetched"] = 0
            return fv

    s, _ = _focus("춘천시", "석사동", "폭우", date(2025, 7, 16), Half())
    assert "지하층에 집이 있는 건물" not in s and "반지하가 있을 수 있는" in s


def test_gangnam_flood_history_is_whole_numbers():
    s, src = _focus("강남구", "개포4동", "폭우", date(2025, 7, 16))
    assert "침수 흔적이 나온 해" in s and ".0곳" not in s
    assert any("침수흔적도" in x for x in src)
    region, _ = _focus("강남구", None, "폭우", date(2025, 7, 16))
    assert "침수 흔적이 나온 동" in region
    # 10-19 팀장이 맡김: 구 담당은 흔적이 많은 동 세 곳의 이름을 붙인다(정수)
    assert "흔적이 많은 곳" in region and ".0곳" not in region
    lines, _ = today._focus("폭우", "강남구", None, DATA, date(2025, 7, 16))
    flood = next(x for x in lines if "침수 흔적이 나온 동" in x)
    assert 1 <= sum(n in flood for n in DONGS["강남구"]) <= 3


def test_snow_tells_weak_roofs():
    s, _ = _focus("춘천시", "사북면", "폭설", date(2025, 12, 30))
    assert "눈 무게에 약한 지붕" in s


def test_public_institutions_join_the_pharmacy_line():
    # 10-19 팀장: 공공기관 = 행정복지센터 · 보건지소 · 노인복지관 · 병원.
    #   약국 줄에 '공공기관도 먼 마을'을 붙인다
    s, src = _focus("춘천시", "동면", "한파", date(2025, 12, 30))
    assert "문 연 약국이 5km 넘게 먼 마을" in s and "공공기관" in s and "품걸리" in s
    assert any("행정복지센터" in x for x in src)
    # 동 지역은 모두 가까워(1.3km 안) 이 말이 없다
    s2, _ = _focus("강남구", "수서동", "한파", date(2025, 12, 30))
    assert "공공기관" not in s2
