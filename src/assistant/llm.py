"""Claude 연결 — 클라이언트 · 값 계산 · 오류 구분 · 장부.

【정함 10-27 팀장】 "cli로 사용되고 있을텐데. api로 바꿔줘. max플랜이 되면서 사용할 수 있게 된거니까
       … 100달러를 기준으로 알뜰살뜰 써야해. 11월 3일까지 … cli는 일단 주석화 시키고. 나중에 api
       심하게 딸릴때 급하게 사용하자"
       → AI를 부르는 길은 **API 하나**다. CLI(구독) 길은 이 파일 맨 아래 주석 블록에 그대로 남겨
       두었다(되살리는 법도 거기). `cli.py`는 지우지 않았다(지금은 어디서도 부르지 않는다).

【판단】 크레딧이 바닥나면(credit balance) 다른 모델로 넘어가지 않고 CreditExhausted 로 멈춘다
       (10-12 팀장: "다쓰면 내게 말만 해주면됨", "API크레딧이 모두 닳으면 API사용을 멈춰줘").
【판단】 오류는 종류별로 잡는다(429 · 5xx 는 SDK 가 다시 시도, 400 은 다시 해도 같음).
【판단】 부를 때마다 장부(ledger)에 적고, 장부 합계가 예산($100)에 닿으면
       부르지 않고 BudgetExhausted 로 멈춘다(10-15 팀장: "api를 사용할떄마다 얼마를
       사용했는지 모두 기록하게 해줘", "총 100달러가 된다면 api사용은 못하게").
【판단】 10-27 알뜰하게 쓰기 — 돈이 드는 곳은 API 호출뿐이라 여기서 지킨다:
       ① 값표(PRICE)에 없는 모델은 부르지 않는다 ② 10만 토큰 넘는 요청(다섯 배 값)은
       부르기 전에 막는다(LONG_PROMPT_GUARD, budget.fit 이 9만에서 덜어 내므로 평소엔 안 걸린다)
       ③ 예산의 8할(WARN_RATIO)을 넘으면 장부 줄에 warn 표시를 남기고 상태(/assistant/status)에
       보인다 ④ 캐시(cache_control)는 부르는 쪽이 고정 지시문에 건다(데스크 · 글쓴이 · 계획기)
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache

import anthropic
import httpx
import httpx2

from . import ledger

# 【기능】 100만 토큰당 $ — (입력, 캐시 읽기, 캐시 쓰기 5분, 출력).
#        Claude API 참고 자료 2026-10 기준. 10-12 공식 값표로 다시 맞춤, 10-15 다시 확인
#        (platform.claude.com/docs/en/about-claude/pricing): Sonnet 5.5 캐시 읽기는 0.05배($0.10).
#        1시간 캐시 쓰기는 입력의 2배(WRITE_1H)
# 【판단】 Haiku 5.5는 질문(새 입력 + 캐시 쓰기 + 캐시 읽기, 도구 정의 포함)이
#        10만 토큰을 넘으면 그 요청 전체가 다섯 배 값이다.
#        한국어는 글자 하나가 대략 1토큰(10-12 count_tokens: 공문 2,382자 = 2,447토큰)
LONG_PROMPT = 100_000
WRITE_1H = 2.0
# 【판단】 10-30 팀장 '5초 8초 9초 이상 걸리는데 왜?' · '캐시부터': 고정 지시문 캐시를 5분에서
#        1시간으로(데스크 · 글쓴이 · 계산 계획). 5분 넘게 아무도 안 쓰면 다음 첫 질문이 데스크
#        지시문(약 1만 4천 토큰)을 다시 써 10초 걸렸다(10-30 재 봄 — 이어진 질문은 2 ~ 5초).
#        쓰기는 2배 값이지만 한 시간 안에 다시 오면 읽기(0.1배)라 띄엄띄엄 쓰는 현장에 맞다
CACHE_1H = {"type": "ephemeral", "ttl": "1h"}
PRICE: dict[str, tuple[float, float, float, float]] = {
    "claude-haiku-5-5": (0.10, 0.01, 0.125, 0.50),
    "claude-haiku-5-5/long": (0.50, 0.05, 0.625, 2.50),
    "claude-sonnet-5-5": (2.00, 0.10, 2.50, 10.00),
    "claude-opus-5-5": (4.00, 0.20, 5.00, 20.00),
    # 【기능】 페르소나 시험의 사용자 역(10-12). 캐시 읽기는 0.025배(공식 값표)
    "claude-fable-5-1": (10.00, 0.25, 12.50, 50.00),
}

# 【기능】 어느 길로 부르나 — 10-27부터 API 하나. 환경 변수 BISU_LLM=cli 는 받지 않는다(아래 주석
#        블록을 되살리기 전에는 cli 를 켜도 돌지 않으니 분명히 오류로 알린다)
BACKEND_ENV = "BISU_LLM"
BACKEND = "api"
# 【판단】 10만 토큰(다섯 배 값) 문턱 바로 아래에서 막는다 — 글자 수로 어림(한국어 1자 ≈ 1토큰)
LONG_PROMPT_GUARD = 95_000
# 【판단】 예산의 8할이 넘으면 '경고'(멈추지는 않는다 — 멈춤은 100%에서, 10-15 팀장 규칙)
WARN_RATIO = 0.8


class LLMError(RuntimeError):
    """다시 해도 같은 오류(요청 모양 · 권한 등)."""


class CreditExhausted(LLMError):
    """API 크레딧 바닥 — 멈추고 사람에게 알린다."""


class BudgetExhausted(CreditExhausted):
    """장부 합계가 예산(api_usage/budget.json, $100)에 닿음 — 더 부르지 않고 사람에게 알린다."""


class UsageLimited(CreditExhausted):
    """Console에 정해 둔 API 사용 한도(월 한도)에 닿음(10-27 실측 400:
    'You have reached your specified API usage limits. You will regain access on 2026-11-01 …').
    키 · 크레딧은 멀쩡해도 그때까지 모든 요청이 400이라 멈추고 사람에게 알린다
    (한도를 올리는 것은 Console에서 팀장이)."""


@dataclass
class Usage:
    """여러 번 부른 값을 모은다(스레드에서 같이 써도 되게 잠금)."""

    calls: int = 0
    input_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    long_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, u) -> dict:
        c = cost(model, u)
        with self._lock:
            self.calls += 1
            self.long_calls += c["long"]
            self.input_tokens += c["in"]
            self.cache_read += c["cr"]
            self.cache_write += c["cw5m"] + c["cw1h"]
            self.output_tokens += c["out"]
            self.usd += c["usd"]
        return c

    @property
    def real_tokens(self) -> int:
        """실질 토큰 = 새 입력 + 캐시 쓰기 + 캐시 읽기의 1/10 + 출력(팀장 비용 보고 규칙)."""
        return self.input_tokens + self.cache_write + self.cache_read // 10 + self.output_tokens


def cost(model: str, u) -> dict:
    """응답 하나의 토큰(종류별)과 정가 돈. 값표에 없는 모델은 부르기 전에 막는다(_before)."""
    cr = getattr(u, "cache_read_input_tokens", 0) or 0
    cw = getattr(u, "cache_creation_input_tokens", 0) or 0
    cw1h = getattr(getattr(u, "cache_creation", None), "ephemeral_1h_input_tokens", 0) or 0
    long = u.input_tokens + cr + cw > LONG_PROMPT and f"{model}/long" in PRICE
    pi, pr, pw, po = PRICE[f"{model}/long" if long else model]
    usd = (
        u.input_tokens * pi
        + cr * pr
        + (cw - cw1h) * pw
        + cw1h * pi * WRITE_1H
        + u.output_tokens * po
    ) / 1e6
    return {
        "in": u.input_tokens,
        "cw5m": cw - cw1h,
        "cw1h": cw1h,
        "cr": cr,
        "out": u.output_tokens,
        "long": bool(long),
        "usd": round(usd, 8),
    }


def backend() -> str:
    """지금은 늘 'api'. BISU_LLM=cli 를 켜 두었으면 오류(주석 블록을 되살리기 전에는 안 돈다)."""
    v = os.environ.get(BACKEND_ENV, BACKEND).strip().lower()
    if v and v != BACKEND:
        raise LLMError(
            f"{BACKEND_ENV}={v} 는 지금 쓰지 않는 길이다(10-27 팀장: API로). "
            "CLI 길을 되살리려면 llm.py 맨 아래 주석 블록을 본다"
        )
    return BACKEND


def budget_status() -> dict:
    """예산 · 쓴 돈 · 남은 돈 · 경고 여부(장부 합계) — 상태 화면 · 보고에 쓴다."""
    over, spent, limit = ledger.over_budget()
    return {
        "limit_usd": limit,
        "spent_usd": round(spent, 4),
        "left_usd": round(limit - spent, 4),
        "warn": spent >= limit * WARN_RATIO,
        "over": over,
    }


def _prompt_chars(kwargs: dict) -> int:
    """요청에 든 글자 수 어림(지시문 + 메시지 + 도구 설명) — 10만 토큰 문턱을 지키는 데 쓴다."""
    n = 0
    system = kwargs.get("system")
    if isinstance(system, str):
        n += len(system)
    else:
        n += sum(len(b.get("text", "")) for b in system or [] if isinstance(b, dict))
    for m in kwargs.get("messages") or []:
        c = m.get("content")
        if isinstance(c, str):
            n += len(c)
        else:
            n += sum(len(b.get("text", "")) for b in c or [] if isinstance(b, dict))
    for t in kwargs.get("tools") or []:
        n += len(str(t.get("input_schema", ""))) + len(t.get("description", ""))
    return n


def _before(kwargs: dict) -> None:
    backend()
    model = kwargs["model"]
    if model not in PRICE:
        raise LLMError(
            f"값표(PRICE)에 없는 모델이라 부르지 않는다: {model} — 공식 값을 먼저 더한다"
        )
    chars = _prompt_chars(kwargs)
    if chars > LONG_PROMPT_GUARD:
        raise LLMError(
            f"요청이 약 {chars:,}자라 10만 토큰(다섯 배 값) 문턱에 닿을 수 있어 부르지 않는다 "
            "— 자료를 덜어 낸다(budget.fit)"
        )
    over, spent, limit = ledger.over_budget()
    if over:
        raise BudgetExhausted(
            f"API 예산 ${limit:.2f} 중 ${spent:.4f}를 썼다(장부 합계). "
            "API를 더 부르지 않는다 — 팀장에게 보고한다"
        )


def _after(model: str, usage: Usage, msg, kind: str) -> None:
    """쓴 양을 모으고 장부에 적는다. 장부에 못 적으면 오류(빠뜨리지 않게)."""
    c = usage.add(model, msg.usage)
    row = {
        "id": msg.id,
        "request_id": getattr(msg, "_request_id", None) or "",
        "kind": kind,
        "model": model,
        **c,
    }
    try:
        over, spent, limit = ledger.over_budget()
        if spent + c["usd"] >= limit * WARN_RATIO:
            row["warn"] = f"예산의 {WARN_RATIO:.0%} 넘음"
        ledger.record(row)
    except OSError as e:
        raise LLMError(f"API 장부에 적지 못했다: {e}") from e


@lru_cache(maxsize=2)
def client(api_key: str) -> anthropic.Anthropic:
    if not api_key:
        raise LLMError("ANTHROPIC_API_KEY 가 비어 있다(.env)")
    return anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=60.0)


def call(api_key: str, usage: Usage, **kwargs):
    """messages.create 한 번. 오류를 우리 종류로 바꾼다."""
    _before(kwargs)
    with _errors():
        r = client(api_key).messages.create(**kwargs)
    _after(kwargs["model"], usage, r, "call")
    return r


def stream_text(api_key: str, usage: Usage, meta: dict | None = None, **kwargs) -> Iterator[str]:
    """messages.stream — 글 조각을 오는 대로 낸다. 끝나면(중간에 멈춰도) 쓴 양을 더한다.

    【판단】 10-12 팀장 "대답이 8초나 걸린다고? 기다리다가 지치겠는데" → 다 쓸 때까지 기다리지 않고
           흘려 보인다(같은 글이라 품질은 그대로).
    【판단】 meta 에 멈춘 까닭(stop_reason)을 적어 준다 — 한도에 닿아 잘린 글을 가려낸다(10-15).
           여러 대화가 한 글쓴이를 같이 쓰므로 Usage 가 아니라 부른 쪽의 dict 에 적는다
    """
    _before(kwargs)
    with _errors(), client(api_key).messages.stream(**kwargs) as s:
        try:
            yield from s.text_stream
        finally:
            snap = getattr(s, "current_message_snapshot", None)
            if snap is not None:
                _after(kwargs["model"], usage, snap, "stream")
                if meta is not None:
                    meta["stop"] = getattr(snap, "stop_reason", None)


@contextmanager
def _errors() -> Iterator[None]:
    """SDK 오류 → 우리 종류(CreditExhausted · LLMError)."""
    try:
        yield
    except anthropic.BadRequestError as e:
        low = str(e).lower()
        if "credit balance" in low:
            raise CreditExhausted(str(e)) from e
        if "usage limit" in low:
            # 【판단】 10-27 village_6: 이 400을 '요청 모양 오류'로 읽어 데스크가 삼키고 6턴 내내
            #        '못 알아들음'이 나갔다 → 멈추는 오류로
            raise UsageLimited(f"API 사용 한도(Console)에 닿음: {e}") from e
        raise LLMError(f"요청 모양 오류: {e}") from e
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        raise LLMError(f"키 · 권한 오류: {e}") from e
    except anthropic.NotFoundError as e:
        raise LLMError(f"모델 이름 오류: {e}") from e
    except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        # 【판단】 SDK 가 이미 3번 다시 했다. 여기까지 오면 이번 턴은 실패로 본다
        raise LLMError(f"일시 오류(다시 해도 실패): {e}") from e
    except (httpx2.HTTPError, httpx.HTTPError) as e:
        # 【판단】 10-15 페르소나 재생 q19: 흘려 받는 도중 연결이 끊기면(RemoteProtocolError)
        #        SDK 오류가 아니라 httpx2(SDK가 쓰는 것) 오류가 그대로 올라와 대화가 통째로
        #        멈췄다 → 이번 턴만 실패로
        raise LLMError(f"연결 끊김: {type(e).__name__}") from e


# ══════════════════════════════════════════════════════════════════════════════════════════
# CLI(구독) 길 — 10-24 ~ 10-27 아침까지 기본이던 길. 10-27 팀장 "cli는 일단 주석화 시키고.
# 나중에 api 심하게 딸릴때 급하게 사용하자" → 아래에 그대로 남긴다(코드는 `cli.py`에 살아 있다).
#
# 되살리는 법(급할 때):
#   1. 맨 위 import 를 `from . import cli, ledger` 로
#   2. 아래 주석을 풀어 Usage.add_cli · SubscriptionLimited · CLILoginError · _after_cli ·
#      _cli_errors · warm · _can_fall_back · _api_call 을 되돌리고, call · stream_text 의
#      `if cli.backend() == "cli":` 갈래를 되돌린다(backend() 는 cli.backend() 로)
#   3. desk._system(SYSTEM_CLI) · doc.write(SYSTEM_CLI) · desk.read 의 cli_desk_votes ·
#      engine.warm · api/assistant.py 의 startup warm 과 CLILoginError · SubscriptionLimited
#      오류 안내 — 각 파일의 '10-27 CLI 주석' 표시를 본다
#   4. 환경 변수 BISU_LLM=cli, 터미널에서 `claude` 로그인(구독). tests/test_cli_1024.py 의
#      맨 위 pytest.skip 을 뺀다
#
# API와 다른 점(10-24 실측 · 10-27 정리):
#   - 돈: CLI는 구독이라 API 크레딧 0(장부엔 kind=cli · api_equiv_usd 만). API는 토큰마다 돈,
#     장부 합계 $100에서 멈춤
#   - 도구: CLI는 도구가 없어 --json-schema 로 JSON 하나를 받고, 지시문 끝줄도 바꿨다(SYSTEM_CLI).
#     API는 strict 도구(tool_use) 그대로. 프롬프트 캐시(cache_control)도 API에서만 뜻이 있다
#   - 횟수: CLI는 한 번에 하나씩(_ONE 잠금)이라 데스크 한 장(cli_desk_votes=1). API는 동시에
#     여러 장(desk_votes) — 돈이 그만큼 든다
#   - 속도: CLI는 띄우는 데만 약 2초(미리 띄우기 warm 으로 가림). API는 띄울 것이 없다
#   - 한도: CLI는 구독 5시간 · 7일 사용률(rate_limit_event)에 막히면 SubscriptionLimited,
#     BISU_API_FALLBACK=1 이면 같은 요청을 API로 다시 불렀다. API는 429를 SDK가 3번 다시 시도
#   - 로그인: CLI는 `claude` 로그인(앱 환경 변수 CLAUDE_* · ANTHROPIC_* 를 빼야 구독으로 돈다).
#     API는 .env 의 ANTHROPIC_API_KEY 하나
#
# class SubscriptionLimited(CreditExhausted):
#     """CLI(구독) 사용량 한도에 막힘(10-24) — API로 넘어가지 않고 멈춰 사람에게 알린다."""
#
#
# class CLILoginError(CreditExhausted):
#     """CLI 로그인 · 권한 오류(10-24 이 PC: 'organization has disabled Claude subscription access')
#     — 매번 같은 오류라 멈추고 사람에게 알린다(팀장이 다시 로그인)."""
#
#
# (Usage 에 cli_calls: int = 0 칸과 아래 메서드)
#     def add_cli(self, u) -> None:
#         """CLI(구독)로 부른 것 — 토큰만 더하고 돈은 0(API 크레딧이 아님)."""
#         with self._lock:
#             self.calls += 1
#             self.cli_calls += 1
#             self.input_tokens += u.input_tokens
#             self.cache_read += u.cache_read_input_tokens
#             self.cache_write += u.cache_creation_input_tokens
#             self.output_tokens += u.output_tokens
#
#
# def _after_cli(model: str, usage: Usage, msg, kind: str) -> None:
#     """CLI로 부른 것을 장부에 적는다 — usd 0, API였다면 얼마(api_equiv_usd)는 따로(10-24)."""
#     usage.add_cli(msg.usage)
#     c = cost(model, msg.usage) if model in PRICE else {"usd": 0.0}
#     try:
#         ledger.record(
#             {
#                 "id": msg.id,
#                 "request_id": "",
#                 "kind": kind,
#                 "model": model,
#                 "backend": "cli",
#                 "in": msg.usage.input_tokens,
#                 "cw5m": msg.usage.cache_creation_input_tokens,
#                 "cw1h": 0,
#                 "cr": msg.usage.cache_read_input_tokens,
#                 "out": msg.usage.output_tokens,
#                 "long": False,
#                 "usd": 0.0,
#                 "api_equiv_usd": c["usd"],
#                 "sub_5h": cli.LIMIT.get("five_hour"),
#                 "sub_7d": cli.LIMIT.get("seven_day"),
#             }
#         )
#     except OSError as e:
#         raise LLMError(f"장부에 적지 못했다: {e}") from e
#
#
# @contextmanager
# def _cli_errors() -> Iterator[None]:
#     try:
#         yield
#     except cli.CLIError as e:
#         if e.code == "limit":
#             raise SubscriptionLimited(str(e)) from e
#         if "oauth" in e.code or "auth" in e.code or str(e).startswith("CLI 로그인"):
#             raise CLILoginError(str(e)) from e
#         raise LLMError(str(e)) from e
#
#
# def warm(stream: bool = False, **kwargs) -> None:
#     """CLI 길이면 이 요청 모양의 CLI를 미리 띄워 둔다(cli.py 맨 위 판단)."""
#     if cli.backend() == "cli" and cli.warm_on():
#         try:
#             cli.prewarm(kwargs, stream)
#         except OSError:
#             pass
#
#
# FALLBACK_ENV = "BISU_API_FALLBACK"
#
#
# def _can_fall_back(api_key: str) -> bool:
#     """구독 한도에 막혔을 때 API로 다시 부를 수 있나(키가 있고 BISU_API_FALLBACK=0 이 아닐 때)."""
#     return bool(api_key) and os.environ.get(FALLBACK_ENV, "1").strip() != "0"
#
#
# def _api_call(api_key: str, usage: Usage, kwargs: dict, kind: str):
#     _before(kwargs)
#     with _errors():
#         r = client(api_key).messages.create(**kwargs)
#     _after(kwargs["model"], usage, r, kind)
#     return r
#
#
# (call 의 CLI 갈래)
#     if cli.backend() == "cli":
#         try:
#             with _cli_errors():
#                 r = cli.run(kwargs)
#         except SubscriptionLimited as e:
#             if not _can_fall_back(api_key):
#                 raise
#             try:
#                 return _api_call(api_key, usage, kwargs, "api-fallback")
#             except BudgetExhausted as b:
#                 raise SubscriptionLimited(f"{e} · API 예산도 바닥: {b}") from b
#         _after_cli(kwargs["model"], usage, r, "cli")
#         return r
#
#
# (stream_text 의 CLI 갈래)
#     if cli.backend() == "cli":
#         done: dict = {}
#         shown = False
#         try:
#             with _cli_errors():
#                 for piece in cli.stream(kwargs, done):
#                     shown = True
#                     yield piece
#         except SubscriptionLimited as e:
#             # 글을 이미 보였으면 API로 다시 쓰지 않는다(같은 답이 두 벌로 이어 붙는다)
#             if shown or not _can_fall_back(api_key):
#                 raise
#             limited = e
#         else:
#             return
#         finally:
#             msg = done.get("message")
#             if msg is not None:
#                 _after_cli(kwargs["model"], usage, msg, "cli-stream")
#                 if meta is not None:
#                     meta["stop"] = msg.stop_reason
#         try:
#             yield from _api_stream(api_key, usage, meta, kwargs, "api-fallback-stream")
#         except BudgetExhausted as b:
#             raise SubscriptionLimited(f"{limited} · API 예산도 바닥: {b}") from b
#         return
# ══════════════════════════════════════════════════════════════════════════════════════════
