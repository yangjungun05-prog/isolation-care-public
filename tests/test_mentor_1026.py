"""멘토 답(10-26 공유, 10-21 질문)을 반영한 것.

1. 자료가 있는지는 코드가 상태값(있음 · 일부 · 없음)으로 정해 글쓴이에게 넘긴다.
"""

from src.assistant import checks
from src.assistant.librarian import Facts
from src.assistant.writer import LEAD_SYSTEM, OUTLOOK_SYSTEM, WRITER_SYSTEM


def test_status_is_decided_by_code():
    assert Facts(title="갈 곳", lines=["[강남구 수서동]", "경로당 12곳"]).status == "있음"
    # 시설이 0곳인 것은 사실이라 '없음'이 아니다
    assert Facts(title="갈 곳", lines=["약국: 동 안에 없음. 가까운 약국 …"]).status == "있음"
    part = Facts(title="지원 기관", lines=["강남구보건소 02-…", "(주소 · 전화는 이 자료에 없음)"])
    assert part.status == "일부"
    none = Facts(title="버스", lines=["[강남구 수서동]", "강남구 버스 노선은 자료에 없어요"])
    assert none.status == "없음"
    assert Facts(title="빈 묶음").status == "없음"


def test_writer_gets_the_status_and_the_rule():
    from src.assistant.config import AssistantSettings
    from src.assistant.writer import ClaudeWriter

    w = ClaudeWriter(AssistantSettings())
    kw, _, _ = w._request("수서동 경로당 몇 곳?", [Facts(title="갈 곳", lines=["경로당 12곳"])])
    user = kw["messages"][0]["content"]
    assert "## 갈 곳 (자료 상태: 있음)" in user
    for system in (WRITER_SYSTEM, OUTLOOK_SYSTEM, LEAD_SYSTEM):
        assert "'자료 상태'" in system and "'있음'이면" in system


def test_status_tag_never_reaches_the_user():
    said = "수서동 경로당은 12곳이에요(자료 상태: 있음)."
    assert checks.tidy(said) == "수서동 경로당은 12곳이에요."


def test_fallback_is_short_and_on_the_asked_words():
    # 세라핀 T8 · T9: 기본 답이 1,511 ~ 1,799자 — 물은 말과 겹치는 줄만 여섯 줄까지
    from src.assistant.writer import SHORT_LINES, short_answer

    lines = ["[강남구 수서동]"] + [f"말뜻 — 낱말{i}: 설명 {i}" for i in range(20)]
    lines += ["경로당 12곳(2025-12 기준)", "약국 3곳"]
    f = Facts(
        title="자료 설명 · 출처",
        lines=lines,
        notes=[
            "모든 값은 동 단위 공개 자료",
            "두 지역을 견주는 물음이면 몫만 쓰고 동 목록은 적지 않는다",
        ],
    )
    out = short_answer([f], "수서동 경로당은 몇 곳이에요?")
    assert "경로당 12곳" in out and "[강남구 수서동]" in out
    assert "낱말3" not in out and len(out) < 300
    assert "적지 않는다" not in out  # 글쓴이에게만 주는 지시문은 내보내지 않는다
    # 겹치는 말이 없으면 앞에서부터 여섯 줄까지
    out2 = short_answer([f], "그래서요?")
    assert sum(1 for x in out2.splitlines() if x.startswith("·")) <= SHORT_LINES + 1
    assert "좁혀 물어봐 주세요" in out2


