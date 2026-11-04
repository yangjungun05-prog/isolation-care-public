"""회원 기능 설정 — 서명 비밀 글자 · 쿠키 · 인증 메일.

【판단】 공용 src/common/settings.py 를 바꾸지 않으려고 따로 둔다(비서의 src/assistant/config.py 와
       같은 방식). 같은 .env 를 읽는다
【판단】 본 서버(src.api.main, 8000)와 비서 서버(src.api.assistant, 8010)가
       같은 로그인 쿠키를 읽어야 해서 서명 비밀 글자가 같아야 한다.
       .env 의 AUTH_SECRET 이 비었으면 처음 켤 때 .auth_secret 파일(git 에 안 올라감)을 만들어
       두 서버가 같이 읽는다
"""

import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).parents[2]
SECRET_FILE = ROOT / ".auth_secret"


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_secret: str = ""
    # 【판단】 https 로 띄울 때만 True(쿠키를 암호화된 연결로만 보냄). 이 PC 시험(http)은 False
    cookie_secure: bool = False
    # 【판단】 dev = 진짜로 보내지 않고 data/outbox/ · /api/auth/dev/outbox 에 남긴다(AWS SES 는
    #        10-24 팀장 '나중에 AWS 할 때' — big-contest docs/미정.md) · smtp = 진짜 발송
    mail_mode: str = "dev"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""

    @property
    def secret(self) -> bytes:
        return (self.auth_secret or _file_secret()).encode("utf-8")


def _file_secret() -> str:
    if not SECRET_FILE.exists():
        tmp = SECRET_FILE.with_suffix(f".{secrets.token_hex(4)}.tmp")
        tmp.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        try:
            tmp.replace(SECRET_FILE)
        except OSError:
            tmp.unlink(missing_ok=True)  # 다른 서버가 먼저 만들었다
    return SECRET_FILE.read_text(encoding="utf-8").strip()


settings = AuthSettings()
