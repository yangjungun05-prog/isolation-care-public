"""10-20 취약 돌보미 판단의 근거 줄은 코드가 붙인다(outlook_text) — 글쓴이가 다시 쓰다 틀린 것을 막는다."""  # noqa: E501

from src.assistant import librarian
from src.assistant import outlook_text as O
from src.assistant.data_source import JsonDongData
from src.assistant.slots import Slots
from src.assistant.writer import TemplateWriter

DATA = JsonDongData()


def _f(**kw):
    librarian.AS_OF = "2025-12-31"
    try:
        return librarian.gather("outlook", Slots(**{"region": "강남구", **kw}), DATA)
    finally:
        librarian.AS_OF = "live"


def test_render_keeps_every_condition_and_letter():
    f = _f(dongs=("수서동",), target="어르신")
    text = O.render([f], "수서동 어르신들 잘 지내? 근거도 보여 줘")
    conds = [x for x in f.lines if x.startswith("해당 조건 ")]
    for x in conds:
        letter = x.split(":")[0].replace("해당 조건 ", "")
        assert f"· 조건 {letter}: " in text
    assert text.count("겹침: ") == sum(1 for x in f.lines if x.startswith("겹침 "))
    assert "살펴본 겹 " in text and "괜찮은 쪽: " in text
    assert text.endswith("이 자료로 알 수 없어요.")
    assert "[사람]" not in text  # 겹 이름 꼬리표는 뗀다


def test_focus_follow_up_keeps_first_pattern_only():
    f = _f(dongs=("수서동",), target="어르신")
    first = O.render([f], "수서동 어르신들 이번 주 괜찮을까? 근거도")
    assert first.count("겹침: ") == 2  # 첫 질문은 '이번 주'가 있어도 근거를 다 보인다
    # 10-27 처음엔 접기: 이어 묻는 말도 근거를 바랄 때만 펼친다(펼치면 첫 겹침만)
    assert O.render([f], "그중 이번 주에 제일 걱정되는 건?", before=first) == O.BRIEF_TAIL
    text = O.render([f], "그중 이번 주에 제일 걱정되는 건 왜 그래?", before=first)
    assert text.count("겹침: ") == 1 and "앞으로 사흘 날씨와 겹침" in text
    assert "괜찮은 쪽" not in text


def test_two_regions_compare_with_code_counted_shares():
    f = _f(target="어르신", compare=True)
    assert "[강남구 어르신 전체]" in f.lines and "[춘천시 어르신 전체]" in f.lines
    line = next(x for x in f.lines if x.startswith("견줌(겹친 걱정이 있는 동 몫): "))
    assert "강남구 어르신 22곳 중" in line and "춘천시 어르신 25곳 중" in line
    text = O.render([f], "강남이랑 춘천 중 어디가 더 힘들까? 근거도")
    assert "· 견줌(" in text and "조건 A" not in text


def test_template_writer_gives_verdict_and_evidence():
    f = _f(dongs=("역삼1동",), target="어르신")
    text = TemplateWriter().write("q", [f], said="역삼1동 어르신 괜찮아? 근거도 보여 줘")
    # 되감기(.env AS_OF)만이면 '○○ 기준'을 붙이지 않는다(사용자가 지난 날을 말했을 때만)
    assert text.splitlines()[0].startswith("강남구 역삼1동 어르신 취약 돌보미 판단")
    assert "· 조건 A: " in text


def test_region_holiday_line_has_no_empty_value():
    f = _f(target="어르신")
    assert not any("(없음)" in x for x in f.lines)


def test_sub_dong_unit_is_disclosed(monkeypatch):
    from src.assistant.config import AssistantSettings
    from src.assistant.engine import Engine
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore

    class Desk:
        def read(self, state, text):
            return DeskCard(
                restate="수서동 어르신들이 어떻게 지내는지",
                act="ask",
                topics=("outlook",),
                dong_op="set",
                dong_mentions=("수서동",),
                target_op="set",
                target="어르신",
            )

    eng = Engine(Desk(), TemplateWriter(), DATA, MemoryStore(), AssistantSettings())
    eng.start("s", Profile(member_region="강남구"))
    r = eng.turn("s", "수서동 3단지 어르신들 괜찮아?")
    assert r.kind == "answer"
    assert "'3단지'처럼 동보다 작은 단위는 자료가 없어 수서동 전체로 봤어요." in r.text


def test_number_follow_up_after_outlook_goes_to_status_topic():
    # 10-20 r2 chuncheon_youth_60 T12: 취약 돌보미 판단 다음 '작년보다 늘었나요?'가 판단으로 갔다
    from src.assistant.slots import DeskCard
    from src.assistant.state import apply_card, new_state

    st = new_state()
    st = apply_card(
        st,
        DeskCard(
            act="ask",
            topics=("outlook",),
            dong_op="set",
            dong_mentions=("석사동",),
            target_op="set",
            target="어르신",
        ),
        "거기 어르신은 어때요?",
    ).state
    assert st.topics == ("outlook",)
    after = apply_card(st, DeskCard(act="ask", topics=("outlook",)), "작년보다 늘었나요?").state
    assert after.topics == ("solo_seniors",)
    young = apply_card(
        st,
        DeskCard(act="ask", topics=("outlook",), target_op="set", target="청년"),
        "청년은 몇 명이에요?",
    ).state
    assert young.topics == ("youth",)
    still = apply_card(st, DeskCard(act="ask", topics=("outlook",)), "몇 분이나 힘드실까요?").state
    assert still.topics == ("outlook",)


