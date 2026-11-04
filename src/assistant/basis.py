"""자료의 때 — 동 자료 스냅숏(dong_profiles.json)이 어느 판으로 만들어졌는지.

【정함 10-16 팀장】 자료는 2026 최신 판. 10-19부터 big-contest가 가장 새 판으로 다시 계산해
       'data_basis'(자료마다의 판)를 적는다. 코드는 '2025-12' 같은 달을 박지 않고 여기서 읽는다
       (10-19 팀장: "앞으로도 우리가 건들지 안하도 모든 데이터들이 자동으로" —
       새 판이 오면 말도 따라 바뀜).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "public" / "dong_profiles.json"
MONTH = re.compile(r"^\d{4}-\d{2}$")


@lru_cache(maxsize=8)
def _read(path: str, mtime: int) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _raw(path: Path = SNAPSHOT) -> dict:
    """파일이 바뀌면(자동 받기, 10-19) 다시 읽는다."""
    return _read(str(path), path.stat().st_mtime_ns)


def data_basis() -> dict:
    """{'주민등록 인구': '2026-09', '주민등록 1인세대': '2026-09', '상가': '2026-06',
    '주민등록 1인세대 1년 전': '2025-09'}. 옛 스냅숏(10-15판)에는 없어 2025-12로 본다."""
    raw = _raw()
    return raw.get("data_basis") or {
        "주민등록 인구": "2025-12",
        "주민등록 1인세대": "2025-12",
        "상가": "2025-12",
        "주민등록 1인세대 1년 전": "2024-12",
    }


def reg() -> str:
    """주민등록 판(예: '2026-09')."""
    return data_basis()["주민등록 인구"]


def reg_prev() -> str:
    """늘고 줄음을 견주는 1년 전 판(예: '2025-09')."""
    return data_basis()["주민등록 1인세대 1년 전"]


def shops() -> str:
    return data_basis()["상가"]


def months(values: dict | None) -> tuple[str, str] | None:
    """{'2025-09': a, '2026-09': b} → ('2025-09', '2026-09').

    달 칸이 둘 넘으면 가장 앞 · 가장 뒤.
    """
    keys = sorted(k for k in (values or {}) if MONTH.match(k))
    return (keys[0], keys[-1]) if len(keys) >= 2 else None


def ko(ym: str) -> str:
    """'2026-09' → '2026년 9월'."""
    return f"{ym[:4]}년 {int(ym[5:7])}월"
