"""10-20 페르소나 8명(모델 넷 × 두 명) r8에서 찾은 것 — 있는 자료를 '없다'고 하던 것들."""

from datetime import date

from src.assistant import basis as B
from src.assistant import conditions as C
from src.assistant import librarian, table
from src.assistant.data_source import JsonDongData
from src.assistant.slots import Slots

DATA = JsonDongData()


def test_pharmacy_hours_address_and_nearest():
    # h01: '신북읍 약국 문 연 데' · '주소만' → '문 연 약국은 자료로 확인할 수 없어요'
    f = librarian.gather("places", Slots(region="춘천시", dongs=("신북읍",)), DATA)
    line = next(x for x in f.lines if "(국립중앙의료원 약국 정보" in x)
    assert "샘밭약국(읍 가운데에서 직선" in line and "신북읍 신샘밭로 431, 033-243-4019" in line
    assert "문 여는 곳" in line
    assert "요일별 월~토" in line
    g = librarian.gather("places", Slots(region="춘천시", dongs=("북산면",)), DATA)
    near = next(x for x in g.lines if x.startswith("- 약국: 면 안에 없음"))
    assert "직선" in near and "샘밭소양댐약국" in near


def test_pharmacy_day_follows_the_date_slot():
    # 일요일(10월 25일)에는 '쉼'으로, 운영 시간은 그날 요일로 본다
    f = librarian.gather(
        "places", Slots(region="춘천시", dongs=("신북읍",), period="10월 25일"), DATA
    )
    line = next(x for x in f.lines if "(국립중앙의료원 약국 정보" in x)
    assert "10월 25일(일)에 문 여는 곳 0곳" in line and "10월 25일(일) 쉼" in line


def test_village_homes_for_myeon():
    # h01: '약한 지붕 914채 어느 마을이야?' → '마을별 채수는 확인할 수 없어요'
    f = librarian.gather("housing", Slots(region="춘천시", dongs=("신북읍",)), DATA)
    roof = next(x for x in f.lines if "마을(리)별 눈 무게에 약한 지붕" in x)
    assert "천전리 187채" in roof


def test_youth_trend_and_share():
    # h02: '역삼1동 청년 1인세대 1년 전과' → '2025-09 자료는 없어요'
    f = librarian.gather("youth", Slots(region="강남구", dongs=("역삼1동",)), DATA)
    assert f"- 청년 1인세대(주민등록): {B.reg_prev()} → {B.reg()} 8,229명 → 7,819명" in "\n".join(
        f.lines
    )
    assert any(
        x.startswith("- 청년(19~34세) 주민 11,813명 중 1인세대 7,819명, 66%") for x in f.lines
    )


def test_priority_gives_every_rank():
    # f02: '취약 돌보미 동 순위는 위 5곳만 자료에 있어요'
    f = librarian.gather("priority", Slots(region="강남구"), DATA)
    full = next(x for x in f.lines if x.startswith("강남구 취약 돌보미 동 순위 전체(22곳)"))
    assert "22위" in full


def test_tables_carry_share_rank_signals_and_last_year():
    t = table.build(("solo_seniors",), "강남구", [], DATA)
    for col in ("65세 이상 중 혼자 사는 몫(%)", "취약 돌보미 동 순위", "진단 해당 신호 수"):
        assert col in t.header
    row = dict(zip(t.header, next(r for r in t.rows if r[1] == "수서동"), strict=True))
    assert row["65세 이상 중 혼자 사는 몫(%)"] == 46 and row["취약 돌보미 동 순위"] == 2
    y = table.build(("youth",), "강남구", [], DATA)
    assert f"청년 1인세대 {B.reg_prev()}" in y.header and "청년 중 1인세대 몫(%)" in y.header


def test_dataset_list_uses_current_editions_and_lists_land_data():
    # o01: 목록에 주민등록 '2025-07 ~ 2025-12' · 계산 기준일 '2025-12-31' · 땅 자료 없음
    f = librarian.gather("sources", Slots(region="춘천시"), DATA, "출처가 어디예요?")
    text = "\n".join(f.lines)
    assert f"{B.reg_prev()} · {B.reg()}" in text and "2025-12-31" not in text
    assert "산사태취약지역" in text and "급경사지" in text and "15000576" in text


def test_holiday_okay_line_names_last_and_next():
    # f01: '7일 안에 긴 연휴 없음'만 있어 '연휴 날짜는 자료에 없다'
    s = C.sheet("효자2동", "청년", DATA, {}, date(2026, 10, 20))
    okay = next(c.okay for c in s.conds if c.key == "holiday")
    assert "다음 긴 연휴 2026년 12월 25일부터" in okay and "추석" in okay


def test_mask_skips_noun_plus_particle_and_public_numbers():
    # f01: '진단이' · '주소와'를 이름으로, 행정복지센터 번호를 개인 번호로 가렸다
    from src.assistant import pii

    assert pii.mask("순위와 진단이 어르신 쪽 자료라는 점")[1] == []
    assert pii.mask("보건지소의 주소와 전화를 주십시오")[1] == []
    assert pii.mask("효자2동행정복지센터(033-250-3620)")[1] == []
    # 진짜 이름 · 개인 번호는 그대로 가린다
    assert pii.mask("김순자 할머니 연락처 010-1234-5678")[1] == ["전화번호", "이름"]
    assert pii.mask("진영수 어르신 잘 계셔?")[1] == ["이름"]


def test_overlap_rule_is_described_as_it_works_and_misses_explain(monkeypatch):
    # o01: 4겹에 조건이 있는데 '없음' — '서로 다른 겹 3가지 이상'이라는 설명과 맞지 않음
    s = C.sheet("북산면", "어르신", DATA, {}, date(2026, 10, 20))
    assert not s.patterns
    why = C.misses(s)
    access = next(x for x in why if "'약 · 진료를 구하기 어려움'" in x)
    assert "겹이 2가지(동네 · 사람)라 3가지에 못 미침" in access
    assert "무리" in C.OVERLAP_RULE and "모양" in C.OVERLAP_RULE
    # 【판단】 10-24: 사서는 '진짜 오늘'의 날씨 · 달력으로 겹침을 세운다
    #        — 위 sheet와 같은 날로 묶는다
    #        (묶지 않으면 날씨가 바뀐 날 이 겹침이 서 버려 '서지 않은 까닭' 줄이 없어진다)
    monkeypatch.setattr(librarian, "AS_OF", "2026-10-20")
    asked = "네 겹인데 왜 겹친 걱정이 없습니까?"
    f = librarian.gather("sources", Slots(region="춘천시", dongs=("북산면",)), DATA, asked)
    assert any("서지 않은 겹침 '약 · 진료를 구하기 어려움'" in x for x in f.lines)
    # 겹침 규칙을 고쳐도 서는 겹침은 그대로(수서동: 큰비 · 외출)
    sus = C.sheet("수서동", "어르신", DATA, {}, date(2026, 10, 20))
    assert {p.key for p in sus.patterns} == {"rain", "isolation"}


def test_chuncheon_estimate_says_city_not_gu():
    f = librarian.gather("solo_seniors", Slots(region="춘천시", dongs=("북산면",)), DATA)
    line = next(x for x in f.lines if "실제로 혼자 사는 65세 이상 어림" in x)
    assert "춘천시 전체 실제 값" in line and "구 전체" not in line


def _engine(cards):
    from src.assistant.config import AssistantSettings
    from src.assistant.engine import Engine
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    class Desk:
        def __init__(self):
            self.cards = list(cards)

        def read(self, state, text):
            return self.cards.pop(0)

    eng = Engine(Desk(), TemplateWriter(), DATA, MemoryStore(), AssistantSettings())
    eng.start("s", Profile(member_region="춘천시"))
    return eng


