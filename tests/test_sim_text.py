"""설명글 읽기(SIM-102 · 103)와 설명글 숫자 검사(SIM-107) — 재료 파일 없이 돈다."""

from src.simulation.text import check_numbers, money_text, read_text, write_paragraph

FORM = {
    "freq": "주 2회",
    "years": 2,
    "kind": "찾아가서 살피기(방문)",
    "who": "80세 이상 혼자 사는 분",
}


def test_form_text_has_no_questions():
    # 대조 — 칸으로 만든 기본 글은 칸과 같다
    t = "일원1동·수서동 80세 이상 혼자 사는 분께 주 2회 찾아가 안부를 살피고 병원 동행을 돕는다."
    assert read_text(t, FORM)["questions"] == []


def test_mismatch_asks():
    # SIM-102 예시 — 칸 주 2회 ↔ 글 주 3회
    q = read_text("수서동 80세 이상 혼자 사는 분께 주3회 찾아감", FORM)["questions"]
    assert q == [{"field": "freq", "label": "횟수", "form": "주 2회", "text": "주 3회"}]


def test_unknown_kind_and_cap():
    # SIM-103 예시 — 교실 → 함께 모이는 활동. 다른 것이 셋이어도 묻는 것은 둘까지
    r = read_text("65세 이상 어르신 경로당 운동 교실을 주 1회 3년", FORM)
    assert r["found"]["kind"] == "함께 모이는 활동"
    assert len(r["questions"]) == 2 and len(r["assumed"]) == 2
    # 종류 낱말이 없으면 칸의 종류를 빌려 쓴다
    assert read_text("동네 어르신을 돕는다", FORM)["guess"] == FORM["kind"]


def test_money_mismatch_asks():
    # SIM-102 — 돈 칸 800만원 ↔ 글 500만원이면 멈춰 묻는다
    form = {**FORM, "money": 800}
    q = read_text("수서동 80세 이상 혼자 사는 분께 주 2회 찾아가 살핀다. 1년 500만원", form)[
        "questions"
    ]
    assert q == [{"field": "money", "label": "돈 (1년)", "form": 800, "text": 500}]
    # 대조 — 같은 돈이면 묻지 않는다(800 과 800.0, '8백'이 아닌 '800만 원' 띄어 쓰기도)
    same = read_text("주 2회 찾아가 살핀다. 연 800만 원", form)
    assert same["questions"] == [] and same["found"]["money"] == 800
    # 대조 — 돈 칸이 비어 있으면 묻지 않고 글의 돈을 알려만 준다(화면이 칸을 채운다)
    empty = read_text("주 2회 찾아가 살핀다. 1년 500만원", {**FORM, "money": None})
    assert empty["questions"] == [] and empty["found"]["money"] == 500


def test_money_words():
    # 억 · 천만 · 쉼표 · 소수 — 만원 단위로 읽는다. '1만 명'처럼 사람 수는 돈이 아니다
    cases = {
        "1년 1,200만원": 1200,
        "연 1억 2천만 원": 12000,
        "1.5억": 15000,
        "5천만원": 5000,
        "80세 이상 1만 명에게": None,
    }
    for t, want in cases.items():
        assert read_text(t, FORM)["found"].get("money") == want, t


RES = {
    "input": {
        "dongs": ["일원1동", "수서동"],
        "who": "80세 이상 혼자 사는 분",
        "kind": "찾아가서 살피기(방문)",
        "money": 10000,
        "years": 2,
    },
    "plan": {"final": {"p10": 0.0, "median": 0.5, "p90": 2.0}},
    "tornado": {"rows": [{"name": "누구부터 만나나"}]},
}


def test_numbers_paragraph_ok():
    para = write_paragraph(RES)
    assert "0.0~2.0명" in para and "가운데 0.5명" in para and "1년 1억을" in para
    assert "10,000만원" not in para
    assert check_numbers(para, RES) == []


def test_money_text():
    # 1억 이상은 억으로(소수 둘째 자리까지), 그 아래는 만원 그대로
    assert [money_text(m) for m in (10_000, 18_200, 15_000, 800, 5_600)] == [
        "1억",
        "1.82억",
        "1.5억",
        "800만원",
        "5,600만원",
    ]
    # 억으로 쓴 숫자도 숫자 검사를 통과하고, 바꿔치기는 잡는다
    res = {**RES, "input": {**RES["input"], "money": 18_200}}
    para = write_paragraph(res)
    assert "1년 1.82억을" in para and check_numbers(para, res) == []
    assert check_numbers(para.replace("1.82억", "2.82억"), res) == ["2.82"]


def test_numbers_catch_swap():
    # 대조 — 숫자 하나를 바꿔치기하면 잡아낸다(동 이름 속 숫자 '1동'은 잡지 않는다)
    para = write_paragraph(RES).replace("가운데 0.5명", "가운데 5.5명")
    assert check_numbers(para, RES) == ["5.5"]
    assert check_numbers(write_paragraph(RES).replace("2.0명", "20명"), RES) == ["20"]


def test_youth_words():
    form = {"kind": "찾아가서 살피기(방문)", "who": "80세 이상 혼자 사는 분"}
    r = read_text("역삼1동 은둔 청년에게 사례관리를 한다", form)
    assert r["found"]["kind"] == "청년 관계 회복(사례관리)"
    assert r["found"]["who"] == "고립·은둔 청년(19~34세)"
