"""10-28 배포 사이트 점검 — 프록시 뒤 로그인 쿠키 Secure · 시험 메일함은 그 컴퓨터에서만."""

from test_auth_flow import EMAIL, PW, _signup, client, db_maker  # noqa: F401 — 픽스처를 같이 쓴다

PROXY = {"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"}


def _login_cookie(c, headers=None) -> str:
    r = c.post(
        "/api/auth/login", json={"login_id": "hong07", "password": PW}, headers=headers or {}
    )
    assert r.status_code == 200, r.text
    return r.headers.get("set-cookie", "")


def test_cookie_is_secure_behind_https_proxy(client):  # noqa: F811
    assert _signup(client).status_code == 200
    plain = _login_cookie(client)
    assert "salpim_session=" in plain and "secure" not in plain.lower()
    behind = _login_cookie(client, {"X-Forwarded-Proto": "https"})
    assert "secure" in behind.lower() and "httponly" in behind.lower()
    cf = _login_cookie(client, {"CF-Visitor": '{"scheme":"https"}'})
    assert "secure" in cf.lower()


def test_dev_outbox_only_on_this_computer(client):  # noqa: F811
    assert client.get("/api/auth/dev/outbox").status_code == 200
    assert client.get("/api/auth/dev/outbox", headers=PROXY).status_code == 404
    assert (
        client.get("/api/auth/dev/outbox", headers={"CF-Connecting-IP": "1.2.3.4"}).status_code
        == 404
    )


def test_dev_mode_code_send_from_outside_says_mail_not_set(client):  # noqa: F811
    body = {"purpose": "signup", "email": "kim01@korea.kr", "name": "김철수"}
    r = client.post("/api/auth/code/send", json=body, headers=PROXY)
    assert r.status_code == 503 and r.json()["field"] == "email" and "관리자" in r.json()["error"]
    # 그 컴퓨터에서는 그대로(시험 메일함 안내)
    r = client.post("/api/auth/code/send", json=body)
    assert r.status_code == 200 and r.json()["dev_outbox"] == "/api/auth/dev/outbox"
    assert EMAIL  # 같은 픽스처 묶음
