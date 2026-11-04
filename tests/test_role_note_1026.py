"""'틀리면 책임은 누가 져요?'에는 비서의 역할 한 문장을 붙인다(10-26 팀장 '추천하는대로')."""

from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import ROLE_ASK, ROLE_NOTE, Engine
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter


def test_role_question_gets_the_role_sentence():
    say = "그 판단이 틀렸던 적은 없어요? 틀리면 책임은 누가 져요?"
    desk = FakeDesk({say: DeskCard(act="ask", topics=("sources",))})
    e = Engine(
        desk,
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        AssistantSettings(anthropic_api_key=""),
    )
    e.start("s", Profile(member_region="강남구"))
    r = e.turn("s", say)
    assert r.kind == "answer" and ROLE_NOTE in r.text


def test_plain_questions_do_not_match():
    assert ROLE_ASK.search("틀리면 책임은 누가 져요?")
    assert not ROLE_ASK.search("수서동 혼자 사는 어르신 몇 명이에요?")
    assert not ROLE_ASK.search("책임 있는 기관 연락처 알려줘")
