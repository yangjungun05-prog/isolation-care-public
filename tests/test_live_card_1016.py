"""10-16 카드의 진짜 오늘 — 기상청 특보가 나오면 특보,
없으면 동마다 단기예보가 우리 기준값을 넘을 때.

【정함 10-16 팀장】 "1,2,3,4 ㄱㄱ"(2026 최신 판 · 진짜 오늘 · 특보 우선 · 11-03은 이 저장소 화면)
기상청에는 묻지 않는다(가짜 FakeWx). 진짜 기상청 연결은 손으로 잰다(HANDOVER 0-10).
"""

from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.assistant import done, today, today_api
from src.assistant import forecast as fc
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.dongname import DONGS

DATA = JsonDongData()
D = fc.today_kst()


def _day(n: int) -> str:
    return (D + timedelta(days=n)).isoformat()


def _calm() -> dict:
    return {
        _day(i): {"tmin": 12.0, "tmax": 21.0, "rain": 0.0, "snow": 0.0, "pop": 20} for i in range(4)
    }


class FakeWx:
    """기상청 대신. rain: {동: (며칠 뒤, mm)} · now/soon: 특보 글 ·
    fail: 'fcst' 또는 'wrn'이면 그쪽이 실패."""

    def __init__(self, rain=None, now=(), soon=(), fail=""):
        self.rain, self.now, self.soon, self.fail = rain or {}, list(now), list(soon), fail
        self.asked: list[dict] = []

    def forecast(self, grids):
        if self.fail == "fcst":
            raise fc.ForecastError("기상청 단기예보를 받지 못함: URLError")
        self.asked.append(dict(grids))
        out = {}
        for dong in grids:
            days = _calm()
            if dong in self.rain:
                n, mm = self.rain[dong]
                days[_day(n)]["rain"] = mm
            out[dong] = days
        return out, f"{D.isoformat()} 14:00"

    def warnings(self, region):
        if self.fail == "wrn":
            raise fc.ForecastError("기상청 특보 현황을 받지 못함: URLError")
        now = [(h, fc.kind_of(h)) for h in self.now]
        soon = [(t, fc.kind_of(t)) for t in self.soon]
        return {
            "issued": f"{D.isoformat()} 10:00",
            "area": fc.AREA[region],
            "now": now,
            "soon": soon,
        }


def _cards(region, dong, wx):
    return today.cards(today.Who(member_region=region, member_dong=dong), DATA, None, wx)


def _weather(r):
    # 앞을 보는 날씨 카드만(큰비 · 눈이 그친 뒤 카드는 진짜 오늘의 관측에 따라 서서 뺀다, 10-20)
    return [c for c in r["cards"] if c["kind"] in today.GROUP]


def test_grid_formula_matches_kma_points():
    # 기상청 격자 공식: 서울시청(60,127) · 춘천시청(73,134)
    assert fc.to_grid(37.5665, 126.9780) == (60, 127)
    assert fc.to_grid(37.8813, 127.7298) == (73, 134)
    g = DATA._j("grids")["regions"]  # noqa: SLF001
    for region in ("강남구", "춘천시"):
        assert set(g[region]) == set(DONGS[region])  # 동마다 격자가 있다
        for v in g[region].values():
            assert fc.to_grid(v["lat"], v["lon"]) == (v["nx"], v["ny"])


def test_daily_reads_kma_words():
    items = [
        {"fcstDate": "20261018", "fcstTime": "1500", "category": "PCP", "fcstValue": "30.0~50.0mm"},
        {"fcstDate": "20261018", "fcstTime": "1600", "category": "PCP", "fcstValue": "1mm 미만"},
        {"fcstDate": "20261018", "fcstTime": "1700", "category": "PCP", "fcstValue": "21.0mm"},
        {"fcstDate": "20261018", "category": "SNO", "fcstValue": "적설없음"},
        {"fcstDate": "20261018", "category": "TMN", "fcstValue": "11.0"},
        {"fcstDate": "20261018", "category": "TMP", "fcstValue": "19"},
        {"fcstDate": "20261018", "category": "POP", "fcstValue": "90"},
    ]
    day = fc.daily(items)["2026-10-18"]
    assert day["rain"] == 51.0 and day["snow"] == 0.0
    assert day["tmin"] == 11.0 and day["tmax"] == 19.0 and day["pop"] == 90
    assert day["rain_peak"] == [15, 17] and day["snow_peak"] is None  # 30 · 0 · 21 → 15~17시


def test_warning_text_parsing():
    t6 = "o 호우주의보 : 서울(동남권, 서남권), 경기도(가평)\no 강풍주의보 : 강원도(강원북부산지)"
    got = [(h, a) for h, a in fc.lines(t6)]
    assert got[0][0] == "호우주의보" and fc.covers("강남구", got[0][1])
    assert not fc.covers("춘천시", got[1][1])  # 권역이 붙은 강원은 춘천이 적혀야
    assert fc.covers("춘천시", "강원도") and not fc.covers("강남구", "서울(동북권)")
    assert fc.kind_of("한파경보") == "한파" and fc.kind_of("강풍주의보") is None


