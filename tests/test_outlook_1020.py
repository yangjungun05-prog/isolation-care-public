"""10-20 취약 돌보미 판단(outlook) — 조건 창고 · 겹침 · 예외(API 없이).

10-20 팀장: "수서동의 노인분들이 잘 지내니? … 근거가 있어야해" · "최소 5겹 이상으로 변수 통제".
"""

from datetime import date, timedelta

import pytest

from src.assistant import conditions as C
from src.assistant import forecast as fc
from src.assistant import librarian
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.dongname import DONGS
from src.assistant.slots import DeskCard, Slots
from src.assistant.state import apply_card, new_state
from src.assistant.writer import OUTLOOK_SYSTEM, ClaudeWriter

DATA = JsonDongData()
COLD = date(2025, 12, 31)  # 한파 · 지난 이레에도 기준 넘은 날
RAIN = date(2025, 7, 16)  # 폭우(서울 73.1mm)
ALL = [n for r in DONGS for n in DONGS[r]]


@pytest.mark.parametrize("target", ["어르신", "청년"])
@pytest.mark.parametrize("day", [COLD, RAIN, date(2025, 10, 1)])
def test_every_dong_sheet_is_sound(target, day):
    for name in ALL:
        s = C.sheet(name, target, DATA, as_of=day)
        assert s is not None
        # 최소 5겹(10-20 팀장) — 자료가 있으면 늘 다섯 겹 넘게 살핀다
        assert len(s.checked) >= 5, (name, target, s.checked, s.missing)
        letters = [c.letter for c in s.conds if c.letter]
        assert len(letters) == len(set(letters))
        assert all(c.letter for c in s.hits)
        for p in s.patterns:
            assert len(p.layers()) >= 3, (name, p.key)
            assert all(c.hit for c in p.conds)
        text = "\n".join(C.facts_lines(s))
        assert "—" not in text and "None" not in text and "nan" not in text
        assert s.verdict().startswith(f"{day.isoformat()} 기준 ")


def test_meaning_names_only_matched_conditions():
    # 10-20 r0: 수서동은 계단 집 0 · 약한 지붕 0인데 뜻 문장에 '계단 집 · 약한 지붕'이 나갔다
    s = C.sheet("수서동", "어르신", DATA, as_of=COLD)
    cold = next(p for p in s.patterns if p.key == "cold")
    assert s.get("walkup").hit is False and s.get("roof").hit is False
    assert "계단 집" not in cold.meaning and "약한 지붕" not in cold.meaning
    assert "비탈" in cold.meaning


def test_this_week_patterns_come_first():
    s = C.sheet("수서동", "어르신", DATA, as_of=COLD)
    assert any(c.key == "ahead" for c in s.patterns[0].conds)


def test_rain_day_sees_rain_and_dated_words():
    s = C.sheet("역삼1동", "어르신", DATA, as_of=RAIN)
    ahead = s.get("ahead")
    assert ahead.hit and "폭우" in ahead.kinds and ahead.label.startswith("그날부터")
    assert s.get("past").label.startswith("그날 앞")
    assert any(p.key == "rain" for p in s.patterns)


def test_forecast_failure_is_said_not_hidden():
    # conftest 가 기상청을 막는다(진짜 오늘) — '앞으로 날씨'를 확인 못 했다고 밝힌다
    s = C.sheet("수서동", "어르신", DATA)
    assert any("앞으로 날씨" in m for m in s.missing)
    assert s.get("ahead") is None
    assert "확인하지 못한 겹: 앞으로 날씨" in "\n".join(C.facts_lines(s))


class _Wx:
    def __init__(self, rain):
        self.rain = rain

    def forecast(self, grids):
        d = fc.today_kst()
        days = {
            (d + timedelta(days=i)).isoformat(): {
                "tmin": 5.0,
                "tmax": 20.0,
                "rain": self.rain,
                "snow": 0.0,
                "pop": 80,
            }
            for i in range(3)
        }
        return {n: days for n in grids}, f"{d.isoformat()} 05:00"


def test_live_forecast_turns_rain_on(monkeypatch):
    monkeypatch.setattr(librarian, "WX", _Wx(60.0))
    s = C.sheet("역삼1동", "어르신", DATA)
    assert s.get("ahead").hit and s.get("ahead").label.startswith("오늘부터")
    assert "기상청 단기예보" in s.get("ahead").value
    assert not s.verdict().startswith("2")  # 오늘이면 '○○ 기준'을 붙이지 않는다


