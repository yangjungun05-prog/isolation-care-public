"""비밀번호 해시 · 인증번호 해시 · 서명한 표(로그인 쿠키 · 인증 마친 표).

【판단】 비밀번호는 표준 라이브러리 scrypt 로 저장한다 — 공용 저장소에 새 패키지를 더하지 않으려고.
       솔트는 회원마다 따로, 비교는 걸리는 시간이 같은 compare_digest
【판단】 로그인은 DB 표 없이 서명한 쿠키로 한다(ERD 에 세션 표가 없다). 쿠키에 비밀번호 해시의 앞
       8글자에서 만든 값을 넣어, 비밀번호를 바꾸면 그 전 쿠키는 저절로 못 쓰게 한다
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from src.auth.config import settings

_N, _R, _P = 2**14, 8, 1


def _now_ts() -> float:
    return time.time()  # 시험이 시각을 앞으로 돌릴 수 있게 한곳에서


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(dk)}"


def check_password(password: str, stored: str) -> bool:
    try:
        name, n, r, p, salt, dk = stored.split("$")
        assert name == "scrypt"
        got = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
    except (ValueError, AssertionError):
        return False
    return hmac.compare_digest(got, _unb64(dk))


def password_tag(stored: str) -> str:
    """쿠키에 넣는 비밀번호 표시(비밀번호를 바꾸면 달라진다). 해시 자체는 쿠키에 넣지 않는다."""
    return hmac.new(settings.secret, stored.encode("utf-8"), hashlib.sha256).hexdigest()[:12]


def code_hash(email: str, purpose: str, code: str) -> str:
    # 【판단】 6자리 숫자는 경우의 수가 적어 그냥 해시하면 금방 거꾸로 찾는다 → 비밀 글자로 서명
    msg = f"{email}|{purpose}|{code}".encode()
    return hmac.new(settings.secret, msg, hashlib.sha256).hexdigest()


def ip_hash(ip: str | None) -> str | None:
    if not ip:
        return None
    return hmac.new(settings.secret, ip.encode("utf-8"), hashlib.sha256).hexdigest()


def sign(purpose: str, data: dict, minutes: int) -> str:
    body = dict(data, p=purpose, exp=int(_now_ts() + minutes * 60))
    raw = _b64(json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return f"{raw}.{_mac(raw)}"


def unsign(purpose: str, token: str | None) -> dict | None:
    """서명이 맞고 · 쓰임이 같고 · 시간이 남았으면 내용을, 아니면 None."""
    if not token or "." not in token:
        return None
    raw, mac = token.rsplit(".", 1)
    if not hmac.compare_digest(mac, _mac(raw)):
        return None
    try:
        body = json.loads(_unb64(raw))
    except ValueError:
        return None
    if body.get("p") != purpose or body.get("exp", 0) < _now_ts():
        return None
    return body


def _mac(raw: str) -> str:
    return hmac.new(settings.secret, raw.encode("ascii"), hashlib.sha256).hexdigest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
