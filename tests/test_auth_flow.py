"""회원가입 → 로그인 → 찾기 · 재설정을 API 로 끝까지 + 로그인해야 쓰는 화면(10-25).

스토리보드 COM-100 ~ 161 · CHT-AUTH · CHT-SESS. 회원 기능은 regionse/BIGCONTEST_AUTH 에서 만들어
시험한 것을 옮겼다.

【판단】 CI 에는 PostgreSQL 이 없다(DATABASE_URL 은 모양만) → 회원 표만 SQLite 임시 DB 에 만들고
       get_db 를 그쪽으로 바꿔 끼운다. 표 모양은 공용 src/common/models.py 그대로
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api import main
from src.auth import mailer, rules, secrets_util
from src.common.database import Base, get_db
from src.common.models import (
    Dong,
    EmailCode,
    LoginLog,
    Member,
    MemberRegion,
    Org,
    Region,
    TermsAgree,
)
from src.common.regions import seed_regions

TABLES = [Region, Dong, Org, Member, MemberRegion, TermsAgree, EmailCode, LoginLog]


@pytest.fixture
def db_maker(tmp_path):
    eng = create_engine(
        f"sqlite:///{(tmp_path / 'auth.db').as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(eng, tables=[t.__table__ for t in TABLES])
    maker = sessionmaker(eng, expire_on_commit=False)
    with maker.begin() as db:
        seed_regions(db)
    return maker


def _use(app, maker) -> None:
    def _db():
        with maker.begin() as s:
            yield s

    app.dependency_overrides[get_db] = _db


@pytest.fixture
def client(db_maker, tmp_path, monkeypatch):
    monkeypatch.setattr(mailer, "OUTBOX", tmp_path / "outbox")
    mailer.SENT.clear()
    _use(main.app, db_maker)
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.pop(get_db, None)


def last_code(email: str) -> str:
    """시험 메일함(MAIL_MODE=dev)에서 그 주소로 온 마지막 인증번호."""
    for item in reversed(mailer.SENT):
        if item["to"] == email and "인증번호" in item["subject"]:
            return item["subject"].split()[-1]
    raise AssertionError(f"{email} 로 온 인증번호가 없다")


EMAIL = "hong07@korea.kr"
PW = "Salpim#2026"
DONGS = ["11230750", "11230730"]  # 수서동 · 일원1동


def _ticket(c, email=EMAIL, name="홍길동"):
    r = c.post("/api/auth/code/send", json={"purpose": "signup", "email": email, "name": name})
    assert r.status_code == 200, r.text
    r = c.post(
        "/api/auth/code/verify",
        json={"purpose": "signup", "email": email, "name": name, "code": last_code(email)},
    )
    assert r.status_code == 200, r.text
    return r.json()["ticket"]


def _signup(c, login_id="hong07", email=EMAIL, **over):
    body = {
        "ticket": _ticket(c, email),
        "login_id": login_id,
        "password": PW,
        "password2": PW,
        "dongs": DONGS,
        "job": "사회복지 공무원",
        "terms": {"use": True, "privacy": True, "marketing": False},
    }
    body.update(over)
    return c.post("/api/auth/signup", json=body)


@pytest.fixture
def clock(monkeypatch):
    """clock(분) — 시험을 시작한 때에서 그만큼 지난 시각으로(DB 시각과 쿠키 시각 둘 다)."""
    base_now, base_ts = rules.now(), secrets_util._now_ts()

    def at(minutes: float) -> None:
        monkeypatch.setattr(rules, "now", lambda: base_now + timedelta(minutes=minutes))
        monkeypatch.setattr(secrets_util, "_now_ts", lambda: base_ts + minutes * 60)

    return at


def test_dong_codes_used_in_tests_exist(client):
    names = {d["dong_cd"]: d["name"] for r in client.get("/api/auth/dongs").json()["regions"]
             for d in r["dongs"]}  # fmt: skip
    assert names["11230750"] == "수서동" and names["11230730"] == "일원1동" and len(names) == 47


def test_signup_then_login_then_me(client):
    r = _signup(client)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["dongs"] == ["수서동", "일원1동"]
    assert client.get("/api/auth/me").status_code == 401  # 가입만 했고 로그인 전
    r = client.post("/api/auth/login", json={"login_id": "hong07", "password": PW})
    assert r.status_code == 200 and r.json()["member"]["name"] == "홍길동"
    me = client.get("/api/auth/me").json()["member"]
    assert [x["dong"] for x in me["regions"]] == ["수서동", "일원1동"]
    assert client.get("/api/meta").status_code == 200  # 로그인한 회원만 쓰는 API
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["detail"]["code"] == "login_required"


def test_signup_reports_every_bad_field(client):
    # COM-140E1: 아이디 중복 · 특수문자 없음 · 확인 불일치(비밀번호가 먼저라 빠짐) · 담당 지역 없음
    r = _signup(client, login_id="admin", password="abcdefgh12", password2="x", dongs=[])
    j = r.json()
    assert r.status_code == 400 and set(j["fields"]) == {"login_id", "password", "dongs"}
    assert j["fields"]["login_id"] == "이미 쓰는 아이디입니다."
    assert j["error"] == "고칠 곳이 3곳 있습니다. 빨간 칸을 확인하세요."


def test_anyone_can_join_without_org(client, db_maker):
    # 【정함 10-25 팀장】 회원 유형 · 기관 코드 없이 누구나(이메일 인증만) — kind '일반', 기관 비움
    assert _signup(client, email="anyone@gmail.com").status_code == 200
    with db_maker.begin() as db:
        m = db.query(Member).one()
        assert m.kind == "일반" and m.org_id is None and m.email == "anyone@gmail.com"
    assert client.get("/api/auth/org?code=GN-4827").status_code in (404, 405)  # 기관 코드 확인 없앰


def test_required_terms_and_taken_email(client, clock):
    r = _signup(client, terms={"use": True, "privacy": False})
    assert r.json()["fields"]["terms"] == "필수 약관에 모두 동의해 주세요."
    clock(2)  # 인증번호는 1분에 한 번만 받을 수 있다
    assert _signup(client).status_code == 200
    r = client.post(
        "/api/auth/code/send", json={"purpose": "signup", "email": EMAIL, "name": "홍길동"}
    )
    assert r.status_code == 400 and r.json()["taken"]  # COM-130 ①: 이미 가입된 이메일


def test_code_rules_wrong_five_times_resend_and_expiry(client, clock):
    send = {"purpose": "signup", "email": EMAIL, "name": "홍길동"}
    client.post("/api/auth/code/send", json=send)
    r = client.post("/api/auth/code/send", json=send)
    assert r.status_code == 400 and r.json()["wait"] > 0  # 1분에 한 번
    bad = dict(send, code="000000" if last_code(EMAIL) != "000000" else "111111")
    for i in range(1, 6):
        assert client.post("/api/auth/code/verify", json=bad).json()["tries"] == i
    good = dict(send, code=last_code(EMAIL))
    assert client.post("/api/auth/code/verify", json=good).json().get("spent")  # 맞아도 못 씀
    clock(2)
    assert client.post("/api/auth/code/send", json=send).status_code == 200  # 새 번호
    clock(10)  # 새 번호(2분)에서 8분 — 5분이 지남
    r = client.post("/api/auth/code/verify", json=dict(send, code=last_code(EMAIL)))
    assert r.json().get("expired")


def test_login_counts_locks_and_unlocks_after_30_minutes(client, clock):
    _signup(client)
    wrong = {"login_id": "hong07", "password": "Wrong#2026"}
    for i in range(1, 5):
        j = client.post("/api/auth/login", json=wrong).json()
        assert j["count"] == i and j["left"] == 5 - i and f"({i}/5회)" in j["error"]
    j = client.post("/api/auth/login", json=wrong).json()
    assert j["locked"]  # COM-100E2
    ok = {"login_id": "hong07", "password": PW}
    assert client.post("/api/auth/login", json=ok).json().get("locked")  # 잠긴 동안은 맞아도 막음
    clock(31)
    assert client.post("/api/auth/login", json=ok).status_code == 200


def test_unknown_id_looks_the_same(client):
    # COM-100E1 ②: 무엇이 틀렸는지 · 그런 아이디가 있는지 알려 주지 않는다
    j = client.post("/api/auth/login", json={"login_id": "nobody9", "password": "x"}).json()
    assert (
        j["error"] == "아이디 또는 비밀번호가 맞지 않습니다. (1/5회)" and j["field"] == "password"
    )
    for _ in range(4):
        j = client.post("/api/auth/login", json={"login_id": "nobody9", "password": "x"}).json()
    assert j["locked"]


def test_find_id_masks_and_mails_full_id_and_hides_unknown(client):
    _signup(client)
    send = {"purpose": "find_id", "email": EMAIL, "name": "홍길동"}
    assert client.post("/api/auth/code/send", json=send).status_code == 200
    r = client.post("/api/auth/code/verify", json=dict(send, code=last_code(EMAIL)))
    assert r.json()["masked"] == "ho***7"
    assert "hong07" in mailer.SENT[-1]["body"]  # 전체 아이디는 메일로
    n = len(mailer.SENT)
    other = {"purpose": "find_id", "email": "who@korea.kr", "name": "누구"}
    r = client.post("/api/auth/code/send", json=other)
    assert r.status_code == 200 and len(mailer.SENT) == n  # 보냈다고만 하고 실제로는 안 보냄


def test_reset_password_unlocks_and_ends_old_login(client):
    _signup(client)
    client.post("/api/auth/login", json={"login_id": "hong07", "password": PW})
    old = client.cookies.get("salpim_session")
    for _ in range(5):
        client.post("/api/auth/login", json={"login_id": "hong07", "password": "Wrong#2026"})
    send = {"purpose": "reset_pw", "email": EMAIL, "login_id": "hong07"}
    client.post("/api/auth/code/send", json=send)
    t = client.post("/api/auth/code/verify", json=dict(send, code=last_code(EMAIL))).json()[
        "ticket"
    ]
    new = "Salpim#2027"
    bad = client.post("/api/auth/password/reset", json={"ticket": t, "password": "hong07#Aa1",
                                                        "password2": "hong07#Aa1"})  # fmt: skip
    assert bad.json()["error"] == "비밀번호에 아이디를 넣을 수 없어요."
    r = client.post(
        "/api/auth/password/reset", json={"ticket": t, "password": new, "password2": new}
    )
    assert r.status_code == 200
    client.cookies.set("salpim_session", old)
    assert client.get("/api/auth/me").json()["detail"]["code"] == "session_expired"  # 옛 쿠키
    assert client.post("/api/auth/login", json={"login_id": "hong07", "password": new}).json()["ok"]


def test_login_lasts_a_month_and_activity_extends(client, clock):
    # 10-24 팀장 "로그인은 한 달로 두자"(스토리보드 CHT-SESS)
    day = 24 * 60
    _signup(client)
    client.post("/api/auth/login", json={"login_id": "hong07", "password": PW})
    clock(20 * day)
    assert client.get("/api/auth/me").status_code == 200  # 쓰는 동안은 한 달이 다시 늘어남
    clock(45 * day)  # 마지막 요청(20일)에서 25일
    assert client.get("/api/auth/me").status_code == 200
    clock(80 * day)  # 마지막 요청(45일)에서 35일
    r = client.get("/api/board?region=강남구")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "session_expired"  # CHT-SESS


# ── 10-25 팀장 "시뮬레이션이나 이런것들 로그인해야지만 가능하게" ──


def test_dashboard_and_simulation_need_login(client):
    for path in ["/api/meta", "/api/board?region=강남구", "/api/geo?region=강남구"]:
        r = client.get(path)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "login_required", path
    r = client.post("/api/simulation/read", json={"text": "x"})
    assert r.status_code == 401
    _signup(client)
    client.post("/api/auth/login", json={"login_id": "hong07", "password": PW})
    assert client.get("/api/meta").status_code == 200
    assert client.get("/api/board?region=강남구").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/meta").status_code == 401


def test_assistant_needs_the_same_login(client, db_maker):
    from src.api.assistant import create_app

    app = create_app(engine=object())  # 엔진은 부르지 않는다(로그인만 본다)
    _use(app, db_maker)
    with TestClient(app) as ac:
        assert ac.get("/assistant/me").status_code == 401
        assert ac.get("/assistant/dongs").status_code == 401
        r = ac.post("/assistant/chat", json={"session_id": "s1", "text": "수서동 어르신"})
        assert r.status_code == 401
        assert ac.get("/").status_code == 200  # 화면은 열리고, 화면이 로그인 안내를 보인다
        _signup(client)
        client.post("/api/auth/login", json={"login_id": "hong07", "password": PW})
        # 본 서버(8000)에서 받은 쿠키를 비서 서버(8010)도 읽는다(같은 호스트 · 같은 비밀 글자)
        ac.cookies.set("salpim_session", client.cookies.get("salpim_session"))
        me = ac.get("/assistant/me").json()["member"]
        assert me["name"] == "홍길동" and [x["dong"] for x in me["regions"]] == [
            "수서동",
            "일원1동",
        ]


def test_auth_db_saves_before_the_response():
    # 10-25: yield 의존성은 기본이 '응답 뒤에 닫기'라 가입 직후 바로 로그인하면 아직 저장 전이었다
    from src.auth import routes

    assert routes.DB.__metadata__[0].scope == "function"
