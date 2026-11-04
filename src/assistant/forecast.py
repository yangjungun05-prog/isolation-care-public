"""기상청 단기예보 · 특보 — '오늘 챙길 일' 카드의 진짜 오늘 날씨(10-16).

【정함 10-16 팀장】 비서의 '오늘'은 진짜 오늘. 카드 계기는 기상청 특보가 나오면 특보로, 없으면
       동마다 단기예보가 우리 기준값(weather.json thresholds)을 넘을 때("1,2,3,4 ㄱㄱ").
【기능】 단기예보(공공데이터포털 15084084, 공공누리 1유형) — 오늘부터 사흘을 하루씩
       (최저 · 최고기온, 비 · 새로 쌓인 눈 하루 합, 비 올 확률).
       동마다 격자(data/public/grids.json —
       그 동 경로당 · 마을회관 좌표의 가운데, big-contest scripts/export_bisu_grids.py)
【기능】 특보(15000415 기상특보 현황, 공공누리 1유형) — 전국 현황 글에서
       이 지역에 걸린 특보 · 예비특보만
【판단】 옮겨 온 곳: big-contest src/bigcon/forecast.py(10-06).
       다른 점 — 지역 한 칸이 아니라 동마다 격자,
       하루 끝까지 받도록 numOfRows 1500(1000이면 사흘째가 잘린다), 강남 격자는 공식으로 다시 냄
       (big-contest의 '강남구청 61,125'는 공식으로 61,126)
【판단】 숫자 글자: "1mm 미만" · "1cm 미만"은 0, "30.0~50.0mm"는 아래 끝, "50.0mm 이상"은 50
       (카드 기준값을 넘는지만 본다). 한 시간 동안은 받은 예보를, 10분 동안은 받은 특보를 다시 쓴다
       (하루 호출 한도 1만 건 — 격자 14개 × 24번 = 336번)
【판단】 키 · 주소가 섞일 수 있는 오류 원문은 내보내지 않는다(ForecastError 에는 종류만)
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from src.assistant.config import AssistantSettings

URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
WRN_URL = "https://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnStatus"
KST = timezone(timedelta(hours=9))
BASES = [2, 5, 8, 11, 14, 17, 20, 23]  # 단기예보 발표 시각(발표 10분쯤 뒤부터 받을 수 있다)
TTL_FCST = 3600
TTL_WRN = 600
AREA = {"강남구": "서울 동남권", "춘천시": "강원 춘천"}
# 특보 이름 → 카드 종류(기준값 카드와 같은 넷)
WRN_KIND = {"호우": "폭우", "한파": "한파", "대설": "폭설", "폭염": "폭염"}

SOURCE_FCST = "기상청 단기예보(공공데이터포털 15084084, 공공누리 1유형)"
SOURCE_WRN = "기상청 기상특보 현황(공공데이터포털 15000415, 공공누리 1유형)"


class ForecastError(RuntimeError):
    pass


def now_kst() -> datetime:
    return datetime.now(KST)


def today_kst() -> date:
    return now_kst().date()


def to_grid(lat: float, lon: float) -> tuple[int, int]:
    """위도 · 경도 → 기상청 단기예보 5km 격자 (nx, ny). 기상청 '동네예보 격자 변환' 공식."""
    re_, grid, slat1, slat2, olon, olat, xo, yo = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    rad = math.pi / 180.0
    re_ /= grid
    s1, s2, ol, oa = slat1 * rad, slat2 * rad, olon * rad, olat * rad
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(
        math.tan(math.pi * 0.25 + s2 * 0.5) / math.tan(math.pi * 0.25 + s1 * 0.5)
    )
    sf = math.tan(math.pi * 0.25 + s1 * 0.5) ** sn * math.cos(s1) / sn
    ro = re_ * sf / math.tan(math.pi * 0.25 + oa * 0.5) ** sn
    ra = re_ * sf / math.tan(math.pi * 0.25 + lat * rad * 0.5) ** sn
    theta = lon * rad - ol
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    x = math.floor(ra * math.sin(theta) + xo + 0.5)
    y = math.floor(ro - ra * math.cos(theta) + yo + 0.5)
    return int(x), int(y)


def latest_base(now: datetime | None = None) -> tuple[str, str]:
    """가장 최근 발표(발표 15분 뒤부터 쓴다) → (base_date, base_time)."""
    t = (now or now_kst()) - timedelta(minutes=15)
    hours = [h for h in BASES if h <= t.hour]
    if not hours:
        t -= timedelta(days=1)
        hours = [23]
    return t.strftime("%Y%m%d"), f"{hours[-1]:02d}00"


def amount(v) -> float:
    """'1mm 미만' → 0, '30.0~50.0mm' → 30, '강수없음' → 0."""
    v = str(v).strip()
    if not v or "없음" in v or "미만" in v:
        return 0.0
    m = re.search(r"[0-9]+(?:\.[0-9]+)?", v)
    return float(m.group()) if m else 0.0


def daily(items: list[dict]) -> dict[str, dict]:
    """단기예보 항목 → {'YYYY-MM-DD': {tmin, tmax, rain, snow, pop}}.

    칸 이름은 카드 기준값(weather.json thresholds)과 같다."""
    by_day: dict[str, list[dict]] = {}
    for it in items:
        by_day.setdefault(str(it["fcstDate"]), []).append(it)
    out = {}
    for day, rows in sorted(by_day.items()):

        def vals(cat: str, rows=rows) -> list[str]:
            return [r["fcstValue"] for r in rows if r.get("category") == cat]

        tmp = [float(x) for x in vals("TMP") if _num(x)]
        tmn, tmx = vals("TMN"), vals("TMX")
        pop = [int(float(x)) for x in vals("POP") if _num(x)]
        out[f"{day[:4]}-{day[4:6]}-{day[6:]}"] = {
            "tmin": float(tmn[0]) if tmn and _num(tmn[0]) else (min(tmp) if tmp else None),
            "tmax": float(tmx[0]) if tmx and _num(tmx[0]) else (max(tmp) if tmp else None),
            "rain": round(sum(amount(x) for x in vals("PCP")), 1),
            "snow": round(sum(amount(x) for x in vals("SNO")), 1),
            "pop": max(pop) if pop else None,
            "rain_peak": peak(rows, "PCP"),
            "snow_peak": peak(rows, "SNO"),
        }
    return out


def peak(rows: list[dict], cat: str) -> list[int] | None:
    """그날 가장 센 때 [처음 시, 끝 시] — 가장 센 시간의 절반 이상인 예보 시각들의 처음과 끝.

    【판단】 10-16 팀장이 카드 예시를 보고 정함: '언제 몰리나'를 넣는다
           (수서동 18일: 15 · 16 · 17시 → [15, 17]). 기상청 1시간 강수량의 예보 시각 그대로
    """
    hours = [
        (int(str(r["fcstTime"])[:2]), amount(r["fcstValue"]))
        for r in rows
        if r.get("category") == cat and str(r.get("fcstTime", ""))[:2].isdigit()
    ]
    top = max((v for _, v in hours), default=0.0)
    if top <= 0:
        return None
    strong = [h for h, v in hours if v >= top / 2]
    return [min(strong), max(strong)]


def _num(x) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def covers(region: str, areas: str) -> bool:
    """특보 구역 글에 이 지역이 들어 있나.

    서울은 '서울(동남권, …)'처럼 권역이 붙고, 권역이 없으면 서울 전체."""
    if region == "강남구":
        return any(
            "동남권" in m.group(0) or not m.group(1)
            for m in re.finditer(r"서울[^,(]*(\(([^)]*)\))?", areas)
        )
    if "춘천" in areas:
        return True
    # '강원도'만 있으면 강원 전체. '강원도(강원북부산지, …)'처럼 권역이 붙으면 춘천이 적혀 있어야
    return any(not m.group(1) for m in re.finditer(r"강원[^,(]*(\(([^)]*)\))?", areas))


ITEM = re.compile(r"^(o\s|o$|\(\d+\))")


def lines(text: str) -> list[tuple[str, str]]:
    """특보 현황 글 → [(특보 이름, 구역 글)]. 'o 호우주의보 : 서울(동남권), …' 꼴.

    【판단】 10-16 원문 확인: 특보가 없으면 'o 없 음'(가운데 빈칸)이 온다 — 빈칸을 빼고
           '없음'으로 본다.
           한 특보의 구역이 길면 다음 줄로 이어질 수 있어, 'o ' · '(1)'로 시작하지 않는 줄은
           앞 줄에 붙인다
    """
    items: list[str] = []
    for ln in str(text or "").replace("\r", "").split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        if ITEM.match(ln) or not items:
            items.append(ln[1:].strip() if ln.startswith("o") else ln)
        else:
            items[-1] += " " + ln
    out = []
    for it in items:
        if not it or it.replace(" ", "") == "없음":
            continue
        head, _, areas = it.partition(":")
        out.append((head.strip(), areas.strip() or it))
    return out


def kind_of(head: str) -> str | None:
    """'호우주의보' · '(1) 호우 예비특보' → '폭우'. 카드 종류가 아닌 특보(강풍 · 건조 등)는 None."""
    for word, kind in WRN_KIND.items():
        if word in head:
            return kind
    return None


class Live:
    """진짜 오늘의 예보 · 특보. 카드(today.cards)가 부른다. 시험에서는 같은 모양의 가짜를 넣는다."""

    def __init__(self, key: str | None = None):
        s = AssistantSettings()
        self._key = key if key is not None else s.data_go_kr_service_key
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def _get(self, url: str, what: str, **q) -> list[dict]:
        if not self._key:
            raise ForecastError("공공데이터포털 키(DATA_GO_KR_SERVICE_KEY)가 없음")
        q = {"serviceKey": self._key, "pageNo": 1, "dataType": "JSON", **q}
        req = urllib.request.Request(
            f"{url}?{urllib.parse.urlencode(q)}", headers={"User-Agent": "Mozilla/5.0"}
        )
        try:
            body = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8"))
            head = body["response"]["header"]
            if head.get("resultCode") != "00":
                raise ForecastError(
                    f"기상청 {what}: {head.get('resultCode')} {head.get('resultMsg')}"
                )
            return body["response"]["body"]["items"]["item"]
        except ForecastError:
            raise
        except Exception as e:  # 키 · 주소가 섞일 수 있는 원문은 내보내지 않는다
            raise ForecastError(f"기상청 {what}을 받지 못함: {type(e).__name__}") from None

    def _remember(self, key: str, ttl: int, make):
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
        v = make()
        with self._lock:
            self._cache[key] = (time.time(), v)
        return v

    def grid_days(self, nx: int, ny: int) -> tuple[dict[str, dict], str]:
        """한 격자의 ({날짜: 하루 값}, 발표 'YYYY-MM-DD HH:00'). 못 받으면 한 번 더 묻는다."""
        bd, bt = latest_base()

        def make():
            for tries in (1, 2):
                try:
                    items = self._get(
                        URL, "단기예보", numOfRows=1500, base_date=bd, base_time=bt, nx=nx, ny=ny
                    )
                    break
                except ForecastError:
                    if tries == 2 or not self._key:
                        raise
                    time.sleep(1)
            return daily(items), f"{bd[:4]}-{bd[4:6]}-{bd[6:]} {bt[:2]}:00"

        return self._remember(f"fcst|{nx},{ny}|{bd}{bt}", TTL_FCST, make)

    def forecast(self, grids: dict[str, tuple[int, int]]) -> tuple[dict[str, dict], str]:
        """{동: (nx, ny)} → ({동: {날짜: 하루 값}}, 발표 시각). 같은 격자는 한 번만 받는다.

        【판단】 10-16: 격자 하나를 못 받아도 나머지로 카드를 낸다(못 받은 동은 결과에서 빠진다 —
               부르는 쪽이 빠진 동을 화면에 알린다). 모두 못 받으면 ForecastError
        """
        uniq = sorted(set(grids.values()))

        def one(g):
            try:
                return self.grid_days(*g)
            except ForecastError as e:
                return e

        with ThreadPoolExecutor(max_workers=6) as ex:
            got = dict(zip(uniq, ex.map(one, uniq), strict=True))
        ok = {g: v for g, v in got.items() if not isinstance(v, ForecastError)}
        if not ok:
            raise next(iter(got.values())) if got else ForecastError("예보 격자가 없음")
        issued = max(v[1] for v in ok.values())
        return {d: ok[g][0] for d, g in grids.items() if g in ok}, issued

    def warnings(self, region: str) -> dict:
        """지금 이 지역에 걸린 특보 · 예비특보.
        {"issued", "area", "now": [(특보 이름, 카드 종류)], "soon": [(글, 카드 종류)]}"""

        def make():
            items = self._get(WRN_URL, "특보 현황", numOfRows=10)
            it = max(items, key=lambda x: str(x.get("tmFc")))
            tm = str(it.get("tmFc"))
            return {
                "issued": f"{tm[:4]}-{tm[4:6]}-{tm[6:8]} {tm[8:10]}:{tm[10:12]}",
                "t6": it.get("t6"),
                "t7": it.get("t7"),
            }

        raw = self._remember("pwn", TTL_WRN, make)
        now = [(h, kind_of(h)) for h, areas in lines(raw["t6"]) if covers(region, areas)]
        soon = [
            (f"{h} : {areas}" if areas != h else h, kind_of(h))
            for h, areas in lines(raw["t7"])
            if covers(region, areas)
        ]
        return {"issued": raw["issued"], "area": AREA.get(region, region), "now": now, "soon": soon}
