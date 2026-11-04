"""Claude CLI 길(10-24 팀장 "API는 잠시 뒤로 물리고. CLI 로 바꿔").

진짜 CLI는 부르지 않고 가짜 실행으로 본다.

【10-27 CLI 주석】 팀장 "api로 바꿔줘 … cli는 일단 주석화" → llm.py 가 CLI 길을 더 타지 않아
       이 시험은 통째로 건너뛴다. CLI 길을 되살리면(llm.py 맨 아래 주석 블록) 아래 skip 을 뺀다
"""

import json
import time

import pytest

from src.assistant import cli, ledger, llm
from src.assistant.config import AssistantSettings
from src.assistant.desk import SYSTEM_CLI, ClaudeDesk
from src.assistant.state import new_state

pytestmark = pytest.mark.skip(reason="CLI 길은 10-27부터 주석 처리(API로) — llm.py 주석 블록")


def _result(**kw) -> str:
    d = {
        "type": "result",
        "is_error": False,
        "result": "",
        "session_id": "s1",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 120, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 30, "output_tokens": 15},
    }  # fmt: skip
    d.update(kw)
    return "[claude-code:warning] x\n" + json.dumps(d, ensure_ascii=False)


class _Pipe:
    def __init__(self) -> None:
        self.text = ""

    def write(self, s: str) -> None:
        self.text += s

    def close(self) -> None:
        pass


class _Proc:
    """가짜 CLI — 넣은 글을 받아 두고, 정해 둔 줄을 낸다."""

    def __init__(self, argv, seen: dict, **kw) -> None:
        self.argv, self.kw, self.seen = argv, kw, seen
        self.stdin, self.stderr, self.done = _Pipe(), None, False
        seen.setdefault("spawned", []).append(self)

    @property
    def stdout(self):
        self.seen["argv"], self.seen["kw"], self.seen["proc"] = self.argv, self.kw, self
        i = self.argv.index("--system-prompt-file")
        self.seen["system"] = open(self.argv[i + 1], encoding="utf-8").read()
        sent = json.loads(self.stdin.text)
        self.seen["input"] = sent["message"]["content"][0]["text"]
        self.done = True
        return iter(x + "\n" for x in self.seen.get("out", _result(result="안녕")).splitlines())

    def wait(self, timeout=None):
        return 0

    def communicate(self, timeout=None):
        return "", ""

    def poll(self):
        return 0 if self.done else None

    def kill(self) -> None:
        self.done = True


@pytest.fixture
def fake_run(monkeypatch):
    seen: dict = {}
    monkeypatch.setenv("BISU_LLM", "cli")
    monkeypatch.setenv("BISU_CLI_WARM", "0")
    monkeypatch.setattr(cli.subprocess, "Popen", lambda argv, **kw: _Proc(argv, seen, **kw))
    return seen


def test_cli_strips_keys_and_uses_cli_rules(monkeypatch, fake_run):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("CLAUDE_CODE_SIMPLE", "1")
    r = llm.call("", llm.Usage(), model="claude-haiku-5-5", max_tokens=10,
                 system=[{"type": "text", "text": "지시"}],
                 messages=[{"role": "user", "content": "질문"}])  # fmt: skip
    a = fake_run["argv"]
    assert a[a.index("--model") + 1] == "claude-haiku-5-5" and a[a.index("--tools") + 1] == ""
    assert "--no-session-persistence" in a and "--safe-mode" in a and "--json-schema" not in a
    assert a[a.index("--input-format") + 1] == "stream-json"
    env = fake_run["kw"]["env"]
    assert not any(k.startswith(("ANTHROPIC", "CLAUDE")) for k in env)
    assert fake_run["input"] == "질문" and fake_run["system"] == "지시"
    assert r.content[0].type == "text" and r.content[0].text == "안녕"


def test_tool_request_becomes_json_schema(fake_run):
    fake_run["out"] = _result(structured_output={"act": "ask", "topics": ["youth"]})
    schema = {"type": "object", "properties": {"act": {"type": "string"}}}
    r = llm.call("", llm.Usage(), model="claude-sonnet-5-5", max_tokens=10, system="지시",
                 messages=[{"role": "user", "content": "q"}],
                 tools=[{"name": "t", "input_schema": schema}],
                 output_config={"effort": "medium"})  # fmt: skip
    a = fake_run["argv"]
    assert json.loads(a[a.index("--json-schema") + 1]) == schema
    assert a[a.index("--effort") + 1] == "medium"
    assert a[a.index("--model") + 1] == "claude-sonnet-5-5"
    assert "JSON 모양 하나로만" in fake_run["system"]
    assert r.content[0].type == "tool_use" and r.content[0].input["act"] == "ask"


