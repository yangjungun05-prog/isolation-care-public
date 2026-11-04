"""10-19 팀장 결정 — 기한 문구 빼기 · 담당 동 여러 곳 · 청년 카드(19 ~ 34세) · 공공기관 1km."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.assistant import today, today_api
from src.assistant.data_source import JsonDongData

DATA = JsonDongData()
MONTH_START = "2025-12-02"  # 월초 점검이 서는 날(첫 근무일 ~ 10일)
BEFORE_CHUSEOK = "2025-09-29"  # 2025-10-03 ~ 09 연휴 1주 전


def test_several_dongs_are_one_card_with_totals():
    some = ["수서동", "세곡동", "일원1동"]
    r = today.cards(today.Who(member_region="강남구", member_dongs=some), DATA, MONTH_START)
    assert r["where"] == "강남구 수서동 · 세곡동 · 일원1동"
    c = next(c for c in r["cards"] if c["kind"] == "월초 점검")
    assert c["where"] == "강남구 수서동 · 세곡동 · 일원1동"
    assert [t["dong"] for t in c["targets"]] == some and all(t["dong_cd"] for t in c["targets"])
    assert c["asks"]["어느 동부터 볼지 묻기"].startswith("수서동 · 세곡동 · 일원1동 중")
    p = DATA.people()["dongs"]
    total = sum(p[n]["solo80"] for n in some)
    assert c["focus"][-1].startswith(f"80세 이상 혼자 사시는 분 합계 {total:,}명(3곳")


def test_unknown_dong_is_dropped():
    r = today.cards(today.Who("강남구", member_dongs=["수서동", "북산면"]), DATA, MONTH_START)
    assert r["where"] == "강남구 수서동"


def test_one_dong_in_list_is_same_as_member_dong():
    a = today.cards(today.Who("강남구", member_dongs=["수서동"]), DATA, MONTH_START)
    b = today.cards(today.Who("강남구", "수서동"), DATA, MONTH_START)
    assert a["cards"] == b["cards"] and a["youth_cards"] == b["youth_cards"]


def test_youth_card_is_19_to_34_and_status_only():
    r = today.cards(today.Who("춘천시", "효자2동"), DATA, MONTH_START)
    (c,) = r["youth_cards"]
    p = DATA.people()["dongs"]["효자2동"]
    assert c["label"] == "청년 · 월초 점검" and c["group"] == "청년"
    assert c["focus"][0] == (
        f"혼자 사는 청년(19 ~ 34세 1인 세대) {p['solo_youth_prev']:,}명 → {p['solo_youth']:,}명"
        f"(2025-09 → 2026-09, {today._more(p['solo_youth'] - p['solo_youth_prev'])})"
    )
    assert f"청년(19 ~ 34세) 주민 {p['pop_youth']:,}명" in c["focus"][1]
    assert c["buttons"] == ["자세히 묻기", "동 상황 문서"] and "청년" in c["asks"]["자세히 묻기"]
    assert "due" not in c


def test_youth_card_before_long_holiday_names_growing_dongs():
    r = today.cards(today.Who("강남구"), DATA, BEFORE_CHUSEOK)
    c = next(c for c in r["youth_cards"] if c["kind"] == "긴 연휴")
    assert c["focus"][0].startswith("혼자 사는 청년(19 ~ 34세 1인 세대) 합계")
    # 10-19 팀장이 맡김: '얼마나 늘면' 카드 대신 1년 새 많이 늘어난 동 세 곳
    p = DATA.people()["dongs"]
    ups = sorted(
        ((p[n]["solo_youth"] - p[n]["solo_youth_prev"], n) for n in DATA.region_dongs("강남구")),
        reverse=True,
    )
    if ups[0][0] >= today.MIN_UP:
        assert f"많이 늘어난 곳 {ups[0][1]} +{ups[0][0]:,}명" in c["focus"][0]
    assert c["buttons"] == ["혼자 사는 청년 많은 동 묻기", "취약 돌보미 판단 보기"]


def test_no_youth_card_on_plain_days():
    # 날씨만 있는 날에는 청년 카드를 세우지 않는다(긴 연휴 · 월초만)
    r = today.cards(today.Who("강남구", "수서동"), DATA, "2025-07-16")
    assert r["youth_cards"] == []


def test_public_far_line_is_1km_villages_only():
    fv = DATA.focus("북산면")
    far = [
        v
        for v in fv["villages"]
        if v.get("halls") and v.get("public_km") is not None and v["public_km"] > today.PUBLIC_KM
    ]
    line, keys = today._weather_facts(["북산면"], DATA, None, None)["pharm_far"]
    assert f"1km 넘게 먼 마을 {len(far)}곳" in line and keys == ("공공기관",)
    # 동 지역은 동 하나에 가운데 한 점이라 세지 않는다
    assert "pharm_far" not in today._weather_facts(["수서동"], DATA, None, None)


def test_api_takes_several_dongs():
    app = FastAPI()
    app.include_router(today_api.router())
    c = TestClient(app)
    r = c.get(
        "/assistant/today",
        params={"region": "강남구", "dong": "수서동,세곡동", "date": MONTH_START},
    )
    assert r.status_code == 200 and r.json()["where"] == "강남구 수서동 · 세곡동"
    assert "youth_cards" in r.json()
    bad = c.get("/assistant/today", params={"region": "강남구", "dong": "수서동,북산면"})
    assert bad.status_code == 400


def test_data_notes_say_what_is_missing():
    # 10-20: 관측 자료 전 날에 '궂은 날씨 없음'으로 읽히는 안내가 나갔다
    r = today.cards(today.Who("강남구"), DATA, "2025-03-02")
    assert r["data_notes"] and r["data_notes"][0].startswith("그날은 날씨 관측 자료가 없어요")
    assert r["notice"] == r["data_notes"][0]
    far = today.cards(today.Who("강남구"), DATA, "2028-01-05")
    assert any("예보가 없어요" in n for n in far["data_notes"])
    assert any("2028년 공휴일 자료가 아직 없어" in n for n in far["data_notes"])
    ok = today.cards(today.Who("강남구", "수서동"), DATA, "2025-12-31")
    assert ok["data_notes"] == []


def test_card_judge_matches_chatbot_conditions():
    from datetime import date

    from src.assistant import conditions as C

    r = today.cards(today.Who("강남구", "수서동"), DATA, "2025-12-31")
    c = next(c for c in r["cards"] if c["kind"] == "한파")
    s = C.sheet("수서동", "어르신", DATA, as_of=date(2025, 12, 31))
    cold = next(p for p in s.patterns if p.key == "cold")
    assert (
        c["judge"]
        == f"취약 돌보미 판단: {cold.title}({cold.kind}, 겹 {len(cold.layers())}가지에 걸침)"
    )
    g = today.cards(today.Who("춘천시"), DATA, "2025-12-31")
    gc = next(c for c in g["cards"] if c["kind"] == "한파")
    assert gc["judge"].startswith(
        "취약 돌보미 판단: '추위 · 눈에 집 밖으로 나오기 어려움' 겹침이 선 곳 25곳 중"
    )
