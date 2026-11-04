"""취약 돌보미 대시보드 API — 공개 자료만 있을 때(CI 와 같은 상태)도 화면이 돈다.

카드 결제 표가 있을 때는 대회 자료 대신 만든 가짜 표로 등급 규칙을 시험한다.
"""

from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.dashboard import cards, grades


def _clear():
    cards.dong_cards.cache_clear()
    cards.alert_month.cache_clear()
    grades.card.cache_clear()
    grades.daily.cache_clear()
    grades.series.cache_clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 【판단】 대회 자료 폴더를 빈 폴더로 바꿔 끼운다 → git 에 올라간 dong_base_2025.csv 만 읽는다
    monkeypatch.setattr(cards, "DERIVED", tmp_path)
    _clear()
    yield TestClient(app)
    _clear()


def _fake_card(path, drop_days: int = 0, drop: tuple[str, str] | None = None, soft_days: int = 0):
    # 【기능】 가짜 카드 표 — 강남구 · 나이 둘. 요일마다 값이 일정하다(흔들림이 없어야 '많이 낮음'이
    #   우연히 생기지 않는다). 70대 이상만 마지막 drop_days 일(또는 drop 기간)을 10 으로 떨어뜨리고,
    #   soft_days 일은 평소의 70% 로 낮춘다(절반 밑이 아니라 관심 · 주의를 시험할 때)
    days = pd.date_range("2025-07-01", "2025-12-31")
    rows = []
    for age in ["60대", "70대 이상"]:
        for group in grades.LIFE:
            n = (100 + 10 * days.dayofweek).to_numpy().copy()
            if age == "70대 이상":
                if drop_days:
                    n[-drop_days:] = 10
                if drop:
                    n[(days >= drop[0]) & (days <= drop[1])] = 10
                if soft_days:
                    n[-soft_days:] = (n[-soft_days:] * 0.7).astype(int)
            rows.append(
                pd.DataFrame({"day": days, "sgg_cd": "11230", "age_group": age, "n": n}).assign(
                    industry_group=group
                )
            )
    pd.concat(rows).to_csv(path / "card_pay_day.csv", index=False)


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["regions"] == ["강남구", "춘천시"]
    assert m["has_contest_data"] is False
    assert m["ref_date"] is None


def test_board_without_card(client):
    b = client.get("/api/board", params={"region": "강남구"}).json()
    assert len(b["dongs"]) == 22
    est = [x["est_n"] for x in b["dongs"]]
    assert est == sorted(est, reverse=True)
    # 카드 자료가 없으면 등급 · 줄어든 사람들 칸은 비어 있다
    assert b["counts"] is None and b["groups"] == []
    assert all(x["grade"] is None for x in b["dongs"])
    assert client.get("/api/chart").status_code == 404


# 【판단】 30일 낮아도 그사이 명절 · 긴 연휴가 없으면 경고까지 — 위험은 아래 연휴 시험에서
CASES = [
    (0, 0, "평상"),
    (7, 0, "평상"),
    (14, 0, "관심"),
    (21, 0, "주의"),
    (0, 15, "경고"),
    (0, 30, "경고"),
    (0, 45, "경고"),
]


@pytest.mark.parametrize(("soft_days", "drop_days", "grade"), CASES)
def test_grade_rules(client, tmp_path, soft_days, drop_days, grade):
    # 【판단】 대조군(0 → 평상)이 함께 있어야 "늘 관심이 나오는" 고장을 잡는다
    _fake_card(tmp_path, drop_days, soft_days=soft_days)
    b = client.get("/api/board", params={"region": "강남구"}).json()
    row = next(g for g in b["groups"] if g["age"] == "70대 이상" and g["group"] == "전체")
    assert row["grade"] == grade
    others = [g["grade"] for g in b["groups"] if g is not row]
    assert set(others) == {"평상"}
    # 그 나이 비율이 높은 절반의 동만 그 등급을 받는다
    assert b["counts"][grade] == (22 if grade == "평상" else 11)


def test_holiday_risk(client, tmp_path):
    # 【기능】 위험 = 경고가 명절 · 긴 연휴 뒤 1주가 지나도 안 풀림. 2025 추석 연휴는 10/3~10/9
    _fake_card(tmp_path, drop=("2025-09-25", "2025-10-31"))
    t = grades.series("강남구", "70대 이상", "전체")
    assert grades.long_breaks(t["holiday"])[-2:] == [
        pd.Timestamp("2025-10-09"),
        pd.Timestamp("2025-12-28"),
    ] or (pd.Timestamp("2025-10-09") in grades.long_breaks(t["holiday"]))
    assert grades.grade_at(t, date(2025, 10, 25)) == "위험"
    # 대조 — 연휴가 끝난 지 7일이 안 됐으면 아직 경고
    assert grades.grade_at(t, date(2025, 10, 14)) == "경고"
    # 대조 — 다시 오른 뒤(11월 말)는 평상 쪽으로 돌아온다
    assert grades.grade_at(t, date(2025, 12, 20)) in ("평상", "관심")


