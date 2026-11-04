"""채팅 표 고치기 — 앞 턴에 코드가 그린 표를 정렬 · 열 더하기 · 빼기 · 위 N곳 · 다른 지역으로.

【판단】 10-28 남은 일 1순위(10-20 · 10-27 페르소나 h02 노엘, 표 요청 10턴): 첫 표는 코드가
       잘 그렸는데, 이어서 '많은 순으로 정렬해 줘' · '증감률 열도 넣어 줘' · '비율 열도 추가해 줘' ·
       '위에서 다섯 곳만'을 말하면 앞 표를 이어받지 못했다(evals/scenarios/table_noel_10.json t1):
       글로 줄 세움 · '증감률은 계산할 수 없다'(표에 두 해 값이 있음) · 앞 열이 다 빠지고 한 열만 ·
       '증감 자료가 없다'(첫 표에 증감 열이 있었음). 표 모양(지역 · 주제 · 보인 열 · 정렬 · 몇 곳)을
       상태에 남기고, 고치는 말이면 코드가 그 표를 고쳐 다시 그린다 — 글쓴이(AI)를 부르지 않아
       앞뒤가 다른 말이 나올 수 없다
"""

from __future__ import annotations

import re

from src.assistant import table
from src.assistant.data_source import DongData
from src.assistant.state import TableSpec

# 표를 고치는 말 — 정렬 · 열 · 칸 더하기 · 빼기 · 위 N곳 · 전부 · 같은 표로
EDIT = re.compile(
    r"정렬|순으로|순서대로|거꾸로|뒤집"
    r"|(?:열|칸|컬럼|항목)(?:도|을|를|만|은|이|으로)?\s*(?:넣|추가|더|빼|지워|없애|보여)"
    r"|추가해|넣어\s*(?:줘|주|달)|빼\s*(?:줘|주|고)|지워\s*(?:줘|주)|없애"
    r"|(?:곳|개|동)만|위에서|아래에서|상위|하위|top|TOP"
    r"|(?:전부|모두|다)\s*(?:넣|보여|줘)|빠진\s*동|빠짐없이"
    r"|같은\s*표"
    # 10-28 밤 브라우저 시험 '… 칸은 2026-09 바로 다음에 오게 자리 바꿔 주세요'를 다듬기로 못 봄
    r"|옮겨|옮기|자리\s?(?:를\s?)?바꿔|순서를?\s?바꿔|다음에\s?오게|옆(?:으로|에)\s?(?:놓|두|붙|넣|옮)"
)
REMOVE = re.compile(r"빼|지워|없애|말고")
# 10-28 재심사 q01_a: '증감률 열 추가 + 80세 · 어림 열 빼기'를 한 말로 하면 빼기만 됐고,
#        '증감률 열을 2026-09 옆으로 옮겨'를 그 열 빼기로, '다시 넣어'는 아무것도 안 했다 →
#        마디마다 따로 보고 옮기기 · 다시 넣기 · '○○ 옆에'를 더한다
# 10-28 밤 브라우저 시험 '늘어난 비율 칸 붙여 주시고, 80세 칸은 지워 주세요': 쉼표 · '-고'로 이은
#        한 문장이 통째로 빼기로 처리됐다 → 쉼표와 부탁하는 이음말에서도 나눈다
CLAUSE = re.compile(r"[.,!?\n]+|그리고|그다음|또한|그럼|(?:주시|해\s?주|하|주)고(?=\s)")
MOVE = re.compile(r"옮겨|옮기|이동|자리를?\s*바꿔|순서를?\s?바꿔|다음에\s?오게")
BACK = re.compile(r"다시\s*(?:넣|추가|보여)|살려|되돌려|복구|빠졌")
NEXT_TO = re.compile(r"옆|오른쪽|뒤(?:에|로|쪽)|다음(?:에|으로|칸)|다음에\s?오게")
ALL_ROWS = re.compile(r"전부|모두|빠진\s*동|빠짐없이|다\s*(?:넣|보여)")
BOTTOM = re.compile(r"아래에서|하위|적은\s*(?:곳|동)\s*(?:\d|한|두|세|네|다섯)")
REVERSE = re.compile(r"거꾸로|뒤집|반대로")

