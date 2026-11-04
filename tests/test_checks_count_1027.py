"""답 검문소 둘(10-27 API 길 첫 실응답 시험에서 본 것).

- village_6 T3: 자료 '[모두 맞는 마을] 모두 10곳 — 그중 위 5곳만 적음'을 글쓴이가 '10곳 중 5곳'으로
  옮김
- fix_check_2 T2(api1027b): 요일을 묻지 않았는데 직전 답을 보고 '일요일 기준 자료는 없어요'라고 씀
"""

from src.assistant import checks
from src.assistant.writer import fix_note

FACTS_ALL = (
    "[여러 조건 계산] 춘천시 읍 · 면 1곳의 마을(법정 리) 10곳, 조건 1가지\n"
    "[모두 맞는 마을] 모두 10곳 — 그중 위 5곳만 적음: 사북면 지암리 · 사북면 원평리\n"
    "[사북면 지암리] 일요일에 문 연 약국까지 거리(마을 가운데에서 직선) 13.5km"
)


def test_all_n_written_as_part_is_caught():
    bad = "사북면에서 일요일에 문 연 약국까지 5km 이상 먼 마을은 10곳 중 5곳이에요."
    assert checks.miscounted_all(bad, FACTS_ALL) == ["10곳 중 5곳"]
    assert any(
        x.startswith("맞는 곳 수 틀림")
        for x in checks.problems(bad, FACTS_ALL, [], facts_text=FACTS_ALL)
    )
    assert "N곳 모두" in fix_note(["맞는 곳 수 틀림 10곳 중 5곳"])


def test_all_n_written_right_passes():
    good = "사북면의 마을 10곳이 모두 5km를 넘어요. 먼 순으로 위 5곳만 적으면 지암리 13.5km …"
    assert checks.miscounted_all(good, FACTS_ALL) == []
    # '22곳 가운데 … 2곳'처럼 붙어 있지 않은 말, 자료의 '모두' 수와 다른 수는 건드리지 않는다
    assert checks.miscounted_all("22곳 가운데 5km 넘게 먼 마을은 2곳이에요", "모두 2곳") == []
    assert checks.miscounted_all("25곳 중 9곳이 기준을 넘어요", FACTS_ALL) == []


def test_weekday_denial_with_pharmacy_facts_is_caught():
    facts = "[신북읍] 10월 27일(화)에 문 연 약국까지 거리: 용산리 4.8km · 지내리 4.3km"
    bad = "일요일 기준 자료는 없어요. 두 약국 모두 일요일에는 쉬어요. 10월 27일(화) 기준으로는 …"
    assert checks.weekday_denial(bad, facts) == ["일요일 기준 자료는 없"]
    assert any(
        x.startswith("요일 자료 있는데") for x in checks.problems(bad, facts, [], facts_text=facts)
    )


def test_weekday_denial_without_pharmacy_facts_is_ignored():
    facts = "[수서동] 혼자 사는 65세 이상 2,543명(주민등록 2026-09)"
    assert checks.weekday_denial("일요일 자료는 없어요.", facts) == []
