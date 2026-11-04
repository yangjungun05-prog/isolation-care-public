"""10-16 카드 전수 시험 — 담당 49가지(동 47 + 구 · 시 2) × 날짜를 모두 돌려 카드 모양 규칙을 본다.

【정함 10-16 팀장】 "우선 카드를 빠르게 만들고. 제대로 튼튼하게 만든 뒤. 바로 공용 깃허브에
       올려버리자"
기상청에는 묻지 않는다(지난 날은 관측 되짚기, 진짜 오늘은 가짜 기상청).
"""

from datetime import date, timedelta

import pytest

from src.assistant import done, today
from src.assistant import forecast as fc
from src.assistant.data_source import JsonDongData
from src.assistant.dongname import DONGS

DATA = JsonDongData()
D = fc.today_kst()
MEMBERS = [(r, None) for r in DONGS] + [(r, n) for r in DONGS for n in DONGS[r]]
PAST = [date(2025, 7, 1) + timedelta(days=i) for i in range(0, 184, 3)]
BANNED = ("서울시 독거노인", "None", "nan", "{", "}")
# 먼저 볼 곳에는 '침수 우려'(우리 판단)를 쓰지 않고 '반지하가 있을 수 있는 옛 집'(자료 그대로)으로
FIELDS = ("id", "kind", "label", "sgg_cd", "where", "title", "note", "why", "start")


def _check(r: dict, region: str, dong: str | None, d: date) -> None:
    assert len(r["cards"]) <= today.MAX_CARDS
    for c in r["cards"]:
        for f in FIELDS:
            assert c[f], (f, c["id"])
        assert done.CARD_ID.match(c["id"]) and c["sgg_cd"] == DATA.region_code(region)
        # 10-19 팀장: 카드 기한 문구는 뺀다("카드 기한 문구 <- 빼줘")
        assert "due" not in c and "오후 6시" not in " ".join(map(str, c.values()))
        assert 1 <= len(c["focus"]) <= today.FOCUS_MAX + 1, c["focus"]
        assert c["focus"][-1].startswith("80세 이상 혼자 사시는 분"), c["focus"]
        # 10-19 팀장: [했어요] 단추는 주석 처리(기록 API는 그대로)
        assert "todo" not in c and c["sources"] and "했어요" not in c["buttons"]
        text = " ".join([c["title"], c["sub"], c["note"], c["why"], *c["focus"]])
        assert not any(b in text for b in BANNED), (c["id"], text)
        assert not any("침수 우려" in s for s in c["focus"])
        if region == "강남구":
            assert "마을회관" not in " ".join(c["focus"])  # 강남은 경로당만
        if any("버스" in s for s in c["focus"]):
            assert any("어림" in s for s in c["focus"] if "버스" in s)
        if dong is None:
            # 10-12 팀장: 순위는 챗봇에서(단추). 10-19 팀장이 맡김: 줄마다 값이 큰 동 이름은 적는다
            #        — 다른 지역 동 이름은 나오면 안 된다
            body = " ".join([c["title"], c["sub"], c["why"], *c["focus"]])
            other = [n for r2 in DONGS if r2 != region for n in DONGS[r2] if len(n) > 2]
            assert not any(n in body for n in other), (c["id"], body)
            # 10-20 팀장이 맡김: 순위 단추에 취약 돌보미 판단 단추를 더함
            assert c["buttons"] == ["어느 동부터 볼지 묻기", "취약 돌보미 판단 보기"]
            assert c["targets"] == []
        else:
            assert c["targets"][0]["dong"] == dong and c["targets"][0]["dong_cd"]
        # 10-20 팀장이 맡김: 카드마다 취약 돌보미 판단 한 줄(챗봇과 같은 조건 창고)
        assert c["judge"].startswith("취약 돌보미 판단: ") and "먼저 볼 동" not in c["judge"]
    # 10-19 팀장: 청년 카드(19 ~ 34세)는 노인 카드와 따로 — 긴 연휴 · 월초에만, 상태만
    for c in r["youth_cards"]:
        assert c["group"] == "청년" and c["label"].startswith("청년 · ")
        assert c["judge"].startswith("취약 돌보미 판단: ")
        assert c["kind"] in ("긴 연휴", "월초 점검")
        assert c["focus"][0].startswith("혼자 사는 청년(19 ~ 34세 1인 세대)")
        assert "했어요" not in c["buttons"]
        if dong:
            assert c["buttons"] == ["자세히 묻기", "동 상황 문서"]
        assert "due" not in c and c["sources"]
    assert all(c["kind"] in ("긴 연휴", "월초 점검") for c in r["youth_cards"])
    assert len(r["youth_cards"]) <= 2


@pytest.mark.parametrize("region,dong", MEMBERS)
def test_every_member_every_past_day(region, dong):
    for d in PAST:
        r = today.cards(today.Who(member_region=region, member_dong=dong), DATA, d.isoformat())
        assert r["weather"]["mode"] == "관측 되짚기"
        _check(r, region, dong, d)


