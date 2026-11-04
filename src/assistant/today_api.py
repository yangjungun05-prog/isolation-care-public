"""오늘 챙길 일 카드 API — FastAPI 라우터(10-16).

    from src.assistant import today_api
    app.include_router(today_api.router())

- GET  /assistant/today
    담당 지역(region · dong) · 날짜(date) · 회원(member) → 카드.
    dong 에 쉼표로 여러 동을 주면 그 동들만 합계로(10-19 팀장 '선택할 수 있게 하자').
    청년 카드는 youth_cards(10-19 팀장, 19 ~ 34세)
    날짜를 안 주면 진짜 오늘(기상청 특보 · 단기예보, 10-16 팀장), 지난 날짜면 그날까지의
    관측을 되짚음. 카드마다 그 회원의 마지막 [했어요] 기록
- POST /assistant/today/{card_id}/done
    {status: 했어요 · 해당 없음, reason} → 기록
    (팀 ERD todo_done 모양. 이유 글의 이름 · 전화는 가려 저장)
    회원은 로그인한 회원(who, 10-25). who 가 없을 때(카드만 시험)만 member 를 주소에서 읽는다
- GET  /assistant/dongs
    지역별 동 이름(담당 동 고르기)

【판단】 10-16 팀장: "우선 카드를 빠르게 만들고. 제대로 튼튼하게 만든 뒤.
       바로 공용 깃허브에 올려버리자". 카드만 따로 팀 저장소에 옮길 수 있게
       챗봇(엔진 · 데스크)과 떼어 둔다. 대시보드 · 시뮬레이션도 이 라우터나
       today.cards()를 그대로 부를 수 있다
"""

# 【판단】 from __future__ import annotations 를 쓰지 않는다 — 라우터 안에서 만든 회원 의존성
#        (who, 10-25)을 FastAPI 가 Annotated 로 읽으려면 표시가 글자가 아니라 진짜 값이어야 한다
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.assistant import done as donelog
from src.assistant import dongname, today
from src.assistant.config import AssistantSettings
from src.assistant.data_source import DongData, JsonDongData


class DoneIn(BaseModel):
    status: str
    reason: str | None = Field(default=None, max_length=donelog.REASON_MAX * 2)


def router(
    get_data: Callable[[], DongData] | None = None,
    get_settings: Callable[[], AssistantSettings] | None = None,
    done_store: donelog.DoneStore | None = None,
    weather=None,
    who: Callable[..., Any] | None = None,
) -> APIRouter:
    """get_data · get_settings: 자료 · 설정을 주는 함수(없으면 공개 자료 스냅숏 · .env).
    done_store: [했어요] 기록(없으면 설정의 done_file JSONL). weather: 기상청(시험에서는 가짜).
    who: 로그인한 회원을 주는 의존성(src/auth require_member) — 기록은 그 회원 번호로."""
    r = APIRouter()

    # 【판단】 10-25 로그인이 붙었는데 [했어요]가 모두 회원 1번으로 적히고 있었다(화면이 회원 번호를
    #        보내지 않음). 로그인한 회원이 있으면 그 번호만 쓰고, 화면이 준 번호는 읽지 않는다
    if who is None:

        def member_id(member: int = 1) -> int:
            return member

    else:

        def member_id(m: Annotated[Any, Depends(who)]) -> int:
            return m.member_id

    Me = Annotated[int, Depends(member_id)]
    cache: dict[str, object] = {}

    def settings() -> AssistantSettings:
        if get_settings:
            return get_settings()
        if "s" not in cache:
            cache["s"] = AssistantSettings()
        return cache["s"]  # type: ignore[return-value]

    def data() -> DongData:
        if get_data:
            return get_data()
        if "d" not in cache:
            cache["d"] = JsonDongData()
        return cache["d"]  # type: ignore[return-value]

    def log() -> donelog.DoneStore:
        if "l" not in cache:
            cache["l"] = done_store or donelog.JsonlDoneStore(Path(settings().done_file))
        return cache["l"]  # type: ignore[return-value]

    @r.get("/assistant/dongs")
    def dongs() -> dict:
        return {region: list(ds) for region, ds in dongname.DONGS.items()}

    @r.get("/assistant/today")
    def today_cards(me: Me, region: str = "", dong: str = "", date: str = "") -> dict:
        # 【판단】 모르는 지역 · 그 지역에 없는 동은 받지 않는다(지역 카드로 돌리지 않고 400)
        if region and region not in dongname.DONGS:
            raise HTTPException(400, "지역은 강남구 · 춘천시만")
        picked = list(dict.fromkeys(x.strip() for x in dong.split(",") if x.strip()))
        for n in picked:
            if n not in dongname.DONGS.get(region, []):
                raise HTTPException(400, f"{region}에 {n}은(는) 없어요")
        try:
            # 【정함 10-16 팀장】 비서의 '오늘'은 진짜 오늘.
            #        .env 의 AS_OF 에 날짜를 넣으면 그날로 되감는다
            as_of = settings().as_of
            res = today.cards(
                today.Who(
                    member_region=region or None,
                    member_dong=picked[0] if len(picked) == 1 else None,
                    member_dongs=picked,
                ),
                data(),
                date or (None if as_of == "live" else as_of),
                weather,
            )
        except ValueError as err:
            raise HTTPException(400, "날짜는 2026-10-16처럼") from err
        last = log().latest(me, [c["id"] for c in res["cards"]])
        for c in res["cards"]:
            rec = last.get(c["id"])
            c["done"] = asdict(rec) if rec else None
        return res

    @r.post("/assistant/today/{card_id}/done")
    def card_done(card_id: str, body: DoneIn, me: Me) -> dict:
        try:
            rec = donelog.make(card_id, me, body.status, body.reason)
        except ValueError as err:
            raise HTTPException(400, str(err)) from err
        log().add(rec)
        return asdict(rec)

    return r