# 말 → 열(열 이름에 이 말이 들어 있으면 그 열). 위에 있는 것부터 본다(긴 말 먼저)
COL_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"증감률|증가율|감소율|변화율|늘어난\s*비율|증감\s*%|몇\s*%\s*늘"), "증감률"),
    (re.compile(r"증감(?!률)|늘어난\s*(?:수|인원|사람)|줄어든\s*(?:수|인원)"), "증감(명)"),
    (
        re.compile(
            r"(?:혼자\s*사(?:는|시는)|1인\s*세대|독거)[^,·/]{0,10}(?:비율|몫|%)|혼자\s*사는\s*몫"
        ),
        "혼자 사는 몫",
    ),
    (re.compile(r"80\s*세"), "80세 이상 1인세대"),
    (re.compile(r"정원|복지시설"), "노인복지시설 정원"),
    (re.compile(r"어림|실제로\s*혼자"), "어림"),
    (
        re.compile(r"65\s*세\s*이상\s*주민|어르신\s*(?:주민\s*)?수(?!\s*를)|노인\s*인구"),
        "65세 이상 주민",
    ),
    (re.compile(r"2025"), "2025"),
    (re.compile(r"2026"), "2026"),
    (re.compile(r"순위"), "동 순위"),
    (re.compile(r"외출|연락"), "외출·연락"),
    (re.compile(r"겹친\s*걱정|취약\s*돌보미\s*판단"), "겹친 걱정"),
    (re.compile(r"신호"), "신호 수"),
    (re.compile(r"위험\s*구간|구간"), "위험 구간"),
    (re.compile(r"자원\s*공백"), "자원 공백"),
)


def is_edit(text: str) -> bool:
    return bool(EDIT.search(text or ""))


def _find(header: list[str], text: str) -> list[str]:
    """말이 가리키는 열(표 머리의 이름, 말한 차례)."""
    out: list[str] = []
    hits: list[tuple[int, str]] = []
    for pat, word in COL_WORDS:
        for m in pat.finditer(text):
            hits.append((m.start(), word))
    for _, word in sorted(hits):
        for h in header[2:]:
            if word in h and h not in out:
                # '2025' · '2026'은 그 해 1인세대 열만(다른 열에 날짜가 붙어도 고르지 않음)
                if word in ("2025", "2026") and "1인세대" not in h:
                    continue
                out.append(h)
                if word != "어림":
                    break
    for h in table._named(header, text):  # 표 모듈의 열 찾기(열 이름을 통째로 말한 것)
        if h not in out:
            out.append(h)
    return out


def _same(a: str, b: str) -> bool:
    # 열 이름은 그대로 견준다 — 날짜를 떼면 '1인세대 2025-09'와 '2026-09'가 같아져 줄 세우기가
    # 지난 판 열로 갔다(10-28 table_noel_10 t2 T2). 두 지역 표의 열 이름은 같은 날짜로 만든다
    return a == b


def apply(
    spec: TableSpec, header: list[str], text: str, region: str
) -> tuple[TableSpec, list[str]]:
    """고치는 말 → 새 표 모양과 고친 것(사람이 읽는 말)."""
    notes: list[str] = []
    cols = [c for c in spec.cols if any(_same(c, h) for h in header)]
    named = _find(header, text)
    sort, desc, top = spec.sort, spec.desc, spec.top
    asked_sort = bool(table.SORT_DESC.search(text) or table.SORT_ASC.search(text)) or bool(
        re.search(r"정렬|순으로|순서대로", text)
    )
    cols = _edit_cols(cols, header, text, asked_sort, notes)
    if asked_sort or REVERSE.search(text):
        if named:
            sort = named[0]
        elif not sort:
            j = table._sort_col(header, [])
            sort = header[j] if j is not None else (cols[0] if cols else "")
        if table.SORT_ASC.search(text):
            desc = False
        elif table.SORT_DESC.search(text):
            desc = True
        elif REVERSE.search(text):
            desc = not desc
        if sort:
            notes.append(f"정렬: {sort} {'많은' if desc else '적은'} 순")
    n = table.top_n(text) or _top_words(text)
    if n:
        top = n
        if BOTTOM.search(text):
            desc = not desc if sort else desc
            notes.append(f"아래에서 {n}곳")
        else:
            notes.append(f"위에서 {n}곳만")
        if not sort:
            j = table._sort_col(header, [])
            sort = header[j] if j is not None else ""
    elif ALL_ROWS.search(text):
        top = None
        notes.append("모든 동")
    if region != spec.region:
        notes.append(f"지역: {region}(같은 열)")
    new = spec.model_copy(
        update={"region": region, "cols": tuple(cols), "sort": sort, "desc": desc, "top": top}
    )
    if region != spec.region:
        # 다른 지역 '같은 표'는 열 · 정렬만 잇고 그 지역 모든 동(앞 표의 '위 N곳'은 잇지 않음)
        new = new.model_copy(update={"dongs": (), "top": n or None})
    return new, notes


def _place(cols: list[str], col: str, anchor: str) -> list[str]:
    """col 을 anchor 바로 뒤로(anchor 가 없으면 그대로)."""
    if not any(_same(anchor, c) for c in cols) or _same(col, anchor):
        return cols
    rest = [c for c in cols if not _same(c, col)]
    i = next(i for i, c in enumerate(rest) if _same(c, anchor))
    return rest[: i + 1] + [col] + rest[i + 1 :]


