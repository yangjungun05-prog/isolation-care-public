"""채팅 표 고치기(10-28) — 앞 턴 표를 정렬 · 열 더하기 · 빼기 · 위 N곳 · 다른 지역으로.

evals/scenarios/table_noel_10.json t1: 첫 표 뒤 '많은 순으로 정렬' · '증감률 열도' · '비율 열도' ·
'위에서 다섯 곳만'이 앞 표를 잇지 못해 글로 답하거나 '증감률은 계산할 수 없다' · '증감 자료가 없다'.
"""

import re

from src.assistant import table, table_edit
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile, TableSpec
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()
HEAD = table.build(("solo_seniors",), "강남구", [], DATA).header
NOW = next(h for h in HEAD if h.startswith("65세 이상 1인세대 2026"))
PREV = next(h for h in HEAD if h.startswith("65세 이상 1인세대 2025"))
RATE = next(h for h in HEAD if "증감률" in h)
SHARE = next(h for h in HEAD if "혼자 사는 몫" in h)
SPEC = TableSpec(region="강남구", topics=("solo_seniors",), cols=(PREV, NOW))


def _rows(md: str) -> list[list[str]]:
    lines = [x for x in md.splitlines() if x.startswith("| ") and not x.startswith("| 동 |")]
    return [[c.strip() for c in x.strip("|").split("|")] for x in lines]


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def test_edit_words():
    for say in (
        "많은 순으로 정렬해 줘",
        "증감률 열도 넣어 줘",
        "비율 열도 추가해 줘",
        "위에서 다섯 곳만 보여 줘",
        "22곳 전부 다 넣어 줘",
        "춘천도 같은 표로 보여 줘",
        "80세 열은 빼 줘",
    ):
        assert table_edit.is_edit(say), say
    for say in ("수서동 청년은요?", "고마워요", "표에서 2025년 9월 값이 없는 동 있어?"):
        assert not table_edit.is_edit(say), say


def test_sort_uses_this_year_not_last_year():
    new, notes = table_edit.apply(SPEC, HEAD, "많은 순으로 정렬해 줘", "강남구")
    assert new.sort == NOW and new.desc
    md, n, _ = table_edit.render(new, DATA)
    vals = [_num(r[2]) for r in _rows(md)]  # 동 · 2025 · 2026
    assert n == 22 and vals == sorted(vals, reverse=True)


def test_add_rate_and_share_keep_old_columns():
    new, notes = table_edit.apply(SPEC, HEAD, "작년 같은 달 대비 증감률 열도 넣어 줘", "강남구")
    assert new.cols == (PREV, NOW, RATE) and "더한 열" in notes[0]
    new, _ = table_edit.apply(new, HEAD, "65세 이상 중에 혼자 사는 비율 열도 추가해 줘", "강남구")
    assert new.cols == (PREV, NOW, RATE, SHARE)
    md, _, _ = table_edit.render(new, DATA)
    assert RATE in md and SHARE in md and PREV in md


def test_sort_by_named_column_adds_it_and_top_n():
    new, _ = table_edit.apply(SPEC, HEAD, "증감률 높은 순으로 다시 정렬해 줘", "강남구")
    assert new.sort == RATE and RATE in new.cols
    new, notes = table_edit.apply(new, HEAD, "위에서 다섯 곳만 보여 줘", "강남구")
    md, n, _ = table_edit.render(new, DATA)
    rates = [_num(r[-1]) for r in _rows(md)]
    assert n == 5 and rates == sorted(rates, reverse=True)
    new, _ = table_edit.apply(new, HEAD, "22곳 전부 다 넣어 줘", "강남구")
    assert table_edit.render(new, DATA)[1] == 22


def test_remove_column():
    new, notes = table_edit.apply(SPEC, HEAD, "2025 열은 빼 줘", "강남구")
    assert new.cols == (NOW,) and notes[0].startswith("뺀 열")


def test_other_region_keeps_columns_but_all_rows():
    five = SPEC.model_copy(update={"top": 5, "sort": NOW})
    new, _ = table_edit.apply(five, HEAD, "춘천도 같은 표로 보여 줘", "춘천시")
    md, n, _ = table_edit.render(new, DATA)
    assert (
        new.region == "춘천시" and new.cols == SPEC.cols and n == len(DATA.region_dongs("춘천시"))
    )


TABLE = {
    "강남구 22개 동 혼자 사는 어르신 수를 표로 보여 줘": DeskCard(
        act="ask", topics=("solo_seniors",), region="강남구", region_op="set"
    ),
    "많은 순으로 정렬해 줘": DeskCard(act="ask", topics=("solo_seniors",)),
    "위에서 다섯 곳만 보여 줘": DeskCard(act="unclear"),
    "청년 많은 순으로 알려 줘": DeskCard(act="ask", topics=("youth",)),
    "수서동 청년은요?": DeskCard(
        act="ask", topics=("youth",), dong_op="set", dong_mentions=("수서동",)
    ),
}


def test_engine_follow_up_redraws_table_without_writer():
    s = AssistantSettings(anthropic_api_key="")
    e = Engine(FakeDesk(TABLE), TemplateWriter(), DATA, MemoryStore(), s)
    e.start("t", Profile(member_region="강남구"))
    r1 = e.turn("t", "강남구 22개 동 혼자 사는 어르신 수를 표로 보여 줘")
    assert "|---" in r1.text and r1.state.table_spec is not None
    r2 = e.turn("t", "많은 순으로 정렬해 줘")
    assert r2.text.startswith("앞의 강남구 표를 고쳤어요(정렬:")
    assert r2.kind == "answer" and len(_rows(r2.text)) == 22
    r3 = e.turn("t", "위에서 다섯 곳만 보여 줘")
    rows = _rows(r3.text)
    assert len(rows) == 5 and rows[0][0] == "수서동"
    # 다른 주제를 물으면 표 고치기가 아니다
    assert not e.turn("t", "청년 많은 순으로 알려 줘").text.startswith("앞의")
    # 동을 말한 새 질문은 표 고치기가 아니다
    r4 = e.turn("t", "수서동 청년은요?")
    assert not r4.text.startswith("앞의")


def test_fact_label_is_stripped():
    from src.assistant import checks

    out = checks.tidy("자료의 F3 표를 보면 22개 동 모두 값이 있어요.")
    assert "F3" not in out and not re.search(r"F\d", out)
