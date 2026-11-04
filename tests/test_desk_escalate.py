from src.assistant.config import AssistantSettings
from src.assistant.desk import ClaudeDesk
from src.assistant.slots import DeskCard
from src.assistant.state import new_state


class ScriptedDesk(ClaudeDesk):
    """API 대신 정해 둔 카드를 차례로 낸다(묻는 횟수를 센다)."""

    def __init__(self, cards):
        super().__init__(AssistantSettings(desk_votes=3, desk_escalate=True, desk_race=False))
        self.cards = list(cards)
        self.asked = 0

    def _one(self, user):
        self.asked += 1
        return self.cards.pop(0)


def test_confident_first_answer_asks_once():
    d = ScriptedDesk([DeskCard(act="ask", topics=("youth",))])
    assert d.read(new_state(), "수서동 청년").act == "ask"
    assert d.asked == 1 and d.escalations == 0


def test_risky_first_answer_escalates_to_vote():
    d = ScriptedDesk(
        [
            DeskCard(act="out_of_scope"),
            DeskCard(act="ask", topics=("youth",)),
            DeskCard(act="ask", topics=("youth",)),
        ]
    )
    card = d.read(new_state(), "거기 청년은")
    assert d.asked == 3 and d.escalations == 1
    assert card.act == "ask"  # 다수결이 첫 판단(범위 밖)을 바로잡는다


class RaceDesk(ClaudeDesk):
    """3번을 같이 보내는 방식 — 카드마다 걸리는 시간을 정해 둔다."""

    def __init__(self, timed_cards):
        super().__init__(AssistantSettings(desk_votes=3, desk_escalate=True, desk_race=True))
        self.timed = list(timed_cards)
        self.lock = __import__("threading").Lock()

    def _one(self, user):
        with self.lock:
            sec, card = self.timed.pop(0)
        __import__("time").sleep(sec)
        return card


def test_race_returns_first_clear_card_without_waiting():
    # 【기능】 3번을 한꺼번에 보내고, 먼저 온 카드가 분명하면 나머지를 기다리지 않는다
    import time

    d = RaceDesk(
        [
            (0.05, DeskCard(act="ask", topics=("youth",))),
            (1.0, DeskCard(act="out_of_scope")),
            (1.0, DeskCard(act="out_of_scope")),
        ]
    )
    t0 = time.time()
    card = d.read(new_state(), "수서동 청년")
    assert card.act == "ask" and d.escalations == 0 and time.time() - t0 < 0.5


def test_race_waits_for_all_when_first_is_risky():
    d = RaceDesk(
        [
            (0.01, DeskCard(act="out_of_scope")),
            (0.05, DeskCard(act="ask", topics=("youth",))),
            (0.05, DeskCard(act="ask", topics=("youth",))),
        ]
    )
    card = d.read(new_state(), "거기 청년은")
    assert card.act == "ask" and d.escalations == 1  # 세 장 다수결
