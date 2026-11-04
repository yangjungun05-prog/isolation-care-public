"""여러 조건 조회 시제품(10-26) — 조건을 코드가 맞춰 보는지."""

import json
from pathlib import Path

from src.assistant import query as Q
from src.assistant.data_source import JsonDongData

DATA = JsonDongData()
PEOPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "public" / "people.json").read_text(
        encoding="utf-8"
    )
)["dongs"]


def test_every_metric_has_values_where_it_says():
    for m in Q.METRICS:
        if m.note:  # 일부 동에만 있다고 밝힌 지표(빈집)
            continue
        if m.level == "마을":  # 10-27 마을 지표는 마을 줄에서 본다(test_concise_1027)
            continue
        for region in m.regions:
            vals = [
                m.get(DATA.dong(n) or {}, DATA.places(n) or {}, PEOPLE.get(n) or {})
                for n in DATA.region_dongs(region)
            ]
            assert sum(v is not None for v in vals) >= len(vals) // 2, (m.key, region)


def test_matched_dongs_meet_every_condition():
    plan = Q.Plan(
        region="강남구",
        conds=(
            Q.Cond(metric="pop65", op="이상", value=3000),
            Q.Cond(metric="solo80", op="이상", value=200),
            Q.Cond(metric="pharmacies", op="이하", value=10),
        ),
    )
    r = Q.run(plan, DATA, PEOPLE)
    for n in r.matched:
        v = r.values[n]
        assert v["pop65"] >= 3000 and v["solo80"] >= 200 and v["pharmacies"] <= 10
    for _n, miss in r.near:
        assert len(miss) == 1
    assert r.lines[0].startswith("[여러 조건 계산] 강남구 22곳")


def test_many_is_top_third_of_region():
    plan = Q.Plan(region="춘천시", conds=(Q.Cond(metric="solo80", op="많음"),))
    r = Q.run(plan, DATA, PEOPLE)
    assert len(r.matched) == 9  # 25곳의 위 3분의 1(올림)
    top = sorted(DATA.region_dongs("춘천시"), key=lambda n: -(r.values[n]["solo80"] or 0))[:9]
    assert set(r.matched) == set(top)


def test_region_only_metric_is_dropped_not_guessed():
    plan = Q.Plan(
        region="춘천시",
        conds=(Q.Cond(metric="lonely_female", op="많음"), Q.Cond(metric="solo65", op="많음")),
    )
    r = Q.run(plan, DATA, PEOPLE)
    assert any("춘천시에는 자료 없음" in x for x in r.dropped)
    assert len(r.conds) == 1


def test_threshold_without_number_is_dropped():
    r = Q.run(Q.Plan(region="강남구", conds=(Q.Cond(metric="pop65", op="이상"),)), DATA, PEOPLE)
    assert r.dropped and not r.conds


def test_schema_lists_only_known_metrics():
    s = Q.plan_schema()
    keys = s["properties"]["conds"]["items"]["properties"]["metric"]["enum"]
    assert keys == [m.key for m in Q.METRICS]
    assert "unknown" in s["required"]


def test_ties_share_a_rank_so_names_do_not_decide():
    plan = Q.Plan(region="강남구", conds=(Q.Cond(metric="halls", op="적음"),))
    r = Q.run(plan, DATA, PEOPLE)
    got = {n: r.values[n]["halls"] for n in r.matched}
    cut = max(got.values())
    # 같은 값인 동은 다 들어가거나 다 빠진다
    same = [n for n in DATA.region_dongs("강남구") if r.values[n]["halls"] == cut]
    assert all(n in r.matched for n in same)


def test_exceptions_1026():
    """10-26 예외 점검: 빈 칸 줄 · 0.0배 · 비율 평균 · 자료 없는 동 · 목록 밖 조건 · 표 정렬."""
    d = JsonDongData()
    r = Q.run(
        Q.Plan(
            region="강남구",
            show=(Q.Ref(metric="solo80"), Q.Ref(metric="basement_old")),
            mode="동마다 표",
        ),
        d,
    )
    assert not any("조건 0가지" in x for x in r.lines)
    assert r.matched[0] == "수서동"  # 첫 지표 많은 순(이름순 아님)
    assert not any("0.0배" in x for x in r.lines)
    r = Q.run(
        Q.Plan(
            region="강남구",
            dongs=("수서동", "세곡동"),
            show=(Q.Ref(metric="solo65_share"),),
            agg=("평균",),
            mode="동마다 표",
        ),
        d,
    )
    assert any("31.4%(고른 동 숫자를 합쳐서 나눈 값)" in x for x in r.lines)
    r = Q.run(Q.Plan(region="춘천시", sort=Q.Ref(metric="empty_houses"), limit=25), d)
    assert sum(x.startswith("[자료 없는 동] 15곳") for x in r.lines) == 1
    assert not any("자료 없음" in x and x.startswith("[강남동]") for x in r.lines)
    r = Q.run(
        Q.Plan(
            region="춘천시",
            conds=(Q.Cond(metric="solo65", op="많음"),),
            unknown=("버스 하루 3번 이하", "우울감"),
        ),
        d,
    )
    assert any(x.startswith("[다른 곳에 있는 자료] 버스") for x in r.lines)
    assert "[취약 돌보미에 없는 자료] 우울감" in r.lines


def test_prev_order_and_show_all_1026():
    d = JsonDongData()
    prev = ["후평1동", "교동", "서면", "남면"]
    r = Q.run(
        Q.Plan(region="춘천시", use_prev=True, show=(Q.Ref(metric="solo80"),), limit=3),
        d,
        prev=prev,
    )
    assert r.matched[:3] == prev[:3]  # '위 3곳'은 앞 답의 차례대로
    r = Q.run(Q.Plan(region="춘천시", conds=(Q.Cond(metric="pharmacies", op="없음"),)), d)
    assert 5 < len(r.matched) <= 8 and Q.shown_limit(r, Q.Plan()) == len(r.matched)
    assert any(x.startswith(f"[모두 맞는 동] 모두 {len(r.matched)}곳:") for x in r.lines)


def test_persona_fixes_query_1026():
    """10-26 페르소나 c01 · c05: 반올림해 같은 값 · 말에 나온 동 줄 · 어림 아래 · 위 값."""
    d = JsonDongData()
    p = Q.Plan(
        region="강남구",
        conds=(Q.Cond(metric="halls", per="pop65", scale=1000, op="평균보다 낮음"),),
    )
    r = Q.run(p, d)
    cell = Q._cell(r, "역삼1동", r.refs[0])
    assert "보다 낮음(" in cell  # 1.9곳 vs 1.9곳으로 보이지 않게
    lines = Q.focus_lines(r, p, ["수서동"])
    assert lines == [] or lines[0].startswith("[말씀하신 동 수서동]")
    r = Q.run(
        Q.Plan(
            region="춘천시",
            dongs=("석사동",),
            show=(Q.Ref(metric="youth_homebound_lo"), Q.Ref(metric="youth_homebound_hi")),
            mode="동마다 표",
        ),
        d,
    )
    assert r.values["석사동"]["youth_homebound_lo"] < r.values["석사동"]["youth_homebound_hi"]
