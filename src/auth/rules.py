"""입력 규칙 — 아이디 · 비밀번호 · 이메일 · 이름 · 회원 유형 · 직무 · 약관.

화면(web/auth.js)도 같은 규칙으로 칸을 벗어나는 순간 검사하지만, 진짜 판정은 여기서 한다.
"""

import re
from datetime import UTC, datetime, timedelta, timezone

# 【판단】 한국은 서머타임이 없어 +9시간으로 고정한다(Windows 에는 시간대 자료가 없어 ZoneInfo 를
#        쓰려면 패키지가 더 든다). DB 에는 공용 표와 같이 시간대 없는 '한국 시각'으로 적는다
KST = timezone(timedelta(hours=9))


def now() -> datetime:
    return datetime.now(UTC).astimezone(KST).replace(tzinfo=None)


# ── 스토리보드에서 정한 숫자 ──
LOCK_AFTER = 5  # COM-100E1 · E2: 5번 틀리면
LOCK_MINUTES = 30  # 30분 잠금
CODE_MINUTES = 5  # COM-130: 인증번호 6자리, 5분 안에
CODE_TRIES = 5  # 5번 틀리면 새 번호
RESEND_SECONDS = 60  # [다시 받기]는 1분에 한 번
# 【정함 10-24 팀장】 "로그인은 한 달로 두자" — 스토리보드 19장(CHT-SESS)의 '한 달 동안 로그인
#        유지'를 따른다(3장의 '30분 동안 아무것도 안 하면 로그아웃'과 어긋났던 것).
#        쓸 때마다 한 달이 다시 늘어난다
IDLE_MINUTES = 30 * 24 * 60
TICKET_MINUTES = 30  # 이메일 인증을 마친 뒤 가입 · 재설정을 끝낼 때까지

# 【정함 10-25 팀장】 "공공기관, 민간기관 <- 이거. 그냥 나누지 말자" · "그냥 기관목록을 넣지말자.
#        그냥. 누구나 와서 사용할 수 있도록 하자"
#        → 회원 유형 · 기관 코드(소속 확인)를 없애고 이메일 인증만으로 누구나 가입한다
#        (자료가 모두 공공데이터라 막을 까닭이 없다).
#        표의 kind 칸은 빈칸이 안 돼서 '일반', org_id 는 비움
MEMBER_KIND = "일반"
JOBS = ("사회복지 공무원", "방문 간호", "생활지원사", "복지관 사회복지사", "기타")
TERMS_VERSION = "2026-10-25"
TERMS = {
    "use": ("서비스 이용약관", True),
    "privacy": ("개인정보 수집 · 이용 동의", True),
    "marketing": ("점검 · 새 기능 안내 이메일 받기", False),
}
# 【판단】 남이 '관리자'처럼 보이는 아이디를 쓰지 못하게
#        (스토리보드 COM-140E1 예: admin → 이미 쓰는 아이디)
RESERVED_IDS = {"admin", "root", "salpim", "system", "manager", "test"}

LOGIN_ID = re.compile(r"^[a-z][a-z0-9_]{3,19}$")
EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
NAME = re.compile(r"^[가-힣A-Za-z ]{2,20}$")


def clean_email(email: str) -> str:
    return (email or "").strip().lower()


def login_id_problem(login_id: str) -> str | None:
    if not LOGIN_ID.match(login_id or ""):
        return "아이디는 영문 소문자로 시작하는 4~20자(영문 소문자 · 숫자 · _)로 정해 주세요."
    return None


def password_checks(password: str, login_id: str = "") -> dict[str, bool]:
    """COM-140: 9~20자 · 영문 · 숫자 · 특수문자 모두 · 아이디가 들어가지 않음 ·
    같은 글자 3번 연속 아님.

    화면이 모자란 조건만 빨간 ×로 바꿀 수 있게 조건마다 맞았는지를 돌려준다.
    """
    pw = password or ""
    return {
        "length": 9 <= len(pw) <= 20,
        "kinds": bool(
            re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw) and re.search(r"[^A-Za-z0-9]", pw)
        ),
        "no_id": not (login_id and login_id.lower() in pw.lower()),
        "no_repeat": not re.search(r"(.)\1\1", pw),
    }


PASSWORD_WORDS = {
    "length": "비밀번호는 9~20자로 정해 주세요.",
    "kinds": "비밀번호에 영문 · 숫자 · 특수문자를 모두 넣어 주세요.",
    "no_id": "비밀번호에 아이디를 넣을 수 없어요.",
    "no_repeat": "같은 글자를 3번 이어 쓸 수 없어요.",
}


def password_problem(password: str, login_id: str = "") -> str | None:
    for key, ok in password_checks(password, login_id).items():
        if not ok:
            return PASSWORD_WORDS[key]
    return None


def mask_login_id(login_id: str) -> str:
    """COM-161: 가운데를 가려서 보여 준다(hong07 → ho***7). 공용 PC에서 옆 사람이 볼 수 있어서."""
    if len(login_id) <= 3:
        return login_id[0] + "*" * (len(login_id) - 1)
    return login_id[:2] + "***" + login_id[-1]
