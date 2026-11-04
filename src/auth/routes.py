"""회원 API — /api/auth/*. 화면(web/auth.js)이 부른다.

    GET  /api/auth/me             지금 로그인한 회원
                                  (없으면 401 · code=login_required | session_expired)
    POST /api/auth/login          로그인 → 쿠키
    POST /api/auth/logout         로그아웃
    GET  /api/auth/check-id       아이디 중복 확인(COM-140)
    GET  /api/auth/dongs          담당 지역 고르기 목록
    GET  /api/auth/terms          약관 글(COM-120)
    POST /api/auth/code/send      인증번호 받기(가입 · 아이디 찾기 · 비밀번호 재설정)
    POST /api/auth/code/verify    인증번호 확인
    POST /api/auth/signup         가입 신청(COM-140 → 150)
    POST /api/auth/password/reset 새 비밀번호(COM-160)
    GET  /api/auth/dev/outbox     시험 메일함(MAIL_MODE=dev 일 때만 — 인증번호가 여기 온다)

다른 API 를 로그인한 사람만 쓰게 하려면 Depends(require_member) 를 붙인다.

【판단】 틀렸을 때는 400 + {"ok": false, "error": 화면에 보일 말, "field": 고칠 칸, ...}.
       AuthError 를 여기서 받아 정상 응답으로 돌려주므로, 그 전에 적은 실패 횟수 · 기록은 저장된다
【판단】 로그인 쿠키는 HttpOnly(화면 스크립트가 못 읽음) · SameSite=Lax(다른 사이트에서
       몰래 못 보냄).
       한 달 동안 요청이 없으면 끝나고, 요청이 있을 때마다 한 달이 다시 늘어난다
       (10-24 팀장 '한 달', 스토리보드 CHT-SESS)
"""

import html
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth import mailer, rules, service
from src.auth.config import settings
from src.auth.service import AuthError
from src.auth.terms import TEXTS
from src.common.database import get_db
from src.common.models import Dong, Member, Region

COOKIE = "salpim_session"
router = APIRouter(prefix="/api/auth", tags=["회원"])
# 【문법】 Annotated = 'DB 세션을 get_db 로 받는다'를 한 이름으로(인자 기본값에 함수를 부르지 않게)
# 【판단】 10-25 scope="function" — FastAPI 0.142 는 yield 의존성을 기본으로 '응답을 보낸 뒤'
#        닫아서 저장(commit)이 응답보다 늦었다. 가입 직후 바로 로그인하면 아직 없는 회원으로
#        한 번 틀렸다(진짜 DB로 확인). 응답 전에 저장을 끝낸다(저장이 실패하면 오류가 나간다)
DB = Annotated[Session, Depends(get_db, scope="function")]


def _fail(e: AuthError, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": e.message, "field": e.field, **e.extra}, status)


# 【판단】 10-28 배포 사이트 점검: 터널(https://…trycloudflare.com)로 열면 화면은 https 인데 서버는
#        뒤에서 http 로 받아, COOKIE_SECURE 를 따로 켜지 않으면 로그인 쿠키에 Secure 가 없었다
#        → https 로 들어온 요청(프록시가 알려 준 것 포함)이면 늘 Secure. 이 PC 시험(http)은 그대로
PROXY_HEADERS = (
    "x-forwarded-for",
    "x-forwarded-host",
    "forwarded",
    "cf-connecting-ip",
    "x-real-ip",
)
LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost", "testclient")


def _https(request: Request | None) -> bool:
    if request is None:
        return False
    if request.url.scheme == "https":
        return True
    proto = request.headers.get("x-forwarded-proto", "")
    return "https" in proto.lower() or '"scheme":"https"' in request.headers.get("cf-visitor", "")


def _local(request: Request) -> bool:
    """그 컴퓨터에서 직접 연 요청인가 — 터널 · 프록시를 거친 요청은 아니다(헤더로 가림)."""
    host = request.client.host if request.client else ""
    return host in LOCAL_HOSTS and not any(h in request.headers for h in PROXY_HEADERS)


def _set_cookie(response: Response, token: str, request: Request | None = None) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=rules.IDLE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure or _https(request),
        path="/",
    )


def require_member(request: Request, response: Response, db: DB) -> Member:
    """로그인한 회원. 아니면 401 — 쿠키가 아예 없으면 login_required(CHT-AUTH), 있는데 끝났으면
    session_expired(CHT-SESS)."""
    token = request.cookies.get(COOKIE)
    m = service.session_member(db, token)
    if m is None:
        code = "session_expired" if token else "login_required"
        msg = "로그인 시간이 지났어요. 다시 로그인해 주세요." if token else "로그인이 필요합니다."
        raise HTTPException(401, {"ok": False, "code": code, "error": msg})
    _set_cookie(response, service.session_token(m), request)  # 한 달 다시 늘림
    return m


class LoginIn(BaseModel):
    login_id: str = Field(max_length=40)
    password: str = Field(max_length=100)


class CodeIn(BaseModel):
    purpose: Literal["signup", "find_id", "reset_pw"]
    email: str = Field(max_length=120)
    name: str = Field("", max_length=20)
    login_id: str = Field("", max_length=40)


class VerifyIn(CodeIn):
    code: str = Field(max_length=10)


class SignupIn(BaseModel):
    ticket: str = Field(max_length=2000)
    login_id: str = Field(max_length=40)
    password: str = Field(max_length=100)
    password2: str = Field(max_length=100)
    dongs: list[str] = Field(max_length=47)
    job: str | None = Field(None, max_length=20)
    terms: dict[str, bool]