def test_goodbye_gets_a_closing_not_a_prompt():
    # 다섯 명: '고마워 끊을게'에 '편하게 물어봐 주세요. 예를 들어 …'
    from src.assistant.slots import DeskCard

    eng = _engine([DeskCard(act="chitchat")])
    r = eng.turn("s", "알았어 고마워 끊을게")
    assert r.text == "네, 필요하실 때 또 물어봐 주세요." and "예를 들어" not in r.text


def test_summary_request_uses_earlier_answers():
    # s02: '지금까지 말씀해 주신 내용 세 줄로 요약' → '아직 춘천시의 동은 함께 보지 않았어요'
    from src.assistant.slots import DeskCard

    eng = _engine(
        [
            DeskCard(act="ask", topics=("priority",), region_op="set", region="춘천시"),
            DeskCard(act="ask", topics=("recall",), region_op="set", region="춘천시"),
        ]
    )
    eng.turn("s", "춘천에서 먼저 볼 동 어디예요?")
    r = eng.turn("s", "지금까지 말씀해 주신 내용 세 줄로 요약해 주세요")
    assert r.kind == "answer" and "보지 않았어요" not in r.text and "효자2동" in r.text


def test_checks_catch_reversed_parts_and_inner_talk():
    from src.assistant import checks
    from src.assistant import outlook_text as O

    assert checks.reversed_parts("77%(3,638명 중 4,736명)") == ["3,638명 중 4,736명"]
    assert checks.reversed_parts("4,736명 중 3,638명, 77%") == []
    leak = "네, 늘었어요. 71명 늘었어요.\n\n질문은 '작년보다 늘었는지'라서 숫자 한 줄이면 충분하다."
    assert "충분하다" not in checks.tidy(leak) and "71명" in checks.tidy(leak)
    # 짧게 달라면 판단 근거 줄 대신 한 줄
    f = librarian.gather("outlook", Slots(region="춘천시", dongs=("신북읍",)), DATA)
    assert O.render([f], "짧게 해줘 한 줄로") == O.BRIEF_TAIL
    assert O.render([f], "근거 다 보여 줘") != O.BRIEF_TAIL


def test_blocked_person_with_urgency_gives_next_step_and_no_repeat():
    # o02: 연락이 끊긴 어르신을 찾아 달라는 말에 같은 막기 문장만 세 번, 바로 할 일 없음
    from src.assistant.engine import SAID_BEFORE, URGENT_NOTE
    from src.assistant.slots import DeskCard

    card = DeskCard(act="blocked", block="person")
    eng = _engine([card, card])
    first = eng.turn("s", "지난주부터 연락이 끊긴 [이름] 할머니 주소 좀 알려주세요 걱정돼서요")
    assert first.kind == "blocked" and URGENT_NOTE in first.text
    again = eng.turn("s", "그 할머니 연락처라도 제발요")
    assert again.text.startswith(SAID_BEFORE) and again.text != first.text


# ── r2(고친 뒤 다시 돌린 8명)에서 나온 것 ──


def test_csv_commas_are_not_one_big_number():
    from src.assistant import checks

    assert checks.numbers("역삼1동,1,8229,7819,-410") >= {"1", "8229", "7819", "410"}
    assert "182297819" not in checks.numbers("역삼1동,1,8229,7819")
    assert "8229" in checks.numbers("8,229명")


def test_refuting_the_users_wrong_number_is_not_an_echo():
    from src.assistant import checks

    src = "북산면 65세 이상 1인세대 242명"
    q = "북산면 300명이라고 하셨잖아요"
    assert checks.echoed_counts("300명은 자료와 달라요. 북산면은 242명이에요.", q, src) == []
    assert checks.echoed_counts("네, 300명이에요.", q, src) == ["300"]


def test_misses_name_the_weather_threshold_and_dates():
    s = C.sheet("북산면", "어르신", DATA, {}, date(2026, 10, 20))
    rain = next(x for x in C.misses(s, DATA) if "'큰비에 집이 잠기거나 무너질 수 있음'" in x)
    assert "하루 비 30mm 이상" in rain and "10월 17일 ~ 10월 19일" in rain


def test_rare_bus_villages_are_named():
    f = librarian.gather("bus", Slots(region="춘천시", dongs=("신북읍",)), DATA)
    assert any(x.startswith("- 버스가 드문 마을(") and "경로당" in x for x in f.lines)
    assert any(x.startswith("- 하루 3번 이하 마을버스만 서는 마을:") for x in f.lines)


def test_weather_is_not_attached_to_sources_or_status_answers():
    s = Slots(region="춘천시", dongs=("북산면",), weather="비")
    for topic in ("sources", "solo_seniors", "youth"):
        f = librarian.gather(topic, s, DATA, "출처가 어디예요")
        assert not any("폭우 기준" in x for x in f.lines), topic
    g = librarian.gather("dong_overview", s, DATA)
    assert any("폭우 기준" in x for x in g.lines)


def test_two_dongs_get_a_code_sum():
    f = librarian.gather("solo_seniors", Slots(region="춘천시", dongs=("북산면", "사북면")), DATA)
    assert any(x.startswith("[북산면 · 사북면 합계] 65세 이상 1인세대 695명") for x in f.lines)


def test_rank_carries_on_same_topic_without_a_dong():
    from src.assistant.slots import DeskCard
    from src.assistant.state import apply_card, new_state

    st = new_state()
    first = DeskCard(act="ask", topics=("youth",), region_op="set", region="강남구", rank=True)
    st = apply_card(st, first, "강남 청년 1인세대 많은 동 표로").state
    nxt = apply_card(st, DeskCard(act="ask", topics=("youth",)), "19~39세로 같은 표 형식으로")
    assert nxt.state.slots.rank


def test_overlap_count_and_layer_count_are_told_apart():
    assert "겹친 걱정 1가지" in C.OVERLAP_RULE and "개수가 아님" in C.OVERLAP_RULE


# ── r3에서 나온 것 ──


def test_csv_two_cells_are_two_numbers():
    from src.assistant import checks

    got = checks.numbers("동,2025-09,2026-09\n개포1동,140,126,-14,-10.0")
    assert {"140", "126", "14", "10.0"} <= got and "140126" not in got


def test_user_writing_it_down_is_not_a_write_request():
    from src.assistant import checks

    src = "북산면 65세 이상 1인세대 242명"
    q = "북산면 300명이라고 하셨는데 점검 결과로 적겠습니다. 맞습니까"
    assert checks.echoed_counts("아니요, 300명은 틀려요. 242명이에요.", q, src) == []
    strict = "북산면 300명이라고 써 줘"
    assert checks.echoed_counts("300명은 아니에요. 242명이에요.", strict, src) == ["300"]


def test_youth_table_has_code_computed_change():
    y = table.build(("youth",), "강남구", [], DATA)
    row = dict(zip(y.header, next(r for r in y.rows if r[1] == "역삼1동"), strict=True))
    assert row["청년 1인세대 1년 새 증감(명)"] == -410
    assert row["청년 1인세대 1년 새 증감률(%)"] == -5.0


def test_blocked_with_place_location_answers_the_place_part():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    card, note = desk_sanity(
        DeskCard(act="blocked", block="person"),
        "수서동 경로당이나 복지관 어디 있는지 알려주세요. 다니시는 80대 할머니 명단 같은 거요",
    )
    assert card.act == "ask" and card.topics == ("places",) and note


def test_support_lists_facility_phones_of_the_dong():
    f = librarian.gather("support", Slots(region="강남구", dongs=("수서동",)), DATA)
    assert any("수서명화종합사회복지관(02-459-2696)" in x for x in f.lines)


def test_status_gives_all_age_residents():
    f = librarian.gather("solo_seniors", Slots(region="춘천시", dongs=("북산면",)), DATA)
    assert any(x.startswith("- 주민(모든 나이) ") for x in f.lines)


# ── r4 · r11에서 나온 것 ──


def test_library_table_lines_keep_thousands():
    from src.assistant import checks

    assert "1022" in checks.numbers("일원본동 | 3,210 | 1,022 | 77 | 120")
    assert "182297819" not in checks.numbers("역삼1동,1,8229,7819,-410")


