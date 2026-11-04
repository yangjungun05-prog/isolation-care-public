"""회원가입 · 로그인 · 아이디/비밀번호 찾기 — 판단은 모두 여기서 한다(API · 화면은 부르기만).

【판단】 틀렸을 때 DB 에 남겨야 하는 것(로그인 실패 횟수 · 인증번호 틀린 횟수 · 로그인 기록)이 있어
       AuthError 를 던져도 그 앞의 변경은 남는다 — API(routes.py)가 AuthError 를 받아 정상 응답으로
       바꾸므로 요청 세션이 저장된다(get_db)
"""

import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth import mailer, rules
from src.auth.secrets_util import (
    check_password,
    code_hash,
    hash_password,
    ip_hash,
    password_tag,
    sign,
    unsign,
)
from src.common.models import (
    Dong,
    EmailCode,
    LoginLog,
    Member,
    MemberRegion,
    Region,
    TermsAgree,
)

PURPOSES = ("signup", "find_id", "reset_pw")


# 【판단】 10-25: 공용 표(email_code)에는 '틀린 횟수' 칸이 없고, 표는 ERDCloud 스냅숏과 같아야 한다
#        (공용 저장소 tests/test_models.py). 칸을 더하지 않고 인증번호 해시 뒤에
#        '#틀린 횟수'를 붙인다
def _split(stored: str) -> tuple[str, int]:
    h, _, n = stored.partition("#")
    return h, int(n or 0)


class AuthError(Exception):
    """화면에 그대로 보일 말(message) · 고칠 칸(field) · 덧붙일 값(extra)."""

    def __init__(self, message: str, field: str | None = None, **extra) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.extra = extra


def _member(db: Session, login_id: str) -> Member | None:
    q = select(Member).where(Member.login_id == login_id, Member.withdrawn_at.is_(None))
    return db.scalar(q)


def _member_by_email(db: Session, email: str) -> Member | None:
    q = select(Member).where(Member.email == email, Member.withdrawn_at.is_(None))
    return db.scalar(q)


# ── 아이디 확인(COM-140) ──


def check_login_id(db: Session, login_id: str) -> None:
    problem = rules.login_id_problem(login_id)
    if problem:
        raise AuthError(problem, "login_id")
    # 【판단】 탈퇴한 회원의 아이디도 다시 쓰지 않는다(표의 유일 조건 · 다른 사람으로 오해)
    taken = db.scalar(select(Member.member_id).where(Member.login_id == login_id))
    if taken or login_id in rules.RESERVED_IDS:
        raise AuthError("이미 쓰는 아이디입니다.", "login_id")


# ── 인증번호(COM-130 · 160 · 161) ──