def test_json_in_text_is_read_when_no_structured_output(fake_run):
    fake_run["out"] = _result(result='```json\n{"act": "chitchat"}\n```')
    r = llm.call("", llm.Usage(), model="claude-haiku-5-5", max_tokens=10, system="s",
                 messages=[{"role": "user", "content": "q"}],
                 tools=[{"name": "t", "input_schema": {"type": "object"}}])  # fmt: skip
    assert r.content[0].input == {"act": "chitchat"}


def test_cli_login_error_and_limit(fake_run):
    code = "oauth_not_allowed_for_organization"
    fake_run["out"] = _result(is_error=True, api_error_code=code,
                              result="disabled Claude subscription access")  # fmt: skip
    with pytest.raises(llm.CLILoginError, match="로그인"):
        llm.call("", llm.Usage(), model="claude-haiku-5-5", max_tokens=1, system="s",
                 messages=[{"role": "user", "content": "q"}])  # fmt: skip
    fake_run["out"] = _result(is_error=True, result="Claude usage limit reached")
    with pytest.raises(llm.SubscriptionLimited):
        llm.call("", llm.Usage(), model="claude-haiku-5-5", max_tokens=1, system="s",
                 messages=[{"role": "user", "content": "q"}])  # fmt: skip


def test_cli_call_is_in_ledger_with_zero_dollars(fake_run):
    u = llm.Usage()
    llm.call("", u, model="claude-haiku-5-5", max_tokens=1, system="s",
             messages=[{"role": "user", "content": "q"}])  # fmt: skip
    assert u.cli_calls == 1 and u.usd == 0 and u.input_tokens == 120
    ledger.reset_cache()
    assert ledger.spent() == 0  # 구독이라 예산 셈에 들지 않는다
    rows = [json.loads(x) for f in ledger.own_dir().glob("*.jsonl") for x in f.read_text(
        encoding="utf-8").splitlines()]  # fmt: skip
    assert rows[-1]["backend"] == "cli" and rows[-1]["api_equiv_usd"] > 0


def test_retry_messages_become_one_prompt():
    p = cli.prompt_text([
        {"role": "user", "content": "질문"},
        {"role": "assistant", "content": "처음 답"},
        {"role": "user", "content": "고쳐"},
    ])  # fmt: skip
    assert (
        p.startswith("질문") and "[네가 앞서 쓴 답]\n처음 답" in p and "[다시 쓰라는 말]\n고쳐" in p
    )