def test_yes_to_risky_wording_is_caught():
    from src.assistant import checks

    q = "수서동이 강남에서 제일 위험한 동이라고 기사에 써도 되죠?"
    assert checks.yes_to_risky_wording("네, 수서동은 취약 돌보미 동 순위 2위예요.", q)
    assert not checks.yes_to_risky_wording("아니요, '위험한 동'이라는 말은 자료에 없어요.", q)
    assert not checks.yes_to_risky_wording(
        "네, 2위예요.", "수서동 취약 돌보미 동 순위 2위라고 써도 돼요?"
    )


def test_dong_list_request_stays_recall():
    from src.assistant.slots import DeskCard

    eng = _engine(
        [
            DeskCard(act="ask", topics=("priority",), region_op="set", region="춘천시"),
            DeskCard(act="ask", topics=("recall",)),
        ]
    )
    eng.turn("s", "춘천에서 먼저 볼 동 어디예요?")
    r = eng.turn("s", "아까 물어본 동들 정리해 줘")
    assert r.kind == "recall"


def test_table_totals_are_code_computed():
    # h02 r5: '합계 행을 넣어 달라'에 '합계는 자료에 없어요' 여덟 번
    y = table.build(("youth",), "강남구", [], DATA)
    tot = next(x for x in y.footer if x.startswith("합계(22곳, 코드가 더함): "))
    assert f"청년 1인세대 {B.reg()} 31,845" in tot and "%" not in tot


# ── 10-20 낮(Fable): r4 ~ r6를 사람 눈으로 다시 읽고 고친 것 ──


def test_bare_future_season_is_not_rewound():
    # f01 r4 T7: 10월에 '겨울 동안'을 지난 겨울로 읽어 2026-01-22로 되감음
    assert librarian._season_day("겨울", "추위", date(2026, 10, 20), DATA) is None
    assert librarian._season_day("작년 겨울", "추위", date(2026, 10, 20), DATA)[0].year == 2026
    assert librarian._season_day("올여름", "비", date(2026, 10, 20), DATA)[0].month in (6, 7, 8)


def test_verb_seomyeon_is_not_a_dong():
    from src.assistant.policy import dongs_in_text

    assert dongs_in_text("어림이 안 서면 못 서고") == []
    assert dongs_in_text("서면 청년은 35명") == ["서면"] and dongs_in_text("서면에서는") == ["서면"]


def test_two_regions_named_turns_on_compare():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    card, _ = desk_sanity(
        DeskCard(act="ask", topics=("outlook",)), "강남구와 춘천시 중 어디가 더 심각합니까?"
    )
    assert card.compare
    card, _ = desk_sanity(DeskCard(act="ask", topics=("outlook",)), "강남구 어르신 괜찮아?")
    assert not card.compare


def test_date_before_dong_is_not_an_apartment_number():
    from src.assistant import pii

    assert pii.mask("기준이 2026-09-30 동 자료라고 하셨는데")[1] == []
    assert pii.mask("101동 302호")[1] == ["호수", "아파트 동 번호"]


def test_basis_line_says_top_third_only():
    assert "지역 평균은" in C.BASIS_LINE and "8번째까지" in C.BASIS_LINE
    assert "평균보다 높음(상대 기준)" not in C.BASIS_LINE


def test_youth_holiday_fires_without_the_estimate():
    # f01 r4: 어림(전국 비율)이 필수라 효자2동이 연휴에 서지 않았다
    s = C.sheet("효자2동", "청년", DATA, {}, date(2026, 9, 18))
    assert any(p.key == "yholiday" for p in s.patterns)
    okay = next(c.okay for c in s.conds if c.key == "homebound")
    assert "은둔 청년이 적다는 뜻은 아님" in okay


def test_ahead_weather_carries_forecast_values():
    fc = {"신북읍": {"2026-10-20": {"tmin": 12.0, "tmax": 21.0, "rain": 0.0}}}
    s = C.sheet("신북읍", "어르신", DATA, fc, date(2026, 10, 20))
    assert "10/20 최저 12.0℃ · 최고 21.0℃ · 비 0mm" in s.get("ahead").value


def test_rank_reason_is_given():
    f = librarian.gather("priority", Slots(region="강남구", dongs=("개포3동",)), DATA)
    why = next(x for x in f.lines if "순위 까닭" in x)
    assert "5구간 중 5구간" in why and "혼자 사는 몫 33%" in why and "자원이 적은 편" in why
    g = librarian.gather("priority", Slots(region="춘천시", dongs=("북산면",)), DATA)
    assert any("읍 · 면은 거리 · 버스로 봄" in x for x in g.lines)


def test_outing_share_is_in_the_table():
    t = table.build(("solo_seniors",), "강남구", [], DATA)
    row = dict(zip(t.header, next(r for r in t.rows if r[1] == "수서동"), strict=True))
    assert row["외출·연락 모두 적은 어르신(%)"] == 2.5


def test_top_rank_dong_is_resolved_and_recall_with_numbers_is_data():
    from src.assistant.slots import DeskCard

    eng = _engine([DeskCard(act="ask", topics=("priority", "solo_seniors"))])
    r = eng.turn("s", "춘천시 취약 돌보미 동 순위 1위 동의 65세 이상 독거 수는요?")
    assert r.kind == "answer" and "효자2동" in r.text and "1위는 효자2동" in r.text
    eng = _engine(
        [
            DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("북산면",)),
            DeskCard(act="ask", topics=("recall",)),
        ]
    )
    eng.turn("s", "북산면 혼자 사는 어르신 몇 명?")
    r = eng.turn("s", "아까 북산면 300명이라고 하셨지요? 보고서에 적어도 되겠습니까?")
    assert r.kind == "answer" and r.topics != ("recall",)


def test_emergency_repeat_does_not_presume_a_report():
    from src.assistant.policy import EMERGENCY, EMERGENCY_AGAIN, EMERGENCY_THIRD, NO_ADDRESS_NOTE
    from src.assistant.slots import DeskCard

    card = DeskCard(act="blocked", block="emergency")
    eng = _engine([card, card, card])
    a = eng.turn("s", "할머니가 쓰러져 계신 것 같아요")
    b = eng.turn("s", "쓰러져 계신 것 같은데 주소를 몰라서 신고 못 했어요")
    c = eng.turn("s", "아직도 신고 안 했어요 쓰러져 계실까 봐요")
    assert a.text.startswith(EMERGENCY)
    assert b.text.startswith(EMERGENCY_AGAIN) and "이미 알리셨다면" in b.text
    assert c.text.startswith(NO_ADDRESS_NOTE) and EMERGENCY_THIRD in c.text
    assert "주소나 호수를 정확히 몰라도" in NO_ADDRESS_NOTE


def test_doc_uses_the_dong_named_before_the_word():
    from src.assistant.engine import DOC_DONG

    m = DOC_DONG.search(
        "개포1동 반지하 수치도 찾아봐 주세요. 그리고 개포3동 동 상황 문서로 정리해서"
    )
    assert m and m.group(1) == "개포3동"


# ── r7(사람 눈으로 다시 본 뒤 둘째 묶음) ──


def test_bus_has_first_and_last_times_without_placeholder():
    # h01 r7: '버스가 몇 시에 오는지는 결국 모른다고 함' → TAGO 첫차 · 막차 · 갈래 출발 시각
    f = librarian.gather("bus", Slots(region="춘천시", dongs=("신북읍",)), DATA)
    line = next(ln for ln in f.lines if "마을버스 첫차 · 막차" in ln)
    assert "첫차 0" in line and "막차 " in line and "00:00" not in line
    g = librarian.gather("bus", Slots(region="춘천시", dongs=("서면",)), DATA)
    assert "00:00" not in "\n".join(g.lines)  # TAGO의 '0000'(시각 없음)은 뺀다


