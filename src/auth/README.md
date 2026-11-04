# src/auth — 회원가입 · 로그인 · 아이디/비밀번호 찾기

스토리보드 v1.3 확정 초안 COM-100 ~ 161 · CHT-AUTH · CHT-SESS. 팀장 저장소 `regionse/BIGCONTEST_AUTH`에서 만들어 시험한 것을 옮겼다(10-25).

## 무엇이 바뀌나

- **대시보드 · 시뮬레이션 API(`src/api/main.py`)와 비서(`src/api/assistant.py`)는 로그인한 회원만** 쓴다. 아니면 401(`code`: `login_required` · `session_expired`)
- 화면(`web/`)의 '체험 계정' 자리가 진짜 로그인으로 바뀌었다. 로그인 · 가입 · 찾기 화면은 `web/auth.js` · `auth.css`(이름은 모두 `au-`)가 그리고, 길 나누기는 `app.js`가 한다
- **누구나 가입**(10-25 팀장: "공공기관, 민간기관 … 그냥 나누지 말자" · "그냥 기관목록을 넣지말자. 누구나 와서 사용할 수 있도록") — 이메일 인증만 하면 된다. 회원 유형 · 기관 코드 없음(표의 kind 는 '일반', org_id 는 비움)
- 담당 지역은 가입할 때 고른 동(회원 담당 지역 표)으로 정해진다. 비서도 같은 쿠키를 읽어 그 지역 · 동으로 시작한다
- 표는 그대로다(ERDCloud 스냅숏과 같음). 인증번호 틀린 횟수는 `email_code.code_hash` 뒤에 `#횟수`로 붙인다

## 처음 한 번

```bash
docker compose up -d              # PostgreSQL
uv run alembic upgrade head       # 표(이미 있으면 그대로)
uv run python -m src.auth.seed    # 지역 · 동(담당 지역 고르기). 10-24의 시험 기관이 남아 있으면 지운다
```


## 켜기

```bash
uv run uvicorn src.api.main:app --port 8000                                   # 화면 + 대시보드 · 시뮬레이션 + 회원
uv run --env-file ../big-contest/.env uvicorn src.api.assistant:app --port 8010  # 비서(키는 팀장 .env)
```

- 두 서버 모두 이 폴더의 `.env`(DATABASE_URL)를 읽는다. 로그인 쿠키 서명 비밀 글자는 `.env`의 `AUTH_SECRET`, 비었으면 처음 켤 때 `.auth_secret` 파일(git 제외)을 만들어 두 서버가 같이 쓴다
- 화면을 연 주소와 비서 주소의 **호스트가 같아야** 쿠키가 같이 간다(포트는 달라도 됨). 화면이 비서를 열 때 알아서 맞춘다
- 인증 메일: 기본은 `MAIL_MODE=dev` — 진짜로 보내지 않고 `http://127.0.0.1:8000/api/auth/dev/outbox`와 `data/outbox/`에 남는다
- **진짜 발송은 Brevo SMTP**(10-26 팀장: 서버는 AWS가 아니라 Tailscale 주소 · "Brevo로 하자"). 코드는 그대로, 서버가 도는 컴퓨터의 `.env`만:
  1. brevo.com 가입(무료 — 하루 300통, [Brevo free SMTP](https://www.brevo.com/en/free-smtp-server/))
  2. 보내는 사람(Senders)에 보낼 주소를 더하고 메일로 인증 — From 주소가 인증된 보내는 사람이 아니면 거절된다([Brevo 문제 해결](https://help.brevo.com/hc/en-us/articles/115000188150))
  3. https://app.brevo.com/settings/keys/smtp 의 'SMTP' 탭에서 서버 · 포트 · 로그인 · SMTP 키를 그대로 옮긴다(API 키가 아니라 SMTP 키 — [Brevo SMTP 문서](https://developers.brevo.com/docs/smtp-integration))
  4. `.env`: `MAIL_MODE=smtp` · `SMTP_HOST=`(SMTP 탭의 서버, 안내 글에는 smtp-relay.brevo.com) · `SMTP_PORT=587` · `SMTP_USER=`(SMTP 탭의 로그인) · `SMTP_PASSWORD=`(SMTP 키) · `MAIL_FROM=`(2에서 인증한 주소)
  5. 확인: `uv run python -m src.auth.mailer 받을주소` — 서버를 켜지 않고 한 통 보낸다(실패하면 무엇을 볼지 알려 줌)
  - 코드는 587 포트에서 STARTTLS로 붙는다(465 포트는 쓰지 않는다)
  - 안 될 때: 화면에 '시험 메일함 열기'가 보이면 아직 dev(`MAIL_MODE=smtp`를 못 읽음 — 서버를 다시 켰는지) · 'SMTPAuthenticationError'면 API 키를 넣은 것(SMTP 키) · 'SMTPSenderRefused'면 보내는 주소 미인증 · 시간 초과면 587 포트가 막힘(2525)
  - 아이디 찾기 · 비밀번호 재설정은 그 서버 DB 회원의 이름 · 아이디 · 이메일이 정확히 맞을 때만 메일을 보낸다(안 맞아도 화면은 '보냈습니다' — 개인정보 보호)

## 규칙(스토리보드 그대로)

- 비밀번호 9 ~ 20자 · 영문 · 숫자 · 특수문자 모두 · 아이디 못 넣음 · 같은 글자 3번 연속 금지. scrypt로 저장
- 5번 틀리면 30분 잠금(잠긴 동안 맞는 비밀번호도 막음), 비밀번호를 새로 정하면 풀림. 없는 아이디도 같은 모양으로 센다
- 인증번호 6자리 · 5분 · 5번 틀리면 새 번호 · 다시 받기 1분에 한 번. 아이디 · 비밀번호 찾기는 맞는 계정이 없어도 '보냈습니다'만
- 로그인은 한 달 유지(쓸 때마다 다시 한 달, 10-24 팀장). 비밀번호를 바꾸면 그 전 쿠키는 못 씀

## 시험

`tests/test_auth_rules.py` · `tests/test_auth_flow.py`(회원 표만 SQLite 임시 DB). 나머지 시험은 `tests/conftest.py`가 '로그인한 회원'으로 끼워 돈다.