def send_code(db: Session, purpose: str, email: str, name: str = "", login_id: str = "") -> dict:
    if purpose not in PURPOSES:
        raise AuthError("알 수 없는 요청이에요.")
    email = rules.clean_email(email)
    if not rules.EMAIL.match(email):
        raise AuthError("이메일 주소 모양이 맞지 않아요.", "email")
    if purpose in ("signup", "find_id") and not rules.NAME.match((name or "").strip()):
        raise AuthError("이름은 2~20자(한글 · 영문)로 적어 주세요.", "name")
    if purpose == "signup" and _member_by_email(db, email):
        # COM-130 ①: 이미 가입한 이메일이면 그렇다고 알리고 [아이디 찾기]를 보여 준다
        raise AuthError("이미 가입된 이메일입니다.", "email", taken=True)
    t = rules.now()
    last = db.scalar(
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == purpose)
        .order_by(EmailCode.code_id.desc())
    )
    if last is not None:
        sent_at = last.expires_at - timedelta(minutes=rules.CODE_MINUTES)
        wait = rules.RESEND_SECONDS - int((t - sent_at).total_seconds())
        if wait > 0:
            raise AuthError(
                f"인증번호는 1분에 한 번만 받을 수 있어요. {wait}초 뒤에 다시 눌러 주세요.",
                "code",
                wait=wait,
            )
    # 【판단】 찾기는 맞는 계정이 없어도 똑같이 '보냈습니다'(COM-160 · 161 ②) — 번호 기록도 똑같이
    #        남겨 [다시 받기] 1분 규칙까지 같게 보인다. 보내지 않은 번호는 아무도 몰라 맞힐 수 없다
    target = True
    if purpose == "find_id":
        m = _member_by_email(db, email)
        target = m is not None and m.name == name.strip()
    elif purpose == "reset_pw":
        m = _member(db, (login_id or "").strip().lower())
        target = m is not None and m.email == email
    code = f"{secrets.randbelow(10**6):06d}"
    if target:
        subject, body = mailer.code_mail(purpose, code)
        try:
            mailer.send(email, subject, body)
        except mailer.MailError as e:
            raise AuthError(str(e), "email") from e
    # 앞서 받은 번호는 새 번호를 받는 순간 못 쓴다
    for old in db.scalars(
        select(EmailCode).where(
            EmailCode.email == email, EmailCode.purpose == purpose, EmailCode.used_at.is_(None)
        )
    ):
        old.used_at = t
    db.add(
        EmailCode(
            email=email,
            purpose=purpose,
            code_hash=code_hash(email, purpose, code),
            expires_at=t + timedelta(minutes=rules.CODE_MINUTES),
        )
    )
    return {"expires_in": rules.CODE_MINUTES * 60, "resend_in": rules.RESEND_SECONDS}


def verify_code(
    db: Session, purpose: str, email: str, code: str, name: str = "", login_id: str = ""
) -> dict:
    if purpose not in PURPOSES:
        raise AuthError("알 수 없는 요청이에요.")
    email = rules.clean_email(email)
    rec = db.scalar(
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == purpose, EmailCode.used_at.is_(None))
        .order_by(EmailCode.code_id.desc())
    )
    if rec is None or rec.expires_at < rules.now():
        raise AuthError(
            "인증번호가 없거나 시간이 지났어요. [다시 받기]를 눌러 주세요.", "code", expired=True
        )
    stored, tries = _split(rec.code_hash)
    if tries >= rules.CODE_TRIES:
        raise AuthError(
            "5번 틀려서 이 번호는 쓸 수 없어요. 새 번호를 받아 주세요.", "code", spent=True
        )
    if not hmac.compare_digest(code_hash(email, purpose, (code or "").strip()), stored):
        tries += 1
        rec.code_hash = f"{stored}#{tries}"
        raise AuthError(
            f"인증번호가 맞지 않아요. ({tries}/{rules.CODE_TRIES}회)", "code", tries=tries
        )
    rec.used_at = rules.now()
    if purpose == "signup":
        ticket = sign("signup", {"email": email, "name": name.strip()}, rules.TICKET_MINUTES)
        return {"ticket": ticket}
    if purpose == "find_id":
        m = _member_by_email(db, email)
        if m is None or m.name != name.strip():
            raise AuthError("맞는 계정을 찾지 못했어요.", "email")
        mailer.send(
            email,
            "[취약 돌보미] 가입한 아이디 안내",
            f"취약 돌보미에 가입한 아이디는 {m.login_id} 입니다.\n가입일: {m.created_at:%Y-%m-%d}",
        )
        return {"masked": rules.mask_login_id(m.login_id), "joined": f"{m.created_at:%Y-%m-%d}"}
    m = _member(db, (login_id or "").strip().lower())
    if m is None or m.email != email:
        raise AuthError("맞는 계정을 찾지 못했어요.", "login_id")
    ticket = sign("reset", {"email": email, "login_id": m.login_id}, rules.TICKET_MINUTES)
    return {"ticket": ticket}