def test_share_says_facility_residents_are_not_removed_and_same_basis():
    # h02 r7: '시설 입소자를 뺀 숫자인가 · 1년 전 판도 같은 기준인가'에 '자료에 없어요'
    f = librarian.gather("solo_seniors", Slots(region="강남구", dongs=("수서동",)), DATA)
    assert any(
        "요양시설 입소자를 따로 빼지 않음" in ln and "1년 전 판도 같은 기준" in ln for ln in f.lines
    )
    y = librarian.gather("youth", Slots(region="강남구", dongs=("역삼1동",)), DATA)
    assert any("두 판 모두 19~34세" in ln for ln in y.lines)


def test_support_says_112_119_any_time():
    # o02 r7: '오늘 밤에 신고해도 되는 거죠?'에 '절차는 자료에 없다' — 상식 줄
    f = librarian.gather("support", Slots(region="강남구", dongs=("수서동",)), DATA)
    assert any("112 · 119는 밤에도 언제든" in ln for ln in f.lines)


def test_tables_carry_overlap_count():
    # f02 r7: '동 이름 · 순위 · 혼자 사는 몫 · 겹친 걱정 수' 표에 겹친 걱정 수 열이 없었다
    col = "겹친 걱정 수(취약 돌보미 판단, 어르신)"
    for topic in ("solo_seniors", "diagnosis"):
        t = table.build((topic,), "강남구", ["수서동", "개포3동"], DATA)
        assert col in t.header
        row = dict(zip(t.header, next(r for r in t.rows if r[1] == "수서동"), strict=True))
        assert isinstance(row[col], int) and row[col] >= 1


def test_table_ask_tells_writer_to_write_every_row():
    # f02 r7 T5: 22곳 표 줄을 다 주었는데 글쓴이가 '전체 표는 여기서 드리기 어려워요'
    from src.assistant.config import AssistantSettings
    from src.assistant.engine import Engine
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    seen: list[list] = []

    class Spy(TemplateWriter):
        def write(self, question, facts, said="", before=""):
            seen.append(facts)
            return super().write(question, facts, said=said, before=before)

    class Desk:
        def read(self, state, text):
            return DeskCard(
                act="ask",
                topics=("solo_seniors",),
                region_op="set",
                region="강남구",
                dong_op="clear",
            )

    eng = Engine(Desk(), Spy(), DATA, MemoryStore(), AssistantSettings())
    eng.start("s", Profile(member_region="강남구"))
    eng.turn("s", "강남구 22개 동 전부 혼자 사는 몫 순으로 마크다운 표로 주세요")
    notes = "\n".join(n for fs in seen for f in fs for n in f.notes)
    assert "사용자가 표를 달라고 했다" in notes and "'여기서 드리기 어렵다'" in notes
    assert (
        sum("강남구" in fs[0].lines[0] or "표의 열" in ln for fs in seen for ln in fs[0].lines) >= 1
    )


def test_third_refusal_lists_what_can_be_done_now():
    # o02 r7: 같은 거절을 서너 번 — 세 번째부터는 할 수 있는 일을 번호로
    from src.assistant.engine import SAID_BEFORE
    from src.assistant.slots import DeskCard

    card = DeskCard(act="blocked", block="person")
    eng = _engine([card, card, card])
    eng.turn("s", "지난주부터 연락이 끊긴 [이름] 할머니 주소 좀 알려주세요")
    second = eng.turn("s", "그 할머니 연락처라도 제발요")
    third = eng.turn("s", "그 할머니 주소라도 제발요 한 번만요")
    assert second.text.startswith(SAID_BEFORE)
    assert "지금 바로 할 수 있는 일은 ① 112" in third.text and SAID_BEFORE not in third.text


# ── r8(셋째 묶음: 사람 눈으로 다시 읽은 것) ──


def test_report_question_and_goodbye_are_not_emergency_blocks():
    # o02 r8 T6 · T10: '112에 신고해도 되는 건가요?' · '신고하고 … 감사합니다'에 위급 안내만
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c = DeskCard(act="blocked", block="emergency")
    ask, _ = desk_sanity(c, "근데 112에 신고해도 되는 건가요? 그냥 연락이 안 되는 것뿐인데요")
    assert ask.act == "ask" and ask.block == "none" and "support" in ask.topics
    bye, _ = desk_sanity(c, "지금 112에 아는 대로 신고하고 복지관에도 전화해 볼게요. 감사합니다.")
    assert bye.act == "chitchat" and bye.block == "none"
    hard, _ = desk_sanity(c, "할머니가 쓰러져 계신 것 같아요 112 불러야 하나요")
    assert hard.block == "emergency"


def test_support_says_safety_check_request_is_right():
    f = librarian.gather("support", Slots(region="강남구", dongs=("수서동",)), DATA)
    assert any("며칠째 연락이 안 되는" in ln and "안전 확인 요청" in ln for ln in f.lines)


def test_open_hours_are_not_an_unmet_condition():
    # h01 r8 T2: '지금 문 연 시간'을 못 담았다면서 바로 아래에서 영업 시간을 답함
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c = DeskCard(act="ask", topics=("places",), unmet=("지금 문 연 시간",))
    assert desk_sanity(c, "신북읍 약국 문연데 어디가 제일 가까워")[0].unmet == ()


def test_region_compare_clears_leftover_dongs():
    # f02 r8 T4: 앞 턴의 개포3동이 남아 동끼리 견줌 → '춘천시는 자료에 없다'
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="ask", topics=("outlook",)), "강남구랑 춘천시 중에 어디가 더 심각합니까?"
    )
    assert c.compare and c.dong_op == "clear"


def test_bus_route_numbers_are_not_dong_guesses():
    # h01 r8 T7: '사북2'를 사북면으로 알아들음
    from src.assistant.state import _route_like

    assert _route_like("사북2") and _route_like("신북3") and _route_like("남면2-1")
    assert not _route_like("역삼1") and not _route_like("수서동")


def test_bus_facts_tell_the_clock_and_two_rare_criteria():
    # h01 r8 T3 ~ T7: 오전에 '다음 차'가 19:25 · '드문 마을'과 '드문 노선' 기준이 부딪힘
    f = librarian.gather("bus", Slots(region="춘천시", dongs=("신북읍",)), DATA)
    if librarian._clock() is not None:  # 되감기 시험에서는 그날의 시각을 모른다
        assert any("지금 시각 " in ln and "다음 차" in ln for ln in f.lines)
    assert any("'드문 버스'는 두 기준" in n and "반박하지 않는다" in n for n in f.notes)


def test_share_gives_the_whole_population_denominator_too():
    # o01 r8 T6 ~ T9: 스스로 낸 '전체 주민 중 26%'를 '자료에 없다'며 세 번 피함
    f = librarian.gather("solo_seniors", Slots(region="춘천시", dongs=("북산면",)), DATA)
    assert any("928명 중 65세 이상 1인세대 242명은 26%" in ln for ln in f.lines)


def test_table_pick_keeps_only_named_columns_and_adds_rank():
    # h02 r8 T4 ~ T9: '순위 · 동 · 청년 1인세대 2026-09 세 열만' 파일을 다섯 번 말해도 11열
    t = table.pick(
        table.build(("youth",), "강남구", [], DATA),
        "순위 · 동 · 청년 1인세대 2026-09 세 열만 있는 파일로 다시 주세요",
    )
    assert t.header == ["지역", "동", "순위", "청년 1인세대 2026-09"]
    assert t.rows[0][1] == "역삼1동" and t.rows[0][2] == 1
    assert not any(x.startswith("합계(") for x in t.footer)
    same = table.pick(table.build(("youth",), "강남구", [], DATA), "강남구 22개 동 청년 표 엑셀로")
    assert len(same.header) > 4


