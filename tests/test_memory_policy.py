from src.assistant import memory
from src.assistant.data_source import JsonDongData
from src.assistant.desk import vote
from src.assistant.policy import (
    OUT_OF_SCOPE,
    OUT_OF_SCOPE_ASK,
    PERSON,
    josa,
    pick_alternatives,
    preflight,
    suggestion_sentence,
)
from src.assistant.slots import DeskCard
from src.assistant.state import Applied, apply_card, new_state

DATA = JsonDongData()


def test_fold_facts_dedup_and_keep_head_tail():
    facts = memory.fold_facts((), tuple(f"사실{i}" for i in range(40)), head=3, tail=4)
    assert facts == ("사실0", "사실1", "사실2", "사실36", "사실37", "사실38", "사실39")
    again = memory.fold_facts(facts, ("사실 0", "새것"), head=3, tail=4)
    assert again[-1] == "새것" and again.count("사실0") == 1  # 띄어쓰기만 다른 것은 같은 사실


def test_note_dongs_recent_first_and_capped():
    seen = ()
    for t, d in enumerate(["수서동", "북산면", "수서동"] + [f"동{i}" for i in range(10)]):
        seen = memory.note_dongs(seen, (d,), t)
    assert len(seen) == memory.DONG_KEEP and seen[0][0] == "동9"


def test_render_order_facts_first_question_last():
    st = new_state().model_copy(
        update={"facts": ("수서동 주민센터 담당",), "last_question": "어느 동?"}
    )
    text = memory.render(st)
    assert (
        text.index("확인된 사실") < text.index("지금 정해진 칸") < text.index("방금 내가 물은 것")
    )


def _plan(card: DeskCard, st=None):
    st = st or new_state()
    return preflight(apply_card(st, card), card, DATA)


def test_out_of_scope_uses_team_lead_sentence_and_catalog_suggestions():
    p = _plan(DeskCard(act="out_of_scope", suggest=("youth",)))
    # 10-27 팀장: 권유 문장 대신 '다른 질문을 말씀해주실 수 있나요?'
    assert p.message == f"{OUT_OF_SCOPE} {OUT_OF_SCOPE_ASK}"
    assert "찾아보시는" not in p.message
    assert p.suggest and all(t in ("youth", "priority", "dong_overview") for t in p.suggest)


def test_blocked_person_and_emergency():
    assert _plan(DeskCard(act="blocked", block="person")).message.startswith(PERSON)
    assert "119" in _plan(DeskCard(act="blocked", block="emergency")).message


def test_not_connected_is_not_out_of_scope(not_ready):
    p = _plan(DeskCard(act="ask", topics=(not_ready[0],)))
    assert p.kind == "not_connected" and OUT_OF_SCOPE not in p.message


def test_ask_one_missing_slot():
    p = _plan(DeskCard(act="ask", topics=("youth",)))
    assert p.kind == "ask_slot" and p.pending == "dong"


def test_coverage_mismatch_explained():
    # 【판단】 10-13: 경로당은 두 지역이 됐다. 강남만 있는 서울시 독거노인 현황으로 본다
    c = DeskCard(act="ask", topics=("seoul_lonely",), dong_op="set", dong_mentions=("북산면",))
    p = _plan(c)
    assert p.kind == "coverage" and "강남구" in p.message


def test_unknown_dong_asks_back():
    c = DeskCard(act="ask", topics=("youth",), dong_op="set", dong_mentions=("판교동",))
    p = _plan(c)
    assert p.kind == "unknown_dong" and "판교동" in p.message


def test_josa():
    assert josa("수서동", "을", "를") == "수서동을"
    assert josa("청년", "이나", "나") == "청년이나"
    assert josa("경로당", "은", "는") == "경로당은"
    assert josa("사는 집", "을", "를") == "사는 집을"


def test_vote_majority_and_conservative_tie():
    a = DeskCard(act="ask", topics=("youth",), dong_op="set", dong_mentions=("수서동",))
    b = DeskCard(act="ask", topics=("youth",), dong_op="set", dong_mentions=("수서동",))
    c = DeskCard(act="out_of_scope")
    v = vote([a, b, c])
    assert v.act == "ask" and v.dong_mentions == ("수서동",)
    tie = vote([DeskCard(act="ask"), DeskCard(act="unclear")])
    assert tie.act == "unclear"  # 표가 갈리면 되묻기 쪽


def test_vote_no_majority_keeps_slot():
    cards = [
        DeskCard(act="ask", dong_op="set", dong_mentions=(d,)) for d in ("수서동", "북산면", "교동")
    ]
    assert vote(cards).dong_op == "keep"


def test_applied_type():
    assert isinstance(apply_card(new_state(), DeskCard()), Applied)


def test_suggestion_uses_short_names_and_josa():
    st = apply_card(
        new_state(), DeskCard(act="ask", dong_op="set", dong_mentions=("수서동",))
    ).state
    # 10-27: 범위 밖 답은 권유 대신 '다른 질문을' 물음 — 권유 문장(다른 지역 · 연결 전)은 따로 잼
    msg = suggestion_sentence(st, pick_alternatives(st))
    assert "한눈에를" not in msg and "수서동 동 상황이나" in msg
    assert josa("먼저 볼 동(취약 돌보미 동 순위)", "을", "를").endswith(")을")


def test_old_notes_stay_visible():
    from src.assistant.state import LogEntry

    log = (LogEntry(turn=1, topic="priority", note="강남구 1위 개포3동 · 3위 논현2동"),) + tuple(
        LogEntry(turn=i, topic="youth", dongs=("수서동",)) for i in range(2, 40)
    )
    text = memory.render(new_state().model_copy(update={"log": log}))
    assert "3위 논현2동" in text
