import os
from types import SimpleNamespace

# 【판단】 회원 기능(src/auth)의 서명 비밀 글자 — 시험이 저장소에 .auth_secret 파일을 만들지 않게
#        설정을 읽기 전에 정해 둔다(로그인 쿠키 · 인증 표는 시험 안에서만 쓴다)
os.environ.setdefault("AUTH_SECRET", "test-secret-test-secret-test-secret")
os.environ.setdefault("MAIL_MODE", "dev")

import pytest  # noqa: E402

from src.assistant import catalog, ledger, librarian, today  # noqa: E402
from src.assistant import forecast as fc  # noqa: E402
from src.assistant.catalog import Topic  # noqa: E402
from src.auth import routes as auth_routes  # noqa: E402

REAL_REQUIRE_MEMBER = auth_routes.require_member


@pytest.fixture(autouse=True)
def _ledger_to_tmp(monkeypatch, tmp_path):
    """시험이 진짜 API 장부(api_usage/)에 적거나 그 합계로 막히지 않게 장부를 임시 폴더로 돌린다."""
    monkeypatch.setenv("API_LEDGER_DIR", str(tmp_path / "api_usage"))
    # 【판단】 10-20: 다시 쓰기(writer._retry)를 더하자 llm.call 을 가짜로 바꾸지 않은 시험 둘이
    #        진짜 API를 불렀고, 장부가 임시 폴더라 진짜 장부에 남지 않았다(4번 $0.00077,
    #        뒤에 옮겨 적음).
    #        시험에서는 키를 비워 진짜 API를 부를 수 없게 한다
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    # 【판단】 10-24 기본 길이 CLI가 됐다. 시험은 CLI도 부르지 않게 API 길(키 비움 → 오류)로 둔다.
    #        CLI 길은 tests/test_cli_1024.py가 가짜 실행으로 따로 본다
    monkeypatch.setenv("BISU_LLM", "api")
    monkeypatch.delenv("API_LEDGER_OTHER_DIRS", raising=False)
    ledger.reset_cache()
    yield
    ledger.reset_cache()


@pytest.fixture
def not_ready(monkeypatch):
    """시험 동안만 있는 '연결 전' 주제 둘(받침 없음 · 있음).

    【판단】 10-13 갈 곳 · 버스 · 동 상황 문서를 잇고 날씨를 동 상황의 조건으로 합치면
           진짜 '연결 전' 주제가 남지 않는다.
           다음에 서가를 더할 때 쓰는 '연결 전' 안내 기능은 이 가짜 주제로 지킨다
    """
    a = Topic("future_a", "다음에 이을 서가", "시험용", "dong", ready=False)
    b = Topic("future_b", "다음 자료함", "시험용", "dong", ready=False)
    monkeypatch.setitem(catalog.BY_ID, a.id, a)
    monkeypatch.setitem(catalog.BY_ID, b.id, b)
    return a.id, b.id


class _NoNetWx:
    """시험은 기상청을 부르지 않는다(10-19: 챗봇 날씨도 진짜 오늘 예보를 받게 되며 더함).
    예보가 필요한 시험은 librarian.WX · today.cards(wx=…)에 가짜를 넣는다."""

    def forecast(self, grids):
        raise fc.ForecastError("시험: 기상청을 부르지 않음")

    def warnings(self, region):
        raise fc.ForecastError("시험: 기상청을 부르지 않음")


@pytest.fixture(autouse=True)
def _no_network_weather(monkeypatch):
    monkeypatch.setattr(librarian, "WX", _NoNetWx())
    monkeypatch.setattr(today, "_LIVE", _NoNetWx())


@pytest.fixture(autouse=True)
def _logged_in(request, monkeypatch):
    """대시보드 · 시뮬레이션 · 비서 API 시험은 로그인한 회원으로 돈다.

    【판단】 10-25 이 API 들이 로그인한 회원만 쓰게 바뀌었다(src/auth). 로그인 자체 · 막힘은
           tests/test_auth_*.py 가 진짜 쿠키로 보므로 거기서는 바꿔 끼우지 않는다
    """
    if request.module.__name__.startswith("test_auth"):
        yield
        return
    from src.api import main

    member = SimpleNamespace(member_id=1, login_id="tester", name="시험 회원", kind="공공")
    monkeypatch.setattr(auth_routes, "require_member", lambda: member)  # 비서 서버(create_app)
    main.app.dependency_overrides[REAL_REQUIRE_MEMBER] = lambda: member  # 본 서버(main.app)
    yield
    main.app.dependency_overrides.pop(REAL_REQUIRE_MEMBER, None)