def test_why_points_to_own_line(client, tmp_path):
    # 【기능】 등급이 붙은 동마다 이유는 그 동이 실제로 받은 줄(나이 × 업종)이어야 한다
    _fake_card(tmp_path, soft_days=21)
    b = client.get("/api/board", params={"region": "강남구"}).json()
    line = next(g for g in b["groups"] if g["age"] == "70대 이상" and g["group"] == "전체")
    graded = [d for d in b["dongs"] if d["grade"] == "주의"]
    assert len(graded) == 11
    for d in graded:
        assert d["why"]["age"] == "70대 이상" and d["why"]["group"] == "전체"
        assert d["dong"] in line["exposed"]
        x = client.get(f"/api/dongs/{d['dong_cd']}").json()
        assert x["why"]["group"] == "전체" and x["grade"] == "주의"
    # 대조 — 평상인 동은 이유가 없다
    assert all(d["why"] is None for d in b["dongs"] if d["grade"] == "평상")


def test_trend_and_weeks(client, tmp_path):
    # 【기능】 4주 흐름(3주 전 → 이번 주)과 몇 주째.
    #   15일 떨어짐 → 이번 주 · 지난주 경고, 2주 전 관심
    _fake_card(tmp_path, drop_days=15)
    b = client.get("/api/board", params={"region": "강남구"}).json()
    assert [w["ref"] for w in b["trend"]] == [
        "2025-12-10",
        "2025-12-17",
        "2025-12-24",
        "2025-12-31",
    ]
    assert [w["counts"]["경고"] for w in b["trend"]] == [0, 0, 11, 11]
    assert b["last_week"] == b["trend"][-2]["counts"] and b["counts"] == b["trend"][-1]["counts"]
    weeks = {d["weeks"] for d in b["dongs"] if d["grade"] == "경고"}
    assert weeks == {2}
    # 대조 — 계속 평상인 동은 8주째(센 만큼 전부)
    assert {d["weeks"] for d in b["dongs"] if d["grade"] == "평상"} == {8}


def test_evidence(client, tmp_path):
    # 【기능】 근거 세 줄 — 4일 떨어짐: 지난 7일 결제가 예상보다 크게 줄고, 많이 낮음, 4일째
    _fake_card(tmp_path, soft_days=21)
    b = client.get("/api/board", params={"region": "강남구"}).json()
    cd = next(d["dong_cd"] for d in b["dongs"] if d["grade"] == "주의")
    ev = client.get(f"/api/dongs/{cd}").json()["evidence"]
    assert ev["label"] == "평소보다 크게 적음" and ev["days"] == 20 and ev["drop_pct"] < -20
    # 대조 — 평상인 동은 근거가 없다
    cd0 = next(d["dong_cd"] for d in b["dongs"] if d["grade"] == "평상")
    assert client.get(f"/api/dongs/{cd0}").json()["evidence"] is None


def test_next_week(client, tmp_path):
    # 【기능】 다음 주 예상 — 다음 7일 예상선, 이어짐 / 반쯤 회복 두 경우의 등급별 동 수 범위
    _fake_card(tmp_path, soft_days=21)
    nw = client.get("/api/board", params={"region": "강남구"}).json()["next_week"]
    assert nw["from"] == "2026-01-01" and nw["to"] == "2026-01-07"
    assert any("신정" in h or "1월 1일" in h or h.startswith("1/1") for h in nw["holidays"])
    assert len(nw["lines"]["70대 이상|전체"]) == 7
    # 70% 로 이어지거나 반쯤 돌아와도 절반 밑은 아니라 경고는 없다. 동 11곳은 평상이 아니다
    assert nw["counts_range"]["경고"] == [0, 0] and nw["counts_range"]["평상"] == [11, 11]
    # 대조 — 아무 일 없으면 다음 주도 전부 평상
    _fake_card(tmp_path, drop_days=0)
    grades.card.cache_clear()
    grades.daily.cache_clear()
    grades.series.cache_clear()
    nw0 = client.get("/api/board", params={"region": "강남구"}).json()["next_week"]
    assert nw0["counts_range"]["평상"] == [22, 22]