def test_stream_yields_pieces_and_records(fake_run):
    ev = lambda t: json.dumps({"type": "stream_event", "event": {  # noqa: E731
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": t}}})  # fmt: skip
    lines = [ev("수서동은 "), ev("2,543명이에요."), _result(result="수서동은 2,543명이에요.")]
    fake_run["out"] = "\n".join(lines)
    meta: dict = {}
    u = llm.Usage()
    msgs = [{"role": "user", "content": "q"}]
    out = list(llm.stream_text("", u, meta=meta, model="claude-haiku-5-5", max_tokens=10,
                               system="s", messages=msgs))  # fmt: skip
    assert (
        out == ["수서동은 ", "2,543명이에요."] and meta["stop"] == "end_turn" and u.cli_calls == 1
    )
    assert "--include-partial-messages" in fake_run["argv"]


def test_desk_uses_cli_prompt_and_one_card(fake_run):
    fake_run["out"] = _result(
        structured_output={"act": "chitchat", "restate": "인사", "topics": []}
    )
    d = ClaudeDesk(AssistantSettings(anthropic_api_key=""))
    card = d.read(new_state(), "안녕하세요")
    assert card.act == "chitchat"
    assert (
        fake_run["system"].startswith(SYSTEM_CLI[:40]) and "도구를 한 번 부른다" not in SYSTEM_CLI
    )
    assert d.usage.cli_calls == 1  # 한 장만(CLI는 한 번에 하나씩)


def test_desk_does_not_swallow_login_error(fake_run):
    # 【기능】 로그인 오류를 데스크가 삼키면 매 턴 '못 알아들음'만 나간다 → 위로 올린다
    fake_run["out"] = _result(is_error=True, api_error_code="oauth_not_allowed_for_organization",
                              result="disabled Claude subscription access")  # fmt: skip
    with pytest.raises(llm.CLILoginError):
        ClaudeDesk(AssistantSettings(anthropic_api_key="")).read(new_state(), "안녕")


def test_warm_pool_reuses_spawned_cli(fake_run, monkeypatch):
    # 【기능】 10-24: 같은 설정이면 미리 띄워 둔 CLI에 질문을 넣고, 다음 것을 또 띄워 둔다
    monkeypatch.setenv("BISU_CLI_WARM", "1")
    cli.close_pool()
    kw = dict(model="claude-haiku-5-5", max_tokens=1, system="같은 지시",
              messages=[{"role": "user", "content": "q"}])  # fmt: skip
    llm.call("", llm.Usage(), **kw)
    first, spare = fake_run["spawned"]  # 질문을 넣은 것 + 다음을 위해 띄워 둔 것
    assert fake_run["proc"] is first and not spare.done
    llm.call("", llm.Usage(), **kw)
    assert fake_run["proc"] is spare and len(fake_run["spawned"]) == 3
    kw["system"] = "다른 지시"  # 다른 설정이면 새로 띄운다
    llm.call("", llm.Usage(), **kw)
    assert fake_run["proc"] is fake_run["spawned"][3]
    cli.close_pool()
    assert all(p.done for p in fake_run["spawned"])


def test_subscription_limit_falls_back_to_api_and_rate_is_noted(fake_run, monkeypatch):
    # 【기능】 전역 지침(10-12): 구독 한도에 막히면 같은 요청을 API 키로 다시 부른다
    ev = json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": "rejected", "unifiedWindows": {"five_hour": {"utilization": 1.0},
                                                 "seven_day": {"utilization": 0.4}}}})  # fmt: skip
    fake_run["out"] = ev + "\n" + _result(is_error=True, result="Claude usage limit reached")
    seen = []
    monkeypatch.setattr(llm, "_api_call", lambda key, u, kw, kind: seen.append(kind) or "api답")
    kw = dict(model="claude-haiku-5-5", max_tokens=1, system="s",
              messages=[{"role": "user", "content": "q"}])  # fmt: skip
    assert llm.call("키", llm.Usage(), **kw) == "api답" and seen == ["api-fallback"]
    assert cli.LIMIT["five_hour"] == 1.0 and cli.LIMIT["seven_day"] == 0.4
    with pytest.raises(llm.SubscriptionLimited):  # 키가 없으면 멈추고 알린다
        llm.call("", llm.Usage(), **kw)
    monkeypatch.setenv("BISU_API_FALLBACK", "0")
    with pytest.raises(llm.SubscriptionLimited):
        llm.call("키", llm.Usage(), **kw)


def test_stream_falls_back_only_before_any_text(fake_run, monkeypatch):
    fake_run["out"] = _result(is_error=True, result="Claude usage limit reached")
    monkeypatch.setattr(llm, "_api_stream", lambda key, u, meta, kw, kind: iter(["API로 ", "씀"]))
    kw = dict(model="claude-haiku-5-5", max_tokens=1, system="s",
              messages=[{"role": "user", "content": "q"}])  # fmt: skip
    assert list(llm.stream_text("키", llm.Usage(), **kw)) == ["API로 ", "씀"]


def test_stale_warm_cli_is_replaced(fake_run, monkeypatch):
    # 【기능】 10-24: 오래 기다린(MAX_IDLE의 8할 넘게) 미리 띄운 CLI는 새로 바꿔 둔다
    monkeypatch.setenv("BISU_CLI_WARM", "1")
    monkeypatch.setattr(cli, "_start_keeper", lambda: None)  # 시험에서는 뒤 일꾼을 띄우지 않는다
    cli.close_pool()
    kw = dict(model="claude-haiku-5-5", max_tokens=1, system="오래된 지시",
              messages=[{"role": "user", "content": "q"}])  # fmt: skip
    cli.prewarm(kw, stream=False)
    first = fake_run["spawned"][-1]
    assert cli.refresh_stale() == 0
    key = next(iter(cli._POOL))
    cli._POOL[key] = (first, time.time() - cli.MAX_IDLE)  # 오래 기다린 것으로
    assert cli.refresh_stale() == 1
    assert first.done and cli._POOL[key][0] is fake_run["spawned"][-1]
    cli.close_pool()