# ── 회원가입(COM-120 ~ 150, 10-25부터 회원 유형 · 기관 코드 없음 — rules.MEMBER_KIND) ──


def signup(
    db: Session,
    ticket: str,
    login_id: str,
    password: str,
    password2: str,
    dongs: list[str],
    job: str | None,
    terms: dict[str, bool],
) -> dict:
    t = unsign("signup", ticket)
    if t is None:
        raise AuthError("본인 확인 시간이 지났어요. 이메일 인증을 다시 해 주세요.", "ticket")
    login_id = (login_id or "").strip()
    fields: dict[str, str] = {}
    if not all(terms.get(k) for k, (_, must) in rules.TERMS.items() if must):
        fields["terms"] = "필수 약관에 모두 동의해 주세요."
    try:
        check_login_id(db, login_id)
    except AuthError as e:
        fields["login_id"] = e.message
    problem = rules.password_problem(password, login_id)
    if problem:
        fields["password"] = problem
    elif password != password2:
        fields["password2"] = "비밀번호가 일치하지 않습니다."
    picked = [db.get(Dong, d) for d in dict.fromkeys(dongs or [])]
    if not picked or any(d is None for d in picked):
        fields["dongs"] = "담당 지역을 하나 이상 골라 주세요."
    if job and job not in rules.JOBS:
        fields["job"] = "직무를 목록에서 골라 주세요."
    if _member_by_email(db, t["email"]):
        fields["email"] = "이미 가입된 이메일입니다."
    if fields:
        raise AuthError(f"고칠 곳이 {len(fields)}곳 있습니다. 빨간 칸을 확인하세요.", fields=fields)
    at = rules.now()
    m = Member(
        login_id=login_id,
        password_hash=hash_password(password),
        kind=rules.MEMBER_KIND,
        name=t["name"],
        email=t["email"],
        email_verified_at=at,
        org_id=None,
        job=job or None,
        role="실무자",
        fail_count=0,
        locked_until=None,
        created_at=at,
    )
    db.add(m)
    db.flush()
    for d in picked:
        assert d is not None
        db.add(MemberRegion(member_id=m.member_id, sgg_cd=d.sgg_cd, dong_cd=d.dong_cd))
    for code in rules.TERMS:
        db.add(
            TermsAgree(
                terms_cd=code,
                version=rules.TERMS_VERSION,
                member_id=m.member_id,
                agreed=bool(terms.get(code)),
                at=at,
            )
        )
    return {
        "login_id": m.login_id,
        "dongs": [d.name for d in picked if d is not None],
        "joined": f"{at:%Y-%m-%d}",
    }


# ── 로그인(COM-100 · E1 · E2) ──


def login(db: Session, login_id: str, password: str, ip: str | None) -> tuple[dict, str]:
    """→ (회원 정보, 로그인 쿠키). 틀리면 AuthError(몇 번째 · 잠김)."""
    login_id = (login_id or "").strip().lower()
    if not login_id or not password:
        raise AuthError(
            "아이디와 비밀번호를 모두 넣어 주세요.", "login_id" if not login_id else "password"
        )
    t = rules.now()
    m = _member(db, login_id)

    def log(ok: bool) -> None:
        db.add(
            LoginLog(
                member_id=m.member_id if m else None,
                login_id_tried=login_id[:40],
                ok=ok,
                at=t,
                ip_hash=ip_hash(ip),
            )
        )

    if m is None:
        # 【판단】 없는 아이디도 있는 아이디와 똑같이 센다(COM-100E1 ②: 남의 아이디가 있는지 알아낼
        #        수 없게) — 회원 표 대신 최근 30분 로그인 기록의 실패를 센다
        since = t - timedelta(minutes=rules.LOCK_MINUTES)
        fails = list(
            db.scalars(
                select(LoginLog.at)
                .where(LoginLog.login_id_tried == login_id, LoginLog.ok.is_(False))
                .where(LoginLog.at >= since)
                .order_by(LoginLog.at)
            )
        )
        log(False)
        n = len(fails) + 1
        if n >= rules.LOCK_AFTER:
            # 다섯 번째로 틀린 때부터 30분
            fifth = fails[rules.LOCK_AFTER - 1] if len(fails) >= rules.LOCK_AFTER else t
            raise _locked(fifth + timedelta(minutes=rules.LOCK_MINUTES))
        raise _wrong(n)
    if m.locked_until and m.locked_until > t:
        log(False)
        raise _locked(m.locked_until)
    if m.locked_until:  # 잠금 시간이 지났으면 저절로 풀린다(COM-100E2 [작동])
        m.locked_until, m.fail_count = None, 0
    if check_password(password, m.password_hash):
        m.fail_count = 0
        log(True)
        return member_view(db, m), session_token(m)
    m.fail_count += 1
    log(False)
    if m.fail_count >= rules.LOCK_AFTER:
        m.locked_until = t + timedelta(minutes=rules.LOCK_MINUTES)
        raise _locked(m.locked_until)
    raise _wrong(m.fail_count)