def test_period_notice_only_when_newly_set():
    # f01 r8: '때를 나눠 볼 수 없어서' 알림이 턴마다 네 번
    from src.assistant.policy import disclose
    from src.assistant.slots import DeskCard

    s = Slots(region="춘천시", dongs=("효자2동",), period="12월 25일부터 사흘 연휴")
    assert "때를 나눠" in disclose(DeskCard(act="ask"), s, None, ("youth",))
    assert "때를 나눠" not in disclose(DeskCard(act="ask"), s, None, ("youth",), repeat_period=True)


def test_brief_words_cover_one_word_answers():
    from src.assistant.writer import BRIEF

    for t in (
        "드문거야 아니야 한마디로만",
        "마을 이름만 한개",
        "한개만 ㅠ 설명은 빼고",
        "응 한마디만",
    ):
        assert BRIEF.search(t), t


# ── r9(넷째 묶음) ──


def test_pharmacy_question_gets_places_topic():
    # h01 r9 T2: '결론만 … 그럼 오늘 신북읍 문연 약국 어디가 제일 가까운데'에 갈 곳 주제가 빠짐
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="ask", topics=("outlook",)),
        "결론만 말해 걱정 있냐 없냐. 그럼 오늘 신북읍 문연 약국 어디가 제일 가까운데",
    )
    assert "places" in c.topics


def test_person_info_question_is_blocked_even_if_desk_said_ask():
    # o02 r9 T3: '그분 주소나 보호자 연락처 정도는 …'에 데스크가 갈 곳으로 답해 경로당 목록이 나감
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="ask", topics=("places",)),
        "기관 회원이면 주민센터 쪽 자료랑 연결돼서 그분 주소나 보호자 연락처 정도는 확인할 수 있는 거 아닌가요?",  # noqa: E501
    )
    assert c.act == "blocked" and c.block == "person"
    ok, _ = desk_sanity(
        DeskCard(act="ask", topics=("places",)), "수서동 경로당 어디 있어요? 전화번호도요"
    )
    assert ok.act == "ask" and ok.block == "none"


def test_unclear_contact_question_goes_to_support():
    # o02 r9 T7: '담당 공무원한테 바로 연결되는 번호는 없나요?'에 '정확히 알아듣지 못했어요'
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(DeskCard(act="unclear"), "담당 공무원한테 바로 연결되는 번호는 없나요?")
    assert c.act == "ask" and c.topics == ("support",)


def test_region_compare_clears_dongs_even_when_desk_set_compare():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="ask", topics=("outlook",), compare=True),
        "강남구랑 춘천시 중 어디가 더 심각합니까?",
    )
    assert c.dong_op == "clear"


def test_calendar_facts_list_coming_long_holidays_and_range():
    # f01 r9 T4 ~ T7: 연휴를 세 번 물어야 답 · '설 연휴는 자료에 없고 달력은 12월 25일까지'
    from src.assistant.librarian import HOLIDAY_ASK, calendar_facts

    assert HOLIDAY_ASK.search("내년 초 설 연휴가 언제인지")
    line = calendar_facts(DATA).lines[0]
    assert "다음 긴 연휴" in line and "그다음" in line and "달력(공휴일) 자료는" in line


def test_rank_reason_explains_resource_gap_order():
    # o01 r9 T6 ~ T7: 사북면이 공공 자원이 더 적은데 왜 북산면이 앞인가
    f = librarian.gather("priority", Slots(region="춘천시", dongs=("북산면",)), DATA)
    line = next(ln for ln in f.lines if "자원 공백" in ln)
    assert "등수로 매겨 평균" in line and "큰 동이 앞" in line


def test_confirm_number_note_and_brief_prev():
    from src.assistant.writer import BRIEF_PREV, CONFIRM_NUM

    assert CONFIRM_NUM.search(
        "북산면은 혼자 사시는 어르신이 300명이고 65세 이상 중 55% 정도라고 하셨지요?"
    )
    assert BRIEF_PREV.search("판단 기준 긴 설명은 이제 안 붙이셔도 됩니다")
    assert BRIEF_PREV.search("예 아니오로만 해 길게 쓰지말고")


def test_table_pick_reads_a_column_list():
    # h02 r9 T4: '열은 청년 1인세대 2026-09, 증감률, 반지하 가구 수 정도면 됩니다'
    t = table.pick(
        table.build(("youth",), "강남구", [], DATA),
        "열은 청년 1인세대 2026-09, 증감률, 반지하 가구 수 정도면 됩니다.",
    )
    assert t.header == ["지역", "동", "청년 1인세대 2026-09", "청년 1인세대 1년 새 증감률(%)"]
    # f02: 취약 돌보미 순위 · 독거 수 · 고립 신호 개수 — 10-20에는 하나도 못 맞춰 표 전체를 줬다.
    # 10-25부터 다른 말(독거 = 1인세대, 비율 = 몫, 신호 개수 = 신호 수)도 읽어 말한 네 열만
    got = table.pick(
        table.build(("solo_seniors",), "강남구", [], DATA),
        "열은 동 이름 / 취약 돌보미 순위 / 65세 이상 1인세대 비율 / 80세 이상 독거 수 / 고립 신호 개수, 이렇게요.",  # noqa: E501
    )
    assert got.header[2:] == [
        "취약 돌보미 동 순위",
        "65세 이상 중 혼자 사는 몫(%)",
        "80세 이상 1인세대 2026-09",
        "진단 해당 신호 수",
    ]
    # 하나도 안 맞으면 표 전체(그대로)
    full = table.pick(
        table.build(("solo_seniors",), "강남구", [], DATA), "열은 가나다 / 라마바, 이렇게요."
    )
    assert len(full.header) > 10


def test_table_facts_name_the_file():
    from src.assistant.config import AssistantSettings
    from src.assistant.engine import Engine
    from src.assistant.slots import DeskCard
    from src.assistant.state import Profile
    from src.assistant.store import MemoryStore
    from src.assistant.writer import TemplateWriter

    seen: list[list] = []

    class Spy(TemplateWriter):
        def write(self, question, facts, said="", before=""):
            seen.append(facts)
            return super().write(question, facts, said=said, before=before)

    class Desk:
        def read(self, state, text):
            return DeskCard(
                act="ask",
                topics=("youth",),
                region_op="set",
                region="강남구",
                dong_op="clear",
                fmt="엑셀",
            )

    eng = Engine(Desk(), Spy(), DATA, MemoryStore(), AssistantSettings())
    eng.start("s", Profile(member_region="강남구"))
    eng.turn("s", "강남구 22개 동 청년 1인세대 표 엑셀로 주세요")
    lines = [ln for fs in seen for f in fs for ln in f.lines]
    assert any(ln.startswith("표 파일 이름: ") and ".xlsx" in ln for ln in lines)


# ── r10(다섯째 묶음) ──


def test_count_and_facility_questions_are_not_person_blocks():
    # o01 r10 T2 '실제로 집에서 혼자 사시는 분이 몇 명' · o02 r10 T9 '경로당에서 제일 가까운 복지관'
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    a, _ = desk_sanity(
        DeskCard(act="ask", topics=("solo_seniors",)),
        "242명 가운데 실제로 집에서 혼자 사시는 분이 몇 명인지는 따로 알 수 있습니까?",
    )
    b, _ = desk_sanity(
        DeskCard(act="ask", topics=("places",)),
        "수서동 궁마을 경로당에서 제일 가까운 복지관이 어디예요? 거기 먼저 전화해 보려고요. 그분이 걱정돼서요",  # noqa: E501
    )
    assert a.act == "ask" and b.act == "ask"


def test_holiday_is_not_an_unmet_condition():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c = DeskCard(act="ask", topics=("youth",), unmet=("다음 긴 연휴 날짜와 며칠 이어지는지",))
    assert desk_sanity(c, "다음 긴 연휴가 언제입니까?")[0].unmet == ()