class AllWx:
    """동마다 날씨가 다른 가짜 기상청 — 넷 다 기준을 넘는 날을 섞고, 특보 · 예비특보도 건다."""

    def __init__(self, warn=False):
        self.warn = warn

    def forecast(self, grids):
        out = {}
        for i, n in enumerate(sorted(grids)):
            days = {}
            for k in range(4):
                day = (D + timedelta(days=k)).isoformat()
                hot = (i + k) % 4 == 0
                days[day] = {
                    "tmin": -12.0 if (i + k) % 4 == 1 else 5.0,
                    "tmax": 35.0 if hot else 20.0,
                    "rain": 45.0 if (i + k) % 4 == 2 else 0.0,
                    "snow": 3.0 if (i + k) % 4 == 3 else 0.0,
                    "pop": 80,
                    "rain_peak": [14, 16],
                    "snow_peak": [6, 6],
                }
            out[n] = days
        return out, f"{D.isoformat()} 05:00"

    def warnings(self, region):
        now = [("호우경보", "폭우"), ("강풍주의보", None)] if self.warn else []
        soon = [("(1) 한파 예비특보 : 내일 아침", "한파")] if self.warn else []
        return {
            "issued": f"{D.isoformat()} 10:00",
            "area": fc.AREA[region],
            "now": now,
            "soon": soon,
        }


@pytest.mark.parametrize("warn", [False, True])
@pytest.mark.parametrize("region,dong", MEMBERS)
def test_every_member_live(region, dong, warn):
    r = today.cards(today.Who(member_region=region, member_dong=dong), DATA, None, AllWx(warn))
    assert r["weather"]["mode"] == "예보" and not r["weather"]["error"]
    _check(r, region, dong, D)
    for c in r["cards"]:
        if c["kind"] == "폭우" and "예보" in c["note"]:
            assert "가장 셈" in c["sub"] and "확률" in c["sub"]
        if warn and c["kind"] == "폭우":
            assert "호우경보" in c["title"] and "특보" in c["note"]
    if warn:
        assert r["weather"]["other_warnings"] == ["강풍주의보"]
        assert "호우경보" in r["weather"]["warnings_here"]
    else:
        assert r["weather"]["warnings_here"] == []


def test_warning_text_real_shapes():
    # 10-16 원문: 특보가 없으면 'o 없 음'(빈칸) — 특보로 읽으면 안 된다
    assert fc.lines("o 없 음") == [] and fc.lines("o 없음") == [] and fc.lines("") == []
    # 구역이 길어 다음 줄로 이어지면 앞 특보에 붙인다
    t = "o 호우경보 : 경기도(가평), 강원도(홍천평지,\n 춘천, 화천)\no 강풍주의보 : 제주도"
    got = fc.lines(t)
    assert len(got) == 2 and "춘천" in got[0][1] and fc.covers("춘천시", got[0][1])
    t7 = "(1) 호우 예비특보 : 10월 18일 오후 : 서울(동남권)\n(2) 강풍 예비특보 : 강원도"
    soon = fc.lines(t7)
    assert [fc.kind_of(h) for h, _ in soon] == ["폭우", None]
    assert fc.covers("강남구", soon[0][1]) and not fc.covers("강남구", "서울(동북권)")


class FlakyLive(fc.Live):
    """격자 하나는 늘 실패하는 기상청."""

    def __init__(self, bad):
        super().__init__(key="x")
        self.bad = bad

    def grid_days(self, nx, ny):
        if (nx, ny) == self.bad:
            raise fc.ForecastError("기상청 단기예보를 받지 못함: URLError")
        day = D.isoformat()
        return {
            day: {
                "tmin": 5.0,
                "tmax": 20.0,
                "rain": 40.0,
                "snow": 0.0,
                "pop": 90,
                "rain_peak": [9, 11],
                "snow_peak": None,
            }
        }, f"{day} 05:00"


def test_one_grid_failing_still_makes_region_card():
    grids = DATA.grids("춘천시")
    bad = grids["북산면"]
    lost = sorted(n for n, g in grids.items() if g == bad)
    lv = FlakyLive(bad)
    by_dong, issued = lv.forecast(grids)
    assert set(by_dong) == set(grids) - set(lost) and issued
    r = today.cards(today.Who(member_region="춘천시"), DATA, None, _NoWarn(lv))
    assert r["weather"]["missing"] == lost and "못 받은 곳" in r["weather"]["error"]
    assert any(c["kind"] == "폭우" for c in r["cards"])
    with pytest.raises(fc.ForecastError):
        FlakyLive(bad).forecast({"북산면": bad})  # 모두 실패하면 오류


class _NoWarn:
    def __init__(self, lv):
        self.lv = lv

    def forecast(self, grids):
        return self.lv.forecast(grids)

    def warnings(self, region):
        return {"issued": f"{D.isoformat()} 10:00", "area": fc.AREA[region], "now": [], "soon": []}


def test_people_are_2026_and_card_says_so():
    # 10-16 팀장: 2026 최신 판 — 카드의 사람 수는 주민등록 2026-09(scripts/update_people.py)
    p = DATA.people()
    assert p["basis"] == "2026-09-30" and set(p["dongs"]) == {n for r in DONGS for n in DONGS[r]}
    r = today.cards(today.Who(member_region="강남구", member_dong="수서동"), DATA, "2025-07-15")
    c = r["cards"][0]
    assert (
        c["focus"][-1]
        == f"80세 이상 혼자 사시는 분 {p['dongs']['수서동']['solo80']:,}명(주민등록 2026-09)"
    )
