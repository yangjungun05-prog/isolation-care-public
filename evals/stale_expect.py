"""시험지 기대값(has)이 지금 자료에도 있는지 전수 점검 — 낡은 기대값 후보를 찾는다(10-26).

    uv run python evals/stale_expect.py

API를 부르지 않는다. 시험지 턴마다 기대 주제 · 동 · 대상으로 사서를 불러, 기대 낱말이 자료 줄
(또는 참고)에 있는지 본다. 없으면 '후보' — 자료가 새 판으로 바뀌었거나, 코드가 붙이는 글(밝힘 ·
근거 꼬리)에서 오는 말이라 사람이 확인한다.

【판단】 10-26 측정에서 rules_v6_16 T4 기대값(10-12 판 '2,543 · 남녀')이 낡아 채점이 거꾸로 됐다.
       남들(평가 방법 조사 arXiv 2407.04069 · 실무 지침 oneuptime · latitude · Langfuse):
       자료가 바뀌면 기대 답부터 검토해 고치고, 고친 기록을 남겨 새 문제 추가와 구분한다.
       우리도 시험지를 git으로 관리하고 자료가 날마다 새 판이라 같은 환경
       → 시험지 'changed' 칸에 까닭을 적고 고친다
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant import librarian  # noqa: E402
from src.assistant.catalog import BY_ID  # noqa: E402
from src.assistant.data_source import JsonDongData  # noqa: E402
from src.assistant.slots import Slots  # noqa: E402


def main() -> None:
    data = JsonDongData()
    total = checked = 0
    for fn in sorted(glob.glob(str(ROOT / "evals" / "scenarios" / "*.json"))):
        sc = json.loads(Path(fn).read_text(encoding="utf-8"))
        region0 = (sc.get("profile") or {}).get("member_region")
        if sc.get("as_of"):  # 되감는 시험지(날씨)는 그날 기준이라 건너뜀
            continue
        for i, t in enumerate(sc.get("turns", []), 1):
            has = t.get("has") or []
            topics = tuple(x for x in (t.get("topic") or []) if x in BY_ID)
            if not has or not topics:
                continue
            total += 1
            dongs = tuple(t.get("dongs") or ())
            # 질문 속 지역 말이 먼저('춘천은 …' — 시험지 기본 지역이 강남이어도)
            said = "춘천시" if "춘천" in t["say"] else "강남구" if "강남" in t["say"] else None
            region = t.get("region") or said or region0
            if any(BY_ID[x].needs == "dong" for x in topics) and not dongs:
                continue
            checked += 1
            sex = "남" if "할아버지" in t["say"] else "여" if "할머니" in t["say"] else None
            slots = Slots(region=region, dongs=dongs, target=t.get("target"), sex=sex)
            text = "\n".join(
                "\n".join(f.lines + f.notes)
                for x in topics
                for f in [librarian.gather(x, slots, data, t["say"])]
            )
            miss = [h for h in has if h not in text]
            if miss:
                print(f"후보 {Path(fn).stem} T{i}: {t['say'][:40]} | 없음 {miss} | 주제 {topics}")
    print(f"\n기대값 있는 턴 {total} · 점검한 턴 {checked}(동이 앞 대화에서 오는 턴은 건너뜀)")


if __name__ == "__main__":
    main()