def test_priority(client, tmp_path):
    # 【기능】 우선순위 — 등급이 먼저, 같은 등급 안에서는 혼자 사는 80세 이상 × (1 + 수급 몫)
    _fake_card(tmp_path, soft_days=21)
    b = client.get("/api/board", params={"region": "강남구"}).json()
    top = sorted(b["dongs"], key=lambda d: -d["priority"])
    assert all(d["grade"] == "주의" for d in top[:11]) and all(
        d["grade"] == "평상" for d in top[11:]
    )
    a, c = top[0], top[10]
    assert (a["solo80"] or 0) * (1 + (a["who_basic"] or 0) / 100) >= (c["solo80"] or 0) * (
        1 + (c["who_basic"] or 0) / 100
    )


def test_chart(client, tmp_path):
    _fake_card(tmp_path, 4)
    c = client.get("/api/chart", params={"age": "70대 이상", "group": "전체"}).json()
    assert len(c) == 56 and c[-1]["day"] == "2025-12-31"
    assert [x["low"] for x in c[-4:]] == [True] * 4
    assert client.get("/api/chart", params={"age": "10대"}).status_code == 404


def test_geo(client):
    g = client.get("/api/geo", params={"region": "강남구"}).json()
    assert len(g["features"]) == 22
    assert {f["properties"]["dong_cd"][:5] for f in g["features"]} == {"11230"}


def test_dong_detail(client):
    x = client.get("/api/dongs/11230640").json()
    assert x["dong"] == "역삼1동"
    assert len(x["standout"]) == 3 and len(x["detail"]) == 13
    assert set(x["who"]) == {"75세 이상", "혼자 삶", "기초수급"}
    assert x["helpers"] >= 0 and x["why"] is None and x["evidence"] is None


def test_not_found(client):
    assert client.get("/api/board", params={"region": "부산"}).status_code == 404
    assert client.get("/api/geo", params={"region": "부산"}).status_code == 404
    assert client.get("/api/dongs/00000000").status_code == 404
    # 공개판에는 옛 예시 파일이 없다
    assert client.get("/api/simulation/demo").status_code == 404


def test_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "취약 돌보미" in r.text


def test_youth_in_dong(client):
    # 【기능】 동별 칸의 청년 — 팀 공개 자료(주민등록 · 청년의 삶 실태조사 2024), 카드 자료 없이도
    y = client.get("/api/dongs/11230640").json()["youth"]
    assert y["total"] == 11813 and y["solo"] == 7819
    assert y["homebound"]["lo"] < y["homebound"]["hi"]
    assert any("청년ON" in t for t in y["desk"])
    b = client.get("/api/board", params={"region": "강남구"}).json()
    assert all(d["youth"] for d in b["dongs"])


def test_ref_date_picks_past_week(client, tmp_path):
    # 【기능】 기준일 고르기 — 10-01 ~ 10-20 에만 80 · 90대 의료가 반토막 아래로 떨어진 가짜 표.
    #   10-20 을 고르면 위험이 보인다(추석 연휴 10-03 ~ 10-09 가 끝나고 1주가 지나도 경고가
    #   이어짐). 고르지 않으면(12-31) 다 회복해 평상이다
    _fake_card(tmp_path, drop=("2025-10-01", "2025-10-20"))
    past = client.get("/api/board", params={"region": "강남구", "ref": "2025-10-20"}).json()
    assert past["ref_date"] == "2025-10-20"
    assert past["counts"]["위험"] == 11
    assert past["trend"][-1]["ref"] == "2025-10-20" and past["trend"][0]["ref"] == "2025-09-29"
    assert past["next_week"]["from"] == "2025-10-21"
    # 대조 — 기준일을 안 고르면 자료 마지막 날, 그때는 경고가 없다
    now = client.get("/api/board", params={"region": "강남구"}).json()
    assert now["ref_date"] == "2025-12-31" and now["counts"]["위험"] == 0
    # 고를 수 있는 범위를 같이 준다(첫날 + 28일 + 8주)
    assert past["ref_min"] == "2025-09-23" and past["ref_max"] == "2025-12-31"
    m = client.get("/api/meta").json()
    assert m["ref_min"] == "2025-09-23" and m["ref_date"] == "2025-12-31"


def test_ref_date_flows_to_dong_and_chart(client, tmp_path):
    # 동 상세 · 근거 세 줄 · 그래프도 같은 기준일로 잰다
    _fake_card(tmp_path, drop=("2025-10-01", "2025-10-20"))
    q = {"region": "강남구", "ref": "2025-10-20"}
    b = client.get("/api/board", params=q).json()
    cd = next(d["dong_cd"] for d in b["dongs"] if d["grade"] == "위험")
    x = client.get(f"/api/dongs/{cd}", params={"ref": "2025-10-20"}).json()
    assert x["grade"] == "위험" and x["evidence"]["label"] == "평소보다 크게 적음"
    # 대조 — 기준일 없이 같은 동을 열면 평상, 근거 없음
    x0 = client.get(f"/api/dongs/{cd}").json()
    assert x0["grade"] == "평상" and x0["evidence"] is None
    c = client.get(
        "/api/chart", params={"age": "70대 이상", "group": "전체", "ref": "2025-10-20"}
    ).json()
    assert len(c) == 56 and c[-1]["day"] == "2025-10-20" and c[-1]["low"] is True


