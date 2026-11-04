"""10-28 페르소나 p01_a T3: '사회복지관 이름과 연락처'의 '이름과'를 사람 이름으로 가렸다."""

from src.assistant import pii


def test_common_words_starting_with_lee_are_not_names():
    for t in (
        "사회복지관 이름과 연락처도 알려 주시겠어요?",
        "이름이 뭐예요",
        "이웃집 할머니가 걱정돼요",
        "이웃이 연락처를 몰라요",
        "이용 방법 알려줘",
    ):
        assert pii.mask(t) == (t, []), t


def test_real_names_are_still_masked():
    assert pii.mask("이영희 주소 알려줘")[1] == ["이름"]
    assert pii.mask("이순자 할머니 연락처")[0].startswith("[이름]")


def test_support_answer_has_no_population_basis():
    # 10-28 화면 확인: 주민센터 주소 답에 '주민등록 2026-09 · 상가 2026-06'이 붙었다
    from types import SimpleNamespace

    from src.assistant import extras
    from src.assistant.data_source import JsonDongData
    from src.assistant.librarian import Facts

    f = Facts(title="지원 기관 · 신청 창구", lines=["- 수서동 주민센터: 광평로 301-4"])
    data = JsonDongData()
    sup = extras.sources(SimpleNamespace(facts=[f], topics=("support",)), data)
    assert sup["items"] and sup["basis"] == ""
    ppl = extras.sources(SimpleNamespace(facts=[f], topics=("solo_seniors",)), data)
    assert ppl["basis"].startswith("주민등록 ")
