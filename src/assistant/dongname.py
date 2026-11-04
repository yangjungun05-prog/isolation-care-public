"""동 이름 확정 — 사용자가 쓴 동 이름 → 정식 행정동(강남구 22 · 춘천시 25).

big-contest `src/bigcon/dongname.py`(10-08)를 옮겼다. 동작은 같다.

【판단】 10-08 시험: AI(Solar pro4)에게 동 이름까지 정식으로 바꾸게 하면 95%만 맞았다
       (남산면 → 남면 같은 틀림). 틀린 동은 틀린 숫자로 이어지므로 이름 확정은 코드가 한다.
       AI는 말에 쓰인 이름을 그대로 뽑고, 여기서 정한다. 못 정하면 '모름'으로 돌려 비서가 되묻는다.

- 정식 이름 그대로 → 그 동
- 숫자 없는 이름(삼성동 · 대치동 · 효자동) → 그 이름의 동 전부
- 옛 이름(일원2동 → 개포3동, 2022-12 신설)
- 숫자를 글자로 쓴 것(대치사동 · 역삼이동)
- 오타는 자판 누름 단위로 견준다(사음서음동 → 삼성동). 영어 자판으로 친 것(tntjehd)도 같다
- 없는 번호(역삼3동 · 효자4동)는 비슷한 동으로 바꾸지 않고 '없는 번호'로 돌린다
"""

from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

DONGS: dict[str, list[str]] = {
    "강남구": (
        "개포1동 개포2동 개포3동 개포4동 논현1동 논현2동 대치1동 대치2동 대치4동 도곡1동 도곡2동 "
        "삼성1동 삼성2동 세곡동 수서동 신사동 압구정동 역삼1동 역삼2동 일원1동 일원본동 청담동"
    ).split(),
    "춘천시": (
        "강남동 교동 근화동 남면 남산면 동내면 동면 동산면 북산면 사북면 서면 석사동 소양동 신동면 "
        "신북읍 신사우동 약사명동 조운동 퇴계동 효자1동 효자2동 효자3동 후평1동 후평2동 후평3동"
    ).split(),
}
OLD_NAMES = {"일원2동": ("강남구", "개포3동")}  # 2022-12 개포3동 신설
_PLACES = Path(__file__).resolve().parents[2] / "data" / "public" / "places.json"
_VILLAGE = re.compile(r"^([가-힣]+?)\d*(?:,\d+)?리")


