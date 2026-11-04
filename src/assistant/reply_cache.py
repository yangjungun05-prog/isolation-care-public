"""같은 입력이면 그날 같은 답 — 데스크 카드 · 글쓴이 답을 기억한다(10-26 멘토 답 4).

【판단】 멘토: LLM은 같은 입력에도 늘 같은 답을 내지 않는다. 흔들림을 0으로 만들 수는 없으니
       같은 입력에 대한 응답을 기억해 두면 사용자에게는 같은 답이 나간다.
       열쇠는 AI에 들어가는 것 전부(모델 · 지시문 · 질문 · 자료 줄 · 직전 답 · 참고)와 오늘 날짜다.
       자료가 새 판으로 바뀌면 자료 줄이 달라져 저절로 새로 묻고, 날이 바뀌어도 새로 묻는다.
       검사를 통과한 것만 넣는다. 기억은 데스크 · 글쓴이 객체마다(서버 하나에 하나) 따로 둔다
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import OrderedDict
from threading import Lock
from typing import Any


class DayCache:
    def __init__(self, size: int) -> None:
        self.size = size
        self._d: OrderedDict[str, Any] = OrderedDict()
        self._lock = Lock()
        self.hits = 0

    def key(self, *parts: object) -> str:
        raw = json.dumps(
            [dt.date.today().isoformat(), *parts], ensure_ascii=False, sort_keys=True, default=str
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, k: str) -> Any | None:
        if self.size <= 0:
            return None
        with self._lock:
            v = self._d.get(k)
            if v is not None:
                self._d.move_to_end(k)
                self.hits += 1
            return v

    def put(self, k: str, v: Any) -> None:
        if self.size <= 0:
            return
        with self._lock:
            self._d[k] = v
            self._d.move_to_end(k)
            while len(self._d) > self.size:
                self._d.popitem(last=False)
