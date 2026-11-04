"""API 장부 · 예산.

10-15 팀장: "api를 사용할떄마다 얼마를 사용했는지 모두 기록",
"총 100달러가 된다면 api사용은 못하게".
"""

import json
from types import SimpleNamespace

import pytest

from src.assistant import ledger, llm


def _msg(i: int, inp=1000, out=200, cr=0, cw=0):
    u = SimpleNamespace(
        input_tokens=inp,
        output_tokens=out,
        cache_read_input_tokens=cr,
        cache_creation_input_tokens=cw,
    )
    return SimpleNamespace(id=f"msg_{i}", usage=u, content=[], _request_id=f"req_{i}")


class _Fake:
    def __init__(self):
        self.n = 0
        self.messages = self

    def create(self, **kw):
        self.n += 1
        return _msg(self.n)


@pytest.fixture
def fake(monkeypatch):
    f = _Fake()
    monkeypatch.setattr(llm, "client", lambda key: f)
    return f


def _lines():
    return [
        json.loads(x)
        for p in ledger.own_dir().glob("ledger_*.jsonl")
        for x in p.read_text(encoding="utf-8").splitlines()
    ]


def test_every_call_is_written_with_tokens_and_price(fake):
    u = llm.Usage()
    llm.call("k", u, model="claude-haiku-5-5", max_tokens=10, messages=[])
    llm.call("k", u, model="claude-sonnet-5-5", max_tokens=10, messages=[])
    rows = _lines()
    assert [r["id"] for r in rows] == ["msg_1", "msg_2"]
    assert rows[0]["request_id"] == "req_1" and rows[0]["in"] == 1000 and rows[0]["out"] == 200
    # 정가: Haiku 1000 × $0.10 + 200 × $0.50 = $0.0002 · Sonnet 1000 × $2 + 200 × $10 = $0.004
    assert rows[0]["usd"] == pytest.approx(0.0002) and rows[1]["usd"] == pytest.approx(0.004)
    assert ledger.spent() == pytest.approx(0.0042) == pytest.approx(u.usd)


def test_long_prompt_and_cache_are_priced_by_kind():
    # Haiku 5.5: 질문(새 입력 + 캐시 쓰기 + 캐시 읽기)이 10만 토큰을 넘으면
    #            그 요청 전체가 다섯 배 값
    u = SimpleNamespace(
        input_tokens=60_000,
        output_tokens=1000,
        cache_read_input_tokens=30_000,
        cache_creation_input_tokens=20_000,
        cache_creation=SimpleNamespace(ephemeral_1h_input_tokens=5_000),
    )
    c = llm.cost("claude-haiku-5-5", u)
    want = (60_000 * 0.50 + 30_000 * 0.05 + 15_000 * 0.625 + 5_000 * 0.50 * 2 + 1000 * 2.50) / 1e6
    assert c["long"] and c["cw5m"] == 15_000 and c["cw1h"] == 5_000
    assert c["usd"] == pytest.approx(want)


def test_unknown_model_is_not_called(fake):
    with pytest.raises(llm.LLMError):
        llm.call("k", llm.Usage(), model="claude-unknown-9", max_tokens=10, messages=[])
    assert fake.n == 0 and _lines() == []


def test_budget_reached_stops_before_calling(fake):
    d = ledger.own_dir()
    d.mkdir(parents=True)
    (d / "budget.json").write_text(json.dumps({"limit_usd": 1.0, "period_start": "2026-10-11"}))
    (d / "opening.jsonl").write_text(
        json.dumps({"id": "opening", "t": "2026-10-11T00:00:00+09:00", "usd": 0.9999}) + "\n"
    )
    llm.call(
        "k", llm.Usage(), model="claude-sonnet-5-5", max_tokens=10, messages=[]
    )  # 0.9999 + 0.004
    with pytest.raises(llm.BudgetExhausted) as e:
        llm.call("k", llm.Usage(), model="claude-haiku-5-5", max_tokens=10, messages=[])
    assert fake.n == 1 and "팀장" in str(e.value)
    # 크레딧 바닥과 같은 길로 멈춘다(엔진 · 시험 도구가 CreditExhausted 를 위로 올린다)
    assert isinstance(e.value, llm.CreditExhausted)


def test_same_line_in_two_copies_counts_once(fake, tmp_path, monkeypatch):
    llm.call("k", llm.Usage(), model="claude-haiku-5-5", max_tokens=10, messages=[])
    other = tmp_path / "copy"
    other.mkdir()
    for p in ledger.own_dir().glob("*.jsonl"):
        (other / p.name).write_bytes(p.read_bytes())  # 작업 폴더 · 본 폴더 사본
    monkeypatch.setenv("API_LEDGER_OTHER_DIRS", str(other))
    ledger.reset_cache()
    assert ledger.spent() == pytest.approx(0.0002)


def test_entries_before_period_start_are_not_counted(fake):
    d = ledger.own_dir()
    d.mkdir(parents=True)
    # 셈 시작일은 늘 오늘보다 뒤여야 한다 — '2026-11-01'로 박아 두었더니 그날이 지나자 깨졌다(11-02)
    (d / "budget.json").write_text(json.dumps({"limit_usd": 100, "period_start": "2999-01-01"}))
    llm.call("k", llm.Usage(), model="claude-haiku-5-5", max_tokens=10, messages=[])
    assert ledger.spent() == 0
    assert ledger.spent(since="2026-10-01") == pytest.approx(0.0002)
