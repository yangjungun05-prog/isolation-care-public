"""글쓴이 고침(10-15, 페르소나 20b에서 찾음).

【기능】 경로당 주무관(q03) 13턴: 앞 답의 숫자를 다음 답이 '자료에 없다'며 뒤집어 신뢰를 잃음.
       글쓴이가 직전 답을 몰랐다 → 직전 답을 함께 주고, 꺼내지 않은 것을 '없다'고 하지 않게 한다.
"""

from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk
from src.assistant.engine import Engine
from src.assistant.librarian import Facts
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import WRITER_SYSTEM, ClaudeWriter


def test_request_carries_previous_answer_and_allows_its_numbers():
    w = ClaudeWriter(AssistantSettings(anthropic_api_key=""))
    facts = [Facts(title="경로당", lines=["세곡동 경로당 25곳"])]
    q = "그 숫자 어디서?"
    kw, allowed, _ = w._request(q, facts, said=q, before="합계는 187곳")
    user = kw["messages"][0]["content"]
    assert user.startswith("[직전 답]\n합계는 187곳") and "187" in allowed
    assert "그 숫자 어디서?" in w._echo[0]


def test_prompt_forbids_saying_unfetched_things_are_missing():
    assert "[직전 답]" in WRITER_SYSTEM and "뒤집" in WRITER_SYSTEM
    assert "찾아 드릴게요" in WRITER_SYSTEM


class SpyWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def write(self, question, facts, said="", before=""):
        self.calls.append((said, before))
        return "수서동 혼자 사는 어르신은 2,471명이에요."


def test_engine_passes_last_answer_to_writer(tmp_path):
    cards = {
        "수서동 혼자 사는 어르신": DeskCard(
            act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("수서동",)
        ),
        "고마워요": DeskCard(act="chitchat"),
        "그 숫자 어디서 나왔어?": DeskCard(act="ask", topics=("sources",)),
    }
    w = SpyWriter()
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    e = Engine(FakeDesk(cards), w, JsonDongData(), MemoryStore(), s)
    e.start("w", Profile(member_region="강남구"))
    e.turn("w", "수서동 혼자 사는 어르신")
    e.turn("w", "고마워요")  # 맞장구는 직전 답을 바꾸지 않는다
    e.turn("w", "그 숫자 어디서 나왔어?")
    assert w.calls[0][1] == "" and "2,471명" in w.calls[1][1]


def test_sources_shelf_uses_dataset_list_with_dates():
    # 【기능】 q03 T2~T6: '그 숫자 어디서?'에 옛 출처 목록만 줘서
    #        서울시 경로당 현황 2025-06이 빠지고,
    #        '출처는 2022인데 기준일 2025?'로 헷갈림 → 자료 목록(기관 · 기준 시점)으로
    from src.assistant.librarian import gather
    from src.assistant.slots import Slots

    text = gather("sources", Slots(region="강남구"), JsonDongData()).text
    assert "서울시 경로당 현황" in text and "2025-06-30" in text
    assert "강남구 경로당 현황" in text and "2022-11-22" in text
    assert "춘천시 기초생활보장" not in text  # 지역에 맞는 것만


def test_priority_answer_states_its_basis():
    # 【기능】 q02 T3 '순위가 무엇을 기준으로?'에 '기준이 없어요'(틀린 말)
    from src.assistant.librarian import gather
    from src.assistant.slots import Slots

    text = gather("priority", Slots(region="춘천시"), JsonDongData()).text
    assert "순위 기준" in text and "혼자 사는 어르신 몫" in text and "도움 거리" in text


def test_our_data_month_is_not_unmatched():
    # 【기능】 q05 T6~T10: '2024년 12월 대비 2025년 12월'에 '때를 나눠 볼 수 없어서'가 다섯 턴 붙음.
    #        우리 자료의 달(주민등록 판의 달)은 밝히지 않는다. 10-19부터 달은 자료에서 읽는다
    #        (2026 최신 판: 주민등록 2026-09, 견줌 2025-09)
    from src.assistant import basis as B
    from src.assistant.policy import disclose
    from src.assistant.slots import Slots

    now, prev = B.ko(B.reg()), B.ko(B.reg_prev())
    month = now.split()[1]
    for p in (f"{prev} 대비 {now}", f"작년 {month}", month, now.split()[0]):
        assert disclose(DeskCard(), Slots(period=p), None, ("solo_seniors",)) == "", p
    t = ("solo_seniors",)
    assert "나눠 볼 수 없" in disclose(DeskCard(), Slots(period="올해 3월"), None, t)
    assert "나눠 볼 수 없" in disclose(DeskCard(), Slots(period="2021년"), None, ("solo_seniors",))


def test_tidy_removes_writer_inner_talk_1015():
    # 【기능】 q05 T6 '사용자 요청은 …입니다. 자료에 있는 숫자를 그대로 옮기고 …',
    #        q04 T12 '질문에 "확인해 달라"고 했으니 "네,"로 시작했습니다. … 이 답에 넣지 않았어요'
    from src.assistant.checks import tidy

    a = (
        "사용자 요청은 세 동의 숫자를 텍스트로 정리하는 것입니다. "
        "자료에 있는 숫자를 그대로 옮기고, "
        "증가율도 자료에 적힌 값을 씁니다.\n수서동은 2,471명이에요."
    )
    assert tidy(a) == "수서동은 2,471명이에요."
    b = (
        "네, 볼 수 있어요. 신사우동은 860명이에요.\n\n"
        '질문에 "확인해 달라"고 했으니 "네,"로 시작했습니다. '
        '다만 "효자2동은 나중에"는 이 답에 넣지 않았어요.'
    )
    assert tidy(b) == "네, 볼 수 있어요. 신사우동은 860명이에요."


