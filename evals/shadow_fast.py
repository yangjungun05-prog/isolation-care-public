"""빠른 길 그림자 시험 — 데스크를 건너뛰고 코드가 카드를 채우면 데스크와 얼마나 다른가(10-14).

    uv run python evals/shadow_fast.py                       # 재생 242턴 + 시험지 여덟 r1_1014
    uv run python evals/shadow_fast.py --results "evals/results/*_20261014_r2_1014.json"

API를 부르지 않는다. 지난 결과 파일(데스크가 실제로 낸 판단)만 읽는다.

【판단】 멘토(10-12)가 '동 이름 + 주제 낱말이 분명한 짧은 질문은 코드가 바로'를 권했고,
       팀장은 '답이 잘못될 수 있다'며 뺐다(결정 대기 3). 고르기 전에 잰다: 빠른 길이 탈 말이
       얼마나 되고, 그중 데스크와 다른 것(주제 · 동)과 데스크만 잡는 것(못 담은 조건 · 단정 ·
       부풀리기 요구)이 몇인지
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant import policy  # noqa: E402

# 【판단】 낱말이 분명하고 다른 주제와 겹치지 않는 넷만(갈 곳 · 지원 · 집은 낱말이 겹친다)
TOPIC_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("solo_seniors", re.compile(r"혼자 ?사는|혼자 ?사시는|독거|1인 ?가구|1인 ?세대")),
    ("youth", re.compile(r"청년|은둔")),
    ("senior_hall", re.compile(r"경로당")),
    ("livelihood", re.compile(r"수급자|기초수급|기초생활")),
)
# 【판단】 데스크가 꼭 읽어야 하는 말(줄 세우기 · 견주기 · 조건 · 때 · 부정 · 문서 · 까닭 · 단정 ·
#        지시문 건드리기 · 가린 개인정보)이 있으면 빠른 길을 타지 않는다
STOP = re.compile(
    r"많은 동|적은 동|순서|순위|제일|가장|비교|견주|보다|차이|말고|빼고|아니|없|"
    r"작년|올해|년|월|때|\d+ ?세|\d+ ?대|이상|이하|할머니|할아버지|남자|여자|남성|여성|"
    r"PDF|pdf|문서|엑셀|표|왜|까닭|이유|때문|맞지|맞죠|확실|정말|진짜|"
    r"전체|전부|모든|합계|합쳐|늘|줄|변화|추이|"
    r"지시|무시|프롬프트|규칙|역할|"
    r"\[|\]"
)
MAX_CHARS = 40


def fast_card(text: str, rule: str = "old") -> dict | None:
    """빠른 길이 탈 말이면 {'topics', 'dongs'}, 아니면 None.

    rule='old' 은 10-14 규칙(주제 낱말 넷), 'catalog' 는 10-26 멘토 답 5 '동 이름이나 주제가
    규칙으로 바로 잡히는 질문'을 장서 목록 낱말(catalog_words.json)로 넓힌 것 — 한 주제에만
    나오는 낱말이 한 주제만 걸릴 때
    """
    t = text.strip()
    if len(t) > MAX_CHARS or STOP.search(t):
        return None
    signs = (policy.PERSON_SIGN, policy.EMERGENCY_SIGN, policy.DISTRESS, policy.WEATHER_ANY)
    if any(p.search(t) for p in signs) or any(p.search(t) for _, p in policy.WEATHER_WORDS):
        return None
    dongs = policy.dongs_in_text(t)
    if rule == "catalog":
        tops = sorted({tp for w, tp in _unique_words().items() if w in t})
    else:
        tops = [tp for tp, p in TOPIC_WORDS if p.search(t)]
    if len(dongs) != 1 or len(tops) != 1:
        return None
    return {"topics": tops, "dongs": dongs}


_PARTICLE = re.compile(r"(?:은|는|이|가|을|를|의|도|에|로|와|과|만)$")
_WORDS: dict[str, str] | None = None


def _unique_words() -> dict[str, str]:
    """장서 목록 낱말에서 한 주제에만 나오는 낱말(두 글자 이상) → 그 주제."""
    global _WORDS
    if _WORDS is None:
        cat = json.loads((ROOT / "src/assistant/catalog_words.json").read_text(encoding="utf-8"))
        seen: dict[str, set[str]] = {}
        for topic, phrases in cat.items():
            for ph in phrases:
                for w in re.findall(r"[가-힣]{2,}", ph):
                    w = _PARTICLE.sub("", w) if len(w) > 2 else w
                    seen.setdefault(w, set()).add(topic)
        common = {"자료", "기준", "어림", "숫자", "주민", "지역", "전체", "이름", "목록", "한눈에"}
        _WORDS = {w: next(iter(ts)) for w, ts in seen.items() if len(ts) == 1 and w not in common}
    return _WORDS


def _turns(replay: str, results: str):
    """(어디, 턴, 말, 처리 종류, 주제, 동, 데스크가 다시 쓴 말)."""
    for f in sorted(glob.glob(str(Path(replay) / "p*.json"))):
        for t in json.loads(Path(f).read_text(encoding="utf-8"))["turns"]:
            b = t["bot"]
            card = b.get("desk_card") or {}
            dongs = (b.get("slots_after") or {}).get("dongs") or []
            restate = card.get("restate", "") + " " + " ".join(card.get("unmet") or [])
            yield (Path(f).stem, t["turn"], t["user"]["message"], b["kind"], b.get("topics") or [],
                   list(dongs), restate)  # fmt: skip
    for f in sorted(glob.glob(results)):
        for r in json.loads(Path(f).read_text(encoding="utf-8")).get("rows", []):
            if "turn" not in r:  # 데스크만 잰 결과(문제마다 여러 번)는 모양이 달라 건너뜀
                continue
            dongs = list((r.get("slots") or {}).get("dongs") or [])
            yield (Path(f).stem.rsplit("_2026", 1)[0], r["turn"], r["say"], r["kind"],
                   list(r["topics"]), dongs, r.get("restate", ""))  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", default=str(ROOT / "evals/results/personas_replay_20261013_final"))
    ap.add_argument("--results", default=str(ROOT / "evals/results/*_20261014_r1_1014.json"))
    ap.add_argument("--rule", choices=["old", "catalog"], default="old")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    total = fired = same = 0
    for where, turn, say, kind, topics, dongs, restate in _turns(a.replay, a.results):
        total += 1
        c = fast_card(say, a.rule)
        if not c:
            continue
        fired += 1
        # 【판단】 '효자동'은 코드가 효자1 · 2 · 3동으로 푼다 — 확정한 동으로 견준다
        want = policy.dongname.confirm(c["dongs"])["dongs"]
        ok = kind == "answer" and topics == c["topics"] and dongs == want
        same += ok
        if a.quiet and ok:
            continue
        print(f"{'같음' if ok else '다름'} {where} T{turn}: {say}")
        print(f"     코드 {c['topics']} {want} | 데스크 {kind} {topics} {dongs}")
        print(f"     데스크가 다시 쓴 말: {restate.strip()[:90]}")
    print(f"\n{total}턴 중 빠른 길이 탔을 턴 {fired} · 주제 · 동이 데스크와 같음 {same}")


if __name__ == "__main__":
    main()
