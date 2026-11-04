"""지역에 없는 자료는 동을 되묻거나 표를 만들기 전에 알린다."""

import pytest

from src.assistant.data_source import JsonDongData
from src.assistant.policy import preflight
from src.assistant.slots import DeskCard
from src.assistant.state import apply_card, new_state


@pytest.mark.parametrize(
    "topic,region,available",
    [
        ("bus", "강남구", "춘천시"),
        ("seoul_lonely", "춘천시", "강남구"),
    ],
)
@pytest.mark.parametrize("extra", [{}, {"rank": True}, {"fmt": "엑셀"}])
def test_unavailable_region_does_not_ask_for_a_dong(topic, region, available, extra):
    card = DeskCard(act="ask", topics=(topic,), region_op="set", region=region, **extra)
    plan = preflight(apply_card(new_state(), card), card, JsonDongData())
    assert plan.kind == "coverage"
    assert region in plan.message and available in plan.message
    assert plan.pending is None
    assert "어느 동" not in plan.message


@pytest.mark.parametrize("region", ["춘천시", None])
def test_bus_still_asks_for_location_when_it_can_help(region):
    card = DeskCard(
        act="ask", topics=("bus",), region_op="set" if region else "keep", region=region or ""
    )
    plan = preflight(apply_card(new_state(), card), card, JsonDongData())
    assert plan.kind == "ask_slot" and plan.pending == "dong"


def test_mixed_topics_do_not_block_available_data():
    card = DeskCard(act="ask", topics=("bus", "youth"), region_op="set", region="강남구")
    plan = preflight(apply_card(new_state(), card), card, JsonDongData())
    assert plan.kind == "ask_slot" and plan.pending == "dong"


def test_existing_dong_still_uses_coverage_message():
    card = DeskCard(act="ask", topics=("bus",), dong_op="set", dong_mentions=("수서동",))
    plan = preflight(apply_card(new_state(), card), card, JsonDongData())
    assert plan.kind == "coverage" and "수서동" in plan.message
