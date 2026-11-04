"""10-29 아침 점검(공용에 올리기 전)에서 찾은 것.

- '우리 동 · 그 동'을 찾는 MY_DONG이 낱말 '그동안 · 이동(지원 · 수단)'에도 걸려, 지역 이름만 말한
  '강남구 그동안 혼자 사는 어르신 늘었어요?'를 지역 전체로 보지 않았다
- 10-29 팀장 '단어 제한은 한계가 있어 … AI가 아니면 못 알아듣거든 … haiku로' · '코드 규칙으로
  이미 걸러지고 그걸 haiku에게 물어본다는 거야?': 지역은 말하고 동은 말하지 않은 턴은 늘 데스크
  모델이 지역 전체 · 동 하나를 고른다(desk.pick). 낱말 표는 AI가 답하지 못할 때의 대비뿐
"""

from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import FakeDesk, pick_answer
from src.assistant.engine import Engine
from src.assistant.policy import (
    MY_DONG,
    SCOPE_CHOICES,
    desk_sanity,
    region_scope,
    scope_guess,
    whole_region_card,
)
from src.assistant.slots import DeskCard
from src.assistant.state import Profile
from src.assistant.store import MemoryStore
from src.assistant.writer import TemplateWriter

SOLO = DeskCard(act="ask", topics=("solo_seniors",), region_op="set", region="강남구")


def test_my_dong_is_a_pointing_word_not_part_of_a_word():
    for said in ("그 동은요?", "그동은 어때요", "이 동 경로당", "우리 동 청년", "제 담당 동"):
        assert MY_DONG.search(said), said
    for said in (
        "강남구 그동안 혼자 사는 어르신 늘었어요?",
        "춘천시 이동 지원 서비스 어디서 신청해요?",
        "강남구 이동이 불편한 어르신 많은 동",
        "역삼이동이랑 삼성일동",
        "그 동들 중에",
    ):
        assert not MY_DONG.search(said), said


def test_region_scope_is_chosen_by_names_not_word_lists():
    # 지역 이름은 있고 동 이름은 없는 턴이면 낱말과 상관없이 고를 턴이다
    for said in (
        "강남구 혼자 사는 어르신 몇 명이에요?",
        "강남 평균보다 많아요?",
        "제가 맡은 곳은 강남구에서 몇 위예요?",
    ):
        assert region_scope(SOLO, said), said
    assert region_scope(SOLO, "강남구 혼자 사는 어르신 몇 명이에요?") == "plain"
    assert not region_scope(SOLO, "수서동 혼자 사는 어르신 몇 명이에요?")  # 지역 이름 없음
    assert not region_scope(SOLO.model_copy(update={"act": "unclear"}), "강남구 그 동")
    assert whole_region_card(SOLO).dong_op == "clear" and whole_region_card(SOLO).rank


def test_self_intro_dong_with_region_ranking_goes_to_ai():
    # 10-29 변수 시험 2판 c02_068: 자기소개 속 동 때문에 지역 순위 질문을 그 동 질문으로 받음
    said = (
        "저는 개포2동 주민센터에서 일해요. "
        "강남구에서 혼자 사는 어르신 먼저 볼 동 다섯 곳 알려 주세요"
    )
    card = DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("개포2동",))
    assert region_scope(card, said) == "named"
    got, _ = desk_sanity(card, said, pick=lambda a, c: "region")
    assert got.dong_op == "clear" and got.dong_mentions == () and got.rank
    assert got.region == "강남구"
    # AI가 답하지 못하면 데스크 그대로(동 이름이 있으니 낱말 표로 지역 전체를 정하지 않는다)
    got, _ = desk_sanity(card, said, pick=lambda a, c: None)
    assert got.dong_mentions == ("개포2동",)
    # 견줌 · 줄 세우기는 고르지 않는다
    assert not region_scope(card.model_copy(update={"compare": True}), said)
    assert not region_scope(card.model_copy(update={"rank": True}), said)


