"""답 둘레의 것 — 이어 물을 질문 · 동 고르기 단추 · 이 답의 자료 · 도움말(10-27).

【정함 10-27 팀장】 "이제는 사용자의 입장에서 데이터를 어떻게 받느냐에 집중하자 … '챗봇 그 자체'에
       집중하자. 챗봇이라면 당연히 넣어야할것들 … 걸러서 넣어보자"
【판단】 모두 코드로 만든다(AI를 부르지 않는다 — 돈 0원 · 0초 · 같은 답이면 같은 단추).
       이어 물을 질문은 장서 목록 안의 주제로만 만들고, 지금 답한 주제와 같은 질문은 내지 않는다.
       단추 글은 데스크가 이미 알아듣는 말투(장서 목록 예시와 같은 꼴)로 쓴다
"""

from __future__ import annotations

from src.assistant import basis as B
from src.assistant.catalog import BY_ID, TOPICS
from src.assistant.data_source import DongData
from src.assistant.policy import josa

MAX_FOLLOW = 3
MAX_CHOICES = 6


def _region_of(reply) -> str:
    st = reply.state
    return st.slots.region or st.profile.member_region or "강남구"


def _ok(topic: str, region: str) -> bool:
    t = BY_ID.get(topic)
    return bool(t and t.ready and t.coverage in ("both", region))


def _for_dong(d: str, region: str) -> list[tuple[str, str]]:
    """동 하나를 본 뒤 이어 물을 만한 것 — (주제, 질문) 차례대로."""
    e = josa(d, "은", "는")
    rows = [
        ("diagnosis", f"{e} 왜 이 순위야?"),
        ("solo_seniors", f"{d} 혼자 사는 어르신 몇 명이야?"),
        ("solo_seniors", f"{d} 80세 이상 혼자 사는 분은?"),
        ("youth", f"{d} 청년은?"),
        ("places", f"{d} 경로당이랑 보건소 알려 줘"),
        ("housing", f"{d} 오래된 계단 집이나 지하층 집 많아?"),
        ("outlook", f"{d} 어르신들 요즘 괜찮을까?"),
        ("dong_doc", f"{d} 상황 PDF로 만들어 줘"),
    ]
    if region == "춘천시":
        rows.insert(4, ("bus", f"{d} 버스는 하루 몇 번 다녀?"))
    return rows


def _for_region(region: str, top: str | None) -> list[tuple[str, str]]:
    short = "강남" if region == "강남구" else "춘천"
    rows = [("priority", f"{short}에서 먼저 볼 동은?")]
    if top:
        rows.append(("diagnosis", f"{josa(top, '은', '는')} 왜 1위야?"))
    rows += [
        ("solo_seniors", f"{short}에서 혼자 사는 어르신 많은 동은?"),
        ("youth", f"{short}에서 혼자 사는 청년 많은 동은?"),
        ("support", f"{short} 응급안전안심서비스 신청은 어디서 해?"),
        ("usage", "뭘 물어볼 수 있어?"),
    ]
    return rows


def followups(reply, data: DongData, asked: str = "") -> list[str]:
    """답 뒤에 보일 '이어 묻기' 단추(최대 3개). 되묻는 중 · 막은 질문 · 마무리에는 내지 않는다."""
    if reply.kind in ("ask_slot", "unknown_dong", "blocked", "farewell", "too_long"):
        return []
    region = _region_of(reply)
    dongs = list(reply.state.slots.dongs)
    done = set(reply.topics)
    files = bool(reply.files)
    ranked = data.ranked(region) if region in ("강남구", "춘천시") else []
    top = ranked[0][1] if ranked else None
    if len(dongs) == 1:
        rows = _for_dong(dongs[0], region)
    else:
        rows = _for_region(region, top)
    out: list[str] = []
    seen_topics: set[str] = set()
    asked_n = asked.replace(" ", "")
    for topic, q in rows:
        if topic in done or topic in seen_topics or not _ok(topic, region):
            continue
        if topic == "dong_doc" and files:
            continue
        if q.replace(" ", "") == asked_n:
            continue
        seen_topics.add(topic)
        out.append(q)
        if len(out) == MAX_FOLLOW:
            break
    return out


def choices(reply, data: DongData, member_dongs: tuple[str, ...] = ()) -> list[str]:
    """'어느 동을 볼까요?'에 누를 동 단추 — 담당 동 먼저, 그다음 먼저 볼 동 순위 위쪽."""
    if reply.kind not in ("ask_slot", "unknown_dong") or reply.state.pending != "dong":
        return []
    region = _region_of(reply)
    have = set(data.region_dongs(region))
    names = [d for d in member_dongs if d in have]
    names += [n for _, n in data.ranked(region)]
    return list(dict.fromkeys(names))[:MAX_CHOICES]


def basis_text() -> str:
    """자료의 때 한 줄 — '주민등록 2026-09 · 상가 2026-06'."""
    b = B.data_basis()
    return f"주민등록 {b['주민등록 인구']} · 상가 {b['상가']}"


def sources(reply, data: DongData) -> dict:
    """'이 답의 자료' — 답에 쓴 자료 묶음 이름 · 자료 상태 · 자료의 때(코드가 이미 가진 것만)."""
    rows = []
    for f in reply.facts or []:
        if not f.lines:
            continue
        rows.append({"title": f.title, "status": f.status})
    if not rows:
        return {}
    # 【판단】 10-28 화면 확인: '수서동 주민센터 어디 있어?'(지원 기관, 주민센터 자료 2023-07)에
    #        '주민등록 2026-09 · 상가 2026-06'이 붙어 그 답의 자료 때처럼 보였다 → 사람 수 · 상가를
    #        쓰지 않는 주제만으로 된 답에는 그 줄을 붙이지 않는다
    if reply.topics and set(reply.topics) <= NO_BASIS_TOPICS:
        return {"items": rows, "basis": ""}
    return {"items": rows, "basis": basis_text()}


NO_BASIS_TOPICS = frozenset(
    {"support", "bus", "sources", "datasets", "usage", "my_region", "recall", "dong_doc"}
)


def help_info(region: str, data: DongData) -> dict:
    """도움말 — 할 수 있는 것(장서 목록에서) · 하지 않는 것 · 예시 · 자료의 때."""
    can = []
    for t in TOPICS:
        if not t.ready or t.id in ("recall", "my_region", "sources", "usage"):
            continue
        where = "" if t.coverage == "both" else f" ({t.coverage}만)"
        can.append(t.title + where)
    ranked = data.ranked(region) if region in ("강남구", "춘천시") else []
    top = ranked[0][1] if ranked else ("개포3동" if region == "강남구" else "효자2동")
    examples = [q for _, q in _for_region(region, top)[:3]] + [
        f"{top} 혼자 사는 어르신 몇 명이야?",
        f"{top} 상황 PDF로 만들어 줘",
    ]
    return {
        "can": can,
        "cannot": [
            "개인(이름 · 연락처 · 주소 · 몇 호)을 찾거나 기억하는 일 — 동과 집단 단위만 다뤄요",
            "강남구 · 춘천시 밖의 지역",
            "공개 자료에 없는 숫자를 짐작하거나 지어내는 일",
            "사진 · 파일 올리기, 1,000자가 넘는 글",
        ],
        "examples": examples,
        "basis": basis_text(),
        "note": "AI가 공개 자료로 만든 참고 답이에요. 결정은 담당자와 기관이 하고, "
        "중요한 숫자는 출처와 기준일로 원자료를 확인해 주세요.",
    }
