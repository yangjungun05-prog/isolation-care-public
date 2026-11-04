"""화면 문구가 실제 계산과 맞는지 — 스토리보드 문구를 그대로 옮겼다가 사실과 달라진 곳을 막는다."""

from pathlib import Path

from src.dashboard import grades

WEB = Path(__file__).parents[1] / "web"
JS = (WEB / "app.js").read_text(encoding="utf-8")


def test_no_daily_schedule_claim():
    # 【판단】 예약 계산이 없다 — 기준일은 나우캐스트 자료의 마지막 주로 고정
    assert "매일 06:00" not in JS
    assert "나우캐스트 자료의 마지막 주" in JS


def test_no_weather_in_expected_range():
    # 【판단】 예상 범위는 공휴일만 빼고 날씨는 넣지 않았다 — 넣었다는 말이 있으면 안 된다
    for phrase in ["날씨·공휴일을 넣어", "날씨 · 공휴일을 넣어", "날씨 예보와 달력을 넣는"]:
        assert phrase not in JS
    assert "날씨는 넣지 않았어요" in JS


def test_risk_rule_matches_code():
    # 【기능】 화면 도움말은 API 의 rules 를 그대로 쓴다 → 규칙 글이 DSH-100H 와 같아야 한다
    assert grades.RULE["위험"] == "경고가 연휴가 끝나고 1주가 지나도 이어져요"
    assert "B.rules[g]" in JS


def test_rules_say_what_and_compared_to_what():
    # 【판단】 등급 글에는 무엇(카드 이용 수준)과 무엇에 비해(평소)가 있어야 한다 —
    #   "절반도 안 됨"만으로는 무엇의 절반인지 알 수 없다(10/23 사용자 지적)
    for g in ["경고", "주의", "관심", "평상"]:
        assert "카드 이용 수준" in grades.RULE[g] and "평소" in grades.RULE[g], g
    # 코드와 같은 수: 주의 = 4주 중 3주 이상, 경고 = 2주 중 절반 넘게
    assert "3주 이상" in grades.RULE["주의"] and "절반 넘게" in grades.RULE["경고"]
    # 옛 문구가 화면에 남아 있지 않다
    for old in ["예상보다 많이 낮음", "예상한 값과 실제 값", "예상 범위 안"]:
        assert old not in JS


def test_cost_row_uses_engine_cost():
    # 【판단】 결과 표의 1인당 비용은 계산에 쓴 값(used.cost)이어야 한다 — 10-25 종류와 상관없이
    #   100 · 102 · 105만원(1.025 배씩)으로 고정돼 있었다(함께 모이는 활동은 14 ~ 35만원)
    assert "1.025 **" not in JS
    assert "s.live?.used" in JS and "used.cost_range" in JS


def test_first_screen_after_login_is_dashboard():
    # 【판단】 11-02 사용자 "처음 로그인하고 나오는 화면은 대시보드로" — 로그인 없이 첫 주소를 열면
    #   돌아갈 곳을 render 가 먼저 적어 두므로, index.html 의 home 만 바꾸면 비서로 간다
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'home: "dashboard"' in html
    assert '"") || "dashboard"' in JS
    assert '|| "assistant"' not in JS
