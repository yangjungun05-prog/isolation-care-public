import json

from fastapi.testclient import TestClient

from src.api.assistant import create_app
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.slots import DeskCard
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

TABLE = {
    "수서동 청년은?": DeskCard(
        act="ask",
        topics=("youth",),
        dong_op="set",
        dong_mentions=("수서동",),
        target_op="set",
        target="청년",
    ),
}


def _client(tmp_path) -> TestClient:
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk(TABLE), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    return TestClient(create_app(e))


def _events(res) -> list[dict]:
    return [json.loads(x[len("data: ") :]) for x in res.text.split("\n\n") if x.strip()]


def test_page_shows_chat_with_1000_char_limit(tmp_path):
    r = _client(tmp_path).get("/")
    assert r.status_code == 200 and "1,000자 제한" in r.text and "/assistant/chat" in r.text


def test_chat_streams_and_ends_with_done(tmp_path):
    c = _client(tmp_path)
    r = c.post("/assistant/chat", json={"session_id": "a", "text": "수서동 청년은?"})
    ev = _events(r)
    assert ev[-1]["event"] == "done" and ev[-1]["data"]["kind"] == "answer"
    assert "1,897명" in ev[-1]["data"]["text"]  # 10-19 2026 최신 판(주민등록 2026-09)


def test_long_input_is_refused_not_clipped(tmp_path):
    r = _client(tmp_path).post("/assistant/chat", json={"session_id": "b", "text": "가" * 1001})
    assert _events(r)[-1]["data"]["kind"] == "too_long"


def test_files_only_from_doc_folder(tmp_path):
    c = _client(tmp_path)
    (tmp_path / "춘천시_북산면_x.pdf").write_bytes(b"%PDF-1.4")
    assert c.get("/assistant/files/춘천시_북산면_x.pdf").status_code == 200
    # 10-14 동별 표(엑셀 · CSV)도 받는다
    (tmp_path / "강남구_표.xlsx").write_bytes(b"PK")
    assert c.get("/assistant/files/강남구_표.xlsx").status_code == 200
    assert c.get("/assistant/files/..%2F.env").status_code == 404
    assert c.get("/assistant/files/notes.txt").status_code == 404


def test_today_cards_for_member_dong(tmp_path):
    # 【기능】 10-14 오늘 챙길 일 카드: 담당 동 · 날짜 → 카드
    #        (기준일 2025-12-31 서울 최저 -8.9℃ 한파)
    c = _client(tmp_path)
    r = c.get(
        "/assistant/today", params={"region": "강남구", "dong": "수서동", "date": "2025-12-31"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["where"] == "강남구 수서동" and body["cards"][0]["kind"] == "한파"
    assert (
        c.get("/assistant/today", params={"region": "강남구", "dong": "북산면"}).status_code == 400
    )
    assert c.get("/assistant/today", params={"region": "부산", "dong": ""}).status_code == 400
    assert c.get("/assistant/today", params={"region": "강남구", "date": "어제"}).status_code == 400
    assert "수서동" in c.get("/assistant/dongs").json()["강남구"]