def _wrong(n: int) -> AuthError:
    left = rules.LOCK_AFTER - n
    return AuthError(
        f"아이디 또는 비밀번호가 맞지 않습니다. ({n}/{rules.LOCK_AFTER}회)",
        "password",
        count=n,
        left=left,
    )


def _locked(until) -> AuthError:
    return AuthError(
        f"로그인이 잠겼습니다. {until:%H:%M}부터 다시 로그인할 수 있어요.",
        "password",
        locked=True,
        until=f"{until:%H:%M}",
    )


# ── 비밀번호 재설정(COM-160) ──


def reset_password(db: Session, ticket: str, password: str, password2: str) -> dict:
    t = unsign("reset", ticket)
    if t is None:
        raise AuthError("본인 확인 시간이 지났어요. 이메일 인증을 다시 해 주세요.", "ticket")
    m = _member(db, t["login_id"])
    if m is None or m.email != t["email"]:
        raise AuthError("맞는 계정을 찾지 못했어요.", "login_id")
    problem = rules.password_problem(password, m.login_id)
    if problem:
        raise AuthError(problem, "password")
    if password != password2:
        raise AuthError("비밀번호가 일치하지 않습니다.", "password2")
    m.password_hash = hash_password(password)
    m.fail_count, m.locked_until = 0, None  # ⑤ 바꾸면 잠김도 풀린다
    return {"login_id": m.login_id}


# ── 로그인 상태(CHT-AUTH · CHT-SESS) ──


def session_token(m: Member) -> str:
    return sign(
        "session", {"m": m.member_id, "t": password_tag(m.password_hash)}, rules.IDLE_MINUTES
    )


def session_member(db: Session, token: str | None) -> Member | None:
    body = unsign("session", token)
    if body is None:
        return None
    m = db.get(Member, body.get("m"))
    if m is None or m.withdrawn_at is not None:
        return None
    if not hmac.compare_digest(body.get("t", ""), password_tag(m.password_hash)):
        return None  # 비밀번호를 바꾼 뒤의 옛 쿠키
    return m


def member_view(db: Session, m: Member) -> dict:
    rows = db.execute(
        select(MemberRegion.sgg_cd, Region.name, MemberRegion.dong_cd, Dong.name)
        .join(Region, Region.sgg_cd == MemberRegion.sgg_cd)
        .outerjoin(Dong, Dong.dong_cd == MemberRegion.dong_cd)
        .where(MemberRegion.member_id == m.member_id)
        .order_by(MemberRegion.id)
    ).all()
    return {
        "login_id": m.login_id,
        "name": m.name,
        "role": m.role,
        "job": m.job,
        "regions": [{"sgg_cd": s, "sgg": sn, "dong_cd": d, "dong": dn} for s, sn, d, dn in rows],
    }
