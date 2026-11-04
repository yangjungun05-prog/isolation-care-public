"""'○○라고 써도 되죠?' 규칙은 그 말을 했을 때만(10-15, 문제 목록 1-7).

시스템 지시문에 규칙을 넣었더니 갈 곳 30 T20 '춘천 노인복지관은 전부 몇 곳이에요?'에
'아니요, … 나와 있지 않아요. 다만 4곳'(앞뒤 안 맞음)이 나왔다(A/B: 규칙 있음 3/4 · 없음 4/4).
그래서 코드가 그 말을 알아볼 때만 그 턴의 [참고]에 붙인다.
"""

from src.assistant import writer
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots
from src.assistant.writer import ClaudeWriter

FACTS = [gather("priority", Slots(region="강남구"), JsonDongData())]


def _user(said: str) -> str:
    kw, _, _ = ClaudeWriter(AssistantSettings())._request("개포3동 순위 확인", FACTS, said)
    return kw["messages"][0]["content"]


def test_rule_is_not_in_the_system_prompt():
    assert "써도 되죠" not in writer.WRITER_SYSTEM


def test_note_only_when_asked_to_write_it():
    asked = "그럼 '개포3동, 강남 위험 순위 1위'라고만 써도 되죠?"
    assert writer.WRITE_OK_NOTE in _user(asked)
    assert writer.WRITE_OK_NOTE in _user("이 문장 그대로 기사에 적어도 되나요?")
    assert writer.WRITE_OK_NOTE not in _user("춘천 노인복지관은 전부 몇 곳이에요?")
    assert writer.WRITE_OK_NOTE not in _user("개포3동이 1위 맞죠?")
