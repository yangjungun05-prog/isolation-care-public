"""자판 손질 — 데스크에 보내기 전에 코드가 고치는 글자(10-14).

- 영어 자판으로 친 한글(tntjehd → 수서동, cjdsus → 청년)을 두벌식 자판 그대로 한글로 조합한다
- 초성만 쓴 동 이름(ㅂㅅㅁ → 북산면)은 맞는 동이 하나일 때만 바꾸고, 여럿이면(ㅅㅅㄷ → 수서동 ·
  신사동 · 삼성동) 그대로 두어 비서가 되묻게 한다(policy.desk_sanity)

【판단】 10-14 데스크 시험(desk_only_60 r0): 데스크(AI)가 'tntjehd'를 알아볼 수 없는 글자로 보고
       버렸다(A01 3/5 · 일원본동 A02 5/5). 100턴 T50은 '삼성1·2동'으로 짐작했다(20번 중 4번).
       영어 자판 → 한글은 정해진 변환이라 코드가 맡는다(동 이름 확정과 같은 까닭).
       'ㅅㅅㄷ'은 데스크가 5번 중 2번 말없이 수서동으로 짐작했다 — 틀린 동이 확인 없이 쓰이는 일
       ('0개' 기준 ①)이라 코드가 막는다.
【판단】 영어 낱말(PDF · SKT · excel · Haiku 등)은 바꾸지 않는다: 모두 대문자인 말(약어)은 건너뛰고,
       두벌식으로 빈틈없이 두 글자 이상 조합될 때만 바꾼다(영어 낱말은 거의 조합이 깨진다).
"""

from __future__ import annotations

import re

from src.assistant import dongname

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = (
    "",
    "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ",
    "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ",
)  # fmt: skip
# 【기능】 두벌식 자판: 영어 글쇠 → 자모(Shift는 쌍자음 · ㅒ · ㅖ만, 나머지 대문자는 소문자와 같다)
KEY = dict(
    zip(
        "qwertyuiopasdfghjklzxcvbnmQWERTOP",
        "ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔㅁㄴㅇㄹㅎㅗㅓㅏㅣㅋㅌㅊㅍㅠㅜㅡㅃㅉㄸㄲㅆㅒㅖ",
        strict=True,
    )
)
V_PAIR = {
    ("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ", ("ㅜ", "ㅓ"): "ㅝ",
    ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ", ("ㅡ", "ㅣ"): "ㅢ",
}  # fmt: skip
F_PAIR = {
    ("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ",
    ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ",
    ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ",
}  # fmt: skip
_LATIN = re.compile(r"[A-Za-z]+")
_CHOSUNG = re.compile(r"(?<![가-힣ㄱ-ㅎ])[ㄱ-ㅎ]{3,5}(?![가-힣ㄱ-ㅎ])")


def _key(ch: str) -> str:
    return KEY.get(ch) or KEY.get(ch.lower(), "")


def compose(token: str) -> str | None:
    """영어 글쇠 줄 → 한글(두벌식). 빈틈없이 조합되지 않으면 None."""
    jamo = [_key(c) for c in token]
    if not all(jamo):
        return None
    out: list[str] = []
    i, n = 0, len(jamo)
    while i < n:
        c = jamo[i]
        if c not in CHO or i + 1 >= n or jamo[i + 1] not in JUNG:
            return None
        v = jamo[i + 1]
        i += 2
        if i < n and (v, jamo[i]) in V_PAIR:
            v = V_PAIR[(v, jamo[i])]
            i += 1
        f = ""
        if i < n and jamo[i] in JONG and not (i + 1 < n and jamo[i + 1] in JUNG):
            f = jamo[i]
            i += 1
            pair = (f, jamo[i]) if i < n else None
            if pair in F_PAIR and not (i + 1 < n and jamo[i + 1] in JUNG):
                f = F_PAIR[pair]
                i += 1
        out.append(chr(0xAC00 + CHO.index(c) * 588 + JUNG.index(v) * 28 + JONG.index(f)))
    return "".join(out)


# 【판단】 10-20 페르소나 o03 r4: 한글 문장 속 영어 낱말 'turn'이 '셔구'로 조합돼 '(turn을 셔구로
#        읽었어요)'가 나가고 글쓴이가 그 메모를 속말로 옮겼다. 조합된 말이 우리 동 이름 · 자주 쓰는
#        낱말을 품을 때, 또는 말의 글자 대부분이 영어(한글 자판을 켜지 않고 친 말)일 때만 바꾼다
VOCAB = (
    "청년", "어르신", "노인", "할머니", "할아버지", "혼자", "독거", "경로당", "수급", "버스",
    "날씨", "약국", "복지관", "주민센터", "행정복지센터", "몇 명", "명이", "순위", "진단", "현황",
    "괜찮", "지내", "걱정", "알려", "보여",
)  # fmt: skip
_HANGUL = re.compile(r"[가-힣]")


def _known(word: str) -> bool:
    names = [n for ns in dongname.DONGS.values() for n in ns]
    stems = {n[:-1] for n in names if len(n) >= 3}
    return (
        any(n in word for n in names)
        or any(s in word for s in stems)
        or any(v in word for v in VOCAB)
    )


def _latin_to_hangul(token: str, mostly_latin: bool = False) -> str | None:
    if token.isupper() or len(token) < 3:  # 약어(PDF · SKT · KT)
        return None
    word = compose(token)
    if not word or len(word) < 2:
        return None
    return word if mostly_latin or _known(word) else None


def ambiguous_chosung(text: str) -> list[str]:
    """맞는 동이 둘 이상인 초성 줄(되묻게 할 것)."""
    return [t for t in _CHOSUNG.findall(text) if len(dongname.chosung_dongs(t)) > 1]


def fix(text: str) -> tuple[str, list[tuple[str, str]]]:
    """→ (고친 말, [(쓴 글자, 바꾼 글자)])."""
    typed: list[tuple[str, str]] = []
    # 한글 자판을 켜지 않고 친 말: 영어 글자가 한글보다 두 배 넘게 많고, 그 영어 낱말이 모두
    # 한글로 빈틈없이 조합될 때('persona turn'처럼 진짜 영어가 섞이면 아니다)
    words = [t for t in _LATIN.findall(text) if len(t) >= 3 and not t.isupper()]
    n_latin = sum(len(t) for t in words)
    mostly_latin = (
        bool(words) and n_latin >= 2 * len(_HANGUL.findall(text)) and all(compose(t) for t in words)
    )

    def latin(m: re.Match[str]) -> str:
        word = _latin_to_hangul(m.group(0), mostly_latin)
        if word is None:
            return m.group(0)
        typed.append((m.group(0), word))
        return word

    def cho(m: re.Match[str]) -> str:
        hits = dongname.chosung_dongs(m.group(0))
        if len(hits) != 1:
            return m.group(0)
        typed.append((m.group(0), hits[0]))
        return hits[0]

    text = _LATIN.sub(latin, text)
    text = _CHOSUNG.sub(cho, text)
    return text, typed
