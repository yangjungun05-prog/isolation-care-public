"""갈 곳: 곳 수보다 이름이 적으면 그렇다고 밝힌다(10-15, 페르소나 20b q13 교동).

'약국 여섯 곳'이라면서 이름은 다섯만 나와 '하나는요?'라고 되물었다.
시설 자료는 이름을 5곳까지 담는다(big-contest export_bisu_places.py NAMES_SHOWN).
10-20: 약국은 국립중앙의료원 자료(이름 · 주소 · 운영 시간을 8곳까지, 나머지는 '그 밖에')로 바뀌어
상가정보의 '이름은 그중 5곳만'은 의원 줄에서 본다.
"""

from src.assistant.data_source import JsonDongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots

DATA = JsonDongData()


def _clinic_rows():
    for n in DATA.region_dongs("춘천시"):
        row = ((DATA.places(n) or {}).get("shops") or {}).get("의원")
        if row and row["n"]:
            yield n, row


def test_fewer_names_than_count_is_said():
    name = next(n for n, row in _clinic_rows() if row["n"] > len(row["names"]))
    text = "\n".join(gather("places", Slots(region="춘천시", dongs=(name,)), DATA).lines)
    assert "이름은 그중 5곳만 자료에 있음" in text
    gyo = "\n".join(gather("places", Slots(region="춘천시", dongs=("교동",)), DATA).lines)
    assert "(국립중앙의료원 약국 정보" in gyo and "문 여는 곳" in gyo


def test_all_names_present_says_nothing_extra():
    full = next(n for n, row in _clinic_rows() if row["n"] == len(row["names"]))
    text = "\n".join(gather("places", Slots(region="춘천시", dongs=(full,)), DATA).lines)
    assert "이름은 그중" not in next(
        x for x in text.splitlines() if x.lstrip("- ").startswith("의원")
    )