class ResetIn(BaseModel):
    ticket: str = Field(max_length=2000)
    password: str = Field(max_length=100)
    password2: str = Field(max_length=100)


@router.get("/me")
def me(request: Request, response: Response, db: DB) -> dict:
    m = require_member(request, response, db)
    return {"ok": True, "member": service.member_view(db, m)}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: DB):
    ip = request.client.host if request.client else None
    try:
        member, token = service.login(db, body.login_id, body.password, ip)
    except AuthError as e:
        return _fail(e)
    _set_cookie(response, token, request)
    return {"ok": True, "member": member}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/check-id")
def check_id(login_id: str, db: DB):
    try:
        service.check_login_id(db, login_id.strip())
    except AuthError as e:
        return _fail(e)
    return {"ok": True, "message": "쓸 수 있는 아이디입니다."}


@router.get("/dongs")
def dongs(db: DB) -> dict:
    regions = db.scalars(select(Region).order_by(Region.sgg_cd)).all()
    out = []
    for r in regions:
        ds = db.scalars(select(Dong).where(Dong.sgg_cd == r.sgg_cd).order_by(Dong.name)).all()
        out.append(
            {
                "sgg_cd": r.sgg_cd,
                "name": r.name,
                "dongs": [{"dong_cd": d.dong_cd, "name": d.name} for d in ds],
            }
        )
    return {"ok": True, "regions": out, "jobs": list(rules.JOBS)}


@router.get("/terms")
def terms() -> dict:
    items = [
        {"code": code, "title": title, "required": must, "lines": TEXTS[code]}
        for code, (title, must) in rules.TERMS.items()
    ]
    return {"ok": True, "version": rules.TERMS_VERSION, "items": items}


@router.post("/code/send")
def code_send(body: CodeIn, request: Request, db: DB):
    # 【판단】 10-28: 시험 방식(dev)은 메일을 보내지 않고 시험 메일함에만 남긴다.
    #        그 메일함이 밖에서도 열리면 남의 비밀번호 재설정 번호까지 보인다
    #        → 메일함은 그 컴퓨터에서만. 밖(터널 · 프록시)에서 dev 서버에 번호를 달라면
    #        '메일 설정이 안 됨'으로 알리고 번호를 만들지 않는다
    if settings.mail_mode != "smtp" and not _local(request):
        return JSONResponse(
            {
                "ok": False,
                "error": (
                    "인증 메일 설정이 아직 안 돼 있어 번호를 보낼 수 없어요. "
                    "관리자에게 알려 주세요."
                ),
                "field": "email",
            },
            503,
        )
    try:
        out = service.send_code(db, body.purpose, body.email, body.name, body.login_id)
    except AuthError as e:
        return _fail(e)
    # 【판단】 10-26 팀장 "이메일에 코드가 안간다" — 시험 방식(MAIL_MODE=dev)은 실제로 보내지 않는데
    #        화면이 '보냈습니다'라고만 했다 → 시험 방식이면 그렇다고 알리고 시험 메일함 주소를 준다
    if settings.mail_mode != "smtp":
        return {
            "ok": True,
            "message": "시험 모드라 메일은 보내지 않았어요. 시험 메일함에서 인증번호를 보세요.",
            "dev_outbox": "/api/auth/dev/outbox",
            **out,
        }
    return {"ok": True, "message": "인증번호를 보냈습니다. 5분 안에 넣어 주세요.", **out}


@router.post("/code/verify")
def code_verify(body: VerifyIn, db: DB):
    try:
        out = service.verify_code(db, body.purpose, body.email, body.code, body.name, body.login_id)
    except AuthError as e:
        return _fail(e)
    return {"ok": True, **out}


@router.post("/signup")
def signup(body: SignupIn, db: DB):
    try:
        out = service.signup(
            db,
            body.ticket,
            body.login_id,
            body.password,
            body.password2,
            body.dongs,
            body.job,
            body.terms,
        )
    except AuthError as e:
        return _fail(e)
    return {"ok": True, **out}


@router.post("/password/reset")
def password_reset(body: ResetIn, db: DB):
    try:
        out = service.reset_password(db, body.ticket, body.password, body.password2)
    except AuthError as e:
        return _fail(e)
    return {"ok": True, **out}


@router.get("/dev/outbox", response_class=HTMLResponse, include_in_schema=False)
def outbox(request: Request) -> str:
    """진짜로 보내지 않은 메일(MAIL_MODE=dev). 서버를 끄면 비워지고, 파일은 data/outbox/.

    그 컴퓨터에서 직접 연 요청만(10-28 — 밖에서 열리면 남의 인증번호가 보인다)."""
    if settings.mail_mode != "dev" or not _local(request):
        raise HTTPException(404)
    rows = "".join(
        f"<article><b>{html.escape(x['subject'])}</b><small>{html.escape(x['to'])} · "
        f"{html.escape(x['at'])}</small><pre>{html.escape(x['body'])}</pre></article>"
        for x in reversed(mailer.SENT)
    )
    return (
        "<!doctype html><meta charset='utf-8'><title>시험 메일함</title>"
        "<style>body{font-family:sans-serif;max-width:720px;margin:24px auto;padding:0 16px}"
        "article{border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0}"
        "small{display:block;color:#666}pre{white-space:pre-wrap}</style>"
        "<h1>시험 메일함</h1><p>MAIL_MODE=dev — 진짜로 보내지 않은 메일(이 서버를 끄면 비워짐, "
        "파일은 data/outbox/)</p>" + (rows or "<p>아직 없음</p>")
    )
