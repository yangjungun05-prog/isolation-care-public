"""10-20 큰비 · 눈이 그친 뒤 카드(today.AFTER) — 관측 되짚기 날짜로."""

from src.assistant import conditions as C
from src.assistant import done, today
from src.assistant.data_source import JsonDongData

DATA = JsonDongData()


def _cards(region, dong, on):
    return today.cards(today.Who(member_region=region, member_dong=dong), DATA, on)


def _after(r):
    return [c for c in r["cards"] if c["kind"] in today.BASE]


def test_after_card_for_three_days_then_gone():
    # 강남(서울 관측소) 2025-09-04 ~ 09-06 큰비 → 09-07 ~ 09-09 '폭우 뒤', 09-10 없음
    for on, gap in (("2025-09-07", 1), ("2025-09-09", 3)):
        got = _after(_cards("강남구", "수서동", on))
        assert [c["kind"] for c in got] == ["폭우 뒤"], on
        c = got[0]
        assert f"그친 지 {gap}일" in c["title"] and c["label"] == "폭우 뒤 알림"
        assert c["group"] == "궂은 날씨" and done.CARD_ID.match(c["id"])
        assert c["id"].endswith("-폭우 뒤-2025-09-04") and c["focus"] and c["judge"]
        assert "3일" in c["rule"] and "관측" in c["why"]
        # 단추 질문에 날짜를 넣지 않는다(데스크가 그날을 '오늘'로 잡으면 그날 앞 사흘을 봄)
        assert c["asks"]["자세히 묻기"] == "비 온 뒤 수서동 어르신들 괜찮으실까요?"
    assert _after(_cards("강남구", "수서동", "2025-09-10")) == []


def test_no_after_card_when_same_weather_is_coming():
    # 09-24 큰비 뒤 이틀째(09-26)에 09-28 큰비가 사흘 안 → 앞 카드만
    r = _cards("강남구", "수서동", "2025-09-26")
    kinds = [c["kind"] for c in r["cards"]]
    assert "폭우" in kinds and "폭우 뒤" not in kinds


def test_snow_after_card_in_chuncheon_says_estimate():
    got = _after(_cards("춘천시", "북산면", "2025-12-24"))
    assert [c["kind"] for c in got] == ["폭설 뒤"]
    assert "어림" in got[0]["why"] and "눈 온 뒤" in got[0]["asks"]["자세히 묻기"]


def test_region_after_card_counts_dongs_and_asks_without_date():
    c = _after(_cards("강남구", None, "2025-09-07"))[0]
    assert "22곳 중" in c["judge"]
    assert c["asks"]["어느 동부터 볼지 묻기"] == "비 온 뒤 강남구 어느 동부터 봐야 해요?"


def test_after_window_is_the_chatbot_past_window():
    # 카드와 챗봇이 같은 날들을 '지난 궂은 날씨'로 본다
    assert today.AFTER_DAYS == C.PAST_DAYS
    assert "지난 사흘" in today.EMPTY_HEAD


def test_slope_wording_drops_the_missing_kind():
    # 수서동: 산사태취약지역 0곳 · 급경사지 여러 곳 → 뜻에 '산사태취약지역'을 쓰지 않는다
    from datetime import date

    s = C.sheet("수서동", "어르신", DATA, {}, date(2025, 9, 7))
    slope = s.get("slope")
    assert slope.value.startswith("산사태취약지역 0곳")
    assert "산사태" not in slope.label and slope.piece == "급경사지(비탈)"
    for p in s.patterns:
        if any(c.key == "slope" for c in p.conds):
            assert "산사태" not in p.meaning


class _NoDay:
    """관측 하루가 아직 들어오지 않은 자료(관측 일자료는 하루 늦게 들어온다)."""

    def __init__(self, data, drop: str):
        self._data, self._drop = data, drop

    def weather(self):
        import copy

        w = copy.deepcopy(self._data.weather())
        for reg in w["regions"].values():
            reg["days"].pop(self._drop, None)
        return w

    def __getattr__(self, name):
        return getattr(self._data, name)


def test_chatbot_past_weather_says_which_day_is_not_in_yet():
    from datetime import date

    s = C.sheet("수서동", "어르신", _NoDay(DATA, "2025-09-06"), {}, date(2025, 9, 7))
    assert "9월 6일 관측은 아직 없음" in s.get("past").value
    s = C.sheet("수서동", "어르신", DATA, {}, date(2025, 9, 7))
    assert "아직 없음" not in s.get("past").value
