import pytest

from src.assistant import doc
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()
GOOD = {
    "summary": ["취약 돌보미 동 순위 25곳 중 2위", "65세 이상 1인세대 242명(1년 19명 늘었음)"],
    "sections": [
        {"heading": "어르신", "bullets": ["65세 이상 1인세대 223명 → 242명(19명 늘었음)"]},
        {"heading": "사는 곳과 갈 곳", "bullets": ["북산면 보건지소 · 조교 보건진료소 있음"]},
    ],
}


class FakeDocWriter:
    model = "fake-model"

    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.calls: list[str] = []

    def write(self, f: doc.DocFacts, fix_note: str = "") -> dict:
        self.calls.append(fix_note)
        return self.docs[min(len(self.calls), len(self.docs)) - 1]


def _fonts_or_skip() -> None:
    try:
        doc.find_fonts()
    except FileNotFoundError:
        pytest.skip("나눔고딕이 없는 곳(CI 등)에서는 PDF 그리기를 건너뛴다")


def test_doc_facts_reuse_chat_shelf_sentences():
    # 【판단】 문서도 대화와 같은 사서 문장을 쓴다 — 같은 사실이 대화와 문서에서 다르게 나오지 않게
    f = doc.doc_facts("북산면", DATA)
    assert f.region == "춘천시" and f.text.startswith("[춘천시 북산면")
    assert "마을에서 약국까지 가운데값 10.7km" in f.text  # 진단 · 갈 곳
    assert "이 면을 지나는 하루 3번 이하 마을버스: 북산2(하루 약 2번)" in f.text  # 버스
    # 10-19 자료 2026 최신 판(주민등록 2026-09)으로 다시 셈
    assert f.text.count("취약 돌보미 동 순위: 춘천시 25곳 중 2위") == 1  # 같은 줄은 한 번만
    assert ("취약 돌보미 동 순위", "25곳 중 2위 · 실제 1인 가구로 다시 매기면 7위") in f.figures
    assert ("65세 이상 1인세대(주민등록 2026-09)", "242명(1년 +19명)") in f.figures


def test_problems_catch_number_direction_banned():
    f = doc.doc_facts("북산면", DATA)
    bad = {
        "summary": ["65세 이상 1인세대 300명"],
        "sections": [
            {"heading": "어르신", "bullets": ["223명 → 242명으로 줄었음", "자료가 없어 알 수 없음"]}
        ],
    }
    p = doc.problems(bad, f)
    assert any("300" in w for w in p["65세 이상 1인세대 300명"])
    assert "늘었다 · 줄었다가 자료와 반대" in p["223명 → 242명으로 줄었음"]
    assert any("쓰지 않기로 한 말" in w for w in p["자료가 없어 알 수 없음"])
    assert doc.problems(GOOD, f) == {}


def test_build_retries_then_drops_bad_lines_and_reuses_files(tmp_path):
    _fonts_or_skip()
    with_bad = {
        "summary": [*GOOD["summary"], "주민 9,999명"],
        "sections": GOOD["sections"],
    }
    w = FakeDocWriter([with_bad, with_bad])
    r = doc.build("북산면", DATA, w, tmp_path)
    assert len(w.calls) == 2 and "주민 9,999명" in w.calls[1]  # 걸린 줄을 알려 주고 한 번 더
    assert "주민 9,999명" not in r.doc["summary"] and "주민 9,999명" in r.dropped
    assert r.pdf.exists() and r.pptx.exists() and r.doc["title"] == "춘천시 북산면 동 상황 문서"
    again = doc.build("북산면", DATA, w, tmp_path)
    assert again.reused and len(w.calls) == 2  # 같은 자료 · 같은 모델이면 다시 쓰지 않는다


def test_engine_makes_doc_and_returns_files(tmp_path):
    _fonts_or_skip()
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    table = {
        "북산면 동 상황 PDF로 만들어 줘": DeskCard(
            act="ask", topics=("dong_doc",), dong_op="set", dong_mentions=("북산면",)
        )
    }
    e = Engine(FakeDesk(table), TemplateWriter(), DATA, MemoryStore(), s, FakeDocWriter([GOOD]))
    e.start("d", Profile(member_region="춘천시"))
    # 10-27: 진행 단계(status)는 화면에서만 쓰는 알림이라 빼고 본다
    events = [x for x in e.turn_stream("d", "북산면 동 상황 PDF로 만들어 줘") if x[0] != "status"]
    assert events[0][0] == "text" and "만드는 중" in events[0][1]
    r = events[-1][1]
    assert r.kind == "answer" and "북산면 상황 문서를 만들었어요" in r.text
    assert len(r.files) == 2 and all(p.endswith((".pdf", ".pptx")) for p in r.files)
    assert "북산면 동 상황 문서" in e.store.load("d").log[-1].note  # 되짚기에 남는다


def test_doc_has_code_built_judge_section(tmp_path):
    # 10-20 할 일 28: 동 상황 문서에 취약 돌보미 판단 절(챗봇 · 카드와 같은 조건 창고, AI를 거치지
    #        않음)
    f = doc.doc_facts("북산면", DATA)
    assert f.judge and f.judge[0].startswith("어르신: ")
    assert any(x.startswith("청년: ") for x in f.judge)
    assert f.judge[-1].startswith("판단 기준: ")
    d = doc._with_judge(
        {"summary": ["a"], "sections": [{"heading": "어르신", "bullets": ["b"]}]}, f
    )
    assert (
        d["sections"][-1]["heading"] == doc.JUDGE_HEAD and d["sections"][-1]["bullets"] == f.judge
    )
    assert doc._with_judge(d, f)["sections"].count(d["sections"][-1]) == 1  # 두 번 붙지 않는다


def test_missing_fonts_stop_before_calling_ai(tmp_path, monkeypatch):
    """10-27 qbank P1-22: 글꼴이 없으면 AI(Sonnet)를 부르기 전에 멈춘다(돈이 헛나가지 않게)."""
    monkeypatch.setattr(doc, "FONT_DIRS", ())
    w = FakeDocWriter([GOOD])
    with pytest.raises(FileNotFoundError):
        doc.build("북산면", DATA, w, tmp_path, font_dir=str(tmp_path / "없는 폴더"))
    assert w.calls == []


def test_google_font_file_names_are_found(tmp_path, monkeypatch):
    monkeypatch.setattr(doc, "FONT_DIRS", ())
    for n in ("NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"):
        (tmp_path / n).write_bytes(b"x")
    reg, bold = doc.find_fonts(str(tmp_path))
    assert reg.endswith("NanumGothic-Regular.ttf") and bold.endswith("NanumGothic-Bold.ttf")


def test_pdf_text_replaces_glyphs_missing_in_nanum():
    assert (
        doc.pdf_text("넓이 120㎡ · 최저 -8℃ · 3.2㎞ · ①") == "넓이 120m² · 최저 -8°C · 3.2km · (1)"
    )
    assert doc.pdf_text(5) == 5
