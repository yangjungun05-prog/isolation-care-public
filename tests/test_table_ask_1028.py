"""10-28 페르소나 p01_c T1: '표 좀 급하게 부탁드립니다'에 '엑셀 표 기능이 없어요'(거짓)."""

from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import CHAT_TABLE, TABLE_ASK, Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter


def test_table_please_is_a_table_ask():
    q = "강남구 22개 동 65세 이상 1인세대 많은 순으로 표 좀 급하게 부탁드립니다"
    assert CHAT_TABLE.search(q) and TABLE_ASK.search(q)
    assert not CHAT_TABLE.search("표준 어떻게 정했어요") and not CHAT_TABLE.search("발표 자료")


def test_table_please_gets_all_22_rows(tmp_path):
    q = "강남구 22개 동 65세 이상 1인세대 많은 순으로 표 좀 급하게 부탁드립니다"
    card = DeskCard(
        act="ask", topics=("solo_seniors",), region_op="set", region="강남구", rank=True
    )
    s = AssistantSettings(doc_dir=str(tmp_path))
    e = Engine(FakeDesk({q: card}), TemplateWriter(), JsonDongData(), MemoryStore(), s)
    e.start("s", Profile(member_region="강남구"))
    r = e.turn("s", q)
    rows = [x for x in r.text.splitlines() if x.startswith("| ") and "동 |" not in x[:6]]
    assert sum(1 for x in rows if "동" in x.split("|")[1]) >= 22, r.text[-800:]