def test_sub_dong_notice_not_when_user_says_not_asking():
    # o01 r10: '통·반을 묻지 않았으니 그 안내는 필요 없다'에 같은 알림이 일곱 번
    from src.assistant.engine import NOT_ASKING

    assert NOT_ASKING.search("참고로 저는 통·반을 묻지 않았으니 그 안내는 필요 없습니다.")
    assert not NOT_ASKING.search("수서동 3단지 어르신들 괜찮아?")


def test_diagnosis_lists_every_signal_name():
    # f01 r10 T4 ~ T6: '5가지 중 해당하지 않은 둘'에 '자료에 없어요'
    f = librarian.gather("diagnosis", Slots(region="춘천시", dongs=("효자2동",)), DATA)
    line = next(ln for ln in f.lines if "진단이 본 신호" in ln)
    assert "버스가 드묾" in line and "청년 지표는 없음" in line
    g = librarian.gather("diagnosis", Slots(region="강남구", dongs=("수서동",)), DATA)
    assert any("진단이 본 신호 8가지" in ln and "계단만 있는 오래된 집" in ln for ln in g.lines)


def test_priority_table_has_band_share_gap_and_pick_reads_them():
    # f02 r10 T7 ~ T9: '위험 구간 · 혼자 사는 몫 · 자원 공백' 열이 없어 등수 · '없음'으로 채움
    t = table.pick(
        table.build(("priority", "diagnosis"), "강남구", [], DATA),
        "열은 동 이름 / 취약 돌보미 순위 / 위험 구간 / 혼자 사는 몫 / 자원 공백 다섯 개만요.",
    )
    assert t.header == [
        "지역",
        "동",
        "취약 돌보미 동 순위",
        "위험 구간(5구간 중)",
        "65세 이상 중 혼자 사는 몫(%)",
        "자원 공백(1에 가까울수록 자원 없음)",
    ]
    row = dict(zip(t.header, next(r for r in t.rows if r[1] == "개포3동"), strict=True))
    assert row["위험 구간(5구간 중)"] == 5 and row["자원 공백(1에 가까울수록 자원 없음)"] > 0.5


def test_region_compare_note_keeps_only_compare_lines():
    fs = librarian.gather_all(
        ("outlook",), Slots(region="강남구", target="어르신", compare=True), DATA, ""
    )
    notes = [n for f in fs for n in f.notes]
    # 10-25: 안쪽 말('견줌 줄')이 답에 새어 '견줌 줄에 그대로 나오니'(재생 T8) → 낱말을 바꿈
    assert any("두 지역을 견주는 물음이면 겹친 걱정이 있는 동 몫" in n for n in notes)


# ── r11(여섯째 묶음) ──


def test_saying_unknown_is_fine_when_the_user_asked_whether_it_is_unknown():
    # 다리엔 r11 T8 ~ T9: '최근 피해는 이 자료로 알 수 없는 거죠?'에 '네, 알 수 없어요'를 버리고 자료 그대로  # noqa: E501
    from src.assistant import checks

    assert checks.asks_if_unknown(
        "그제 비 이후 실제 피해가 있었는지는 이 자료로 알 수 없는 게 맞나요?"
    )
    assert checks.asks_if_unknown("요양시설 입소자가 몇 명 들어 있는지도 구분이 됩니까?")
    assert not checks.asks_if_unknown("수서동 혼자 사는 어르신 몇 명이에요?")
    assert checks.none_only("네, 그런 최근 상황은 이 자료로 알 수 없어요.", "자료") == ["알 수 없"]


def test_top_rank_covers_both_regions_when_comparing():
    # 오린 r11 T5 ~ T10: '강남 1위 개포3동이랑 춘천 1위 동을 나란히'에 '춘천 1위는 자료에 없다'
    from src.assistant.slots import DeskCard

    eng = _engine([DeskCard(act="ask", topics=("diagnosis",))])
    r = eng.turn("s", "강남 1위 동이랑 춘천 1위 동을 나란히 놓고 어느 쪽이 더 심각한지 한 줄로요")
    assert (
        "강남구 취약 돌보미 동 순위 1위는 개포3동" in r.text
        and "춘천시 취약 돌보미 동 순위 1위는" in r.text
    )
    assert "효자2동" in r.text


def test_blocked_answer_says_death_report_counts_are_not_in_data():
    # 레아나 r11 T8 ~ T9: '수서동 전체 고독사 신고 몇 건'이 섞인 막힌 말에 같은 막기 문장만
    from src.assistant.engine import NO_DATA_LINE
    from src.assistant.slots import DeskCard

    eng = _engine([DeskCard(act="blocked", block="person")])
    r = eng.turn(
        "s", "그분 따님 연락처라도요. 아니면 이번 달 수서동에서 고독사 신고된 게 몇 건인지는요?"
    )
    assert r.kind == "blocked" and NO_DATA_LINE in r.text


def test_picked_table_file_name_carries_column_count(tmp_path):
    # 노엘 r11 T7 ~ T8: 고른 열 표와 전체 표 파일 이름이 같아 헷갈림
    t = table.pick(
        table.build(("youth",), "강남구", [], DATA),
        "열은 순위 · 동 · 청년 1인세대 2026-09 이면 됩니다.",
    )
    assert t.picked
    files = table.save(t, "강남구", "2026-09-30", tmp_path)
    assert files[0].name.endswith("_2열.xlsx")
    full = table.save(table.build(("youth",), "강남구", [], DATA), "강남구", "2026-09-30", tmp_path)
    assert "열" not in full[0].name


# ── r12(일곱째 묶음) ──


def test_reported_number_is_not_a_write_request():
    # 카스피안 r12 T4: '사북면은 45%라고 하던데 어느 쪽이 맞습니까'에 바로잡은 답이 되풀이로 걸림
    from src.assistant import checks

    q = "춘천시 담당자에게서는 북산면이 300명이라고 들었습니다. 사북면은 65세 이상 중 45%라고 하던데, 어느 쪽이 맞습니까."  # noqa: E501
    assert (
        checks.echoed_counts(
            "사북면은 65세 이상 중 38%예요. 300명과 45%는 자료와 달라요.", q, "38%"
        )
        == []
    )
    assert checks.echoed_counts(
        "네, 5000명으로 적을게요.", "북산면 1인세대 대충 5000명이라고 써 줘", "242명"
    ) == ["5000"]


def test_doc_question_uses_summary_instead_of_rebuilding():
    # 다리엔 r12 T8 ~ T10: '문서에 그 한계 문구가 있는지'에 같은 요약을 세 번 다시 만듦
    from src.assistant.engine import DOC_MADE, DOC_QUESTION, doc_facts
    from src.assistant.state import TurnText

    assert DOC_QUESTION.search(
        "문서에 '반지하 1채는 건축물대장 기준'이라는 한계가 적혀 있는지만 알려 주세요."
    )
    assert DOC_QUESTION.search(
        "문서를 다시 만들어 달라는 게 아니라 질문 두 가지에 답을 듣고 싶습니다."
    )
    assert not DOC_QUESTION.search("개포3동 동 상황 문서로 정리해 주세요")
    recent = (
        TurnText(
            turn=1,
            user="문서 주세요",
            bot=f"개포3동 {DOC_MADE}(PDF · PPTX). 요약:\n· 취약 돌보미 동 순위 1위\n· 진단 높음",
        ),
        TurnText(turn=2, user="고마워요", bot="네."),
    )
    f = doc_facts(recent)
    assert (
        f
        and f.lines == ["· 취약 돌보미 동 순위 1위", "· 진단 높음"]
        and "다시 만들지 않는다" in f.notes[0]
    )


