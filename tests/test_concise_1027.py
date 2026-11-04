"""10-27 팀장: 묻는 것만 답하기 · 마을 단위 조건 넣기 · 글 다듬기는 되묻기."""

from src.assistant import query as Q
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.engine import Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()


def test_hub_names_join_to_legal_ri():
    ris = {"조교리": {}, "가정리": {}, "강촌리": {}, "고탄리": {}, "물로리": {}}
    assert Q._hub_ri("조교1리 경로당", ris) == "조교리"
    assert Q._hub_ri("가정1,2리 경로당", ris) == "가정리"
    assert Q._hub_ri("발뢰 경로당(강촌3리)", ris) == "강촌리"
    assert Q._hub_ri("고탄늘푸른경로당", ris) == "고탄리"
    assert Q._hub_ri("물로리 경로당", ris) == "물로리"
    assert Q._hub_ri("해강아파트 경로당", ris) is None


def test_village_rows_cover_every_ri_of_the_towns():
    towns = [t for t in DATA.region_dongs("춘천시") if t.endswith(("읍", "면"))]
    rows, _ = Q.village_rows(DATA, towns)
    n_ri = sum(len((DATA.focus(t) or {}).get("villages") or []) for t in towns)
    assert len(rows) == n_ri and all(" " in k for k in rows)
    assert sum(r["bus_per_day"] is not None for r in rows.values()) >= len(rows) * 0.8


def test_village_conditions_are_counted_by_code():
    p = Q.Plan(
        region="춘천시",
        conds=(
            Q.Cond(metric="v_bus", op="이하", value=5),
            Q.Cond(metric="v_pharm", op="이상", value=5),
        ),
    )
    r = Q.run(p, DATA)
    rows, _ = Q.village_rows(
        DATA, [t for t in DATA.region_dongs("춘천시") if t.endswith(("읍", "면"))]
    )
    want = [
        n
        for n, v in rows.items()
        if v["bus_per_day"] is not None
        and v["bus_per_day"] <= 5
        and v.get("pharm_km_3") is not None
        and v["pharm_km_3"] >= 5
    ]
    assert sorted(r.matched) == sorted(want) and want
    text = "\n".join(r.lines)
    assert "[마을 단위]" in text and "[모두 맞는 마을]" in text and "[모두 맞는 동]" not in text


def test_town_condition_filters_towns_first():
    p = Q.Plan(
        region="춘천시",
        conds=(Q.Cond(metric="solo80", op="많음"), Q.Cond(metric="v_pharm", op="이상", value=5)),
    )
    r = Q.run(p, DATA)
    assert any(x.startswith("[읍 · 면 먼저 거름]") for x in r.lines)
    head = next(x for x in r.lines if x.startswith("[마을 단위]"))
    towns = head.split(": ", 1)[1].split(". ")[0].split(" · ")
    assert all(m.split()[0] in towns for m in r.matched)


def test_village_metric_in_gangnam_is_dropped_not_guessed():
    r = Q.run(Q.Plan(region="강남구", conds=(Q.Cond(metric="v_bus", op="이하", value=3),)), DATA)
    assert r.dropped and "강남구에는 자료 없음" in r.dropped[0]


def test_near_list_only_when_nothing_matches():
    p = Q.Plan(
        region="강남구",
        conds=(Q.Cond(metric="solo80", op="많음"), Q.Cond(metric="halls", op="적음")),
    )
    r = Q.run(p, DATA)
    text = "\n".join(r.lines)
    assert ("[하나만 못 맞춘 동]" in text) == (not r.matched)


def _engine(card: DeskCard) -> Engine:
    class Desk:
        def read(self, state, text):
            return card

    e = Engine(Desk(), TemplateWriter(), DATA, MemoryStore(), AssistantSettings())
    e.start("s", Profile(member_region="춘천시"))
    return e


def test_polish_request_asks_back_with_what_we_can_make():
    e = _engine(DeskCard(restate="보고서 문장을 다듬는 방법", act="ask", topics=("usage",)))
    r = e.turn("s", "보고서 문장 좀 다듬어 줘")
    assert r.kind == "unclear" and "어느 동으로 만들까요" in r.text
    assert "효자2동 상황을 보고용 한 줄로" in r.text and "고치거나 다듬는 일은" in r.text


def test_top_rank_question_has_no_duplicate_head():
    e = _engine(DeskCard(restate="춘천 먼저 볼 동 1위", act="ask", topics=("priority",)))
    r = e.turn("s", "춘천에서 먼저 볼 동 1위가 어디예요?")
    assert "그 동으로 볼게요" not in r.text


