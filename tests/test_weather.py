from datetime import date, timedelta

from src.assistant import catalog, librarian
from src.assistant import forecast as fc
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.policy import disclose, preflight
from src.assistant.slots import DeskCard, Slots, card_from_tool
from src.assistant.state import DialogueState, Profile, apply_card, new_state

DATA = JsonDongData()


def test_no_weather_shelf_weather_is_a_condition():
    # 【판단】 10-13 팀장 결정: 날씨 서가는 없애고 날씨는 동 상황의 조건으로
    assert "weather_today" not in catalog.TOPIC_IDS
    c = card_from_tool({"restate": "", "act": "ask", "topics": ["dong_overview"], "weather": "비"})
    assert c.weather_op == "set" and c.weather == "비"
    c = card_from_tool({"restate": "", "act": "ask", "topics": ["youth"], "off": ["weather"]})
    assert c.weather_op == "clear"


def test_weather_kept_on_follow_up_and_cleared_when_topic_changes():
    st = DialogueState(profile=Profile(member_region="강남구"))
    card = DeskCard(
        act="ask",
        topics=("dong_overview",),
        dong_op="set",
        dong_mentions=("역삼1동",),
        weather_op="set",
        weather="비",
    )
    st = apply_card(st, card, "폭우 오면 역삼1동은?").state
    st = apply_card(
        st, DeskCard(act="ask", dong_op="set", dong_mentions=("수서동",)), "수서동은요?"
    )
    assert st.state.slots.weather == "비"  # 주제를 생략한 이어 묻기는 조건을 남긴다
    st = apply_card(st.state, DeskCard(act="ask", topics=("youth",)), "그냥 청년은?").state
    assert st.slots.weather is None  # 자료 주제가 바뀌면 비운다


class _Wx:
    """기상청 단기예보 대신 — 오늘부터 사흘, 동마다 같은 값(tmin만 정해 줌)."""

    def __init__(self, today, tmin):
        self.today, self.tmin = today, tmin

    def forecast(self, grids):
        days = {
            (self.today + timedelta(days=i)).isoformat(): {
                "tmin": self.tmin,
                "tmax": 3.0,
                "rain": 0.0,
                "snow": 0.0,
                "pop": 10,
            }
            for i in range(3)
        }
        return {d: days for d in grids}, f"{self.today.isoformat()} 05:00"


def test_today_and_date_records_with_thresholds(monkeypatch):
    # 【정함 10-19 팀장】 "오늘도 진짜 오늘로" — 오늘 · 내일 · 모레는 기상청 단기예보,
    #        지난 날은 관측
    day = date(2026, 1, 20)
    monkeypatch.setattr(fc, "today_kst", lambda: day)
    monkeypatch.setattr(librarian, "WX", _Wx(day, -9.5))
    f = gather("dong_overview", Slots(region="강남구", weather="날씨"), DATA)
    assert "2026-01-20(오늘) 기상청 단기예보" in f.text and "최저 -9.5℃" in f.text
    assert "한파 기준(최저기온 -8℃ 이하) 넘음, 22곳 중 22곳" in f.text
    f = gather("dong_overview", Slots(region="춘천시", weather="날씨", period="내일"), DATA)
    assert "2026-01-21(내일) 기상청 단기예보" in f.text
    later = Slots(region="춘천시", weather="날씨", period="다음 주 월요일")
    f = gather("dong_overview", later, DATA)
    # 10-26: 요일 말도 날짜로 읽는다(전에는 못 읽어 오늘로 봤다). 단기예보는 모레까지라 없다고 밝힘
    assert "2026-01-26(다음 주 월요일)은 아직 예보가 없음" in f.text
    f = gather("dong_overview", Slots(region="춘천시", weather="날씨", period="연말쯤"), DATA)
    assert "2026-01-20(오늘)" in f.text  # 날짜로 못 읽는 때는 오늘
    # 지난 날은 관측(weather.json)
    monkeypatch.setattr(fc, "today_kst", lambda: date(2025, 12, 31))
    f = gather("dong_overview", Slots(region="강남구", weather="비", period="7월 16일"), DATA)
    assert "비 73.1mm" in f.text and "폭우 기준(하루 비 30mm 이상) 넘음" in f.text
    assert "춘천" not in " ".join(f.notes)  # 물은 지역의 관측소 안내만
    # 기상청을 못 받으면 그렇다고 말한다(다른 답은 그대로)
    monkeypatch.setattr(fc, "today_kst", lambda: day)
    monkeypatch.setattr(librarian, "WX", type("Down", (), {"forecast": _down})())
    f = gather("dong_overview", Slots(region="강남구", weather="날씨"), DATA)
    assert "기상청 예보를 받지 못함" in f.text