class _NoHoliday:
    def __init__(self, data):
        self.d = data

    def holidays(self):
        return {"2019-01-01": "1월1일"}

    def __getattr__(self, k):
        return getattr(self.d, k)


def test_missing_holiday_year_is_said():
    s = C.sheet("수서동", "어르신", _NoHoliday(DATA), as_of=COLD)
    assert any(m.startswith("달력") for m in s.missing)


def test_small_youth_is_not_compared():
    small = [n for n in ALL if (DATA.people()["dongs"][n].get("pop_youth") or 0) < C.MIN_YOUTH]
    for n in small:
        s = C.sheet(n, "청년", DATA, as_of=COLD)
        assert s.get("yshare").place == "" and not s.get("yshare").hit
        assert any("견주지 않음" in x for x in s.notes)


def test_region_lines_count_and_wording():
    lines = C.region_lines("춘천시", "어르신", DATA, COLD)
    assert lines[0].startswith("춘천시 어르신 취약 돌보미 판단: 25곳 중")
    assert "취약 돌보미 동 순위와는 다른 것" in lines[0] and "먼저 볼 동" not in lines[0]
    tops = C.region_top("춘천시", "어르신", DATA, COLD)
    for name in tops[:5]:
        assert any(x.startswith(f"{name}: 겹친 걱정") for x in lines)


def _slots(**kw):
    return Slots(**{"region": "강남구", **kw})


def test_gather_outlook_both_targets_and_compare():
    librarian.AS_OF = COLD.isoformat()
    try:
        f = librarian.gather("outlook", _slots(dongs=("수서동", "역삼1동"), target="어르신"), DATA)
    finally:
        librarian.AS_OF = "live"
    assert f.style == "outlook"
    assert "[강남구 수서동 어르신]" in f.lines and "[강남구 역삼1동 어르신]" in f.lines
    assert any(x.startswith("견줌(겹친 걱정 수 · 해당 조건 수): ") for x in f.lines)
    f2 = librarian.gather("outlook", _slots(dongs=("효자2동",)), DATA)
    assert "[춘천시 효자2동 어르신]" in f2.lines and "[춘천시 효자2동 청년]" in f2.lines


def test_period_past_and_far(monkeypatch):
    f = librarian.gather("outlook", _slots(dongs=("개포1동",), period="7월 16일"), DATA)
    assert any("을 오늘로 보고" in n for n in f.notes)
    assert any(
        x.endswith("취약 돌보미 판단: 세 겹 넘게 겹친 걱정은 없음. 따로따로 해당하는 조건 3가지")
        or "기준 강남구 개포1동" in x
        for x in f.lines
    )
    f2 = librarian.gather("outlook", _slots(dongs=("대치1동",), period="내년 여름"), DATA)
    assert any("날짜로 읽을 수 없어" in n for n in f2.notes)


def test_outlook_period_lasts_one_turn():
    st = new_state()
    c1 = DeskCard(
        act="ask",
        topics=("outlook",),
        dong_op="set",
        dong_mentions=("개포1동",),
        period_op="set",
        period="7월 16일",
    )
    st = apply_card(st, c1, "7월 16일 폭우 때 개포1동 어르신들은?").state
    assert st.slots.period == "7월 16일"
    c2 = DeskCard(act="ask", topics=("outlook",), dong_op="set", dong_mentions=("대치1동",))
    st = apply_card(st, c2, "대치1동 어르신들 괜찮으실까요?").state
    assert st.slots.period is None


def test_region_outlook_with_dong_topic_uses_top_dongs():
    librarian.AS_OF = COLD.isoformat()
    try:
        facts = librarian.gather_all(("outlook", "senior_hall"), _slots(target="어르신"), DATA)
    finally:
        librarian.AS_OF = "live"
    halls = facts[1]
    assert halls.lines, "경로당 주제가 비면 '자료가 비어 있다'는 틀린 말이 나간다(10-20 r1 T9)"
    tops = C.region_top("강남구", "어르신", DATA, COLD)[: librarian.MAX_DONGS]
    assert all(f"[강남구 {n}]" in halls.lines for n in tops)


def test_writer_uses_outlook_prompt():
    s = AssistantSettings(anthropic_api_key="x")
    w = ClaudeWriter(s)
    f = librarian.gather("outlook", _slots(dongs=("수서동",), target="어르신"), DATA)
    kw, allowed, _ = w._request("수서동 어르신들 잘 지내?", [f])
    assert kw["system"][0]["text"] == OUTLOOK_SYSTEM
    assert "조건 A" in allowed
