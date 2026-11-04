import re

KIND_WORDS = {
    "찾아가서 살피기(방문)": ["찾아", "방문", "동행", "살피"],
    "안부 확인(전화 · IoT)": ["전화", "IoT", "AI", "문자"],
    "함께 모이는 활동": ["모임", "교실", "프로그램", "동아리", "함께"],
    "생활 지원": ["도시락", "반찬", "청소", "식사", "생활"],
    "청년 관계 회복(사례관리)": ["사례관리", "은둔", "청년", "관계 회복"],
}

WHO_WORDS = {
    "80세 이상 혼자 사는 분": ["80세"],
    "65세 이상 혼자 사는 분": ["65세"],
    "기초수급 어르신": ["수급"],
    "고립·은둔 청년(19~34세)": ["청년", "은둔", "20대", "30대"],
}


# 【기능】 돈 낱말 — '1억 2천만 원'처럼 이어진 조각을 만원 단위로 더한다
MONEY_PART = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천\s*만|만)\s*(원)?")
MONEY_UNIT = {"억": 10_000, "천만": 1_000, "만": 1}


def read_money(text: str) -> int | float | None:
    # 【기능】 설명글 속 첫 돈(만원) — 없으면 None
    # 【판단】 '만'은 '1만 명'처럼 사람 수에도 쓰여서, 덩어리 끝에 '원'이 있거나 '억'이 든 것만
    #   돈으로 본다
    parts = list(MONEY_PART.finditer(text))
    i = 0
    while i < len(parts):
        j, total = i, 0.0
        while True:
            m = parts[j]
            total += float(m.group(1).replace(",", "")) * MONEY_UNIT[m.group(2).replace(" ", "")]
            nxt = parts[j + 1] if j + 1 < len(parts) else None
            if m.group(3) or nxt is None or text[m.end() : nxt.start()].strip():
                break
            j += 1
        units = {parts[k].group(2) for k in range(i, j + 1)}
        if parts[j].group(3) or "억" in units:
            return int(total) if total.is_integer() else total
        i = j + 1
    return None


def read_text(text: str, form: dict) -> dict:
    found = {}
    m = re.search(r"주\s*(\d+)\s*회", text)
    if m:
        found["freq"] = f"주 {m.group(1)}회"
    # 【판단】 '1년 500만원'의 1년은 기간이 아니라 '1년에 드는 돈'이라 기간으로 읽지 않는다
    m = re.search(r"(\d+)\s*년(?!\s*(?:에\s*)?\d[\d,.]*\s*(?:억|천\s*만|만))", text)
    if m:
        found["years"] = int(m.group(1))
    hits = {k: sum(w in text for w in words) for k, words in KIND_WORDS.items()}
    best = max(hits, key=lambda k: hits[k])
    if hits[best] > 0:
        found["kind"] = best
    for who, words in WHO_WORDS.items():
        if any(w in text for w in words):
            found["who"] = who
            break
    money = read_money(text)
    if money is not None:
        found["money"] = money
    labels = {
        "freq": "횟수",
        "years": "기간",
        "kind": "정책 종류",
        "who": "누구에게",
        "money": "돈 (1년)",
    }

    def differ(f: str, v) -> bool:
        # 【판단】 돈은 숫자로 견준다 — 칸 800 과 글 800.0 은 같은 돈
        if f == "money":
            return abs(float(form[f]) - float(v)) >= 0.5
        return str(form[f]).replace(" ", "") != str(v).replace(" ", "")

    # 【판단】 칸이 비어 있으면 묻지 않는다 — 돈 칸이 비었으면 화면이 글의 돈으로 채운다(SIM-102)
    questions = [
        {"field": f, "label": labels[f], "form": form.get(f), "text": v}
        for f, v in found.items()
        if form.get(f) is not None and differ(f, v)
    ]
    # 【판단】 한 번 실행에 최대 2번만 멈춰 묻는다(SIM-102) — 나머지는 칸대로 하고 결과에 적는다
    return {
        "found": found,
        "questions": questions[:2],
        "assumed": questions[2:],
        "guess": None if "kind" in found else form.get("kind"),
    }


# ── 여기부터 Claude — 설명글 쓰기 · 숫자 검사(SIM-107) ──


def _n1(v: float) -> str:
    return f"{round(v * 10) / 10:.1f}"


def money_text(man: float) -> str:
    # 【기능】 만원 단위 돈을 읽기 쉬운 말로 — 10000 → '1억', 18200 → '1.82억', 800 → '800만원'
    # 【판단】 10-25 화면에 '1년 10,000만원'이 떴다. 1억 이상은 억으로, 소수점은 둘째 자리까지만
    if man >= 10_000:
        return f"{round(man / 10_000, 2):g}억"
    return f"{man:,.0f}만원"


def write_paragraph(res: dict) -> str:
    # 【기능】 /api/simulation/run 결과로 보고서용 문단 하나 — 결론 → 가장 흔드는 값 → 한계 순서
    x, final = res["input"], res["plan"]["final"]
    top = res["tornado"]["rows"][0]["name"]
    return (
        f"{'·'.join(x['dongs'])} {x['who']}께 {x['kind']} 사업에 1년 {money_text(x['money'])}을 "
        f"{x['years']}년 쓰면, 3년 뒤 고립 위험인 분이 사업이 없을 때보다 "
        f"{_n1(final['p10'])}~{_n1(final['p90'])}명"
        f"(가운데 {_n1(final['median'])}명) 줄 것으로 보입니다. "
        f"결과를 가장 크게 흔드는 값은 '{top}'입니다. "
        "한계: 효과 값은 다른 지역 연구에서 빌렸고, "
        "가상 주민은 지역사회건강조사 응답자로 만들었습니다."
    )


def numbers_in(text: str, skip: list[str]) -> list[str]:
    # 【기능】 글 속 숫자를 차례로 뽑는다. skip 에 든 낱말(동 이름의 숫자 등)은 먼저 지운다
    for w in skip:
        text = text.replace(w, " ")
    return re.findall(r"\d[\d,]*(?:\.\d+)?", text)


def check_numbers(text: str, res: dict) -> list[str]:
    # 【기능】 문단 속 숫자 중 계산 결과 · 입력에 없는 것 목록. 빈 목록이면 통과
    # 【판단】 문단을 나중에 AI 가 다듬더라도 숫자는 이 검사를 통과해야 화면에 낸다(SIM-107 작동)
    x, final = res["input"], res["plan"]["final"]
    allowed = {"1", "3", str(x["years"])}  # 1년마다 · 3년 뒤
    allowed |= set(numbers_in(money_text(x["money"]), []))
    allowed |= {_n1(final[k]) for k in ("p10", "median", "p90")}
    return [n for n in numbers_in(text, x["dongs"] + [x["who"]]) if n not in allowed]