def test_forecast_over_threshold_makes_dong_card():
    wx = FakeWx(rain={"수서동": (2, 51.0)})
    r = _cards("강남구", "수서동", wx)
    c = next(c for c in r["cards"] if c["kind"] == "폭우")
    assert "51mm" in c["title"] and "기상청 단기예보" in c["why"]
    assert "되짚어" not in c["why"]  # 진짜 예보다
    assert c["sources"][0] == fc.SOURCE_FCST
    # 비 오기 전날까지, 그날이 쉬는 날이면 그 전 마지막 근무일
    assert "due" not in c and c["start"]  # 10-19 팀장: 기한 문구는 뺌
    assert r["weather"]["mode"] == "예보" and r["weather"]["forecast_issued"]
    assert wx.asked == [{"수서동": DATA.grids("강남구")["수서동"]}]  # 그 동 격자만 물었다


def test_warning_comes_first_and_replaces_forecast_card():
    # 【정함 10-16 팀장】 특보가 나오면 특보로 — 같은 종류의 예보 카드는 내지 않는다
    wx = FakeWx(rain={"수서동": (1, 80.0)}, now=["호우주의보"])
    r = _cards("강남구", "수서동", wx)
    rain = [c for c in r["cards"] if c["kind"] == "폭우"]
    assert len(rain) == 1
    c = rain[0]
    assert "호우주의보" in c["title"] and "서울 동남권" in c["why"]
    assert c["sources"][0] == fc.SOURCE_WRN and "due" not in c


def test_pre_warning_makes_card_and_other_warnings_are_listed():
    wx = FakeWx(now=["강풍주의보"], soon=["(1) 한파 예비특보 : 강원도"])
    r = _cards("춘천시", "북산면", wx)
    c = next(c for c in r["cards"] if c["kind"] == "한파")
    assert "예비특보" in c["title"]
    assert r["weather"]["other_warnings"] == ["강풍주의보"]  # 카드 종류가 아닌 특보는 알림으로만


def test_region_member_names_dongs_over_threshold():
    # 10-19 팀장이 맡김: 구 담당 예보 카드는 기준을 넘는 동 이름과 값을 센 쪽부터
    wx = FakeWx(rain={"수서동": (2, 45.0), "세곡동": (2, 35.0)})
    r = _cards("강남구", None, wx)
    c = next(c for c in r["cards"] if c["kind"] == "폭우")
    assert "22곳 중 2곳" in c["why"] and "최대 45.0mm" in c["why"]
    assert "22곳 중 2곳이 기준을 넘음(수서동 45.0mm · 세곡동 35.0mm)" in c["sub"]
    # 순위는 챗봇에서(10-12 팀장) · 취약 돌보미 판단도 챗봇에서(10-20 팀장이 맡김)
    assert c["buttons"] == ["어느 동부터 볼지 묻기", "취약 돌보미 판단 보기"]


def test_quiet_forecast_gives_no_weather_card():
    r = _cards("춘천시", "효자2동", FakeWx())
    assert _weather(r) == []


def test_kma_failure_keeps_other_cards_and_says_so():
    r = _cards("강남구", "수서동", FakeWx(fail="fcst", now=["폭염경보"]))
    assert [c["kind"] for c in _weather(r)] == ["폭염"]  # 특보 카드는 낸다
    assert "단기예보" in r["weather"]["error"]
    r = _cards("강남구", "수서동", FakeWx(fail="wrn", rain={"수서동": (0, 40.0)}))
    assert [c["kind"] for c in _weather(r)] == ["폭우"]
    assert "특보" in r["weather"]["error"]


def test_past_date_still_replays_observation_without_kma():
    wx = FakeWx()
    r = today.cards(today.Who(member_region="강남구", member_dong="수서동"), DATA, "2025-07-15", wx)
    assert wx.asked == [] and r["weather"]["mode"] == "관측 되짚기"
    assert any(c["kind"] == "폭우" for c in r["cards"])


def test_api_today_without_date_is_real_today(tmp_path):
    app = FastAPI()
    app.include_router(
        today_api.router(
            done_store=done.JsonlDoneStore(tmp_path / "done.jsonl"),
            weather=FakeWx(rain={"효자2동": (1, 60.0)}),
            get_settings=lambda: AssistantSettings(as_of="live"),
        )
    )
    c = TestClient(app)
    body = c.get("/assistant/today", params={"region": "춘천시", "dong": "효자2동"}).json()
    assert body["date"] == D.isoformat() and body["weather"]["mode"] == "예보"
    assert any(c["kind"] == "폭우" for c in body["cards"])


def test_no_deadline_on_cards():
    # 【정함 10-19 팀장】 "카드 기한 문구 <- 빼줘" — 10-16의 '마지막 근무일로 당기기'도 함께 없어짐
    assert not hasattr(today, "_lead") and not hasattr(today, "_due")


def test_holidays_cover_this_year_and_next_from_october():
    # 【기능】 긴 연휴 카드는 한 달 반 앞을 본다 — 10월부터는 다음 해 공휴일도 있어야
    #        (scripts/update_holidays.py)
    years = {int(k[:4]) for k in DATA.holidays()}
    assert D.year in years
    if D.month >= 10:
        assert D.year + 1 in years
