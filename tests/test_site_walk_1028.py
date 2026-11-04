"""10-28 배포 사이트 점검에서 찾은 것 — 날씨 오류 글 · 회원 화면 짧은 주소 · 인증번호 받기 막힘."""

from pathlib import Path

from src.assistant.today import weather_error

WEB = Path(__file__).parents[1] / "web"


def test_weather_error_hides_setting_name_and_dedupes():
    msg = weather_error(
        [
            "공공데이터포털 키(DATA_GO_KR_SERVICE_KEY)가 없음",
            "공공데이터포털 키(DATA_GO_KR_SERVICE_KEY)가 없음",
        ]
    )
    assert "DATA_GO_KR" not in msg and msg.count("기상청 자료 연결 설정") == 1
    assert weather_error(["예보를 못 받은 곳 2곳"]) == "예보를 못 받은 곳 2곳"


def test_auth_screen_fixes_are_in_place():
    js = (WEB / "auth.js").read_text(encoding="utf-8")
    # 멈춘 서버에 시간 제한 · 숨은 칸 대신 이메일 칸 아래 · 짧은 주소
    assert "AbortController" in js and "서버가 응답하지 않아요" in js
    assert "if (box.hidden) onSent && onSent(r);" in js
    assert "signup: signup2, find: findId" in js
    assert "auth.js?v=1028a" in (WEB / "index.html").read_text(encoding="utf-8")