def test_consistency_counts_same_answers_across_runs():
    # 멘토 답 4: 같은 시험지를 세 번 — '모두 같은 답 비율'과 핵심 턴(has 있음) 비율
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "evals" / "consistency.py"
    spec = importlib.util.spec_from_file_location("consistency", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def run(reply2: str, ok2: bool) -> dict:
        rows = [
            {
                "turn": 1,
                "say": "수서동 혼자 사는 어르신 몇 명?",
                "expect": {"has": ["2,471"]},
                "kind": "answer",
                "topics": ["solo_seniors"],
                "reply": "2,471명이에요.",
                "ok": {"all": True},
            },
            {
                "turn": 2,
                "say": "경로당은?",
                "expect": {},
                "kind": "answer",
                "topics": ["senior_hall"],
                "reply": reply2,
                "ok": {"all": ok2},
            },
        ]
        return {"scenario": "t", "score": {"all": 1 + ok2}, "rows": rows}

    out = mod.compare(
        [run("12곳이에요.", True), run("12곳이에요.", True), run("자료에 없어요.", False)]
    )
    assert out["turns"] == 2 and out["core_turns"] == 1 and out["core_same_pct"] == 100.0
    assert out["same_judge_pct"] == 50.0 and out["all_ok_pct"] == 50.0
    assert [d["turn"] for d in out["differ"]] == [2]


# ── 자료 줄 번호 · 쓴 줄(멘토 답 1, ⑥) ──


def _two_dongs():
    return [
        Facts(
            title="혼자 사는 어르신",
            lines=[
                "[강남구 수서동]",
                "65세 이상 1인세대 2,471명",
                "[강남구 개포3동]",
                "65세 이상 1인세대 1,082명",
            ],
        )
    ]


def test_lines_get_ids_and_heads():
    from src.assistant.writer import number_facts

    text, ids = number_facts(_two_dongs())
    assert "F1) 65세 이상 1인세대 2,471명" in text and "F2) 65세 이상 1인세대 1,082명" in text
    assert "[강남구 수서동]" in text and "F" not in text.splitlines()[1]  # 머리줄은 번호 없음
    assert ids["F2"] == ("65세 이상 1인세대 1,082명", "[강남구 개포3동]")


def test_basis_line_is_split_off_and_ids_never_shown():
    from src.assistant.writer import split_basis

    body, cited = split_basis("수서동은 2,471명이에요(F1).\n근거: F1")
    assert body == "수서동은 2,471명이에요." and cited == ["F1"]
    assert split_basis("수서동은 2,471명이에요.") == ("수서동은 2,471명이에요.", None)
    assert checks.tidy("F1) 수서동은 2,471명이에요.\n근거: F1, F2") == "수서동은 2,471명이에요."


def test_number_from_another_dong_is_caught():
    from src.assistant.writer import misattributed, number_facts

    _, ids = number_facts(_two_dongs())
    # 수서동 줄(F1)을 인용하고 개포3동 숫자를 수서동 숫자처럼 씀
    assert misattributed("수서동은 1,082명이에요.", ["F1"], ids, "") == ["다른 동 숫자 1082"]
    # 맞게 쓰면 없음 · 인용을 빼먹으면 걸지 않음(기록만) · 질문에 있던 숫자는 됨
    assert misattributed("수서동은 2,471명이에요.", ["F1"], ids, "") == []
    assert misattributed("수서동은 1,082명이에요.", None, ids, "") == []
    assert misattributed("수서동은 1,082명이에요.", ["F1"], ids, "1,082명 맞죠?") == []


def test_stream_gate_hides_the_basis_line():
    from src.assistant.writer import StreamGate

    allowed = "65세 이상 1인세대 2,471명"
    gate = StreamGate(allowed, [])
    shown = gate.feed("수서동은 2,471명이에요.\n") + gate.feed("근거: F1\n") + gate.flush()
    assert "".join(shown).strip() == "수서동은 2,471명이에요." and gate.basis == "근거: F1"
    assert gate.ok


# ── 주제 구출 규칙 표(멘토 답 3, ⑦) ──


def test_rescues_are_one_ordered_table():
    from src.assistant import policy
    from src.assistant.slots import DeskCard

    names = [r.name for r in policy.RESCUES]
    assert names == [
        "혼자 사는 어르신",  # 10-28 재심사 q08_a
        "약국",
        "보건 시설",
        "지붕",
        "보고서 쓰는 법",
        "지역 시설",
        "누구부터",
        "연휴",
        "연락처",
    ]
    policy.RESCUE_HITS.clear()
    # 범위 밖으로 낸 지붕 물음 → 집 주제 더함, 몇 번 걸렸는지 센다
    c = policy.rescue_topics(DeskCard(act="out_of_scope"), "슬레이트 지붕 집이 몇 채나 됩니까")
    assert c.act == "ask" and c.topics == ("housing",) and policy.RESCUE_HITS == {"지붕": 1}
    # 사람 하나를 가리키는 연락처 물음은 지원 기관으로 되살리지 않는다
    c = policy.rescue_topics(DeskCard(act="unclear"), "그분 연락처 알려줘")
    assert c.act == "unclear"
    # 비서를 바꿔 달라는 말도
    assert (
        policy.rescue_topics(DeskCard(act="unclear"), "너 말고 사람 담당자 번호").act == "unclear"
    )


# ── 같은 입력이면 그날 같은 답(멘토 답 4, ⑩) ──


def test_same_input_same_day_reuses_the_answer(monkeypatch):
    from types import SimpleNamespace

    from src.assistant import writer as W
    from src.assistant.config import AssistantSettings

    calls = []

    def fake_call(key, usage, **kw):
        calls.append(kw)
        text = "수서동 경로당은 12곳이에요.\n근거: F1"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="x")

    monkeypatch.setattr(W.llm, "call", fake_call)
    w = W.ClaudeWriter(AssistantSettings())
    facts = [Facts(title="경로당", lines=["[강남구 수서동]", "경로당 12곳"])]
    a = w.write("수서동 경로당 몇 곳?", facts)
    b = w.write("수서동 경로당 몇 곳?", facts)
    assert a == b == "수서동 경로당은 12곳이에요." and len(calls) == 1 and w.last.cited == ["F1"]
    # 자료가 바뀌면(새 판) 다시 묻는다
    n = len(calls)
    new_facts = [Facts(title="경로당", lines=["[강남구 수서동]", "경로당 13곳"])]
    w.write("수서동 경로당 몇 곳?", new_facts)
    assert len(calls) > n
    # 끄면(0) 기억하지 않는다
    off = W.ClaudeWriter(AssistantSettings(reply_cache=0))
    n = len(calls)
    off.write("수서동 경로당 몇 곳?", facts)
    off.write("수서동 경로당 몇 곳?", facts)
    assert len(calls) == n + 2


