"""자료 창구 — 사서는 자료를 이 창구로만 읽는다.

【판단】 지금은 공개 자료 스냅숏(data/public/dong_profiles.json). 팀 저장소에 옮기면
       같은 메서드를 PostgreSQL 표(dong_rank · diag_dong 등)로 채운 구현을 하나 더 만들면 된다.
       사서 · 엔진 코드는 바뀌지 않는다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Protocol

SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "public" / "dong_profiles.json"
# 【기능】 갈 곳 · 지원 기관 서가의 시설 자료(10-13, big-contest scripts/export_bisu_places.py)
PLACES = SNAPSHOT.with_name("places.json")
# 【기능】 춘천 버스 서가(10-13, big-contest scripts/export_bisu_bus.py)
BUS = SNAPSHOT.with_name("bus.json")
# 【기능】 날씨 관측 기록(10-13, big-contest scripts/export_bisu_weather.py)
#        — 동 상황의 조건으로 쓴다
WEATHER = SNAPSHOT.with_name("weather.json")
# 【기능】 공휴일(10-14, big-contest scripts/export_bisu_holidays.py) — 오늘 챙길 일의 긴 연휴 계기
HOLIDAYS = SNAPSHOT.with_name("holidays.json")
# 【기능】 원문 자료 서가의 자료 목록(10-14) — 이름 · 만든 곳 · 기준 · 이용 조건 · 받는 곳
DATASETS = SNAPSHOT.with_name("datasets.json")
# 【기능】 동마다 기상청 단기예보 격자(10-16, big-contest scripts/export_bisu_grids.py)
#        — 카드의 진짜 오늘 날씨
GRIDS = SNAPSHOT.with_name("grids.json")
# 【기능】 동마다 사람 수 2026 최신 판(10-16, scripts/update_people.py) — 카드가 먼저 읽는다
PEOPLE = SNAPSHOT.with_name("people.json")
# 【기능】 날씨마다 먼저 볼 곳 변수(10-18, big-contest scripts/build_weather_focus.py)
#        — 춘천 읍면은 마을(법정 리)마다, 동 지역은 행정동마다 지하층 집 · 산사태 · 급경사지 ·
#        침수 흔적 · 약한 지붕 · 요일별 문 연 약국 거리
FOCUS = SNAPSHOT.with_name("focus.json")
PHARMACIES = FOCUS.with_name("pharmacies.json")
# 【기능】 거의 집에만 있는 청년 어림의 방법 · 숫자
#        (10-25, big-contest scripts/export_bisu_youth_method.py)
YOUTH_METHOD = FOCUS.with_name("youth_method.json")


class DongData(Protocol):
    def dong(self, name: str) -> dict | None: ...

    def region_dongs(self, region: str) -> list[str]: ...

    def region_code(self, region: str) -> str: ...

    def ranked(self, region: str) -> list[tuple[int, str]]: ...

    def sources(self, region: str) -> list[str]: ...

    def places(self, name: str) -> dict | None: ...

    def region_places(self, region: str) -> dict: ...

    def places_common(self) -> dict: ...

    def bus(self, name: str) -> dict | None: ...

    def bus_info(self) -> dict: ...

    def weather(self) -> dict: ...

    def holidays(self) -> dict[str, str]: ...

    def datasets(self) -> dict: ...

    def grids(self, region: str) -> dict[str, tuple[int, int]]: ...

    def people(self) -> dict: ...

    def focus(self, name: str) -> dict | None: ...

    def pharmacies(self, name: str) -> dict | None: ...

    @property
    def basis(self) -> str: ...


class JsonDongData:
    """공개 자료 스냅숏을 읽는 창구."""

    def __init__(
        self,
        path: Path = SNAPSHOT,
        places_path: Path = PLACES,
        bus_path: Path = BUS,
        weather_path: Path = WEATHER,
        holidays_path: Path = HOLIDAYS,
        datasets_path: Path = DATASETS,
        grids_path: Path = GRIDS,
        people_path: Path = PEOPLE,
        focus_path: Path = FOCUS,
        pharmacies_path: Path = PHARMACIES,
        youth_method_path: Path = YOUTH_METHOD,
    ) -> None:
        # 【판단】 10-19 자동 받기(big-contest scripts/update_all.py)가 밤마다 파일을 바꾼다 —
        #        읽을 때마다 파일 시각을 보고 바뀌었으면 다시 읽는다(서버를 다시 켜지 않아도 새 판)
        self._paths = {
            "raw": path,
            "holidays": holidays_path,
            "datasets": datasets_path,
            "places": places_path,
            "bus": bus_path,
            "weather": weather_path,
            "grids": grids_path,
            "people": people_path,
            "focus": focus_path,
            "pharmacies": pharmacies_path,
            "youth_method": youth_method_path,
        }
        self._j("raw")  # 동 자료는 꼭 있어야 한다(없으면 여기서 멈춤)

    def _j(self, key: str) -> dict:
        p = self._paths[key]
        if key != "raw" and not p.exists():
            # 【판단】 시설 파일이 없으면(옛 스냅숏만 있는 곳) 갈 곳 서가만 비고 나머지는 돈다
            return {}
        return _load(str(p), p.stat().st_mtime_ns)

    @property
    def basis(self) -> str:
        return self._j("raw")["basis"]

    def dong(self, name: str) -> dict | None:
        return self._j("raw")["dongs"].get(name)

    def region_dongs(self, region: str) -> list[str]:
        return list(self._j("raw")["regions"].get(region, {}).get("dongs", []))

    def region_code(self, region: str) -> str:
        """시군구 코드(통계청 5자리, 팀 ERD sgg_cd)."""
        return self._j("raw")["regions"].get(region, {}).get("sgg_cd", "")

    def ranked(self, region: str) -> list[tuple[int, str]]:
        dongs = self._j("raw")["dongs"]
        rows = [(d["rank"]["now"], n) for n, d in dongs.items() if d["region"] == region]
        return sorted(rows)

    def sources(self, region: str) -> list[str]:
        return list(self._j("raw")["sources"].get(region, []))

    def places(self, name: str) -> dict | None:
        return self._j("places").get("dongs", {}).get(name)

    def region_places(self, region: str) -> dict:
        return self._j("places").get("regions", {}).get(region, {})

    def places_common(self) -> dict:
        return self._j("places").get("common", {})

    def bus(self, name: str) -> dict | None:
        return self._j("bus").get("dongs", {}).get(name)

    def bus_info(self) -> dict:
        return {k: v for k, v in self._j("bus").items() if k != "dongs"}

    def weather(self) -> dict:
        return self._j("weather")

    def holidays(self) -> dict[str, str]:
        return dict(self._j("holidays").get("days", {}))

    def datasets(self) -> dict:
        return self._j("datasets")

    def grids(self, region: str) -> dict[str, tuple[int, int]]:
        """{동: (nx, ny)} — 기상청 단기예보 격자."""
        rows = (self._j("grids").get("regions") or {}).get(region) or {}
        return {n: (v["nx"], v["ny"]) for n, v in rows.items()}

    def people(self) -> dict:
        """{basis, prev, source, dongs: {동: {solo65, solo65_prev, solo80, residents, pop65,
        pop80}}}."""
        return self._j("people")

    def focus(self, name: str) -> dict | None:
        """동의 날씨 변수. 동 지역은 {unit: '동', …값},
        읍면은 {unit: '면', villages: [마을마다 값]}."""
        for rows in (self._j("focus").get("regions") or {}).values():
            if name in rows:
                return rows[name]
        return None

    def pharmacies(self, name: str) -> dict | None:
        """동 안 약국(이름 · 주소 · 전화 · 요일별 운영 시간)과, 없으면 가까운 약국 세 곳(10-20),
        요일마다 그날 문 여는 가장 가까운 약국 세 곳(open_near, 10-25).

        국립중앙의료원 약국 정보. 10-20 판을 만든 스크립트는 저장소에 없다(BISU c64104b).
        open_near 와 거리(동 · 읍면 경계의 가운데)는 big-contest
        scripts/export_bisu_pharmacy_near.py 가 다시 쓴다."""
        return (self._j("pharmacies").get("dongs") or {}).get(name)

    def youth_method(self) -> dict:
        """청년 어림의 방법 · 비율 · 구 전체 어림(없으면 빈 것)."""
        return self._j("youth_method")

    def pharmacies_meta(self) -> dict:
        j = self._j("pharmacies")
        return {k: j.get(k) for k in ("source", "basis", "note")}


@lru_cache(maxsize=64)
def _load(path: str, mtime: int = 0) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
