"""먼저 볼 동(priority)을 동과 함께 물으면 그 동의 순위도(10-15, 문제 목록 1-4).

100턴 T90 '역삼2동은 다시 매기면 몇 위예요?': 데스크는 priority + 역삼2동을 적었는데
사서가 위 5곳만 줘서 글쓴이가 '역삼2동 순위는 확인되지 않아요 · 다시 매길 수 없어요'라고 했다
(10-13 · 14 · 15 세 번 모두).
자료에는 역삼2동 지금 13위 · 다시 매기면 17위가 있다.
"""

from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots

DATA = JsonDongData()


def test_priority_with_dong_gives_that_dongs_rank():
    f = gather("priority", Slots(region="강남구", dongs=("역삼2동",)), DATA)
    text = "\n".join(f.lines)
    # 10-19 2026 최신 판: 역삼2동 17위, 다시 매겨도 17위(전에는 13위 → 17위)
    assert "역삼2동" in text and "17위" in text and "다시 매겨도 17위로 같음" in text
    assert "1위 개포3동" in text  # 위 5곳도 그대로


def test_rank_line_says_so_when_rerank_is_the_same():
    # 다시 매겨도 같은 동은 '같다'고 말할 거리가 있어야 '다시 매기면?'에 답한다
    dongs = DATA._j("raw")["dongs"]  # noqa: SLF001
    same = next(n for n, d in dongs.items() if d["rank"]["fix"] == d["rank"]["now"])
    f = gather("priority", Slots(region=DATA.dong(same)["region"], dongs=(same,)), DATA)
    assert "다시 매겨도" in "\n".join(f.lines)
