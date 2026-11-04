"""있는 자료를 못 꺼내는 구멍을 막는 시험(10-12 밤 100턴 3 · 4차 T39에서 배움).

【기능】 자료 스냅숏의 사람 수 · 개수 칸이 어느 주제의 답(사실 묶음)에든 나와야 한다.
       칸을 새로 더하고 사서에 안 넣으면 여기서 걸린다.
"""

import pytest

from src.assistant.catalog import TOPICS
from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots

DATA = JsonDongData()
# 【판단】 연도 · 비율 · 코드는 표기가 달라(2,010 · 0.093) 견주지 않는다. 사람 수 · 개수만
SKIP = {
    "dong_cd",
    "region",
    "year",
    "from_year",
    "old_walkup_share",
    "per100_lo",
    "per100_hi",
    "per100",
    "city_per100",
    "rank",
    "of",
    "date",
    "fac_mix",
    "avg_per100",
    "now",
    "fix",
    "n_of",
}


def _numbers(key: str, value, out: list[int]) -> None:
    if key in SKIP or isinstance(value, bool) or value is None:
        return
    if isinstance(value, dict):
        for k, v in value.items():
            _numbers(k, v, out)
    elif isinstance(value, int) and value >= 10:
        out.append(value)


@pytest.mark.parametrize("name", [n for r in ("강남구", "춘천시") for n in DATA.region_dongs(r)])
def test_every_count_is_reachable(name):
    d = DATA.dong(name)
    slots = Slots(dongs=(name,), region=d["region"])
    # 【바꿈 10-14】 강남 성별 숫자(seoul_lonely_sex)는 할머니 · 할아버지를 물었을 때만 나온다.
    #        성별을 물은 답도 함께 본다(어떤 질문으로든 나오면 된다)
    asks = [slots, slots.model_copy(update={"sex": "여"}), slots.model_copy(update={"sex": "남"})]
    text = "\n".join(
        gather(t.id, s, DATA).text for s in asks for t in TOPICS if t.ready and t.needs == "dong"
    )
    wanted: list[int] = []
    for k, v in d.items():
        if k != "diag":
            _numbers(k, v, wanted)
    missing = [n for n in wanted if f"{n:,}" not in text]
    assert missing == [], f"{name}: 답에 안 나오는 숫자 {missing}"
