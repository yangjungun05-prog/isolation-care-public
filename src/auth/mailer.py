"""인증 메일 보내기.

    MAIL_MODE=dev(기본)  진짜로 보내지 않고 data/outbox/ 에 한 통씩 파일로,
                         /dev/outbox 화면에 보인다
    MAIL_MODE=smtp       SMTP_HOST · SMTP_PORT · SMTP_USER · SMTP_PASSWORD · MAIL_FROM 으로
                         진짜 발송

【판단】 10-24 팀장: 회원가입 · 로그인부터, 이메일 기능은 그다음. 그래서 지금은 dev 로 시험하고
       진짜 발송은 설정만 바꾸면 되게 둔다(보내는 계정은 팀장이 정한다)
"""

import json
import smtplib
from email.message import EmailMessage

from src.auth import rules
from src.auth.config import ROOT, settings

OUTBOX = ROOT / "data" / "outbox"
SENT: list[
    dict
] = []  # 【기능】 dev 에서 보낸 메일(시험이 인증번호를 꺼내 쓴다). 서버를 끄면 비워진다


class MailError(RuntimeError):
    pass


def send(to: str, subject: str, body: str) -> None:
    if settings.mail_mode == "smtp":
        _smtp(to, subject, body)
        return
    item = {
        "to": to,
        "subject": subject,
        "body": body,
        "at": rules.now().isoformat(timespec="seconds"),
    }
    SENT.append(item)
    del SENT[:-50]
    OUTBOX.mkdir(parents=True, exist_ok=True)
    name = f"{rules.now():%Y%m%d_%H%M%S}_{len(SENT):02d}.json"
    (OUTBOX / name).write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")


def _smtp(to: str, subject: str, body: str) -> None:
    s = settings
    if not (s.smtp_host and s.mail_from):
        raise MailError("메일 설정(SMTP_HOST · MAIL_FROM)이 비어 있어요.")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as e:
        raise MailError(f"메일을 보내지 못했어요: {e.__class__.__name__}") from e


def code_mail(purpose: str, code: str) -> tuple[str, str]:
    what = {"signup": "회원가입", "find_id": "아이디 찾기", "reset_pw": "비밀번호 재설정"}[purpose]
    subject = f"[취약 돌보미] {what} 인증번호 {code}"
    body = (
        f"취약 돌보미 {what} 인증번호는 {code} 입니다.\n"
        "5분 안에 화면에 넣어 주세요.\n\n"
        "직접 요청하지 않았다면 이 메일은 지워 주세요. 다른 사람은 이 번호 없이 들어갈 수 없습니다."
    )
    return subject, body


if __name__ == "__main__":
    # 【기능】 10-26: 메일 설정 확인 — 서버를 켜지 않고 한 통 보내 본다(팀장 'Brevo로 하자')
    #        uv run python -m src.auth.mailer 받을주소@예시.com
    import sys

    if len(sys.argv) < 2:
        print("쓰는 법: uv run python -m src.auth.mailer 받을주소")
        sys.exit(2)
    s = settings
    print(
        f"방식 {s.mail_mode} · 서버 {s.smtp_host or '-'}:{s.smtp_port} · "
        f"보내는 주소 {s.mail_from or '-'} · 로그인 {'있음' if s.smtp_user else '없음'}"
    )
    try:
        send(sys.argv[1], "[취약 돌보미] 메일 설정 확인", "메일 설정이 맞으면 이 메일이 옵니다.")
    except MailError as e:
        print(
            f"{e}\n- SMTP 키(비밀번호)와 로그인이 Brevo 'SMTP' 탭 값과 같은지\n"
            "- 보내는 주소(MAIL_FROM)가 Brevo에서 인증한 보내는 사람인지\n"
            "- 포트가 587인지 확인해 주세요"
        )
        sys.exit(1)
    if s.mail_mode == "smtp":
        print("보냈어요. 받은편지함(없으면 스팸함)을 확인해 주세요.")
    else:
        print("dev 방식이라 실제로 보내지 않고 data/outbox/ 에 남겼어요(MAIL_MODE=smtp 면 보냄).")
