"""여러 조건 계산 뒤 '엑셀로' — 계산의 전체 표(후보 동 모두 · ○ × 와 값 · 맞은 수)로 파일(10-28).

페르소나 p09_c(강남구청 데이터 담당): 계산 뒤 엑셀을 세 번 달라 했는데 파일이 2곳 → 8곳 → 1곳(그때
동 칸)으로 바뀌고 조건 열이 없었다.
"""

import csv
from pathlib import Path

from src.assistant import query as Q
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

ASK = "반지하 많고 혼자 사는 할머니 많은 동"
XLS = "엑셀로 주세요"
TABLE = {
    ASK: DeskCard(act="ask", topics=("housing", "solo_seniors")),
    XLS: DeskCard(act="ask", topics=("solo_seniors",), fmt="엑셀"),
    "수서동 엑셀로 주세요": DeskCard(
        act="ask", topics=("solo_seniors",), fmt="엑셀", dong_op="set", dong_mentions=("수서동",)
    ),
}
PLAN = Q.Plan(
    conds=(Q.Cond(metric="basement_old", op="많음"), Q.Cond(metric="lonely_female", op="많음"))
)


class FakePlanner:
    def __init__(self, plan):
        self.p = plan

    def plan(self, question, region, context=""):
        return self.p


def _engine(tmp_path):
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    p = FakePlanner(PLAN)
    e = Engine(FakeDesk(TABLE), TemplateWriter(), JsonDongData(), MemoryStore(), s, planner=p)
    e.start("x", Profile(member_region="강남구"))
    return e, p


def _csv(path: str) -> list[list[str]]:
    with Path(path).with_suffix(".csv").open(encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def test_calc_then_excel_gives_whole_calc_sheet(tmp_path):
    e, p = _engine(tmp_path)
    r1 = e.turn("x", ASK)
    head, *rows = r1.state.calc_sheet
    assert head[0] == "동" and head[-1] == "맞은 수" and len(rows) == 22
    # 다음 턴에는 계산을 다시 하지 않아도(계획기가 '바로') 앞 계산 표로 파일
    p.p = Q.Plan(need="바로")
    r2 = e.turn("x", XLS)
    assert r2.files and any(f.endswith(".xlsx") for f in r2.files)
    assert "앞 계산 표(강남구 22곳 전부 · 조건 2가지 · 맞은 수)" in r2.text
    got = _csv(next(f for f in r2.files if f.endswith(".csv")))
    assert got[0][:2] == ["지역", "동"] and got[0][-1] == "맞은 수"
    body = [r for r in got[1:] if len(r) > 2]
    assert len(body) == 22
    # 맞은 수 많은 동이 위
    assert [int(r[-1].split("/")[0]) for r in body] == sorted(
        (int(r[-1].split("/")[0]) for r in body), reverse=True
    )
    assert any(r and r[0].startswith("조건 1)") for r in got)
    # 파일만 달라는 말이면 글쓴이 없이 코드 한 문장(새 결론을 지어내지 않게)
    assert "파일에는 22곳마다" in r2.text and "맞은 수가 들어 있어요" in r2.text


def test_new_dong_excel_is_not_the_calc_sheet(tmp_path):
    e, p = _engine(tmp_path)
    e.turn("x", ASK)
    p.p = Q.Plan(need="바로")
    r = e.turn("x", "수서동 엑셀로 주세요")
    assert "앞 계산 표" not in r.text


def test_calc_note_says_mean_is_not_denominator():
    from src.assistant.engine import CALC_NOTES

    joined = " ".join(CALC_NOTES)
    assert "분모도 아니다" in joined and "3분의 1" in joined


def test_same_turn_calc_and_excel(tmp_path):
    """한 말에 '계산 + 엑셀'이면 계산 길을 타고 그 계산 표로 파일(10-28, 전에는 보통 표 파일)."""
    say = "반지하 많고 혼자 사는 할머니 많은 동 엑셀로"
    TABLE[say] = DeskCard(act="ask", topics=("housing", "solo_seniors"), fmt="엑셀")
    e, _ = _engine(tmp_path)
    r = e.turn("x", say)
    assert r.files and "이 계산 표(강남구 22곳 전부 · 조건 2가지 · 맞은 수)" in r.text
    got = _csv(next(f for f in r.files if f.endswith(".csv")))
    assert got[0][-1] == "맞은 수"


def test_excel_only_words():
    from src.assistant.engine import EXCEL_ONLY

    for say in (
        "엑셀로 주세요",
        "엑셀로 받을 수 있어요?",
        "그 결과 엑셀 파일로 주세요",
        "CSV로 줘",
    ):
        assert EXCEL_ONLY.fullmatch(say), say
    for say in ("엑셀로 주시고 계산 방법도 알려 주세요", "수서동 엑셀로 주세요"):
        assert not EXCEL_ONLY.fullmatch(say), say
