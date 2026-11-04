"""장서 목록의 주제마다 시험 질문이 3개 이상(멘토 답 2, 10-26).

자료(주제)를 더하면 시험지에도 질문 셋을 더해야 이 시험이 통과한다 — 빠뜨림을 막는다.
대화 시험지(turns[].topic)와 데스크 시험지(cases[].expect.topics)를 함께 센다.
'내 담당 지역'은 kind settings, '되짚기'는 kind recall로도 센다.
"""

import json
from collections import Counter
from pathlib import Path

from src.assistant.catalog import TOPICS

ROOT = Path(__file__).resolve().parents[1]
BY_KIND = {"my_region": "settings", "recall": "recall"}
MIN = 3


def _count() -> Counter:
    per: Counter = Counter()
    for fn in (ROOT / "evals" / "scenarios").glob("*.json"):
        d = json.loads(fn.read_text(encoding="utf-8"))
        items = [(t.get("topic") or [], t.get("kind") or []) for t in d.get("turns", [])]
        items += [
            ((c.get("expect") or {}).get("topics") or [], (c.get("expect") or {}).get("kind") or [])
            for c in d.get("cases", [])
        ]
        for topics, kinds in items:
            topics = [topics] if isinstance(topics, str) else topics
            kinds = [kinds] if isinstance(kinds, str) else kinds
            for t in TOPICS:
                if t.id in topics or BY_KIND.get(t.id) in kinds:
                    per[t.id] += 1
    return per


def test_every_topic_has_at_least_three_test_questions():
    per = _count()
    short = {t.id: per.get(t.id, 0) for t in TOPICS if per.get(t.id, 0) < MIN}
    assert not short, f"시험 질문이 {MIN}개보다 적은 주제: {short}"