@lru_cache(maxsize=1)
def villages() -> dict[str, tuple[str, ...]]:
    """춘천 마을(리) 이름 → 그 마을이 있는 읍면(10-15 페르소나 q06: '율문리'를 못 알아들음).

    【판단】 경로당 · 마을회관 이름('율문1리 경로당')에서 뽑는다. 두 읍면에 같은 마을 이름이 있으면
           둘 다(발산리 = 신북읍 · 남면) — 짐작하지 않고 되묻는다
    """
    if not _PLACES.exists():
        return {}
    raw = json.loads(_PLACES.read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for dong, d in raw.get("dongs", {}).items():
        if d.get("region") != "춘천시":
            continue
        for h in (d.get("halls") or {}).get("list", []):
            m = _VILLAGE.match(h.get("name", ""))
            if m:
                out.setdefault(m.group(1), set()).add(dong)
    return {k: tuple(sorted(v)) for k, v in out.items()}


REGION_WORDS = {"강남", "강남구", "춘천", "춘천시", "서울", "강원"}
NUM_WORD = {"일": "1", "이": "2", "삼": "3", "사": "4"}

# 【기능】 (지역, '삼성동') → [삼성1동, 삼성2동]
FAMILY: dict[tuple[str, str], list[str]] = {}
for _reg, _names in DONGS.items():
    for _n in _names:
        _m = re.match(r"^(.+?)(\d|본)동$", _n)
        if _m:
            FAMILY.setdefault((_reg, _m.group(1) + "동"), []).append(_n)

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅗㅏ ㅗㅐ ㅗㅣ ㅛ ㅜ ㅜㅓ ㅜㅔ ㅜㅣ ㅠ ㅡ ㅡㅣ ㅣ".split()
JONG = [""] + (
    "ㄱ ㄲ ㄱㅅ ㄴ ㄴㅈ ㄴㅎ ㄷ ㄹ ㄹㄱ ㄹㅁ ㄹㅂ ㄹㅅ ㄹㅌ ㄹㅍ ㄹㅎ "
    "ㅁ ㅂ ㅂㅅ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ"
).split()
KEY = dict(
    zip(
        "qwertyuiopasdfghjklzxcvbnmQWERTOP",
        "ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔㅁㄴㅇㄹㅎㅗㅓㅏㅣㅋㅌㅊㅍㅠㅜㅡㅃㅉㄸㄲㅆㅒㅖ",
        strict=True,
    )
)
# 【판단】 자판 누름이 이만큼 같아야 오타로 본다(1.0이면 똑같음)
CUT = 0.75


def region_of(dong: str) -> str | None:
    for reg, names in DONGS.items():
        if dong in names:
            return reg
    return None


# 【기능】 우리 동 이름 앞에 붙어도 우리 동인 말(지역 이름 · 가리키는 말)
OURS_PREFIX = REGION_WORDS | {
    "강남구", "춘천시", "서울시", "서울특별시", "강원도", "강원특별자치도", "강원도춘천시",
    "서울강남구", "서울시강남구", "서울특별시강남구",
    "우리", "저희", "관내", "담당", "그", "이", "아까",
}  # fmt: skip


def initials(word: str) -> str:
    """'수서동' → 'ㅅㅅㄷ'."""
    return "".join(
        CHO[(ord(ch) - 0xAC00) // 588] if 0xAC00 <= ord(ch) <= 0xD7A3 else ch for ch in word
    )


def chosung_dongs(token: str) -> list[str]:
    """초성 줄과 맞는 동 이름(정식 이름 · 숫자 없는 이름)."""
    names = {n for ds in DONGS.values() for n in ds} | {fam for (_, fam) in FAMILY}
    return sorted(n for n in names if initials(n) == token)


def _region_of_name(n: str) -> str | None:
    """정식 이름 · 숫자 없는 이름 → 지역."""
    return region_of(n) or next((r for (r, fam) in FAMILY if fam == n), None)


def _shown(n: str, cand: dict[str, tuple[str, list[str]]]) -> str:
    """되묻기에 내밀 이름 — '수서'처럼 줄인 이름은 정식 이름으로."""
    reg, members = cand[n]
    if n in DONGS[reg] or (reg, n) in FAMILY:
        return n
    return members[0]


def keys(s: str) -> str:
    """글 → 자판 누름 줄. '삼성' → ㅅㅏㅁㅅㅓㅇ, 'tkatjd' → ㅅㅏㅁㅅㅓㅇ."""
    out = []
    for ch in s:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            i = o - 0xAC00
            out += [CHO[i // 588], JUNG[(i % 588) // 28], JONG[i % 28]]
        elif ch in KEY:
            out.append(KEY[ch])
        elif not ch.isspace():
            out.append(ch)
    return "".join(out)


def _candidates(regs: list[str]) -> dict[str, tuple[str, list[str]]]:
    out: dict[str, tuple[str, list[str]]] = {}
    for reg in regs:
        for n in DONGS[reg]:
            out[n] = (reg, [n])
        for (r, fam), members in FAMILY.items():
            if r == reg:
                out[fam] = (reg, members)
        for n in DONGS[reg]:  # '압구정' · '청담'처럼 '동'을 뺀 것
            out.setdefault(re.sub(r"(동|면|읍)$", "", n), (reg, [n]))
    return out


def resolve(mention: str, region: str | None = None) -> dict:
    """이름 하나 → {'dongs', 'region', 'how', 'near'}. near = 못 정했을 때 비슷한 이름."""
    t = re.sub(r"\s", "", str(mention))
    if not re.search(r"(동|면|읍)$", t):
        t = re.sub(r"(에서|에는|은|는|이|가|을|를|에|의|도)$", "", t)
    if not t or t in REGION_WORDS or t.endswith(("구", "시", "군", "도")):
        return {"dongs": [], "region": None, "how": "지역 이름", "near": []}
    # 【판단】 10-29 회귀 village_6 T2: 데스크가 앞 답의 '사북면 지암리' · '남면 추곡리'를 동 칸에
    #        적으면 '찾지 못했어요'로 되물었다 → 읍면 이름이 붙은 마을은 그 읍면(같은 이름 마을이
    #        두 읍면에 있어도 붙은 읍면으로 정해진다)
    m = re.fullmatch(r"([가-힣]+?[읍면])([가-힣]+?)\d*리", t)
    if m and m.group(1) in villages().get(m.group(2), ()):
        return {"dongs": [m.group(1)], "region": "춘천시", "how": f"마을({t} → {m.group(1)})",
                "near": []}  # fmt: skip
    m = re.fullmatch(r"([가-힣]+?)\d*리", t)
    if m and m.group(1) in villages():
        where = villages()[m.group(1)]
        if len(where) == 1:
            return {"dongs": [where[0]], "region": "춘천시", "how": f"마을({t} → {where[0]})",
                    "near": []}  # fmt: skip
        return {"dongs": [], "region": None, "how": "마을 여러 곳", "near": list(where)}
    if t in OLD_NAMES:
        reg, new = OLD_NAMES[t]
        return {"dongs": [new], "region": reg, "how": f"옛 이름({t} → {new})", "near": []}
    # '대치사동' → 대치4동, 10-29 변수 시험 c01_017 '개포삼'(동을 뺀 글자 번호) → 개포3동
    m = re.match(r"^(.+?)(일|이|삼|사|\d)동?$", t)
    if m and any(fam == m.group(1) + "동" for (_, fam) in FAMILY):
        t = m.group(1) + NUM_WORD.get(m.group(2), m.group(2)) + "동"
    order = [region] if region in DONGS else []
    order += [r for r in DONGS if r not in order]
    for reg in order:  # 정식 이름 · 숫자 없는 이름 · '동' 뺀 이름
        cand = _candidates([reg])
        if t in cand:
            return {"dongs": cand[t][1], "region": reg, "how": "목록에 있음", "near": []}
    m = re.match(r"^(.+?)(\d)동$", t)  # 없는 번호: 역삼3동 · 효자4동
    if m:
        for reg in order:
            fam = FAMILY.get((reg, m.group(1) + "동"))
            if fam:
                return {"dongs": [], "region": reg, "how": "없는 번호", "near": fam}
    if re.fullmatch(r"[ㄱ-ㅎ]+", t):
        # 【판단】 초성만 쓴 이름은 짐작하지 않는다(맞는 동이 하나뿐이면 keyboard.fix 가 이미 바꿈).
        #        맞는 동을 다 보이되(ㅅㅅㄷ → 삼성동 · 수서동 · 신사동 · 석사동) 지금 지역 동을 앞에
        hits = sorted(chosung_dongs(t), key=lambda n: _region_of_name(n) != order[0])
        return {"dongs": [], "region": None, "how": "초성", "near": hits[:4]}
    # 【판단】 우리 동 이름 앞에 다른 곳 이름이 붙으면(부산 서면 · 판교동) 오타로 맞추지 않는다.
    #        붙여 읽으면 '부산서면'이 북산면(0.84)이 됐다(문제 목록 2-6). 우리 지역 이름 · 가리키는
    #        말(춘천 서면 · 우리 수서동)이면 그 동이다
    for reg in order:
        cand = _candidates([reg])
        for n in sorted(cand, key=len, reverse=True):
            if len(n) >= 2 and re.search(r"(동|면|읍)$", n) and t.endswith(n) and t != n:
                head = t[: -len(n)]
                if head in OURS_PREFIX:
                    return {"dongs": cand[n][1], "region": reg, "how": "목록에 있음", "near": []}
                return {
                    "dongs": [],
                    "region": None,
                    "how": "다른 곳 이름",
                    "near": [_shown(n, cand)],
                }
    k = keys(t)
    for regs in ([order[0]], list(DONGS)):
        # 【판단】 우리 동 이름 앞에 글자가 더 붙은 이름(판교동 = 판 + 교동)은 다른 곳이다.
        #        오타로 맞추면 성남 판교동이 춘천 교동이 된다(10-12 밤 시험에서 찾음)
        cand = {n: v for n, v in _candidates(regs).items() if not (t != n and t.endswith(n))}
        sc = sorted(
            ((difflib.SequenceMatcher(None, k, keys(n)).ratio(), n) for n in cand), reverse=True
        )
        if not sc or sc[0][0] < CUT:
            continue
        reg, ds = cand[sc[0][1]]
        # 【판단】 '삼성동'과 '삼성1동'은 겨루지 않는다(같은 동을 가리킴)
        rival = next((s for s, n in sc[1:] if not set(cand[n][1]) & set(ds)), 0)
        if sc[0][0] - rival >= 0.05:
            how = f"오타({t} → {sc[0][1]}, {sc[0][0]:.2f})"
            return {"dongs": ds, "region": reg, "how": how, "near": []}
    every = _candidates(list(DONGS))
    scored = sorted(
        ((difflib.SequenceMatcher(None, k, keys(n)).ratio(), n) for n in every), reverse=True
    )
    near = list(dict.fromkeys(_shown(n, every) for _, n in scored))[:3]
    return {"dongs": [], "region": None, "how": "모름", "near": near}


def confirm(mentions: list[str], region: str | None = None) -> dict:
    """여러 이름 → {'dongs', 'regions', 'unknown': [(쓴 이름, 비슷한 이름)], 'how'}."""
    dongs: list[str] = []
    regions: list[str] = []
    unknown: list[tuple[str, list[str]]] = []
    how: list[tuple[str, str]] = []
    for mtn in mentions:
        r = resolve(mtn, region)
        how.append((mtn, r["how"]))
        if r["dongs"]:
            dongs += r["dongs"]
            regions.append(r["region"])
        elif r["how"] != "지역 이름":
            unknown.append((mtn, r["near"]))
    return {
        "dongs": sorted(set(dongs)),
        "regions": sorted(set(regions)),
        "unknown": unknown,
        "how": how,
    }
