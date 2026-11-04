"""비서 시험 화면 · API — FastAPI(팀원 저장소의 src/api 자리, 10-13).

    uv run --env-file ../big-contest/.env uvicorn src.api.assistant:app --port 8010
    → http://127.0.0.1:8010

- GET  /                          채팅 화면(입력 1,000자 제한 · 답을 문장마다 흘려 보임 ·
                                  문서 내려받기)
- POST /assistant/chat            {session_id, text, region} → text/event-stream
                                  (text 조각 · replace 통째로 바꾸기 · done 끝과 처리 종류 · 파일)
- GET  /assistant/files/{name}    만든 동 상황 문서(PDF · PPTX) · 동별 표(엑셀 · CSV, 10-14)
                                  내려받기 — 문서 폴더 안 파일 이름만
- GET  /assistant/today           담당 지역(region · dong) · 날짜(date) · 회원(member)
                                  → 오늘 챙길 일 카드(10-14), 카드마다 그 회원의 마지막
                                  [했어요] 기록(10-15). 날짜를 안 주면 진짜 오늘(기상청 특보 ·
                                  단기예보, 10-16 팀장), 지난 날짜면 그날까지의 관측을 되짚음
- POST /assistant/today/{card_id}/done  {status: 했어요 · 해당 없음, reason, member} → 기록(10-15,
                                  팀 ERD todo_done 모양. 이유 글의 이름 · 전화는 가려 저장)
- GET  /assistant/dongs           지역별 동 이름(담당 동 고르기)
- GET  /assistant/me              로그인한 회원(이름 · 담당 지역) — 화면이 담당 지역을 채운다
- GET  /assistant/history         그 회원의 지난 대화 묶음(최근 것부터). session_id 를 주면
                                  그 묶음의 문답(질문 · 한 줄 답) — 팀 표 chat_turn
                                  (10-25, src/assistant/history.py)
- GET  /assistant/help            도움말 — 할 수 있는 것 · 하지 않는 것 · 예시 · 자료의 때(10-27)
- POST /assistant/sessions/{session_id}/title     {title} → 세션 제목 바꾸기(빈 글이면 첫 질문으로,
                                  10-27 팀장)
- POST /assistant/sessions/{session_id}/continue  → 이 세션을 이어 새 세션(기억은 옮기고 목록은
                                  줄임). {session_id, title} 를 돌려준다(10-27 팀장, 50턴 추천)

done 이벤트에는 세션 제목(title) · 이 세션의 대화 수(turns) · 새 세션 추천(long, 50턴부터)도 온다.
done 이벤트에는 답 글 · 종류 · 파일과 함께 follow(이어 물을 질문 3개까지) · choices('어느 동?'에
누를 동 단추) · sources(이 답의 자료 묶음 · 자료의 때)가 온다(10-27, extras.py, AI 없음)

【판단】 10-25 팀장 "로그인해야지만 가능하게" → 화면(/) 말고는 모두 로그인한 회원만(src/auth).
       본 서버(8000)에서 로그인한 쿠키를 그대로 읽는다(같은 호스트면 포트가 달라도 쿠키가 같이 간다,
       서명 비밀 글자도 같다 — src/auth/config.py)

【판단】 10-25 팀장 "대화기록도 해줘" → 질문마다 chat_turn 한 줄. 대화 묶음(session_id)은 회원마다
       따로 둔다(저장소 열쇠에 회원 번호를 붙여 남의 묶음 번호로는 그 대화를 이어 쓸 수 없다)

【판단】 팀장이 깔끔한 버전 비서(데스크 v6 ~)와 직접 대화해 본 적이 없다(문제 목록 8-1).
       시험지 도구가 아니라 사람이 쓰는 모양으로 돌려 볼 수 있게 한다
【판단】 키는 실행할 때 --env-file 로 넘긴다(이 저장소에 키를 복사하지 않는다)
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.assistant import extras, history, llm, pii, query, today_api
from src.assistant.config import AssistantSettings
from src.assistant.data_source import JsonDongData
from src.assistant.desk import ClaudeDesk
from src.assistant.engine import (
    LONG_SESSION_TURNS,
    Engine,
    Reply,
    session_title,
    session_turns,
)
from src.assistant.policy import MAX_INPUT
from src.assistant.state import Profile
from src.assistant.store import JsonFileStore
from src.assistant.writer import ClaudeWriter
from src.auth import routes as auth_routes
from src.auth import service as auth_service
from src.common.database import get_db
from src.common.models import Member

PAGE = Path(__file__).with_name("chat.html")


SID = r"^[A-Za-z0-9_-]{1,36}$"
TITLE_MAX = 40  # 세션 제목 글자 수
NEW_TITLE = "새 대화"  # 제목도 첫 질문도 없을 때(화면의 setTitle 과 같은 말)


class TitleIn(BaseModel):
    title: str = Field("", max_length=200)


class ChatIn(BaseModel):
    # 【판단】 팀 표 chat_turn.session_id 가 36자 — 영문 · 숫자 · _ · - 만(저장 파일 이름에도 쓴다)
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,36}$")
    # 【판단】 1,000자 넘는 글도 받아서 엔진이 '받지 못했어요'라고 알린다(몰래 자르지 않는다)
    text: str = Field(max_length=MAX_INPUT * 20)
    region: str = "강남구"
    dong: str | None = None
    # 【기능 10-27】 화면에서 고른 담당 동들 — '어느 동을 볼까요?'에 이 동부터 단추로 보인다
    dongs: list[str] = Field(default_factory=list, max_length=30)


def build_engine(s: AssistantSettings | None = None) -> Engine:
    s = s or AssistantSettings()
    # 【판단】 10-25 대화 상태(칸 · 기억)를 파일로 — 서버를 다시 켜도 지난 대화를 이어 간다.
    #        팀 표 chat_turn 에는 상태 칸이 없다(PostgreSQL 로 옮기려면 chat_state 표 · 팀원 확인)
    store = JsonFileStore(Path(s.state_dir))
    e = Engine(
        ClaudeDesk(s, llm.Usage()),
        ClaudeWriter(s, llm.Usage()),
        JsonDongData(),
        store,
        s,
        **query.planners(s, llm.Usage()),
    )
    # 【10-27 CLI 주석】 e.warm() — CLI 미리 띄우기. API 길에는 없다
    return e


def _event(kind: str, data: object) -> str:
    return "data: " + json.dumps({"event": kind, "data": data}, ensure_ascii=False) + "\n\n"


def create_app(
    engine: Engine | None = None,
    done_store=None,
    weather=None,
    record: history.DbHistory | None = None,
) -> FastAPI:
    """weather: 기상청 예보 · 특보를 주는 것(시험에서는 가짜). 없으면 today.live().
    record: 대화 기록(chat_turn). 없으면 남기지 않는다(진짜 서버는 아래 app 이 DB 에 남긴다)."""
    state: dict[str, Engine] = {}
    lock = threading.Lock()

    def eng() -> Engine:
        with lock:
            if "e" not in state:
                state["e"] = engine or build_engine()
        return state["e"]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # 【판단】 서버가 켜질 때 엔진(자료 읽기 · 계획기)을 뒤에서 미리 만들어 첫 질문이 기다리지
        #        않게 한다. 10-27부터 AI는 API라 미리 띄울 CLI는 없다(10-24 CLI 주석).
        #        10-27 on_event('startup')는 FastAPI가 더 쓰지 말라고 해(경고) lifespan 으로
        if engine is None:
            threading.Thread(target=eng, daemon=True).start()
        yield

    app = FastAPI(title="취약 돌보미 AI 비서 시험 화면", lifespan=lifespan)
    # 【판단】 부를 때 찾는다(auth_routes.require_member) — 시험이 가짜 회원으로 바꿔 끼울 수 있게
    login = [Depends(auth_routes.require_member)]

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE.read_text(encoding="utf-8")

    @app.get("/assistant/me")
    def me(
        m: Annotated[Member, Depends(auth_routes.require_member)],
        db: Annotated[Session, Depends(get_db)],
    ) -> dict:
        return {"ok": True, "member": auth_service.member_view(db, m)}

    @app.post("/assistant/chat")
    def chat(
        body: ChatIn, m: Annotated[Member, Depends(auth_routes.require_member)]
    ) -> StreamingResponse:
        e = eng()
        key = f"m{m.member_id}_{body.session_id}"  # 회원마다 따로(남의 묶음을 열 수 없게)
        if e.store.load(key) is None:
            region = body.region if body.region in ("강남구", "춘천시") else "강남구"
            e.start(key, Profile(member_region=region, member_dong=body.dong))
        t0 = time.perf_counter()

        def run() -> Iterator[str]:
            try:
                for kind, value in e.turn_stream(key, body.text):
                    if kind == "done":
                        r: Reply = value  # type: ignore[assignment]
                        if record is not None:
                            # 끝 알림보다 먼저 — 화면이 끊겨도 기록은 남게
                            ms = int((time.perf_counter() - t0) * 1000)
                            record.add(m.member_id, body.session_id, body.text, r, ms)
                        files = [Path(p).name for p in r.files]
                        mine = tuple(body.dongs) or ((body.dong,) if body.dong else ())
                        try:
                            more = {
                                "follow": extras.followups(r, e.data, body.text),
                                "choices": extras.choices(r, e.data, mine),
                                "sources": extras.sources(r, e.data),
                            }
                        except Exception:  # noqa: BLE001 — 단추가 못 나와도 답은 나가게
                            more = {"follow": [], "choices": [], "sources": {}}
                        n = session_turns(r.state)
                        # 10-27: 막은 질문 · 너무 긴 글만 있으면 첫 질문이 비어 있다 — 원문을
                        #        대신 쓰지 않는다(가리지 않은 글이 제목으로 나갔다)
                        more["title"] = session_title(r.state, NEW_TITLE)
                        more["turns"] = n
                        more["long"] = n >= LONG_SESSION_TURNS
                        yield _event(
                            "done", {"text": r.text, "kind": r.kind, "files": files, **more}
                        )
                    else:
                        yield _event(kind, value)
            # 【10-27 CLI 주석】 CLI 길의 오류 안내 둘 — 되살릴 때 같이 푼다
            # except llm.CLILoginError:
            #     yield _event("error", "AI(Claude CLI) 로그인 문제로 멈췄어요. "
            #                  "터미널에서 claude 로 다시 로그인해 주세요.")
            # except llm.SubscriptionLimited:
            #     yield _event("error", "Claude 구독 사용량 한도에 닿아 AI를 멈췄어요. "
            #                  "한도가 풀린 뒤 다시 해 주세요.")
            except llm.BudgetExhausted:
                yield _event(
                    "error", "API 예산 $100을 다 써서 AI를 멈췄어요. 팀장님께 알려 주세요."
                )
            except llm.UsageLimited as err:
                # 10-27: Console의 월 사용 한도 — 키 · 크레딧이 아니라 한도 설정이다
                when = re.search(r"regain access on ([0-9-]+ at [0-9:]+ UTC)", str(err))
                yield _event(
                    "error",
                    "Console에 정해 둔 API 사용 한도에 닿아 AI를 멈췄어요. "
                    "팀장님이 Console(Limits)에서 한도를 올리거나"
                    + (f" {when.group(1)}" if when else " 다음 달")
                    + " 뒤에 다시 해 주세요.",
                )
            except llm.CreditExhausted:
                yield _event("error", "API 크레딧이 바닥났어요. 팀장님께 알려 주세요.")
            except llm.LLMError as err:
                yield _event(
                    "error", f"AI 연결 오류예요. 잠시 뒤 다시 해 주세요({type(err).__name__})."
                )

        return StreamingResponse(run(), media_type="text/event-stream")

    # 【기능 10-16】 오늘 챙길 일 카드 · [했어요] · 동 이름 — 카드 모듈의 라우터(팀 저장소에도
    #            그대로)
    app.include_router(
        today_api.router(
            get_data=lambda: eng().data,
            get_settings=lambda: eng().s,
            done_store=done_store,
            weather=weather,
            who=auth_routes.require_member,
        ),
        dependencies=login,
    )

    @app.get("/assistant/history")
    def past(
        m: Annotated[Member, Depends(auth_routes.require_member)], session_id: str = ""
    ) -> dict:
        """지난 대화 — session_id 가 없으면 묶음 목록, 있으면 그 묶음의 문답(그 회원 것만)."""
        if record is None:
            return {"ok": True, "sessions": [], "turns": []}
        if session_id:
            return {"ok": True, "turns": record.turns(m.member_id, session_id[:36])}
        rows = record.sessions(m.member_id)
        for x in rows:
            # 10-27 제목: 사용자가 정한 것, 없으면 첫 질문(대화 기억 파일에서 · 회원마다 따로)
            x["title"] = session_title(
                eng().store.load(f"m{m.member_id}_{x['session_id']}"), x.get("first") or ""
            )
        return {"ok": True, "sessions": rows}

    def _key(m: Member, session_id: str) -> str:
        if not re.fullmatch(SID, session_id):
            raise HTTPException(status_code=422, detail="세션 번호 모양이 아니에요.")
        return f"m{m.member_id}_{session_id}"  # 회원마다 따로(남의 세션은 열 수 없음)

    @app.post("/assistant/sessions/{session_id}/title")
    def rename(
        session_id: str,
        body: TitleIn,
        m: Annotated[Member, Depends(auth_routes.require_member)],
    ) -> dict:
        """세션 제목 바꾸기 — 이름 · 전화 같은 것은 가리고, 빈 글이면 첫 질문으로 돌아간다."""
        title, _ = pii.mask(" ".join(body.title.split()))
        # 잠금 안에서 고친다 — 답을 쓰는 중인 턴이 끝에 저장해도 이 제목은 남는다
        st = eng().set_title(_key(m, session_id), title[:TITLE_MAX])
        if st is None:
            raise HTTPException(status_code=404, detail="아직 문답이 없는 세션이에요.")
        return {"ok": True, "title": session_title(st, NEW_TITLE)}

    @app.post("/assistant/sessions/{session_id}/continue")
    def carry(session_id: str, m: Annotated[Member, Depends(auth_routes.require_member)]) -> dict:
        """이 세션을 이어 새 세션을 연다(50턴 추천에서 [예], 10-27 팀장)."""
        e = eng()
        key = _key(m, session_id)
        old = e.store.load(key)
        if old is None:
            raise HTTPException(status_code=404, detail="이을 세션이 없어요.")
        new_id = "c" + uuid.uuid4().hex[:20]
        title = (session_title(old, "앞 대화")[: TITLE_MAX - 6] + " (이어서)").strip()
        st = e.carry_over(key, f"m{m.member_id}_{new_id}", title)
        return {"ok": True, "session_id": new_id, "title": session_title(st, title)}

    @app.get("/assistant/help", dependencies=login)
    def help_page(region: str = "강남구") -> dict:
        """도움말 — 장서 목록에서 만든다(AI 없음, 10-27)."""
        region = region if region in ("강남구", "춘천시") else "강남구"
        return {"ok": True, **extras.help_info(region, eng().data)}

    @app.get("/assistant/status", dependencies=login)
    def status() -> dict:
        """AI가 어느 길로 도는지와 API 예산(장부 합계 · 남은 돈 · 8할 경고) — 시연 전에 본다.

        【10-27 CLI 주석】 전에는 구독 사용률(cli.LIMIT)을 보였다:
            {"backend": cli.backend(), "warm": cli.warm_on(), "subscription": dict(cli.LIMIT)}
        """
        return {"backend": llm.BACKEND, "budget": llm.budget_status()}

    @app.get("/assistant/files/{name}", dependencies=login)
    def file(name: str) -> FileResponse:
        folder = Path(eng().s.doc_dir).resolve()
        path = (folder / name).resolve()
        # 【판단】 문서 폴더 안의 PDF · PPTX 이름만 — 다른 경로(../ 등)는 받지 않는다
        if (
            Path(name).name != name
            or path.parent != folder
            or path.suffix not in (".pdf", ".pptx", ".xlsx", ".csv")
        ):
            raise HTTPException(404)
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, filename=name)

    return app


app = create_app(record=history.DbHistory())
