"""장서 목록의 '자료에 있는 것' 낱말 → src/assistant/catalog_words.json

【판단】 10-21 새벽(팀장 "범위 바깥이다(있는데 없다고 대화함) 이게 왜 생기는 걸까 근본적으로"):
       데스크가 읽는 장서 목록 설명은 손으로 적은 한 줄이라 사서에 자료가 늘어도(지붕 · 마을별 집 ·
       첫차 · 달력) 목록은 그대로였다 → 데스크가 '목록에 없다'며 범위 밖으로 보냈다.
       그래서 목록을 두 갈래로 만든다. ① 사서가 실제로 적는 줄 이름을 자동으로 뽑고(자료를 더하면
       다시 돌림) ② 사용자가 쓸 법한 말(EXTRA — 줄 이름과 다른 일상 말)을 손으로 붙인다.
       둘을 합쳐 주제마다 낱말 목록으로 저장하고 데스크 지시문 6절에 '자료에 있는 것'으로 붙는다.
  uv run python scripts/build_catalog_words.py            # 만들고 저장
  uv run python scripts/build_catalog_words.py --show     # 보기만
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant import dongname, librarian  # noqa: E402
from src.assistant.catalog import TOPICS  # noqa: E402
from src.assistant.data_source import JsonDongData  # noqa: E402
from src.assistant.slots import Slots  # noqa: E402

OUT = ROOT / "src" / "assistant" / "catalog_words.json"
SAMPLES = {"강남구": ("수서동", "역삼1동"), "춘천시": ("신북읍", "효자2동")}
# 사용자가 쓸 법한 말(줄 이름과 다른 일상 말 · 사투리) — 자료에 실제로 있는 것만 적는다
EXTRA = {
    "dong_overview": [
        "동 하나 한눈에",
        "오늘 · 내일 날씨 · 앞으로 사흘 예보",
        "그날 비 얼마나 · 눈 온 날 · 한파 · 폭염 날 수",
        "비 · 눈 · 추위 · 더위일 때 이 동은(날씨 칸)",
    ],
    "outlook": [
        "잘 지내나 · 괜찮나 · 걱정할 점",
        "겹친 걱정과 근거",
        "어떤 어르신부터 · 먼저 살필 무리",
        "설 · 추석 · 긴 연휴 날짜(2025 ~ 2027 달력)",
    ],
    "priority": [
        "먼저 볼 동 순서(지역 전체)",
        "1위 동 · 위쪽 몇 곳",
        "동별 표(순위 · 위험 구간 · 혼자 사는 몫 · 자원 공백)",
    ],
    "diagnosis": [
        "왜 이 동인가 · 왜 먼저 볼 동인가",
        "순위 까닭(위험 구간 · 혼자 사는 몫 · 자원 공백)",
        "고립 신호 몇 가지",
        "본 신호 이름 전부",
    ],
    "solo_seniors": [
        "혼자 사는 어르신 수(65세 · 80세 이상)",
        "작년보다 늘었나 줄었나",
        "실제로 혼자 사는 어림",
        "주민 수 · 분모(65세 이상 중 · 전체 주민 중)",
        "요양시설 정원",
    ],
    "youth": [
        "혼자 사는 청년 수",
        "거의 집에만 있는 청년 어림",
        "작년과 견줌",
        "나이대(19~24 · 25~29 · 30~34)",
    ],
    "housing": [
        "슬레이트 · 함석 · 판넬 지붕 집(눈 무게에 약한 지붕)",
        "마을(리)별 집 수 · 읍면 합계",
        "지하층 · 반지하 건물",
        "30년 넘은 계단 집(승강기 없음)",
        "1995년 이전 집",
        "빈집",
    ],
    "senior_hall": ["경로당 · 마을회관 수와 이름"],
    "livelihood": ["기초생활수급자 수", "수급권자 독거노인", "빈집"],
    "places": [
        "약국(요일별 문 여는 시간 · 가장 가까운 약국 · 거리)",
        "경로당 · 복지관 · 급식소 · 보건소 · 의원 주소",
        "요양기관 · 입소 시설",
    ],
    "support": [
        "주민센터 · 행정복지센터 · 보건소 전화번호",
        "지역 전체 노인복지관 · 급식소 목록(동 없이)",
        "응급안전안심서비스 · 노인맞춤돌봄 신청",
        "위기 상담 전화(24시간) · 112 · 119 · 120 · 129",
        "연락이 끊긴 분 안부 확인 창구",
        "청년 연결 창구",
    ],
    "bus": [
        "마을버스 하루 몇 번 · 드문 버스",
        "첫차 · 막차 · 출발 시각",
        "마을(경로당)에서 정류장까지 거리",
        "버스가 드문 마을 이름",
        "시내버스 노선 번호",
    ],
}
# 줄 이름으로 쓰지 않는 것(안내문 · 코드 표시 · 너무 일반적인 말)
_DROP = re.compile(
    r"^\[|^참고|^출처|^기준|^모든 값|^주의|^표의 열|^지금 시각|^이 \S+을 지나|^견줌|^같은 잣대|"
    r"^판단 기준|^살펴본 겹|^괜찮은 쪽|^해당 조건|^해당하지 않는|^조건 [A-Z]|^그 밖에|^근거|^-|^·|"
    r"합계|코드가 더함|라고 하시면|살핌 판단$|^겹침|^주민$|^청년$|^정원이|^하루$|^마을$|"
    r"^춘천에서 하루|^수급자$|^주거$"
)
# ': ' 앞을 줄 이름으로. 없으면 첫 숫자(단위) 앞까지
_UNIT = re.compile(r"\s\d[\d,.]*\s*(?:명|가구|세대|곳|채|위|%|㎡|건|번|개|km|회|℃|도|mm|cm|년|월)")
MAX_PER_TOPIC = 14
MAX_LEN = 24
_DONGS = sorted((d for r in dongname.DONGS.values() for d in r), key=len, reverse=True)


def label(line: str) -> str | None:
    s = line.strip().lstrip("-· ").strip()
    if not s or _DROP.search(s):
        return None
    head = s.split(":", 1)[0] if ":" in s[:40] else _UNIT.split(s, 1)[0]
    head = re.sub(r"\(.*?\)", "", head)
    for d in _DONGS:  # 동 이름은 일반화
        head = head.replace(d, "")
    head = re.sub(r"\s+", " ", head).strip(" ,.·—")
    if len(head) < 3 or len(head) > MAX_LEN or _DROP.search(head):
        return None
    if re.search(r"없음$|없어요$|모름$|못 함$|\d$|\d+\s*(?:곳|개|가지|명|채)\s*\S*$|없음\(", head):
        return None
    return head


def collect() -> dict[str, list[str]]:
    data = JsonDongData()
    out: dict[str, list[str]] = {}
    for t in TOPICS:
        if t.id in ("my_region", "recall", "dong_doc", "usage", "datasets", "sources"):
            continue
        seen: dict[str, None] = {}
        for w in EXTRA.get(t.id, []):
            seen.setdefault(w, None)
        regions = ("강남구", "춘천시") if t.coverage == "both" else (t.coverage,)
        for region in regions:
            slots_list = [Slots(region=region, dongs=(d,)) for d in SAMPLES[region]]
            if t.needs == "region":
                slots_list.append(Slots(region=region))
            for sl in slots_list:
                targets = ("어르신", "청년") if t.id in ("outlook", "dong_overview") else (None,)
                for target in targets:
                    s = sl.model_copy(update={"target": target}) if target else sl
                    try:
                        f = librarian.gather(t.id, s, data)
                    except Exception as e:  # noqa: BLE001 — 자료가 없는 조합은 건너뛴다
                        print(
                            f"  ({t.id} {s.region} {s.dongs}: {type(e).__name__})", file=sys.stderr
                        )
                        continue
                    for ln in f.lines:
                        lb = label(ln)
                        if lb:
                            seen.setdefault(lb, None)
        out[t.id] = list(seen)[:MAX_PER_TOPIC]
    return out


def main() -> None:
    words = collect()
    for k, v in words.items():
        print(f"{k}: {' · '.join(v)}")
    if "--show" not in sys.argv:
        OUT.write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n저장: {OUT}")


if __name__ == "__main__":
    main()
