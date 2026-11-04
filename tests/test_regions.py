"""지역 코드(src/common/regions.py) 테스트 — 인터넷·DB 없이 돈다."""

from collections import Counter

from src.common.regions import dong_rows, family_name


def test_family_name():
    # 【기능】 번호 붙은 동은 묶음 이름, 번호 없는 동·읍·면은 None
    assert family_name("대치1동") == "대치동"
    assert family_name("일원본동") == "일원동"
    assert family_name("신사동") is None
    assert family_name("동면") is None


def test_dong_rows():
    # 【기능】 저장해 둔 경계 파일에서 47줄이 나오고, 칸 값이 DB 규칙에 맞는다
    rows = dong_rows()
    assert len(rows) == 47
    assert Counter(r["sgg_cd"] for r in rows) == {"11230": 22, "32010": 25}
    for r in rows:
        assert len(r["dong_cd"]) == 8
        assert len(r["mois_cd"]) == 10
        assert r["sgg_cd"] == r["dong_cd"][:5]
        assert r["kind"] in ("동", "읍", "면")
