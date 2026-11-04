from datetime import date

import holidays
from sqlalchemy.orm import Session

from src.common.database import SessionLocal
from src.common.models import Holiday

YEARS = (2025, 2026)


def holiday_rows(years: tuple[int, ...] = YEARS) -> list[dict]:
    calendar = holidays.KR(years=years, language="ko")
    return [{"day": day, "name": name.split(";")[0]} for day, name in sorted(calendar.items())]


def is_holiday(day: date) -> bool:
    return day in holidays.KR(years=day.year)


def seed_holidays(session: Session) -> int:
    rows = holiday_rows()
    for row in rows:
        session.merge(Holiday(**row))
    return len(rows)


if __name__ == "__main__":
    with SessionLocal.begin() as session:
        print(seed_holidays(session))
