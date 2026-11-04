"""Claude CLI(`claude -p`) 길 — API 대신 팀장 구독으로 부른다(10-24 팀장).

    BISU_LLM=cli(기본) · api      어느 길로 부를지(환경 변수)
    CLAUDE_BIN=claude              CLI 실행 파일
    CLI_MODEL_<이름>=<다른 이름>      모델 이름을 바꿔 부를 때(기본: 정식 이름 그대로)
    BISU_CLI_WARM=1(기본) · 0         CLI를 미리 띄워 둘지(아래 판단)

【판단】 10-24 팀장: "API는 잠시 뒤로 물리고. CLI 로 바꿔 그러면. 프롬프트 다시 재작성하고
       (cli전용으로)". 코드가 AI를 부르는 곳은 llm.call · llm.stream_text 두 군데뿐이라 그 안에서
       길만 바꾼다(데스크 · 글쓴이 · 동 상황 문서가 한 번에 바뀐다)
【판단】 CLI 규칙(big-contest CLAUDE.md 12번 · 전역 지침): 기본 지시문을 빼고(--system-prompt-file)
       도구를 끄고(--tools ""), 한 번에 하나씩 차례로 부른다(_ONE). 대화 기록 파일을 남기지 않는다
       (--no-session-persistence — 사용자 질문 원문이 이 PC 디스크에 쌓이지 않게)
【판단】 CLI를 부를 때 ANTHROPIC_* · CLAUDE_* 환경 변수를 뺀다. ANTHROPIC_API_KEY가 남으면 CLI가
       구독이 아니라 API 크레딧으로 돈다(전역 지침). 데스크톱 앱 세션의 변수(CLAUDE_CODE_* ·
       ANTHROPIC_BASE_URL)도 CLI의 로그인을 흐린다(10-24 확인)
【판단】 도구(tools) 꼴 요청은 --json-schema로 바꾼다. 결과는 API 응답처럼 보이게 감싸서
       부른 쪽(desk · doc · writer) 코드는 그대로 둔다
【판단】 구독으로 돌아 돈(API 크레딧)은 들지 않는다. 장부에는 kind=cli로 토큰과 'API였다면 얼마'
       (api_equiv_usd)만 적고 usd는 0(예산 셈에 들지 않음). CLI와 API 결과는 섞어 견주지 않는다
【판단】 10-24 실측: CLI는 한 번 부를 때마다 띄우는 데만 약 2초가 든다(인사 한 마디가 전체 2.9 ~
       3.4초, 그중 AI 시간 1.1 ~ 1.3초). 한 턴에 데스크 · 글쓴이 두 번이라 첫 글까지 7 ~ 9초였다.
       → 같은 설정(모델 · 지시문 · JSON 모양)의 CLI를 하나씩 미리 띄워 두고, 질문이 오면 그것에
       넣는다(--input-format stream-json 이면 띄운 채 입력을 기다린다. 미리 띄운 것은 1.1 ~ 1.8초).
       미리 띄운 것은 AI를 부르지 않고 기다리기만 한다. 질문 하나를 넣으면 입력을 닫아
       답 하나만 하고 끝난다(대화가 이어 쌓이지 않는다)
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

ENV = "BISU_LLM"
# 【판단】 10-24 확인: 별칭 'haiku'는 이 CLI(2.1.281)에서
#        Haiku 4.5(claude-haiku-4-5-20251001)로 돈다.
#        정식 이름 'claude-haiku-5-5'는 '[claude-code:unrecognized_model]' 경고가 나와도 Haiku 5.5로
#        돈다(modelUsage 확인) → 정식 이름을 그대로 넘긴다
DEFAULT_MODEL_ALIAS: dict[str, str] = {}
TIMEOUT = 180
_ONE = threading.Lock()  # 【판단】 한 번에 하나씩(CLI 규칙)
_RUN_DIR = Path(tempfile.gettempdir()) / "bisu_cli_run"  # 프로젝트 CLAUDE.md가 없는 빈 폴더
WARM_ENV = "BISU_CLI_WARM"
# 【판단】 오래 기다린 것은 로그인 정보가 바뀌었을 수 있어 버리고 새로 띄운다(10분).
#        설정마다 하나씩, 모두 4개까지(데스크 · 글쓴이 · 취약 돌보미 판단 · 동 상황 문서)
MAX_IDLE = 600
POOL_MAX = 4
# 【기능】 CLI가 결과 줄 앞에 주는 구독 사용률(rate_limit_event)의 마지막 값(10-24).
#        five_hour · seven_day 는 0 ~ 1(1이면 한도에 닿음). 이 비서는 팀장의 Claude Code
#        세션들과 같은 구독 한도를 나눠 쓴다 — 시연 전에 /assistant/status 로 본다
LIMIT: dict = {}


class CLIError(RuntimeError):
    """CLI가 실패함 — llm 이 LLMError 로 바꾼다."""

    def __init__(self, msg: str, code: str = "") -> None:
        super().__init__(msg)
        self.code = code


def backend() -> str:
    v = os.environ.get(ENV, "cli").strip().lower()
    return v if v in ("cli", "api") else "cli"


def claude_bin() -> str:
    """CLI 실행 파일.

    【판단】 10-24 확인: Windows의 `claude`는 npm 배치 파일(claude.cmd)이라
           subprocess가 이름만으로는 찾지 못하고(WinError 2), 배치 파일을 거치면
           따옴표가 많은 인자(--json-schema)가 깨지기 쉽다
           → 배치 파일이 부르는 실제 claude.exe 를 바로 부른다
    """
    env = os.environ.get("CLAUDE_BIN")
    if env:
        return env
    found = shutil.which("claude")
    if found and found.lower().endswith((".cmd", ".bat")):
        exe = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin"
        if (exe / "claude.exe").exists():
            return str(exe / "claude.exe")
    return found or "claude"


def model_alias(model: str) -> str:
    key = "CLI_MODEL_" + model.upper().replace("-", "_")
    return os.environ.get(key) or DEFAULT_MODEL_ALIAS.get(model, model)


def clean_env() -> dict[str, str]:
    """CLI에 넘길 환경 — ANTHROPIC_* · CLAUDE_* · CLAUDECODE 를 뺀다(위 판단)."""
    return {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith("ANTHROPIC") or k.startswith("CLAUDE"))
    }


def _system_text(system) -> str:
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in system or [] if isinstance(b, dict))


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))


def prompt_text(messages: list[dict]) -> str:
    """API 대화(여러 번 오간 것)를 CLI에 넣을 한 글로 편다.

    【판단】 글쓴이의 '다시 쓰기'(writer._retry)는 [질문 · 앞서 쓴 답 · 고칠 점] 세 덩이를 보낸다.
           CLI -p 는 한 번 묻기라 덩이마다 이름표를 붙여 한 글로 넣는다
    """
    if len(messages) == 1:
        return _content_text(messages[0]["content"])
    parts = []
    for i, m in enumerate(messages):
        body = _content_text(m["content"])
        if m["role"] == "assistant":
            parts.append(f"[네가 앞서 쓴 답]\n{body}")
        elif i == 0:
            parts.append(body)
        else:
            parts.append(f"[다시 쓰라는 말]\n{body}")
    return "\n\n".join(parts)


def schema_of(kwargs: dict) -> dict | None:
    tools = kwargs.get("tools") or []
    return tools[0].get("input_schema") if tools else None


# 【판단】 도구가 없는 실행이라 도구를 부르라는 말 대신 JSON 하나를 내라고 덧붙인다(CLI 전용 지시)
SCHEMA_NOTE = (
    "\n\n[CLI 실행 규칙] 이 실행에는 도구가 없다. 결과는 주어진 JSON 모양 하나로만 낸다"
    "(설명 · 머리말 · 코드 울타리 없이)."
)


def args(kwargs: dict, sys_file: Path, stream: bool) -> list[str]:
    a = [
        claude_bin(),
        "-p",
        "--model",
        model_alias(kwargs["model"]),
        "--system-prompt-file",
        str(sys_file),
        "--tools",
        "",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        # 【판단】 10-24 확인: 빈 폴더 · 지시문 바꾸기만으로는 사용자 전역 CLAUDE.md(약 9천 토큰)가
        #        그대로 붙었다. --safe-mode면 CLAUDE.md · 스킬 · 플러그인 · 훅이 빠지고(540토큰)
        #        로그인 · 모델은 그대로
        "--safe-mode",
    ]
    effort = (kwargs.get("output_config") or {}).get("effort")
    if effort:
        a += ["--effort", effort]
    schema = schema_of(kwargs)
    if schema:
        a += ["--json-schema", json.dumps(schema, ensure_ascii=False)]
    # 【판단】 입력도 stream-json 이어야 미리 띄워 둘 수 있다(맨 위 판단). 글로 넣으면 CLI가 3초만
    #        기다리고 '입력 없음'으로 끝난다(10-24 확인)
    a += ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    if stream:
        a.append("--include-partial-messages")
    return a


def _prepare(kwargs: dict, stream: bool) -> tuple[list[str], str]:
    """→ (실행 인자, 넣을 글).

    지시문 파일 이름은 내용으로 정한다 — 같은 지시문이면 같은 인자라 미리 띄워 둔 것을 쓸 수 있다.
    """
    _RUN_DIR.mkdir(parents=True, exist_ok=True)
    sys_text = _system_text(kwargs.get("system"))
    if schema_of(kwargs):
        sys_text += SCHEMA_NOTE
    f = _RUN_DIR / f"sys_{hashlib.sha256(sys_text.encode('utf-8')).hexdigest()[:20]}.txt"
    if not f.exists():
        tmp = f.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
        tmp.write_text(sys_text, encoding="utf-8")
        tmp.replace(f)
    return args(kwargs, f, stream), prompt_text(kwargs["messages"])


def _usage(d: dict) -> SimpleNamespace:
    u = d.get("usage") or {}
    return SimpleNamespace(
        input_tokens=int(u.get("input_tokens") or 0),
        cache_read_input_tokens=int(u.get("cache_read_input_tokens") or 0),
        cache_creation_input_tokens=int(u.get("cache_creation_input_tokens") or 0),
        output_tokens=int(u.get("output_tokens") or 0),
        cache_creation=None,
    )


def _check(d: dict) -> None:
    if not d.get("is_error"):
        return
    code = str(d.get("api_error_code") or d.get("subtype") or "")
    text = str(d.get("result") or "")
    if "oauth" in code or "auth" in code or "subscription access" in text:
        raise CLIError(f"CLI 로그인 · 권한 오류({code}): {text[:200]}", code)
    if "limit" in text.lower() or "rate" in code:
        raise CLIError(f"구독 사용량 한도({code}): {text[:200]}", code or "limit")
    raise CLIError(f"CLI 오류({code}): {text[:200]}", code)


def last_json(out: str) -> dict:
    """CLI 출력에서 결과 줄(JSON)을 찾는다. 앞에 경고 줄이 붙을 수 있다('[claude-code:…] {…}')."""
    for line in reversed(out.strip().splitlines()):
        i = line.find("{")
        if i < 0:
            continue
        try:
            d = json.loads(line[i:])
        except ValueError:
            continue
        if isinstance(d, dict) and (d.get("type") == "result" or "result" in d):
            return d
    raise CLIError(f"CLI 결과를 읽지 못했다: {out[-300:]!r}")


def to_message(d: dict, schema: bool) -> SimpleNamespace:
    """CLI 결과 → API 응답처럼(content · stop_reason · usage · id)."""
    _check(d)
    if schema:
        data = d.get("structured_output")
        if data is None:
            raw = str(d.get("result") or "").strip().strip("`")
            raw = raw[raw.find("{") : raw.rfind("}") + 1] if "{" in raw else raw
            try:
                data = json.loads(raw)
            except ValueError as e:
                raise CLIError(f"JSON 모양이 아닌 답: {raw[:200]!r}") from e
        content = [SimpleNamespace(type="tool_use", input=data)]
    else:
        content = [SimpleNamespace(type="text", text=str(d.get("result") or ""))]
    return SimpleNamespace(
        id=f"cli_{d.get('session_id') or d.get('uuid') or uuid.uuid4().hex}_{uuid.uuid4().hex[:6]}",
        _request_id="",
        content=content,
        stop_reason=d.get("stop_reason") or "end_turn",
        usage=_usage(d),
    )


_POOL: dict[tuple[str, ...], tuple[subprocess.Popen, float]] = {}
_POOL_LOCK = threading.Lock()


def warm_on() -> bool:
    return os.environ.get(WARM_ENV, "1").strip() != "0"


def _spawn(argv: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=clean_env(),
        cwd=_RUN_DIR,
    )


def _kill(p: subprocess.Popen) -> None:
    if p.poll() is None:
        p.kill()


def _take(argv: list[str]) -> tuple[subprocess.Popen, bool]:
    """미리 띄워 둔 것이 살아 있으면 그것, 아니면 지금 띄운다. → (프로세스, 미리 띄운 것인지)."""
    with _POOL_LOCK:
        got = _POOL.pop(tuple(argv), None)
    if got:
        p, born = got
        if p.poll() is None and time.time() - born < MAX_IDLE:
            return p, True
        _kill(p)
    return _spawn(argv), False


def _refill(argv: list[str]) -> None:
    """다음 질문을 위해 같은 설정의 CLI를 하나 띄워 둔다(AI는 부르지 않고 입력만 기다린다)."""
    if not warm_on():
        return
    try:
        p = _spawn(argv)
    except OSError:
        return
    with _POOL_LOCK:
        old = _POOL.pop(tuple(argv), None)
        _POOL[tuple(argv)] = (p, time.time())
        extra = list(_POOL)[: max(0, len(_POOL) - POOL_MAX)]
        drop = [_POOL.pop(k)[0] for k in extra] + ([old[0]] if old else [])
    for q in drop:
        _kill(q)
    _start_keeper()


def refresh_stale() -> int:
    """MAX_IDLE에 가까워진(8할 넘게 기다린) 것을 새로 띄워 바꾼다. → 바꾼 수."""
    with _POOL_LOCK:
        now = time.time()
        stale = [list(k) for k, (_, born) in _POOL.items() if now - born > MAX_IDLE * 0.8]
    for argv in stale:
        _refill(argv)
    return len(stale)


_KEEPER: list[threading.Thread] = []


def _start_keeper() -> None:
    """뒤에서 1분마다 오래된 미리 띄운 CLI를 새로 바꿔 둔다(AI는 부르지 않는다).

    【판단】 10-24: 미리 띄운 것은 10분이 지나면 버려서, 시연 중 오래 쉰 뒤 첫 질문이 다시
           느려졌다(+2초)
    """
    with _POOL_LOCK:
        if _KEEPER:
            return

        def loop() -> None:
            while True:
                time.sleep(60)
                refresh_stale()

        t = threading.Thread(target=loop, daemon=True, name="bisu-cli-keeper")
        _KEEPER.append(t)
    t.start()


def prewarm(kwargs: dict, stream: bool) -> None:
    """이 설정의 CLI를 미리 하나 띄워 둔다(이미 있으면 그대로). 서버가 켜질 때 첫 질문도 빠르게."""
    argv, _ = _prepare(kwargs, stream)
    with _POOL_LOCK:
        have = tuple(argv) in _POOL
    if not have:
        _refill(argv)


@atexit.register
def close_pool() -> None:
    with _POOL_LOCK:
        procs = [p for p, _ in _POOL.values()]
        _POOL.clear()
    for p in procs:
        _kill(p)


def _user_line(prompt: str) -> str:
    msg = {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": prompt}]},
    }
    return json.dumps(msg, ensure_ascii=False) + "\n"


def _json_line(line: str) -> dict | None:
    i = line.find("{")
    if i < 0:
        return None
    try:
        d = json.loads(line[i:])
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def _reap(p: subprocess.Popen) -> None:
    """결과 줄을 받은 CLI는 뒤에서 혼자 끝나게 둔다.

    【판단】 10-24 실측: 결과 줄 뒤 CLI가 꺼질 때까지 0.6 ~ 0.8초가 걸려, 한 턴에 두 번(데스크 ·
           글쓴이) 기다렸다. 강제로 끄지는 않는다 — 끝날 때 CLI가 사용자 설정 파일을 쓰다 끊기면
           이 PC의 다른 Claude 세션까지 망가질 수 있다. 1분이 지나도 안 끝나면 그때 끈다
    """

    def wait() -> None:
        try:
            p.communicate(timeout=60)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            _kill(p)

    threading.Thread(target=wait, daemon=True).start()


def _note_limit(d: dict) -> None:
    info = d.get("rate_limit_info") or {}
    w = info.get("unifiedWindows") or {}
    LIMIT.update(
        status=info.get("status"),
        five_hour=(w.get("five_hour") or {}).get("utilization"),
        five_hour_resets=(w.get("five_hour") or {}).get("resetsAt"),
        seven_day=(w.get("seven_day") or {}).get("utilization"),
        seen=time.time(),
    )


def _send(p: subprocess.Popen, prompt: str) -> None:
    assert p.stdin is not None
    p.stdin.write(_user_line(prompt))
    p.stdin.close()  # 질문 하나만 — 입력을 닫으면 답 하나를 내고 끝난다


def _exchange(argv: list[str], prompt: str) -> Iterator[dict]:
    """질문 하나를 넣고 CLI가 내는 JSON 줄을 차례로 낸다. 결과 줄이 없으면 CLIError."""
    try:
        p, warm = _take(argv)
        try:
            _send(p, prompt)
        except OSError:
            if not warm:
                raise
            _kill(p)  # 【판단】 미리 띄운 것이 그새 죽었으면 한 번만 새로 띄운다
            p = _spawn(argv)
            _send(p, prompt)
    except OSError as e:
        raise CLIError(f"CLI를 실행하지 못했다: {e}") from e
    _refill(argv)
    timer = threading.Timer(TIMEOUT, p.kill)
    timer.start()
    final: dict | None = None
    try:
        assert p.stdout is not None
        for line in p.stdout:
            d = _json_line(line)
            if d is None:
                continue
            if d.get("type") == "rate_limit_event":
                _note_limit(d)
            if d.get("type") == "result":
                final = d
            yield d
            if final is not None:
                break
    finally:
        expired = final is None and not timer.is_alive()
        timer.cancel()
        if final is None:
            _kill(p)
        else:
            _reap(p)
    if final is None:
        if expired:
            raise CLIError(f"CLI가 {TIMEOUT}초 안에 답하지 않았다")
        err = (p.stderr.read() if p.stderr else "")[-300:]
        raise CLIError(f"CLI 결과 줄이 없다: {err!r}")


def run(kwargs: dict) -> SimpleNamespace:
    """한 번 묻기. 결과는 API 응답 모양."""
    argv, prompt = _prepare(kwargs, stream=False)
    final: dict = {}
    with _ONE:
        for d in _exchange(argv, prompt):
            if d.get("type") == "result":
                final = d
    return to_message(final, bool(schema_of(kwargs)))


def stream(kwargs: dict, done: dict) -> Iterator[str]:
    """흘려 받기 — 글 조각을 오는 대로 낸다. 끝나면 done['message']에 API 응답 모양."""
    argv, prompt = _prepare(kwargs, stream=True)
    with _ONE:
        final: dict = {}
        for d in _exchange(argv, prompt):
            if d.get("type") == "stream_event":
                ev = d.get("event") or {}
                delta = ev.get("delta") or {}
                if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    yield delta.get("text", "")
            elif d.get("type") == "result":
                final = d
        done["message"] = to_message(final, schema=False)