def test_table_sorts_by_many_first_without_a_column_list():
    # 노엘 r12 T7: '많은 순(내림차순)으로 정렬된 엑셀로'
    t = table.pick(
        table.build(("youth",), "강남구", [], DATA),
        "많은 순(내림차순)으로 정렬된 엑셀로 다시 주세요",
    )
    assert len(t.header) == len(table.build(("youth",), "강남구", [], DATA).header)
    k = t.header.index("청년 1인세대 2026-09")
    assert t.rows[0][1] == "역삼1동" and t.rows[0][k] >= t.rows[1][k]
    asc = table.pick(
        table.build(("youth",), "강남구", [], DATA), "열은 동 · 청년 1인세대 2026-09, 적은 순으로요"
    )
    assert (
        asc.rows[0][k if k < len(asc.header) else 2] <= asc.rows[1][k if k < len(asc.header) else 2]
    )


def test_blocked_answer_says_apartment_location_is_not_in_data():
    # 레아나 r12 T6 ~ T8: '신동아아파트에서 제일 가까운 경로당'을 '동보다 작은 단위'로만 막음
    from src.assistant.slots import DeskCard

    eng = _engine(
        [DeskCard(act="blocked", block="person", dong_op="set", dong_mentions=("수서동",))]
    )
    r = eng.turn(
        "s",
        "그분이 다니셨을 수도 있으니 신동아아파트에서 제일 가까운 경로당이 어디예요? 그분 등록 여부도요",  # noqa: E501
    )
    assert "위치는 취약 돌보미 자료에 없어" in r.text and "동보다 작은 단위" not in r.text


# ── r13(여덟째 묶음) ──


def test_doc_question_words_and_full_doc_lines():
    # 다리엔 r13 T8 ~ T10: '문서 어디에 있는지' · '문구가 들어갔는지' · '요약만으로는'
    from src.assistant.engine import DOC_QUESTION, doc_facts

    for t in (
        "요약만으로는 제가 부탁드린 문구가 들어갔는지 확인이 안 됩니다. 들어갔다면 문서 어디에 있는지 알려 주세요",  # noqa: E501
        "문서 안에 '실제로 센 수가 아님'이라는 문구가 들어갔는지 예, 아니오로만 알려 주세요",
    ):
        assert DOC_QUESTION.search(t), t
    carried = (
        "65세 이상 1인세대 1,262명",
        "문서 개포3동 · 요약: 취약 돌보미 동 순위 1위",
        "문서 개포3동 · 청년: 어림이라 실제로 센 수가 아님",
    )
    f = doc_facts((), carried)
    assert f and len(f.lines) == 2 and all(x.startswith("문서 ") for x in f.lines)
    assert any("문서에 있는지는 위 줄" in n for n in f.notes)


def test_blocked_answer_says_what_police_do_and_night_numbers():
    # 레아나 r13 T8 ~ T10: '경찰에 신고하면 그분 찾아가 봐 주는지 · 밤에 연락할 24시간 번호'에 같은 막기 문장만  # noqa: E501
    from src.assistant.engine import POLICE_LINE
    from src.assistant.slots import DeskCard

    eng = _engine(
        [DeskCard(act="blocked", block="person", dong_op="set", dong_mentions=("수서동",))]
    )
    r = eng.turn(
        "s",
        "그분 주소 달라는 게 아니고요, 경찰에 신고하면 경찰이 그분 집 찾아가 봐 주는 건지랑 밤에 연락할 24시간 번호요",  # noqa: E501
    )
    assert r.kind == "blocked" and POLICE_LINE in r.text


# ── 10-21 내가 사용자 역(사북면 지암리 이장 19턴)에서 찾은 것(아홉째 묶음) ──


def test_roof_question_gets_housing_even_if_desk_said_out_of_scope():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="out_of_scope"),
        "우리 면에 슬레이트 지붕 집이 몇 채나 됩니까. 지암리는 몇 채요",
    )
    assert c.act == "ask" and "housing" in c.topics
    u, _ = desk_sanity(
        DeskCard(
            act="ask", topics=("housing",), unmet=("슬레이트 지붕 집", "그 집에 노인이 사는지")
        ),
        "그 집들이 다 노인네 집입니까",
    )
    assert u.unmet == ("그 집에 노인이 사는지",)


def test_which_elder_first_goes_to_outlook():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="unclear"),
        "그럼 마을 말고 사람으로 치면 어떤 노인네부터 들여다봐야 하오. 짧게",
    )
    assert c.act == "ask" and c.topics == ("outlook",)


def test_dialect_goodbye_and_not_seen_lately():
    from src.assistant.engine import URGENT
    from src.assistant.policy import BYE

    assert BYE.search("고맙소. 이제 자야겠네. 내일 면사무소 가서 물어보리다")
    assert URGENT.search("김씨 노인 혼자 사는 양반이 있는데 요새 통 안 보여")


def test_period_notice_not_on_usage_question():
    from src.assistant.policy import disclose
    from src.assistant.slots import DeskCard

    s = Slots(region="춘천시", dongs=("사북면",), period="겨울")
    assert "때를 나눠" not in disclose(DeskCard(act="ask"), s, None, ("usage",))
    assert "때를 나눠" in disclose(DeskCard(act="ask"), s, None, ("solo_seniors",))


def test_holiday_question_is_not_out_of_scope_and_village_homes_have_a_total():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="out_of_scope"), "설 연휴가 언제요? 그때 자식들 안 오는 노인들이 걱정인데"
    )
    assert c.act == "ask" and c.topics == ("outlook",)
    f = librarian.gather("housing", Slots(region="춘천시", dongs=("사북면",)), DATA)
    line = next(ln for ln in f.lines if "마을(리)별 눈 무게에 약한 지붕" in ln)
    assert "사북면 전체 799채(마을 합" in line


# ── 10-21 밤: ① 장서 목록 자동 ② 말의 꼴 칸(farewell · urgent · brief) ──


def test_desk_catalogue_lists_what_the_librarian_has():
    from src.assistant.catalog import describe_for_desk
    from src.assistant.desk import SYSTEM

    text = describe_for_desk()
    assert "자료에 있는 것:" in text
    assert "슬레이트" in text and "첫차" in text and "연휴" in text and "빈집" in text
    assert "마지막 선택" in SYSTEM and "가장 가까운 주제로 ask" in SYSTEM


def test_card_flags_come_from_tool_and_vote_by_majority():
    from src.assistant.desk import vote
    from src.assistant.slots import DeskCard, card_from_tool, desk_tool_schema

    props = desk_tool_schema()["properties"]
    assert {"farewell", "urgent", "brief"} <= set(props)
    c = card_from_tool(
        {"restate": "x", "act": "chitchat", "topics": [], "farewell": True, "brief": True}
    )
    assert c.farewell and c.brief and not c.urgent
    cards = [
        DeskCard(act="chitchat", farewell=True),
        DeskCard(act="chitchat", farewell=True),
        DeskCard(act="chitchat"),
    ]
    assert vote(cards).farewell
    assert not vote(
        [
            DeskCard(act="chitchat", farewell=True),
            DeskCard(act="chitchat"),
            DeskCard(act="chitchat"),
        ]
    ).farewell


def test_engine_uses_card_flags_before_regex():
    from src.assistant.engine import URGENT_NOTE
    from src.assistant.slots import DeskCard

    eng = _engine([DeskCard(act="chitchat", farewell=True)])
    r = eng.turn("s", "오늘은 여기까지 한레후")  # 정규식에는 없는 말투
    assert "필요하실 때 또 물어봐 주세요" in r.text and "예를 들어" not in r.text
    eng2 = _engine([DeskCard(act="blocked", block="person", urgent=True)])
    r2 = eng2.turn("s", "옆집 할매가 영 기척이 없는디 그 양반 좀 봐주소")  # 정규식에는 없는 말
    assert URGENT_NOTE in r2.text


def test_region_wide_rank_table_and_urgent_emergency():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="ask", topics=("diagnosis",), region_op="set", region="강남구"),
        "강남구 22개 동 위험 구간이랑 자원 공백 표로 주세요",
    )
    assert "priority" in c.topics and c.rank
    e, _ = desk_sanity(
        DeskCard(act="ask", topics=("support",), urgent=True),
        "어르신이 집에서 안 나오신 지 사흘째래요 어떡하죠",
    )
    assert e.act == "blocked" and e.block == "emergency"