def _edit_cols(
    cols: list[str], header: list[str], text: str, asked_sort: bool, notes: list[str]
) -> list[str]:
    """열 더하기 · 빼기 · 옮기기 — 마디마다 따로(한 말에 더하기와 빼기가 섞일 수 있다)."""
    added: list[str] = []
    gone: list[str] = []
    moved: list[str] = []
    last = ""  # 이 말에서 마지막으로 더하거나 옮긴 열('○○ 옆에 다시 넣어 주세요'가 가리킴)
    for part in (x.strip() for x in CLAUSE.split(text or "")):
        named = _find(header, part) if part else []
        if not named:
            continue
        here = [h for h in named if any(_same(h, c) for c in cols)]
        if MOVE.search(part) and not REMOVE.search(part):
            col, anchor = named[0], (named[1] if len(named) > 1 else "")
            if not any(_same(col, c) for c in cols):
                cols = cols + [col]
                added.append(col)
            if anchor and NEXT_TO.search(part):
                cols = _place(cols, col, anchor)
                moved.append(col)
            last = col
        elif REMOVE.search(part) and not BACK.search(part) and not asked_sort:
            out = [h for h in here if h not in gone]
            cols = [c for c in cols if not any(_same(c, g) for g in out)]
            gone += out
        else:
            new = [h for h in named if not any(_same(h, c) for c in cols)]
            cols = cols + new
            added += new
            if new:
                last = new[0]
            # '2026-09 옆에 (다시) 넣어' — 이 마디에 더할 열이 없으면 앞 마디에서 더한 열을
            #        그 옆으로
            if NEXT_TO.search(part):
                anchor = next((h for h in named if h not in new), "")
                col = new[0] if new else last
                if col and anchor:
                    cols = _place(cols, col, anchor)
                    moved.append(col)
    if added:
        notes.append("더한 열: " + ", ".join(dict.fromkeys(added)))
    if gone:
        notes.append("뺀 열: " + ", ".join(dict.fromkeys(gone)))
    if moved:
        notes.append("옮긴 열: " + ", ".join(dict.fromkeys(moved)))
    return cols


_KO = {
    "한": 1,
    "두": 2,
    "세": 3,
    "네": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
    "열": 10,
}
_TOP_WORDS = re.compile(
    r"(?:위에서|아래에서|상위|하위)?\s*(\d{1,2}|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*(?:곳|개|동|군데)만"
)


def _top_words(text: str) -> int | None:
    m = _TOP_WORDS.search(text)
    if not m:
        return None
    n = _KO.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else 0)
    return n if 0 < n < 100 else None


def render(spec: TableSpec, data: DongData) -> tuple[str, int, list[str]]:
    """표 모양 → 마크다운 표 · 줄 수 · 표 밑 줄(기준 · 출처)."""
    t = table.build(spec.topics, spec.region, list(spec.dongs), data)
    # 열 차례는 표 모양(spec.cols) 그대로 — '○○ 옆으로 옮겨'(10-28 재심사 q01_a)
    keep = [0, 1] + [j for c in spec.cols for j, h in enumerate(t.header) if j >= 2 and _same(h, c)]
    header = [t.header[i] for i in keep]
    rows = [[r[i] for i in keep] for r in t.rows]
    if spec.sort:
        k = next((i for i, h in enumerate(header) if _same(h, spec.sort)), None)
        if k is not None:
            num = [r for r in rows if isinstance(r[k], int | float)]
            rest = [r for r in rows if not isinstance(r[k], int | float)]
            num.sort(key=lambda r: r[k], reverse=spec.desc)
            rows = num + rest
    if spec.top:
        rows = rows[: spec.top]
    out = table.Table(title=t.title, header=header, rows=rows, footer=t.footer)
    return table.markdown(out, max_cols=len(header) - 1), len(rows), list(t.footer)


def spec_from(
    region: str, topics: tuple[str, ...], dongs: list[str], t: table.Table, text: str
) -> TableSpec:
    """코드가 그린 첫 표 → 표 모양(채팅 표에 보인 열 · 말한 정렬 · 위 N곳)."""
    shown = table.shown_header(t)[1:]
    sort, desc = "", True
    if table.SORT_DESC.search(text) or table.SORT_ASC.search(text):
        j = table._sort_col(t.header, t.rows)
        sort = t.header[j] if j is not None else ""
        desc = not table.SORT_ASC.search(text)
    return TableSpec(
        region=region,
        topics=tuple(topics),
        dongs=tuple(dongs),
        cols=tuple(shown),
        sort=sort,
        desc=desc,
        top=table.top_n(text),
    )
