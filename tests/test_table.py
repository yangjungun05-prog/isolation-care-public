"""동별 표 내려받기(원문 자료 서가, 10-14)."""

import csv

from src.assistant import table
from src.assistant.data_source import JsonDongData

DATA = JsonDongData()


def _col(t: table.Table, name: str) -> dict[str, object]:
    i = t.header.index(name)
    return {r[1]: r[i] for r in t.rows}


def test_region_table_has_every_dong_and_sources():
    t = table.build(("solo_seniors",), "강남구", [], DATA)
    assert len(t.rows) == 22
    assert _col(t, "65세 이상 1인세대 2026-09")["수서동"] == 2543  # 10-19 주민등록 2026-09
    assert _col(t, "65세 이상 1인세대 2025-09")["수서동"] == 2462
    assert any("주민등록" in f for f in t.footer) and "기준일" in t.footer[0]


def test_livelihood_columns_follow_region():
    # 춘천은 전체 수급자, 강남은 서울시 독거노인 현황의 수급권자 독거노인(값이 없는 열은 뺀다)
    cc = table.build(("livelihood",), "춘천시", [], DATA)
    assert _col(cc, "기초생활수급자(명)")["북산면"] == 73
    assert "수급권자 독거노인 2025" not in cc.header
    gn = table.build(("livelihood",), "강남구", [], DATA)
    assert _col(gn, "수급권자 독거노인 2025")["수서동"] == 1786
    assert "기초생활수급자(명)" not in gn.header


def test_chosen_dongs_only_and_skipped_topics():
    t = table.build(("places", "youth"), "춘천시", ["북산면", "교동"], DATA)
    assert [r[1] for r in t.rows] == ["북산면", "교동"]
    assert _col(t, "거의 집에만 있는 청년 어림(아래)")["북산면"] == "10명 아래"
    assert t.skipped and "갈 곳" in t.skipped[0]


def test_save_writes_xlsx_and_csv(tmp_path):
    t = table.build(("solo_seniors",), "강남구", ["수서동"], DATA)
    paths = table.save(t, "강남구", DATA.basis, tmp_path)
    assert [p.suffix for p in paths] == [".xlsx", ".csv"]
    with paths[1].open(encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert rows[0][:2] == ["지역", "동"] and rows[1][1] == "수서동"


def test_engine_table_turn_gives_files(tmp_path):
    # 【기능】 '그거 엑셀로'(fmt=엑셀) → 글쓴이 없이 코드가 표 파일 둘을 만든다
    from src.assistant.config import AssistantSettings
    from src.assistant.desk import FakeDesk
    from src.assistant.engine import Engine
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    card = DeskCard(
        act="ask", topics=("solo_seniors",), region_op="set", region="강남구",
        dong_op="clear", rank=True, fmt="엑셀",
    )  # fmt: skip
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk({"강남구 22개 동 독거노인 수 동별로 엑셀로": card}), TemplateWriter(),
               DATA, MemoryStore(), s)  # fmt: skip
    e.start("t", Profile(member_region="강남구"))
    done = [v for k, v in e.turn_stream("t", "강남구 22개 동 독거노인 수 동별로 엑셀로")
            if k == "done"][0]  # fmt: skip
    assert (
        done.kind == "answer" and "22개 동" in done.text and "엑셀 · CSV로 만들었어요" in done.text
    )
    assert sorted(p[-4:] for p in done.files) == [".csv", "xlsx"]


def test_datasets_shelf_lists_by_region():
    from src.assistant.librarian import gather
    from src.assistant.slots import Slots

    cc = gather("datasets", Slots(region="춘천시"), DATA)
    text = "\n".join(cc.lines)
    assert "춘천시 기초생활보장 수급권자" in text and "서울시 독거노인" not in text
    assert "이용허락범위 제한 없음" in text and cc.notes  # 건넬 수 있는 것 안내
    both = gather("datasets", Slots(), DATA)
    assert len(both.lines) == len(DATA.datasets()["items"])