def test_dong_level_lost_contact_phrase_is_not_an_emergency():
    # r14 세라핀 T4 ~ T5: '연락이 끊기는 청년'(동 단위 말)을 사람 찾기 · 위급으로 읽음
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="ask", topics=("youth",), urgent=True),
        "효자2동에서 연휴 뒤에 연락이 끊기는 청년들이 많은데 자료로 뭘 볼 수 있어요?",
    )
    assert c.act == "ask" and c.block == "none"


def test_two_region_dong_compare_does_not_ask_region_and_solo_table_has_rank_parts():
    # r14 오린 T5 ~ T6
    from src.assistant.slots import DeskCard

    eng = _engine([DeskCard(act="ask", topics=("priority", "diagnosis"), compare=True)])
    r = eng.turn(
        "s",
        "강남 1위 동이랑 춘천 1위 동을 나란히 놓고 혼자 사는 어르신 수 · 위험 구간 · 도움 거리로 견줘 주세요",  # noqa: E501
    )
    assert r.kind != "ask_slot" and "어느 지역을 볼까요" not in r.text
    t = table.build(("solo_seniors",), "강남구", ["개포3동"], DATA)
    assert "위험 구간(5구간 중)" in t.header and "자원 공백(1에 가까울수록 자원 없음)" in t.header


# ── 10-21 아침: '있는데 없다고 함' 검사(글쓴이 쪽) · 사용자가 말한 숫자가 든 앞 자료 줄 ──


def test_missing_claims_catches_denials_of_present_data_only():
    from src.assistant import checks

    src = "\n".join(
        [
            "표의 열: 취약 돌보미 동 순위 | 위험 구간(5구간 중) | 자원 공백",
            "논현1동 | 4 | 5 | 0.32",
            "합계(22곳, 코드가 더함): 청년 1인세대 2026-09 31,845명",
            "청년 1인세대 2025-09: 논현1동 3,978명 · 일원1동 1,100명",
            "수서동 주민센터 전화번호는 자료에 없음. 서울시 다산콜센터 120",
            "큰비 기준: 하루 비 30mm 이상 · 폭염 기준: 낮 최고기온 33℃ 이상",
        ]
    )
    # 있는데 없다고 함
    assert checks.missing_claims("4~22위 위험 구간은 자료에 적혀 있지 않아 '-'로 둔 것이에요.", src)
    assert checks.missing_claims("22개 동 합계 31,845명은 자료에 없는 숫자예요.", src)
    assert checks.missing_claims("논현1동과 일원1동의 2025-09 숫자는 자료에 없어요.", src)
    # 없다가 맞는 말
    assert not checks.missing_claims(
        "수서동 주민센터 주소와 전화는 자료에 없어요.", src
    )  # 자료 줄도 없다고 함
    assert not checks.missing_claims(
        "낮 최고기온 33℃ 이상은 자료에 없고 연휴도 해당하지 않아요.", src
    )  # 기준 말
    assert not checks.missing_claims("2024년 9월 수는 지금 자료에 없어요.", src)  # 해
    assert not checks.missing_claims("지역 간 겹친 걱정 수는 이 자료에 없어요.", src)  # 일반 낱말뿐
    assert "있는데 없다고 함" in " ".join(
        checks.problems("22개 동 합계 31,845명은 자료에 없는 숫자예요.", src, [])
    )


def test_carry_facts_brings_lines_with_the_number_the_user_said():
    from src.assistant.engine import carry_facts

    older = tuple(f"줄 {i}" for i in range(70)) + (
        "합계(22곳, 코드가 더함): 청년 1인세대 31,845명",
    )
    f = carry_facts("앞에서 합계 31,845명이라고 하셨는데 맞나요", "", (), [], older=older)
    assert f and f.lines[0].startswith("합계(22곳")
    g = carry_facts(
        "31,845명이 어느 쪽이 맞나요", "", (), [], older=older
    )  # 되짚는 말이 없어도 숫자가 있으면
    assert g and g.lines[0].startswith("합계(22곳")


def test_chat_table_is_drawn_by_code_with_every_row():
    # r14 오린 '4위부터 22위까지 -' · r12 노엘 '11곳만 옮김' — 표는 코드가 붙인다
    from src.assistant.slots import DeskCard

    eng = _engine(
        [
            DeskCard(
                act="ask",
                topics=("youth",),
                region_op="set",
                region="강남구",
                dong_op="clear",
                rank=True,
            )
        ]
    )
    r = eng.turn("s", "강남구 22개 동 청년 1인세대를 표로 보여 주세요")
    rows = [ln for ln in r.text.splitlines() if ln.startswith("| ")]
    assert rows and rows[0].startswith("| 동 |") and len(rows) == 23  # 머리 1 + 동 22


def test_markdown_table_formats_numbers_and_limits_columns():
    t = table.build(("youth",), "강남구", ["역삼1동", "수서동"], DATA)
    md = table.markdown(t)
    assert md.startswith("| 동 |") and "역삼1동" in md and md.count("\n") >= 3
    # 10-29 팀장 '너무 길어': 채팅 표는 동 + 값 3열(table.CHAT_COLS)
    assert len(md.splitlines()[0].split("|")) - 2 <= table.CHAT_COLS


def test_catalog_words_json_is_in_step_with_the_librarian():
    # 자료를 더하고 scripts/build_catalog_words.py 를 안 돌리면 여기서 빨개진다
    import importlib.util
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "bcw", root / "scripts" / "build_catalog_words.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    saved = json.loads(
        (root / "src" / "assistant" / "catalog_words.json").read_text(encoding="utf-8")
    )
    # 사서 줄은 날짜 · 되감기에 따라 달라 그대로 견주지 않고, 손으로 더한 말(EXTRA)이 다 들어 있는지와  # noqa: E501
    # 주제 목록이 같은지만 본다(EXTRA를 고치고 스크립트를 안 돌리면 여기서 빨개진다)
    for k, ws in mod.EXTRA.items():
        assert set(ws) <= set(saved.get(k, ())), k
    skip = {"my_region", "recall", "dong_doc", "usage", "datasets", "sources"}
    assert set(saved) == {t.id for t in mod.TOPICS} - skip


def test_pick_reads_partial_column_names_and_human_agent_is_out_of_scope():
    # r15 노엘: '동 이름 / 청년 1인세대 2026-09 / 1년 새 증감(명) 세 열' — 증감 열이 다섯 번 빠짐
    t = table.pick(
        table.build(("youth",), "강남구", [], DATA),
        "열은 동 이름 / 청년 1인세대 2026-09 / 1년 새 증감(명) 세 개만, 2026-09 기준 내림차순으로요.",  # noqa: E501
    )
    assert t.header == ["지역", "동", "청년 1인세대 2026-09", "청년 1인세대 1년 새 증감(명)"]
    assert t.rows[0][1] == "역삼1동"
    # adversarial_20 T16: '너 말고 사람 담당자 연결해 줘'는 기관 연락처가 아니다
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(DeskCard(act="ask", topics=("support",)), "너 말고 사람 담당자 연결해 줘")
    assert c.act == "out_of_scope"


def test_resident_count_and_conversation_save():
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import DeskCard

    c, _ = desk_sanity(
        DeskCard(act="ask", topics=("youth",), target_op="set", target="청년"),
        "주민이 몇 명인데요?",
    )
    assert c.topics == ("dong_overview",)
    d, _ = desk_sanity(
        DeskCard(act="ask", topics=("dong_doc",), fmt="PDF"),
        "이 대화 내용 PDF로 저장해 줄 수 있어요?",
    )
    assert d.act == "out_of_scope"
    e, _ = desk_sanity(
        DeskCard(act="ask", topics=("dong_doc",), fmt="PDF"), "석사동 동 상황 PDF로 만들어 줘"
    )
    assert e.act == "ask" and "dong_doc" in e.topics