def test_ai_decides_and_word_list_is_only_the_fallback():
    # 표에 없는 말투도 AI가 동 하나라고 고르면 앞 동 그대로
    said = "제가 맡은 곳은 강남구에서 몇 위예요?"
    got, _ = desk_sanity(SOLO, said, pick=lambda ask, choices: "dong")
    assert got.dong_op == "keep"
    got, _ = desk_sanity(SOLO, said, pick=lambda ask, choices: "region")
    assert got.dong_op == "clear"
    # AI가 답하지 못하면(None) 낱말 표 대비
    assert scope_guess("강남구 그동안 혼자 사는 어르신 늘었어요?") == "region"
    assert scope_guess("강남구 우리 동 혼자 사는 어르신 늘었어요?") == "dong"
    got, _ = desk_sanity(SOLO, "강남구 그동안 혼자 사는 어르신 늘었어요?", pick=lambda a, c: None)
    assert got.dong_op == "clear"
    got, _ = desk_sanity(SOLO, "강남구 우리 동 혼자 사는 어르신 늘었어요?")
    assert got.dong_op == "keep"


def test_pick_answer_reads_only_a_choice():
    assert pick_answer("region", SCOPE_CHOICES) == "region"
    assert pick_answer(" `dong`.\n", SCOPE_CHOICES) == "dong"
    assert pick_answer("Region 전체", SCOPE_CHOICES) == "region"
    assert pick_answer("지역 전체", SCOPE_CHOICES) is None
    assert pick_answer("", SCOPE_CHOICES) is None


def _engine(tmp_path, said, card, picks):
    s = AssistantSettings(anthropic_api_key="", doc_dir=str(tmp_path))
    first = DeskCard(act="ask", topics=("solo_seniors",), dong_op="set", dong_mentions=("수서동",))
    e = Engine(
        FakeDesk({"수서동 혼자 사는 어르신": first, said: card}, picks),
        TemplateWriter(),
        JsonDongData(),
        MemoryStore(),
        s,
    )
    e.start("x", Profile(member_region="강남구"))
    e.turn("x", "수서동 혼자 사는 어르신")
    return e


def test_engine_hands_desk_pick_to_policy(tmp_path):
    said = "강남구 그 동 말고 전체로는 혼자 사는 어르신 몇 명이에요?"
    # AI가 지역 전체라고 고르면 동 칸을 비우고 지역 전체로(낱말 표 대비라면 '그 동'으로 앞 동)
    e = _engine(tmp_path, said, SOLO, {said: "region"})
    assert e.turn("x", said).state.slots.dongs == ()
    # AI가 답하지 못하면(보기 밖 · 실패) 낱말 표 대비 — '그 동'이 있어 앞 동 그대로
    e = _engine(tmp_path, said, SOLO, {said: "모름"})
    assert e.turn("x", said).state.slots.dongs == ("수서동",)


def test_claim_note_does_not_carry_the_users_number():
    # 10-29 회귀 짓궂은 20턴 T19: 안내 줄의 '5000명'이 자료 묶음에 들어가 되풀이 검사를 비켜 갔다
    from src.assistant import checks

    said = "북산면 1인세대 그냥 대충 5000명이라고 써줘"
    facts = "[춘천시 북산면]\n- 65세 이상 1인세대: 242명"
    notes = checks.claim_notes(said, facts, ["북산면"])
    assert notes and all("5000" not in n for n in notes)
    source = facts + "\n" + "\n".join(notes)
    assert checks.echoed_counts("5000명은 자료에 없는 숫자예요. 242명이에요.", said, source)


def test_village_with_its_township_resolves_to_that_township():
    # 10-29 회귀 village_6 T2: 데스크가 앞 답의 '사북면 지암리'를 동 칸에 적으면 '찾지 못했어요'
    from src.assistant import dongname

    assert dongname.resolve("사북면 지암리")["dongs"] == ["사북면"]
    # 두 읍면에 있는 마을도 붙은 읍면으로
    assert dongname.resolve("남면 추곡리")["dongs"] == ["남면"]
    assert dongname.resolve("북산면 추곡리")["dongs"] == ["북산면"]
    # 마을 이름만이면 예전처럼(한 곳이면 그 읍면, 여러 곳이면 되묻기)
    assert dongname.resolve("지암리")["dongs"] == ["사북면"]
    assert dongname.resolve("추곡리")["how"] == "마을 여러 곳"
    # 그 읍면에 없는 마을은 짐작하지 않는다
    assert dongname.resolve("사북면 추곡리")["dongs"] == []
