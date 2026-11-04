"""공휴일 새로 받기 — 한국천문연구원 특일 정보
(공공데이터포털 15012690, getRestDeInfo, 이용허락범위 제한 없음).

    uv run --env-file .env python scripts/update_holidays.py 2027          # 2027년을 받아 더한다
    uv run --env-file .env python scripts/update_holidays.py 2026 2027     # 여러 해

【기능】 data/public/holidays.json 에 그 해 공휴일을 더한다(이미 있는 해는 새로 받은 것으로 바꾼다).
       '오늘 챙길 일'의 긴 연휴 카드가 읽는다(연휴 1주 전부터).
【판단】 10-16: 상업 배포판이 big-contest 없이 혼자 자료를 새로 받게 하는 첫 걸음
       (전에는 big-contest scripts/export_bisu_holidays.py 가 만들어 옮겼다).
       키는 이 저장소 .env 의 DATA_GO_KR_SERVICE_KEY
【판단】 키 · 주소가 섞일 수 있는 오류 원문은 내보내지 않는다
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant.config import AssistantSettings  # noqa: E402

URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
OUT = ROOT / "data" / "public" / "holidays.json"


def month(key: str, year: int, mon: int) -> list[dict]:
    q = {
        "serviceKey": key,
        "solYear": str(year),
        "solMonth": f"{mon:02d}",
        "_type": "json",
        "numOfRows": 50,
    }
    req = urllib.request.Request(
        f"{URL}?{urllib.parse.urlencode(q)}", headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        body = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — 원문에 키가 섞일 수 있다
        raise SystemExit(f"{year}-{mon:02d} 특일 정보를 받지 못함: {type(e).__name__}") from None
    head = body["response"]["header"]
    if head.get("resultCode") != "00":
        raise SystemExit(f"{year}-{mon:02d} 특일 정보: {head.get('resultMsg')}")
    items = body["response"]["body"].get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else []
    return items if isinstance(items, list) else [items]


def year_days(key: str, year: int) -> dict[str, str]:
    out = {}
    for m in range(1, 13):
        for it in month(key, year, m):
            if it.get("isHoliday") != "Y":
                continue
            d = str(it["locdate"])
            out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = str(it["dateName"]).strip()
    return out


def main(years: list[int]) -> None:
    key = AssistantSettings().data_go_kr_service_key
    if not key:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY 가 .env 에 없다")
    data = json.loads(OUT.read_text(encoding="utf-8"))
    days = {k: v for k, v in data["days"].items() if int(k[:4]) not in years}
    for y in years:
        got = year_days(key, y)
        if not got:
            raise SystemExit(f"{y}년 공휴일이 비었다(아직 발표 전일 수 있다)")
        days.update(got)
        print(f"{y}년 {len(got)}일: " + ", ".join(f"{k[5:]} {v}" for k, v in sorted(got.items())))
    data["days"] = dict(sorted(days.items()))
    data["years"] = sorted({int(k[:4]) for k in data["days"]})
    data["built"] = dt.date.today().isoformat()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(OUT, data["years"])


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [dt.date.today().year + 1])
