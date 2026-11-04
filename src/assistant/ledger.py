"""API 장부 — Claude API를 부를 때마다 쓴 토큰과 돈을 한 줄씩 적고,
합계가 예산에 닿으면 더 부르지 않게 한다.

【판단】 10-15 팀장: "api를 사용할떄마다 얼마를 사용했는지 모두 기록하게 해줘.
       (정밀하고 세밀하게 전부 다 빠지지않고)", "그게 총 100달러가 된다면 api사용은 못하게"
       → 사람이 적으면 빠질 수 있어 API를 부르는 곳(llm.call · llm.stream_text)에서 코드가 적는다.
       big-contest 저장소의 src/bigcon/api_ledger.py 와 같은 모양이고,
       합계는 두 저장소 장부를 더한다.
- 줄 하나 = 응답 하나(메시지 id). 같은 줄이 여러 사본(작업 폴더 · 본 폴더 · 두 저장소)에
  있어도 id로 한 번만 센다
- 돈은 정가로 셈(llm.PRICE, platform.claude.com/docs/en/about-claude/pricing 10-15 다시 확인).
  청구와 맞춰 볼 수 있게 토큰 종류별 수 · 메시지 id · 요청 id도 적는다
- 파일: api_usage/ledger_<PC 이름>.jsonl
  (PC마다 따로라 git에서 부딪히지 않음, .gitattributes merge=union)
- 예산: api_usage/budget.json(한도 · 셈 시작일). 장부 이전에 쓴 돈은 api_usage/opening.jsonl 한 줄
- 시험(pytest)은 API_LEDGER_DIR 를 임시 폴더로 바꿔 진짜 장부에 적지 않는다(tests/conftest.py)

보기: uv run python -m src.assistant.ledger [--since 2026-10-15T10:00]
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = "BISU"
# 【판단】 두 저장소는 보통 같은 폴더에 나란히 둔다(PC: E:/CLAUDE, 노트북: Downloads).
#        폴더 이름이 PC마다 달라 셋 다 본다
SIBLINGS = ("BIGCONTEST_AI_BISU", "bigcontest", "big-contest")
DEFAULT_BUDGET = {"limit_usd": 100.0, "period_start": "2026-10-11"}
KST = timezone(timedelta(hours=9))
RUN = f"{os.getpid()}-{int(time.time())}"

_LOCK = threading.Lock()
_files: dict[Path, int] = {}  # 읽은 파일 → 읽은 곳(바이트)
_seen: dict[str, tuple[str, float]] = {}  # 줄 id → (때, 돈)


def own_dir() -> Path:
    return Path(os.environ.get("API_LEDGER_DIR") or ROOT / "api_usage")


def dirs() -> list[Path]:
    """합계에 넣을 장부 폴더: 이 저장소 + 옆 저장소 + 같은 저장소의 작업 폴더(worktree)들."""
    out = [own_dir()]
    out += [Path(p) for p in os.environ.get("API_LEDGER_OTHER_DIRS", "").split(os.pathsep) if p]
    if not os.environ.get("API_LEDGER_DIR"):
        main = ROOT.parents[2] if ROOT.parent.name == "worktrees" else ROOT
        roots = [main] + [main.parent / n for n in SIBLINGS]
        for r in roots:
            out.append(r / "api_usage")
            out += list((r / ".claude" / "worktrees").glob("*/api_usage"))
    seen, uniq = set(), []
    for d in out:
        key = os.path.normcase(str(d.resolve())) if d.exists() else None
        if key and key not in seen:
            seen.add(key)
            uniq.append(d)
    return uniq


def machine() -> str:
    name = os.environ.get("COMPUTERNAME") or socket.gethostname() or "unknown"
    return re.sub(r"[^\w.-]", "_", name)


def budget() -> dict:
    p = own_dir() / "budget.json"
    b = dict(DEFAULT_BUDGET)
    if p.exists():
        b.update(json.loads(p.read_text(encoding="utf-8")))
    return b


def record(entry: dict) -> None:
    """한 번 부른 값을 장부에 한 줄 더한다. 적지 못하면 오류를 낸다(빠뜨리지 않게)."""
    line = {
        "t": datetime.now(KST).isoformat(timespec="milliseconds"),
        "machine": machine(),
        "repo": REPO,
        "run": RUN,
        "argv": " ".join(sys.argv)[:300],
        **entry,
    }
    data = (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8")
    path = own_dir() / f"ledger_{machine()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(path, "ab") as f:
        _lock(f)
        try:
            f.write(data)
            f.flush()
        finally:
            _unlock(f)


def _lock(f) -> None:
    # 【판단】 여러 시험을 같이 돌리면 여러 프로세스가 한 파일에 쓴다
    #        — 줄이 섞이지 않게 파일을 잠근다
    if os.name == "nt":
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_EX)


def _unlock(f) -> None:
    if os.name == "nt":
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _scan() -> None:
    """장부 파일에서 새로 붙은 줄만 읽는다(부를 때마다 다 읽지 않게)."""
    for d in dirs():
        for p in sorted(d.glob("*.jsonl")):
            start = _files.get(p, 0)
            size = p.stat().st_size
            if size < start:  # 파일이 줄었으면(git 되돌림 등) 처음부터
                start = 0
            if size == start:
                continue
            with open(p, "rb") as f:
                f.seek(start)
                chunk = f.read(size - start)
            end = chunk.rfind(b"\n") + 1  # 다 쓰지 않은 마지막 줄은 다음에
            for raw in chunk[:end].splitlines():
                if raw.strip():
                    e = json.loads(raw)
                    _seen[e["id"]] = (e["t"], float(e["usd"]))
            _files[p] = start + end


def spent(since: str = "") -> float:
    """셈 시작일(또는 since) 뒤로 장부에 적힌 돈(id마다 한 번)."""
    with _LOCK:
        _scan()
        start = since or budget()["period_start"]
        return sum(usd for t, usd in _seen.values() if t >= start)


def over_budget() -> tuple[bool, float, float]:
    b = budget()
    s = spent()
    return s >= float(b["limit_usd"]), s, float(b["limit_usd"])


def reset_cache() -> None:
    """시험용: 읽은 기록을 비운다."""
    with _LOCK:
        _files.clear()
        _seen.clear()


def report(since: str = "") -> str:
    """사람이 읽는 합계: 예산 · 쓴 돈 · 남은 돈, 날마다 · 모델마다 · PC마다 · 실행마다."""
    b = budget()
    with _LOCK:
        _scan()
    rows: list[dict] = []
    for d in dirs():
        for p in sorted(d.glob("*.jsonl")):
            for raw in p.read_bytes().splitlines():
                if raw.strip():
                    rows.append(json.loads(raw))
    uniq = {r["id"]: r for r in rows if r["t"] >= b["period_start"]}
    total = sum(float(r["usd"]) for r in uniq.values())
    lines = [
        f"예산 ${float(b['limit_usd']):.2f} · 셈 시작 {b['period_start']} · 쓴 돈 ${total:.4f} · "
        f"남은 돈 ${float(b['limit_usd']) - total:.4f} · 응답 {len(uniq)}개",
    ]
    for title, key in (
        ("날마다", lambda r: r["t"][:10]),
        ("모델마다", lambda r: r.get("model") or "장부 이전"),
        (
            "PC · 저장소마다",
            lambda r: f"{r['machine']} · {r['repo']}" if "machine" in r else "장부 이전",
        ),
    ):
        agg: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        for r in uniq.values():
            a = agg[key(r)]
            a[0] += 1
            a[1] += float(r["usd"])
        lines.append(f"[{title}]")
        lines += [f"  {k}: {n}번 ${u:.4f}" for k, (n, u) in sorted(agg.items())]
    if since:
        part = [r for r in uniq.values() if r["t"] >= since]
        runs: dict[str, list] = defaultdict(lambda: [0, 0.0, ""])
        for r in part:
            a = runs[r.get("run", "")]
            a[0] += 1
            a[1] += float(r["usd"])
            a[2] = r.get("argv", "")
        lines.append(f"[{since} 뒤] {len(part)}번 ${sum(float(r['usd']) for r in part):.4f}")
        lines += [f"  {n}번 ${u:.4f} — {argv[:120]}" for n, u, argv in runs.values()]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="API 장부 합계")
    ap.add_argument("--since", default="", help="이 때 뒤로 쓴 돈도 따로(예: 2026-10-15T10:00)")
    print(report(ap.parse_args().since))