def test_table_words_only_when_asked_as_file():
    # 【기능】 q05 T5 '엑셀 파일 감사합니다'에 표 낱말이 걸려 표만 또 줌 → 달라는 꼴만
    from src.assistant.policy import TABLE_FILE

    for yes in ("엑셀로 줘", "CSV로 받을 수 있어?", "표 파일로 주세요", "엑셀 파일로 받고 싶어요",
                "엑셀 받을 수 있어?"):  # fmt: skip
        assert TABLE_FILE.search(yes), yes
    for no in ("엑셀 파일 감사합니다", "CSV는 엑셀에서 바로 열 수 있나요?", "표로 정리해 줘",
               "엑셀로 열어 보니"):  # fmt: skip
        assert not TABLE_FILE.search(no), no


def test_youth_rank_has_solo_and_homebound_and_each_dong_means_rank():
    # 【기능】 q04 T2 '혼자 사는 청년 많은 동' → '없어요'(1인세대 있음),
    #        T3 '동별로 집에만 있는 청년' → '어느 동?'
    #        → 청년 줄 세우기에 1인세대 · 어림 순서도, '동별'이면 줄 세우기
    from src.assistant.librarian import gather
    from src.assistant.policy import desk_sanity
    from src.assistant.slots import Slots

    text = gather("youth", Slots(region="춘천시", rank=True), JsonDongData()).text
    assert "청년 1인세대" in text and "거의 집에만 있는 청년 어림" in text
    card, _ = desk_sanity(
        DeskCard(act="ask", topics=("youth",)), "춘천 동별로 집에만 있는 청년 어림"
    )
    assert card.rank
    card, _ = desk_sanity(DeskCard(act="ask", topics=("youth",)), "퇴계동 청년 동별로")
    assert not card.rank  # 동을 말했으면 그 동


def test_threshold_days_carry_their_values():
    # 【기능】 q02 T4 '한파 넘은 6일 각각 최저기온과 제일 추운 날'에
    #        '날짜별 최저기온은 자료에 없어요'
    #        (관측 기록은 날마다 있음) → 기준 넘은 날마다 값과 가장 심한 날을 함께
    import re
    from datetime import date

    from src.assistant.librarian import _kind_days

    line = _kind_days("강남구", JsonDongData().weather(), "한파", date.today())
    # 10-20: 넘은 날 전부 대신 가장 최근 다섯 날(그날 값과 함께) + 가장 심한 날
    assert len(re.findall(r"\d{2}-\d{2}\(-?\d+(?:\.\d)?℃\)", line)) >= 5
    assert "가장 낮은 날" in line and "외 " in line


def test_same_lines_not_repeated_across_topics():
    # 【기능】 q02 T1: 먼저 볼 동 + 동 상황이 둘 다 날씨 줄을 붙여 같은 줄이 두 번 나감
    from src.assistant.engine import dedupe_facts
    from src.assistant.librarian import gather
    from src.assistant.slots import Slots

    s = Slots(region="강남구", weather="추위")
    facts = dedupe_facts([gather(t, s, JsonDongData()) for t in ("priority", "dong_overview")])
    lines = [ln for f in facts for ln in f.lines]
    assert len(lines) == len(set(lines))


def test_dedupe_keeps_dong_header_lines():
    from src.assistant.engine import dedupe_facts

    a = Facts(title="가", lines=["[강남구 수서동]", "- 같은 줄"])
    b = Facts(title="나", lines=["[강남구 수서동]", "- 같은 줄", "- 다른 줄"])
    dedupe_facts([a, b])
    assert b.lines == ["[강남구 수서동]", "- 다른 줄"]


def test_chuncheon_village_names_map_to_myeon():
    # 【기능】 q06 T4 '율문리 · 발산리 버스'에 '율문리는 목록에 없어요. 일원1동?'
    #        → 경로당 이름의 마을(리) → 읍면.
    #        두 읍면에 다 있는 마을(발산리)은 짐작하지 않고 되묻는다
    from src.assistant import dongname

    r = dongname.resolve("율문리")
    assert r["dongs"] == ["신북읍"] and r["how"].startswith("마을")
    assert dongname.resolve("율문4리")["dongs"] == ["신북읍"]
    amb = dongname.resolve("발산리")
    assert amb["dongs"] == [] and set(amb["near"]) == {"신북읍", "남면"}
    assert dongname.resolve("수서동")["dongs"] == ["수서동"]


def test_village_note_before_answer(tmp_path):
    from src.assistant.writer import TemplateWriter

    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    card = DeskCard(act="ask", topics=("bus",), dong_op="set", dong_mentions=("율문리",))
    e = Engine(FakeDesk({"율문리 버스 몇 번 와요": card}), TemplateWriter(), JsonDongData(),
               MemoryStore(), s)  # fmt: skip
    e.start("v", Profile(member_region="춘천시"))
    r = e.turn("v", "율문리 버스 몇 번 와요")
    assert r.kind == "answer"
    assert "율문리는 신북읍의 마을이라 신북읍으로 볼게요" in r.text


def test_bus_note_route_names_are_destination_myeon():
    # 【기능】 q06 T3: 신북읍 버스에 북산2 · 사북2가 나와 '북산 · 사북은 다른 면 아니에요?'로 헷갈림
    from src.assistant.librarian import gather
    from src.assistant.slots import Slots

    f = gather("bus", Slots(region="춘천시", dongs=("신북읍",)), JsonDongData())
    assert any("가는 면 이름" in n for n in f.notes)