def _down(self, grids):
    raise fc.ForecastError("기상청 단기예보를 받지 못함: URLError")


def test_condition_rows_pick_data_for_that_weather():
    f = gather("dong_overview", Slots(dongs=("역삼1동",), weather="비"), DATA)
    assert "[강남구 역삼1동] 비일 때 함께 볼 이 동 자료" in f.text
    assert "지하층이 있는 30년 넘은 저층 주거 건물 410채" in f.text  # 10-19 건축물대장 2026-10
    f = gather("dong_overview", Slots(dongs=("북산면",), weather="추위"), DATA)
    assert (
        "80세 이상 1인세대(주민등록 2026-09): 63명" in f.text and "경로당 · 마을회관 11곳" in f.text
    )
    # 넘은 날 수는 관측 기록(자동 받기가 날마다 늘림)에서 센다
    days = DATA.weather()["regions"]["춘천시"]["days"].values()
    n = sum(1 for v in days if v.get("tmin") is not None and v["tmin"] <= -8)
    assert f"한파 기준(최저기온 -8℃ 이하)을 넘은 날 {n}일" in f.text


def test_region_level_weather_answers_without_asking_dong():
    st = new_state(Profile(member_region="강남구"))  # 대화를 시작하면 담당 지역이 지역 칸에
    card = DeskCard(act="ask", topics=("dong_overview",), weather_op="set", weather="날씨")
    applied = apply_card(st, card, "오늘 날씨 어때요?")
    assert preflight(applied, card, DATA).kind == "answer"
    # 날씨 칸이 있으면 때(7월 16일)를 '나눠 볼 수 없다'고 밝히지 않는다
    assert disclose(DeskCard(), Slots(weather="비", period="7월 16일")) == ""


def test_desk_sanity_fills_weather_and_date_from_words():
    # 【기능】 10-13 날씨 r8: 데스크가 날짜 칸을 비우거나(T5 '7월 16일에 비 얼마나', T8 '내일 비')
    #        앞 날씨 칸을 그대로 둠(T13 '폭설 온 날', 칸은 추위). 날짜 · 날씨 낱말은 코드가 확정한다
    from src.assistant.policy import desk_sanity

    base = DeskCard(act="ask", topics=("dong_overview",))
    c, _ = desk_sanity(base, "7월 16일에 비 얼마나 왔어요?")
    assert (c.weather_op, c.weather, c.period_op, c.period) == ("set", "비", "set", "7월 16일")
    c, _ = desk_sanity(base, "내일 비 온대요?")
    assert c.weather == "비" and c.period == "내일"
    c, _ = desk_sanity(
        base.model_copy(update={"weather_op": "set", "weather": "추위"}),
        "춘천은 하반기에 폭설 온 날 있었어요?",
    )
    assert c.weather == "눈"
    c, _ = desk_sanity(DeskCard(act="ask", topics=("youth",)), "비서님 수서동 청년 비율은?")
    assert c.weather_op == "keep" and c.period_op == "keep"  # '비서 · 비율'은 날씨가 아니다


def test_temperature_and_rain_units_count_as_given_numbers():
    from src.assistant import checks

    src = "강남구 2025-12-31 관측: 최저 -8.9℃ · 최고 -1.2℃ · 비 0.0mm"
    ans = "내일 예보는 알 수 없어요. 오늘(12월 31일)은 최저 -8.9℃였어요."
    assert checks.none_only(ans, src) == []


def test_as_of_rewinds_chat_weather_to_observations(monkeypatch):
    # 10-19: .env AS_OF(카드의 되감기)가 챗봇 날씨에도 — 그날을 오늘로 보고 관측으로 답한다
    monkeypatch.setattr(fc, "today_kst", lambda: date(2026, 10, 19))
    monkeypatch.setattr(librarian, "AS_OF", "2025-12-31")
    f = gather("dong_overview", Slots(region="강남구", weather="날씨"), DATA)
    assert "2025-12-31(오늘)" in f.text and "최저 -8.9℃" in f.text
    f = gather("dong_overview", Slots(region="강남구", weather="비", period="7월 16일"), DATA)
    assert "비 73.1mm" in f.text  # 그 해(2025)의 7월 16일
    f = gather("dong_overview", Slots(region="강남구", weather="날씨", period="내일"), DATA)
    assert "되감기" in f.text
