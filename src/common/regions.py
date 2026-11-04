import json
import re
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from src.common.database import SessionLocal
from src.common.models import Dong, Region

REGIONS = {"11230": "강남구", "32010": "춘천시"}

VERSION = "ver20251231"
SOURCE_URL = (
    "https://raw.githubusercontent.com/vuski/admdongkor/master/"
    f"{VERSION}/HangJeongDong_{VERSION}.geojson"
)

BOUNDARY = Path(__file__).parents[2] / "data" / "public" / f"admdong_{VERSION}.geojson"


def fetch_boundaries() -> int:
    response = httpx.get(SOURCE_URL, timeout=120)
    response.raise_for_status()
    features = response.json()["features"]
    keep = [f for f in features if f["properties"]["adm_cd"][:5] in REGIONS]
    collection = {"type": "FeatureCollection", "features": keep}
    BOUNDARY.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    return len(keep)


def family_name(name: str) -> str | None:
    family = re.sub(r"(\d+|본)동$", "동", name)
    return family if family != name else None


def dong_rows() -> list[dict]:
    festures = json.loads(BOUNDARY.read_text(encoding="utf-8"))["features"]
    rows = []
    for f in festures:
        p = f["properties"]
        name = p["adm_nm"].split()[-1]

        rows.append(
            {
                "dong_cd": p["adm_cd"],  # 통계청 8자리
                "mois_cd": p["adm_cd2"],  # 행안부 10자리
                "sgg_cd": p["adm_cd"][:5],  # 통계청 시군구 5자리
                "name": name,
                "family": family_name(name),
                "kind": name[-1],  # 끝 글자: 동·읍·면
                "geom": json.dumps(f["geometry"]),  # 경계 모양을 글자로
            }
        )
    return rows


def seed_regions(session: Session) -> tuple[int, int]:
    for sgg_cd, name in REGIONS.items():
        session.merge(Region(sgg_cd=sgg_cd, name=name))
    rows = dong_rows()
    for row in rows:
        session.merge(Dong(**row))
    return len(REGIONS), len(rows)


if __name__ == "__main__":
    with SessionLocal.begin() as session:
        print(seed_regions(session))
