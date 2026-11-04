"""모두 맞는 동이 답 글에서 빠지면 코드가 채운다(10-26 calc_flow_8 T5). AI를 부르지 않는다."""

import json
from pathlib import Path

from src.assistant import query as Q
from src.assistant.data_source import JsonDongData
from src.assistant.engine import calc_missing

DATA = JsonDongData()
PEOPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "public" / "people.json").read_text(
        encoding="utf-8"
    )
)["dongs"]


def _run():
    plan = Q.Plan(region="춘천시", conds=(Q.Cond(metric="solo80", op="많음"),))
    return Q.run(plan, DATA, PEOPLE), plan


def test_nothing_added_when_every_shown_dong_is_written():
    r, plan = _run()
    top = r.matched[: Q.shown_limit(r, plan)]
    assert (
        calc_missing(r, plan, f"맞는 곳은 {len(r.matched)}곳, " + ", ".join(top) + "이에요.") == ""
    )
    # 10-27 village_6 c1 T3: 위 몇 곳만 쓰고 전체 수가 글에 없으면 수를 한 줄로 알린다
    if len(r.matched) > len(top):
        got = calc_missing(r, plan, "맞는 곳은 " + ", ".join(top) + "이에요.")
        assert f"모두 {len(r.matched)}곳" in got


def test_missing_dong_brings_the_whole_list():
    r, plan = _run()
    top = r.matched[: Q.shown_limit(r, plan)]
    got = calc_missing(r, plan, "맞는 곳은 " + ", ".join(top[:2]) + "이에요.")
    assert f"조건에 모두 맞는 동 {len(r.matched)}곳(위 {len(top)}곳만)" in got
    assert all(n in got for n in top)


def test_name_inside_longer_name_does_not_count():
    # '동면'은 '신동면' 안에 있어도 쓴 것이 아니다
    r, plan = _run()
    r.matched = ["동면", "신북읍"]
    assert "동면 · 신북읍" in calc_missing(r, plan, "신동면 · 신북읍")


def test_ranked_or_table_modes_are_left_alone():
    plan = Q.Plan(region="춘천시", conds=(Q.Cond(metric="solo80", op="많음"),), mode="많이 맞는 순")
    r = Q.run(plan, DATA, PEOPLE)
    assert calc_missing(r, plan, "") == ""


def test_age_and_list_numbers_do_not_pull_old_facts():
    # q5 2-26: '2. 80세 이상'의 80 · 번호를 앞 답 숫자로 읽어 앞 동 자료가 통째로 따라옴
    from src.assistant.engine import carry_facts

    old = (
        "[춘천시 신북읍]",
        "- 80세 이상 1인세대(주민등록 2026-09): 343명",
        "- 보건기관: 신북읍 보건지소",
    )
    text = "1. 동면이 춘천에서 어떤 편인지 2. 80세 이상 혼자 사는 분 4. 가까운 보건지소"
    assert carry_facts(text, "", old, []) is None
    # 진짜 숫자를 되짚으면 앞 줄을 준다
    assert carry_facts("80세 이상 343명이라고 했죠?", "", old, []) is not None