def test_ref_date_out_of_range(client, tmp_path):
    _fake_card(tmp_path)
    for bad in ["2025-08-01", "2025-09-22", "2026-01-05", "10월 20일"]:
        r = client.get("/api/board", params={"region": "강남구", "ref": bad})
        assert r.status_code == 422, bad
    # 대조 — 범위의 처음 · 끝 날은 받는다
    for ok in ["2025-09-23", "2025-12-31"]:
        assert client.get("/api/board", params={"region": "강남구", "ref": ok}).status_code == 200


def test_skt_alert_follows_ref_month(client, tmp_path):
    # 【기능】 SKT 동 경보는 기준일이 든 달의 값 — 10월을 보면 10월 경보, 12월을 보면 12월 경보
    _fake_card(tmp_path)
    t, _ = cards.dong_cards()
    cd = t[t["region"] == "강남구"]["dong_cd"].iloc[0]
    name = t[t["dong_cd"] == cd]["dong"].iloc[0]
    pd.DataFrame(
        [
            {"dong_cd": cd, "month": 202510, "dong": name, "grade": "주의", "why": "10월 경보"},
            {"dong_cd": cd, "month": 202512, "dong": name, "grade": "평상", "why": "12월"},
        ]
    ).to_csv(tmp_path / "dong_alert_month.csv", index=False)
    _clear()
    oct_ = client.get("/api/board", params={"region": "강남구", "ref": "2025-10-15"}).json()
    mine = next(d for d in oct_["dongs"] if d["dong_cd"] == cd)
    assert mine["grade"] == "주의" and mine["why"] == {"rule": "10월 경보", "source": "SKT"}
    # 대조 — 12월(기본)에는 그 동도 평상
    dec = client.get("/api/board", params={"region": "강남구"}).json()
    assert next(d for d in dec["dongs"] if d["dong_cd"] == cd)["grade"] == "평상"


def test_visit_order_within_grade(client, tmp_path):
    # 【기능】 방문 순서 — 같은 등급 안에서 신호 수(카드 + SKT) → 몇 주째 → 인원(est_n) 순
    _fake_card(tmp_path, soft_days=21)
    b = client.get("/api/board", params={"region": "강남구"}).json()
    warn = [d for d in b["dongs"] if d["grade"] == "주의"]
    assert len(warn) == 11 and all(d["signals"] == ["카드"] for d in warn)
    # 신호 · 몇 주째가 같으면 인원 많은 순 → 1 ~ 11
    by_rank = sorted(warn, key=lambda d: d["visit_rank"])
    assert [d["visit_rank"] for d in by_rank] == list(range(1, 12))
    est = [d["est_n"] for d in by_rank]
    assert est == sorted(est, reverse=True)
    # 대조 — 평상인 동은 순서가 없다
    assert all(d["visit_rank"] is None for d in b["dongs"] if d["grade"] == "평상")

    # 인원이 가장 적은 주의 동에 SKT 관심을 얹으면, 등급은 그대로 주의지만 1순위로 올라간다
    last = by_rank[-1]
    calm = next(d for d in b["dongs"] if d["grade"] == "평상")
    pd.DataFrame(
        [
            {
                "dong_cd": last["dong_cd"],
                "month": 202512,
                "dong": last["dong"],
                "grade": "관심",
                "why": "외출 줄어듦",
            },
            {
                "dong_cd": calm["dong_cd"],
                "month": 202512,
                "dong": calm["dong"],
                "grade": "주의",
                "why": "외출 줄어듦",
            },
        ]
    ).to_csv(tmp_path / "dong_alert_month.csv", index=False)
    _clear()
    b2 = client.get("/api/board", params={"region": "강남구"}).json()
    mine = next(d for d in b2["dongs"] if d["dong_cd"] == last["dong_cd"])
    assert mine["grade"] == "주의" and mine["signals"] == ["카드", "SKT"]
    assert mine["visit_rank"] == 1
    # 대조 — SKT 하나로 주의가 된 동은 신호 1개라 카드 주의 동들과 인원으로만 견준다
    skt_only = next(d for d in b2["dongs"] if d["dong_cd"] == calm["dong_cd"])
    assert skt_only["grade"] == "주의" and skt_only["signals"] == ["SKT"]
    assert skt_only["visit_rank"] > 1
