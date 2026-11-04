"""오늘 챙길 일 카드 10-15 고침 · [했어요] 기록."""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.assistant import done, today, today_api
from src.assistant.data_source import JsonDongData

DATA = JsonDongData()


def _cards(region=None, dong=None, on=None):
    return today.cards(today.Who(member_region=region, member_dong=dong), DATA, on)


def _one(region, dong, on, kind):
    return next(c for c in _cards(region, dong, on)["cards"] if c["kind"] == kind)


def test_card_id_follows_team_erd_and_is_shared_by_dong_and_region():
    # 팀 ERD todo_card.card_id '지역-종류-계기 첫날' — [했어요]는 회원마다 따로 남기므로 카드는 하나
    a = _one("강남구", "수서동", "2025-07-15", "폭우")
    b = _one("강남구", None, "2025-07-15", "폭우")
    assert a["id"] == b["id"] == "11230-폭우-2025-07-16" and a["sgg_cd"] == "11230"
    assert a["targets"] == [{"dong_cd": "11230750", "dong": "수서동"}] and b["targets"] == []
    assert done.CARD_ID.match(a["id"])


def test_monthly_card_id_is_first_workday():
    c = _one("강남구", None, "2025-11-05", "월초 점검")
    assert c["id"] == "11230-월초 점검-2025-11-03"  # 11월 1일은 토요일


def test_sources_are_only_what_the_lines_used():
    # 10-15: 긴 연휴 카드에 집 · 시설 줄이 없는데 건축물대장 · 시설 자료가 출처에 붙었다
    c = _one("강남구", "개포1동", "2025-08-08", "긴 연휴")
    assert not any("건축물대장" in s for s in c["sources"])
    assert any("특일" in s for s in c["sources"]) and any("주민등록" in s for s in c["sources"])
    # 10-16 팀장: 카드에서 서울시 독거노인 줄을 뺐다 — 출처에도 없어야
    assert not any("서울시 독거노인" in s for s in c["sources"])
    hall = _one("춘천시", "강남동", "2025-12-01", "한파")
    assert any("마을회관" in s for s in hall["sources"])
    assert not any("서울시 경로당" in s for s in hall["sources"])  # 춘천에 서울 자료 이름 없음


def test_chuncheon_snow_is_said_to_be_estimated():
    # 춘천 관측소에는 쌓인 눈 기록이 없어 어림한 날 — '관측 1cm'처럼 말하지 않는다
    c = _one("춘천시", "남면", "2025-12-21", "폭설")
    assert "어림" in c["title"] and "어림" in c["why"] and "1.0cm" not in c["why"]


def test_card_has_no_todo_only_status():
    # 10-19 팀장: "카드 할 일은 적어두지마. 그냥 전체적인 status(상태)만 보여줘"
    for region, dong, day, kind in [
        ("춘천시", "강남동", "2025-07-01", "폭염"),
        ("강남구", "수서동", "2025-07-05", "폭염"),
        ("춘천시", "사북면", "2025-12-31", "한파"),
    ]:
        c = _one(region, dong, day, kind)
        assert "todo" not in c and c["focus"]
        assert not any("확인)" in s for s in c["focus"])


def test_region_card_sums_and_names_big_dongs():
    # 10-19 팀장이 맡김: 합계와 함께 줄마다 값이 큰 동 세 곳까지
    c = _one("춘천시", None, "2025-12-21", "한파")
    text = " ".join(c["focus"])
    assert "합계" in text and "25곳" in text and "많은 곳" in text
    names = DATA.region_dongs("춘천시")
    for line in c["focus"]:
        assert sum(n in line for n in names) <= 3, line


def test_headline_and_empty_day_follow_storyboard():
    r = _cards("강남구", "수서동", "2025-07-15")
    assert r["headline"] == "7월 15일(화), 오늘 챙길 일이 1건 있습니다."
    e = _cards("강남구", "개포1동", "2025-11-20")
    assert e["headline"].endswith("오늘은 먼저 챙길 일이 없습니다.")
    assert e["notice"].startswith("오늘부터 사흘 안에") and len(e["suggest"]) == 3


def test_buttons_carry_a_question_for_the_chat():
    c = _one("강남구", "수서동", "2025-07-15", "폭우")
    # 10-20 팀장이 맡김: '자세히 묻기'는 챗봇의 취약 돌보미 판단(outlook)으로, 그날을 담아
    assert c["asks"]["자세히 묻기"] == "7월 16일 비 오는데 수서동 어르신들 괜찮으실까요?"
    assert set(c["asks"]) == set(c["buttons"]) - {"했어요"}
    g = _one("강남구", None, "2025-07-15", "폭우")
    assert g["asks"] == {
        "어느 동부터 볼지 묻기": "7월 16일 폭우 때 강남구 어느 동부터 봐야 해요?",
        "취약 돌보미 판단 보기": "7월 16일 비 오는데 강남구 어르신들 괜찮으실까요?",
    }