def test_day_cache_keeps_the_newest():
    from src.assistant.reply_cache import DayCache

    c = DayCache(2)
    for i in range(3):
        c.put(c.key(i), i)
    assert c.get(c.key(0)) is None and c.get(c.key(2)) == 2 and c.hits == 1


# ── 물은 조건에 맞는 값(10-26 측정 rules_v6_16 T4) ──


def test_line_matching_the_asked_sex_is_marked():
    from src.assistant import librarian
    from src.assistant.data_source import JsonDongData
    from src.assistant.slots import Slots

    s = Slots(region="강남구", dongs=("수서동",), sex="남")
    fs = librarian.gather_all(
        ("solo_seniors",), s, JsonDongData(), "수서동 혼자 사는 할아버지 몇 명"
    )
    marked = [x for f in fs for x in f.lines if librarian.ASKED_MARK in x]
    assert len(marked) == 1 and "남성(할아버지)" in marked[0] and "1,548" in marked[0]
    # 물은 조건이 없으면 표시하지 않는다
    plain = librarian.gather_all(
        ("solo_seniors",),
        Slots(region="강남구", dongs=("수서동",)),
        JsonDongData(),
        "수서동 혼자 사는 어르신",
    )
    assert not any(librarian.ASKED_MARK in x for f in plain for x in f.lines)
    from src.assistant.writer import WRITER_SYSTEM

    assert "'물은 조건에 맞는 값'" in WRITER_SYSTEM
