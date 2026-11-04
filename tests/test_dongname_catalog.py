import pytest

from src.assistant import catalog, dongname
from src.assistant.data_source import JsonDongData


@pytest.mark.parametrize(
    ("said", "want"),
    [
        ("수서동", ["수서동"]),
        ("삼성동", ["삼성1동", "삼성2동"]),
        ("대치사동", ["대치4동"]),
        ("일원2동", ["개포3동"]),  # 옛 이름
        ("사음서음동", ["삼성1동", "삼성2동"]),  # 자판 오타
        ("tntjehd", ["수서동"]),  # 영어 자판
        ("북산", ["북산면"]),
    ],
)
def test_resolve(said, want):
    assert dongname.resolve(said)["dongs"] == want


def test_missing_number_is_not_guessed():
    # 【기능】 없는 번호(역삼3동)는 비슷한 동으로 바꾸지 않는다 — 틀린 동은 틀린 숫자가 된다
    r = dongname.resolve("역삼3동")
    assert r["dongs"] == [] and r["how"] == "없는 번호"


def test_dong_list_matches_data_snapshot():
    # 【기능】 동 이름 목록과 자료 스냅숏이 어긋나지 않게 묶는다
    data = JsonDongData()
    for region, names in dongname.DONGS.items():
        assert sorted(names) == sorted(data.region_dongs(region))


def test_catalog_ids_unique_and_prompt_stable():
    ids = [t.id for t in catalog.TOPICS]
    assert len(ids) == len(set(ids))
    assert set(catalog.DATA_IDS) <= set(catalog.READY_IDS) <= set(ids)
    # 【판단】 지시문 글자가 매번 같아야 프롬프트 캐시가 된다
    assert catalog.describe_for_desk() == catalog.describe_for_desk()


def test_coverage():
    # 【판단】 10-13: 경로당은 두 지역이 됐다. 지역 범위는 서울시 독거노인 현황(강남만)으로 본다
    assert catalog.covers("seoul_lonely", "강남구")
    assert not catalog.covers("seoul_lonely", "춘천시")
    assert catalog.covers("senior_hall", "춘천시")
    assert catalog.covers("youth", "춘천시")