def test_erd_rows_match_team_tables():
    c = _one("강남구", "수서동", "2025-07-15", "폭우")
    rows = today.erd_rows(c, "2025-07-15T06:00:00+09:00")
    assert set(rows["todo_card"]) == {
        "card_id",
        "kind",
        "sgg_cd",
        "title",
        "why",
        "due",
        "created_at",
        "evidence",
        "todo",
    }
    assert rows["todo_card"]["todo"] == []  # 10-19 할 일 없음(팀 ERD 칸은 빈 목록)
    assert rows["todo_target"][0]["dong_cd"] == "11230750"


# ── [했어요] ──


def test_done_record_checks_and_masks():
    cid = "11230-폭우-2025-07-16"
    r = done.make(cid, 1, "해당 없음", "김철수 할머니 010-1234-5678 은 이미 이사 감")
    assert "김철수" not in (r.reason or "") and "010-1234-5678" not in (r.reason or "")
    assert r.masked
    assert done.make(cid, 1, "했어요", "남길 말").reason is None  # 이유는 '해당 없음'일 때만
    for bad in [
        ("11230-폭우", "했어요", None),
        (cid, "몰라요", None),
        (cid, "해당 없음", "가" * 201),
    ]:
        try:
            done.make(bad[0], 1, bad[1], bad[2])
        except ValueError:
            continue
        raise AssertionError(bad)


def test_done_store_keeps_history_and_shows_latest(tmp_path):
    for store in (done.MemoryDoneStore(), done.JsonlDoneStore(tmp_path / "d.jsonl")):
        cid = "32010-한파-2025-12-22"
        store.add(done.make(cid, 1, "해당 없음", "담당 동에 해당 없음"))
        store.add(done.make(cid, 1, "했어요"))
        store.add(done.make(cid, 2, "해당 없음", "다른 회원"))
        last = store.latest(1, [cid, "32010-폭설-2025-12-23"])
        assert list(last) == [cid] and last[cid].status == "했어요"
        assert store.latest(2, [cid])[cid].reason == "다른 회원"


def _client(tmp_path, weather=None) -> TestClient:
    # 10-16: 카드 API는 챗봇과 떼어 둔 라우터(today_api) — 팀 저장소에도 그대로 옮긴다
    app = FastAPI()
    app.include_router(
        today_api.router(done_store=done.JsonlDoneStore(tmp_path / "done.jsonl"), weather=weather)
    )
    return TestClient(app)


def test_api_saves_done_and_card_shows_it(tmp_path):
    c = _client(tmp_path)
    q = {"region": "강남구", "dong": "수서동", "date": "2025-07-15"}
    card = c.get("/assistant/today", params=q).json()["cards"][0]
    assert card["done"] is None
    r = c.post(f"/assistant/today/{card['id']}/done", json={"status": "했어요"})
    assert r.status_code == 200 and r.json()["status"] == "했어요"
    again = c.get("/assistant/today", params=q).json()["cards"][0]
    assert again["done"]["status"] == "했어요" and re.match(
        r"\d{4}-\d{2}-\d{2}T", again["done"]["at"]
    )
    # 다른 회원에게는 보이지 않는다
    assert c.get("/assistant/today", params={**q, "member": 2}).json()["cards"][0]["done"] is None


def test_api_rejects_bad_done(tmp_path):
    c = _client(tmp_path)
    assert (
        c.post("/assistant/today/11230-폭우-2025-07-16/done", json={"status": "몰라요"}).status_code
        == 400
    )
    assert c.post("/assistant/today/아무거나/done", json={"status": "했어요"}).status_code == 400


def test_cards_are_ordered_by_first_day():
    # 10-15: 기한 글자로 줄 세워 '내일 12월 22일' 폭설이 '오늘 오후 6시' 한파보다 앞에 왔다.
    # 10-19 팀장이 기한을 뺀 뒤에는 계기 첫날로 줄 세운다
    r = _cards("춘천시", "남면", "2025-12-21")
    assert [c["kind"] for c in r["cards"]] == ["한파", "폭설"]
    assert r["cards"][0]["start"] <= r["cards"][1]["start"]