def test_same_sheet_again_is_one_line_and_lists_are_stripped():
    f = _f(dongs=("수서동",), target="어르신")
    first = O.render([f], "수서동 어르신들 괜찮을까? 근거도")
    assert O.render([f], "근거를 다시 말해 줘", before=first) == O.SAME_AS_BEFORE
    ai = (
        "수서동 어르신들은 살펴볼 점이 있어요.\n· 조건 A: 지난 7일\n"
        "겹침: 추위\n괜찮은 쪽으로는 …\n끝 문장."
    )
    assert O.strip_lists(ai) == "수서동 어르신들은 살펴볼 점이 있어요.\n끝 문장."


def test_season_words_pick_a_day_from_observations():
    from datetime import date

    librarian.AS_OF = "2026-10-20"
    try:
        f = librarian.gather(
            "outlook",
            Slots(region="춘천시", dongs=("북산면",), period="작년 여름", weather="비"),
            DATA,
        )
        g = librarian.gather(
            "outlook", Slots(region="춘천시", dongs=("북산면",), period="내년 겨울"), DATA
        )
    finally:
        librarian.AS_OF = "live"
    note = next(n for n in f.notes if "그 계절 비가 가장 많이 온 날" in n)
    day = date.fromisoformat(note.split("(")[1][:10])
    assert date(2025, 6, 1) <= day <= date(2025, 8, 31)
    assert any(x.startswith(f"{day.isoformat()} 기준 ") for x in f.lines)
    assert any("날짜로 읽을 수 없어" in n for n in g.notes)


def test_rule_line_only_when_asked():
    f = _f(dongs=("수서동",), target="어르신")
    assert "판단 기준: " not in O.render([f], "수서동 괜찮아?")
    assert "판단 기준: " in O.render([f], "그 판단 기준이 뭐야?")


def test_block_is_capped_unless_asked():
    f = _f(dongs=("북산면",), target="어르신")
    full = O.render([f], "나머지 조건도 다 보여 줘")
    short = O.render([f], "북산면 어르신 괜찮을까? 근거도")
    n_full = full.count("· 조건 ")
    assert short.count("· 조건 ") < n_full or "그 밖에" not in short
    if short.count("· 조건 ") < n_full:
        assert "그 밖에 따로 해당하는 조건" in short


def test_meaning_question_gets_glossary_not_dataset_list():
    m = librarian.gather("sources", Slots(region="춘천시"), DATA, asked="어림이 무슨 뜻이에요?")
    assert m.lines and all(x.startswith("말뜻 — ") for x in m.lines)
    assert "어림" in m.lines[0]
    s = librarian.gather("sources", Slots(region="춘천시"), DATA, asked="이 숫자 출처가 어디예요?")
    assert any(x.startswith("자료: ") for x in s.lines)


def test_month_day_picks_the_nearest_year():
    from datetime import date

    assert librarian._when("12월 4일", date(2026, 1, 2))[0] == "2025-12-04"
    assert librarian._when("1월 3일", date(2025, 12, 30))[0] == "2026-01-03"
    assert librarian._when("7월 16일", date(2025, 12, 31))[0] == "2025-07-16"


def test_english_words_are_not_turned_into_hangul():
    # 10-20 페르소나 o03 r4: 'turn' → '셔구'
    from src.assistant import keyboard as K

    assert K.fix("persona turn 결과는요?") == ("persona turn 결과는요?", [])
    assert K.fix("효자2동 청년 turn") == ("효자2동 청년 turn", [])
    assert K.fix("tntjehd 청년")[0] == "수서동 청년"
    assert K.fix("cjdsus 몇 명이야?")[0] == "청년 몇 명이야?"
    assert K.fix("dkfu wntpdy")[0] == "아려 주세요"  # 한글 자판을 켜지 않고 친 말


def test_region_outlook_leads_when_no_dong():
    # 10-20 r5 강남 T9: senior_hall이 앞이라 '어느 동?'을 되물었다
    from src.assistant.policy import preflight
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile, apply_card, new_state

    st = new_state(Profile(member_region="강남구"))
    card = DeskCard(act="ask", topics=("senior_hall", "outlook"), region_op="set", region="강남구")
    plan = preflight(apply_card(st, card, "걱정이 겹친 동 중에 경로당이 적은 곳은요?"), card, DATA)
    assert plan.kind == "answer" and plan.topics[0] == "outlook" and "senior_hall" in plan.topics


def test_first_answer_folds_basis_until_asked():
    # 【정함 10-27 팀장】 처음엔 접기 — 판단 문장은 글쓴이, 근거 줄은 물을 때만
    f = _f(dongs=("수서동",), target="어르신")
    assert O.render([f], "오늘 챙길 일이 뭐예요?") == O.BRIEF_TAIL
    assert O.render([f], "수서동 어르신들 잘 지내?") == O.BRIEF_TAIL
    for ask in ("근거 보여 줘", "왜 그렇게 봤어요?", "어떤 조건이 맞았어요?", "자세히 알려 줘"):
        assert "· 조건 " in O.render([f], ask), ask