def test_town_pharmacy_answer_lists_far_villages():
    from src.assistant import librarian
    from src.assistant.slots import Slots

    f = librarian.gather("places", Slots(region="춘천시", dongs=("신북읍",)), DATA)
    line = next((x for x in f.lines if x.lstrip("- ").startswith("약국이 먼 마을")), "")
    assert "km 넘는 마을" in line and "먼 순" in line


def test_village_use_prev_filters_inside_previous_villages():
    p = Q.Plan(region="춘천시", conds=(Q.Cond(metric="v_weak_roof", op="많음"),), use_prev=True)
    prev = ["사북면 지암리", "남산면 행촌리", "남면 추곡리"]
    r = Q.run(p, DATA, prev=prev)
    assert set(r.values) == set(prev) and any(x.startswith("[앞 결과 안에서]") for x in r.lines)


def test_town_show_metric_is_kept_as_town_value():
    p = Q.Plan(
        region="춘천시",
        dongs=("동면",),
        conds=(Q.Cond(metric="v_bus", op="이하", value=3),),
        show=(Q.Ref(metric="solo80"),),
    )
    r = Q.run(p, DATA)
    town = [x for x in r.lines if x.startswith("[읍 · 면 값] [동면]")]
    assert town and "혼자 사는 80세 이상" in town[0]


def test_calc_count_is_added_when_writer_misses_it():
    from src.assistant.engine import calc_missing

    p = Q.Plan(
        region="춘천시",
        dongs=("사북면",),
        conds=(Q.Cond(metric="v_pharm_sun", op="이상", value=5),),
    )
    r = Q.run(p, DATA)
    top = r.matched[: Q.shown_limit(r, p)]
    body = "5곳 모두예요. " + " · ".join(top)
    if len(r.matched) > len(top):
        assert f"{len(r.matched)}곳" in calc_missing(r, p, body)


def test_rest_of_rank_only_when_asked_for_all():
    from src.assistant import librarian
    from src.assistant.slots import Slots

    s = Slots(region="강남구", rank=True)
    some = librarian.gather("housing", s, DATA, asked="지하층 집이 많은 동이 어디예요?")
    every = librarian.gather("housing", s, DATA, asked="지하층 집 많은 순서 22개 동 전부 알려 줘")
    assert not any("나머지 동 순서" in x for x in some.lines)
    assert any("나머지 동 순서" in x for x in every.lines)


def test_weekday_in_question_picks_that_day_for_pharmacies():
    from src.assistant import librarian
    from src.assistant.slots import Slots

    f = librarian.gather(
        "places",
        Slots(region="춘천시", dongs=("사북면",)),
        DATA,
        asked="사북면에서 일요일에 약국이 먼 마을은?",
    )
    line = next(x for x in f.lines if x.lstrip("- ").startswith("약국이 먼 마을"))
    assert "(일)" in line
    assert any("약국이 먼 곳을 물었다" in n for n in f.notes)


def test_status_events_come_before_the_answer():
    # 10-27 멘토 제안: 진행 단계 — 글보다 먼저, 답 글 · 끝은 그대로
    e = _engine(
        DeskCard(
            restate="수서동 혼자 사는 어르신 수",
            act="ask",
            topics=("solo_seniors",),
            dong_op="set",
            dong_mentions=("수서동",),
            target_op="set",
            target="어르신",
        )
    )
    events = list(e.turn_stream("s", "수서동 혼자 사는 어르신 몇 분이에요?"))
    kinds = [k for k, _ in events]
    assert kinds[0] == "status" and kinds[-1] == "done"
    first_text = next(i for i, k in enumerate(kinds) if k in ("text", "replace"))
    assert all(k == "status" for k in kinds[:first_text])
    assert "질문을 알아듣는 중" in [v for k, v in events if k == "status"]


def test_desk_input_lists_found_dong_names():
    from src.assistant.desk import user_text
    from src.assistant.state import new_state

    u = user_text(new_state(), "삼성1동이 아니라 대치4동 보다는.. 글쎄 수서동 청년")
    assert "[말 속 동 이름(코드가 찾음)]" in u
    tail = u.split("[말 속 동 이름(코드가 찾음)]")[1]
    assert all(n in tail for n in ("삼성1동", "대치4동", "수서동"))
    assert "[말 속 동 이름" not in user_text(new_state(), "오늘 날씨 어때요?")
