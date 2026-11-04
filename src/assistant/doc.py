"""동 상황 문서(PDF · PPTX) — 한 동의 상황을 결재 문서에 옮겨 적을 수 있게 정리한다.

big-contest `scripts/make_dong_doc.py`(10-12, 47곳 시험)를 옮겼다. 순서(비서 설계 v3 6절):
① 사서(코드): 대화와 **같은 사서 문장**을 주제마다 모은다
   (같은 사실이 대화와 문서에서 다르게 나오지 않게).
   '한눈에' 표도 코드가 만든다
② 글쓴이(AI): 그 묶음만 보고 요약 · 절을 정해진 모양(JSON)으로 쓴다
③ 검사(코드): 자료에 없는 숫자 · 늘었다 · 줄었다 반대 · 쓰지 않기로 한 말 · 순위 섞임 · 명단 뒤집힘.
   걸리면 한 번 고쳐 쓰게 하고, 그래도 걸린 줄은 뺀다(틀린 줄을 결재 문서에 남기지 않는다)
④ 문서 틀(코드): PDF(fpdf2) · PPTX(python-pptx). AI가 파일을 직접 만들지 않는다

【판단】 글쓴이 모델은 Sonnet 5.5(10-13 팀장 결정). 10-12 동 10곳 시험: 자료에 없는 해석 · 단정
       Haiku 6건 · Sonnet 0, 지어낸 숫자 Haiku 1 · Sonnet 0. 한 장 약 25원
【판단】 같은 동 · 같은 자료 · 같은 모델이면 만든 파일을 다시 쓴다(사실 묶음의 해시로 이름을 붙임)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.assistant import basis as B
from src.assistant import checks, llm
from src.assistant.catalog import covers
from src.assistant.config import AssistantSettings
from src.assistant.data_source import DongData
from src.assistant.librarian import gather
from src.assistant.slots import Slots

# 【기능】 문서에 모으는 주제(순서대로).
#        지역에 없는 주제(서울시 독거노인 · 버스 · 수급자)는 건너뛴다
DOC_TOPICS = (
    "dong_overview",
    "diagnosis",
    "solo_seniors",
    "seoul_lonely",
    "youth",
    "housing",
    "livelihood",
    "senior_hall",
    "places",
    "bus",
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "sections"],
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["heading", "bullets"],
                "properties": {
                    "heading": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

SYSTEM = """너는 구청 · 주민센터 · 복지관 실무자에게 '동 상황 문서'를 써 주는 비서다.
받은 자료만으로, 이 동에서 무슨 일이 일어나고 있는지 자세히 쓴다.
- 숫자는 받은 자료에 있는 것만 쓴다. 새로 계산하지 않는다(합 · 차 · 비율을 만들지 않는다).
  늘었다 · 줄었다 · 몇 위는 자료에 적힌 대로 옮긴다
- 자료가 말하지 않는 해석 · 단정 · 짐작을 붙이지 않는다
  (예: '착시가 아니다', '실제 부담이 더 크다', '꾸준히 늘었다'처럼 자료에 없는 말)
- 날씨 · 계절 · 연휴처럼 모든 동에 똑같이 오는 것을 이 동의 원인처럼 붙이지 않는다
- '취약 돌보미 동 순위', '진단', '혼자 사는 비율의 순위'는 서로 다른 것이다. 섞지 않는다.
  '실제 1인 가구 어림으로 바꿔 다시 매긴 순위'도 동 순위다(혼자 사는 비율의 순위가 아니다)
- 취약 돌보미 동 순위는 요약에만 쓴다. 진단에 해당한 신호는 그 내용에 맞는 절에 한 번만 쓴다
- '자료가 없어서', '애매해서', '알 수 없다' 같은 말로 끝내지 않는다.
  어림은 어림이라고 밝히고 그 범위와 만든 방법을 쓴다
- 개인을 다루지 않는다. 모든 내용은 동 단위다. 시설 이름 · 주소 · 전화는 자료 그대로 쓸 수 있다
- 어르신과 청년을 둘 다 다룬다
- 개조식으로 짧게 쓴다. 공무원이 결재 문서에 옮겨 적을 수 있게.
  문장 끝은 '~명', '~늘었음', '~해당'처럼 맺고 '~이다', '~다'로 끝내지 않는다. 줄표(—)를 쓰지 않는다
- summary는 이 동에서 가장 먼저 알아야 할 3~5가지만 쓴다
- sections는 이 순서로 쓴다: 어르신 / 청년 / 사는 곳과 갈 곳 / 현장에서 확인할 것.
  늘었다 · 줄었다는 그 대상의 절 안에 쓴다. 같은 내용을 두 절에 되풀이하지 않는다.
  받은 자료에 그 내용이 없는 절은 만들지 않는다.
  시설 목록(경로당 이름 · 주소 등)은 다 옮기지 말고 수와 눈에 띄는 것만 쓴다
- '현장에서 확인할 것'에는 이 동 자료에서 눈에 띄는 것(높은 순위 · 큰 숫자 · 빠른 증가 ·
  어림과 주민등록의 큰 차이 · 먼 약국 · 드문 버스)을 현장에서 맞춰 볼 점으로 2~4개 쓴다.
  모든 동에 똑같이 붙는 말은 쓰지 않는다. 할 일을 지시하지 않는다
- 결과는 반드시 report 도구를 한 번 불러서 낸다"""

# 【10-27 CLI 주석】 CLI(구독) 길에는 도구가 없어 끝줄만 JSON으로 내라고 바꿨다. 지금은 쓰지 않는다
#        (API로 바꿈, llm.py 맨 아래 주석 블록)
SYSTEM_CLI = SYSTEM.replace(
    "결과는 반드시 report 도구를 한 번 불러서 낸다",
    "결과는 주어진 JSON 모양 하나로 낸다(설명 없이)",
)

BANNED = ("자료가 없", "애매", "알 수 없", "착시", "부담은 순위보다", "꾸준히", "—", "확인되지 않")


@dataclass
class DocFacts:
    region: str
    dong: str
    text: str
    compares: list[tuple[str, float, float]] = field(default_factory=list)
    figures: list[tuple[str, str]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    rank_fix: int | None = None
    # 【기능 10-20】 취약 돌보미 판단 절(코드가 만든다 · AI를 거치지 않는다). 날씨로 날마다 바뀐다
    judge: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:8]


def _figures(d: dict, p: dict | None) -> list[tuple[str, str]]:
    """'한눈에' 표 — 코드가 동 자료에서 바로 만든다(AI 안 거침)."""
    out = []
    r = d["rank"]
    s = f"{r['of']}곳 중 {r['now']}위"
    if r["fix"] != r["now"]:
        s += f" · 실제 1인 가구로 다시 매기면 {r['fix']}위"
    out.append(("취약 돌보미 동 순위", s))
    g = d.get("diag")
    if g:
        out.append(("진단", f"진단 {g['level']}(신호 {g['of']}가지 중 {g['n']}가지)"))
    s65 = d.get("solo65")
    if s65:
        pm = B.months(s65)
        if pm:
            a, b = s65[pm[0]], s65[pm[1]]
            out.append((f"65세 이상 1인세대(주민등록 {pm[1]})", f"{b:,}명(1년 {b - a:+,}명)"))
    s80 = d.get("solo80")
    if s80:
        out.append(("80세 이상 1인세대(주민등록)", f"{s80['n']:,}명"))
    e = d.get("solo65_est")
    if e:
        out.append(("실제로 혼자 사는 65세 이상(어림)", f"약 {e['lo']:,}~{e['hi']:,}명"))
    y = d.get("youth")
    if y:
        out.append(("청년(19~34세)", f"{y['total']:,}명 · 1인세대 {y['solo']:,}명"))
    lv = d.get("livelihood")
    if lv:
        out.append(("기초생활수급자", f"{lv['people']:,}명({lv['year']}년)"))
    if p:
        out.append(("경로당 · 마을회관", f"{len(p['halls']['list'])}곳"))
    return out


def doc_facts(dong: str, data: DongData) -> DocFacts:
    """① 사서 — 대화 서가의 문장을 주제마다 모은다. 같은 줄은 한 번만."""
    d = data.dong(dong)
    if d is None:
        raise KeyError(dong)
    region = d["region"]
    slots = Slots(dongs=(dong,), region=region)
    seen: list[str] = []
    compares: list[tuple[str, float, float]] = []
    for t in DOC_TOPICS:
        if not covers(t, region):
            continue
        f = gather(t, slots, data)
        for line in f.lines + f.notes:
            if line.startswith("[") or line in seen:
                continue
            seen.append(line)
        compares += [c for c in f.compares if c not in compares]
    head = f"[{region} {dong} — 공개 자료만, 기준 {data.basis}]"
    sources = list(data.sources(region))
    sources.append(
        "시설: 경로당 현황 · 무료급식소 · 심평원 병의원 · 상가정보 · 장기요양기관(공개 자료)"
    )
    if covers("bus", region):
        sources.append("버스: 국토교통부 TAGO 버스노선정보 · 춘천시 버스정류장 노선정보")
    return DocFacts(
        region=region,
        dong=dong,
        judge=judge_bullets(dong, data),
        text=head + "\n" + "\n".join(seen),
        compares=compares,
        figures=_figures(d, data.places(dong)),
        sources=sources,
        rank_fix=d["rank"]["fix"] if d["rank"]["fix"] != d["rank"]["now"] else None,
    )


def judge_bullets(dong: str, data: DongData) -> list[str]:
    """【정함 10-20 팀장이 맡김】 동 상황 문서의 '취약 돌보미 판단' 절 — 챗봇 · 카드와 같은 조건
    창고.

    【판단】 결재 문서라 AI가 다시 쓰지 않고 코드가 사서 줄을 옮긴다(챗봇의 근거 줄과 같은 까닭).
           대상마다 판단 한 줄, 겹침마다 '이름(종류, 조건 글자): 뜻', 겹침에 든 조건 줄
    """
    from src.assistant import conditions as C

    out: list[str] = []
    for target in ("어르신", "청년"):
        sh = C.sheet(dong, target, data)
        if sh is None:
            continue
        out.append(f"{target}: " + sh.verdict().split("취약 돌보미 판단: ", 1)[-1])
        for p in sh.patterns:
            letters = "·".join(sorted(c.letter for c in p.conds))
            out.append(f"{target} 겹침 {p.title}({p.kind}, 조건 {letters}): {p.meaning}")
        used = {c.letter for p in sh.patterns for c in p.conds}
        for c in sorted((c for c in sh.conds if c.letter in used), key=lambda c: c.letter):
            out.append(f"{target} 조건 {c.letter}: {c.label}({c.value})")
        if sh.missing:
            out.append(f"{target}: 확인하지 못한 겹 {' / '.join(sh.missing)}")
    if out:
        out.append(
            "판단 기준: 같은 지역 동들 가운데 위쪽 3분의 1 또는 정한 기준을 넘으면 해당, "
            "겹침마다 정한 조건 무리가 서로 다른 겹 3가지 이상에서 함께 해당하면 겹친 걱정"
            "(취약 돌보미 동 순위와는 다른 것)"
        )
    return out


JUDGE_HEAD = "취약 돌보미 판단(조건 겹침, 코드가 계산)"


def _with_judge(doc: dict, f: DocFacts) -> dict:
    if not f.judge:
        return doc
    secs = [s for s in doc["sections"] if s["heading"] != JUDGE_HEAD]
    return {**doc, "sections": [*secs, {"heading": JUDGE_HEAD, "bullets": list(f.judge)}]}


def _pieces(doc: dict) -> list[str]:
    return [*doc["summary"], *[b for s in doc["sections"] for b in s["bullets"]]]


def problems(doc: dict, f: DocFacts) -> dict[str, list[str]]:
    """③ 검사 — 줄마다 무엇에 걸렸나. 비어 있으면 통과."""
    allowed = f.text + " " + " ".join(v for _, v in f.figures)
    bad: dict[str, list[str]] = {}
    for x in _pieces(doc):
        why = []
        extra = checks.extra_numbers(x, allowed)
        if extra:
            why.append(f"자료에 없는 숫자 {', '.join(extra)}")
        if checks.wrong_direction(x, f.compares):
            why.append("늘었다 · 줄었다가 자료와 반대")
        ban = [w for w in BANNED if w in x]
        if ban:
            why.append(f"쓰지 않기로 한 말 {', '.join(ban)}")
        # 【판단】 10-12 북산면: '다시 매긴 동 순위'를 혼자 사는 비율의 순위처럼 씀
        if f.rank_fix and f"{f.rank_fix}위" in x and "비율" in x and "다시 매" not in x:
            why.append("다시 매긴 동 순위를 비율 순위처럼 씀")
        # 【판단】 10-12 대치1동: '명단에 없음'을 빼고 써서 뜻이 거꾸로 됨
        if re.search(r"\d+(?:\.\d+)?%가 기초수급", x) and "없" not in x and "밖" not in x:
            why.append("기초수급 · 저소득 명단 문장의 뜻이 거꾸로")
        if why:
            bad[x] = why
    return bad


class DocWriter(Protocol):
    model: str

    def write(self, f: DocFacts, fix_note: str = "") -> dict: ...


class ClaudeDocWriter:
    """② 글쓴이 — report 도구(strict)로 요약 · 절을 받는다."""

    def __init__(self, s: AssistantSettings, usage: llm.Usage | None = None) -> None:
        self.s = s
        self.model = s.doc_model
        self.usage = usage or llm.Usage()

    def write(self, f: DocFacts, fix_note: str = "") -> dict:
        ask = f.text + "\n이 자료로 동 상황 문서를 써 줘."
        if fix_note:
            ask += "\n\n앞서 쓴 글에서 아래 줄이 검사에 걸렸다. "
            ask += "그 줄은 자료 그대로 고치거나 빼고 다시 써라:\n"
            ask += fix_note
        tool = {
            "name": "report",
            "description": "동 상황 문서",
            "strict": True,
            "input_schema": SCHEMA,
        }
        for _ in range(2):
            r = llm.call(
                self.s.anthropic_api_key,
                self.usage,
                model=self.model,
                max_tokens=8000,
                # 【10-27 CLI 주석】 system=SYSTEM_CLI if cli.backend() == "cli" else SYSTEM
                # 【판단】 문서 지시문도 캐시에(한 장 약 $0.03 중 지시문 읽기가 큰 몫, Sonnet)
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": ask}],
                tools=[tool],
                tool_choice={"type": "auto"},
                output_config={"effort": "medium"},
            )
            call = next((b for b in r.content if b.type == "tool_use"), None)
            if call:
                return dict(call.input)
        raise llm.LLMError("글쓴이가 report 도구를 부르지 않았다")


@dataclass
class DocResult:
    region: str
    dong: str
    model: str
    doc: dict
    pdf: Path
    pptx: Path
    dropped: dict[str, list[str]] = field(default_factory=dict)
    reused: bool = False


def build(
    dong: str, data: DongData, writer: DocWriter, out_dir: Path, font_dir: str = ""
) -> DocResult:
    """동 상황 문서 하나 — 같은 자료 · 같은 모델로 만든 파일이 있으면 그것을 쓴다."""
    f = doc_facts(dong, data)
    stem = f"{f.region}_{dong}_{f.key}_{writer.model}"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = out_dir / f"{stem}.json"
    # 【판단】 10-20: 취약 돌보미 판단 절은 날씨로 날마다 바뀐다. AI 글(meta)은 자료가 같으면 다시
    #        쓰지
    #        않고,
    #        파일 이름에 판단 절의 해시를 붙여 판단이 바뀐 날만 다시 그린다(AI를 다시 부르지 않음)
    jkey = hashlib.sha256("\n".join(f.judge).encode("utf-8")).hexdigest()[:6]
    pdf, pptx = out_dir / f"{stem}_{jkey}.pdf", out_dir / f"{stem}_{jkey}.pptx"
    # 【판단】 10-27 qbank P1-22(API): 글꼴이 없는 PC에서 Sonnet으로 글을 다 쓴 뒤($0.036)
    #        PDF를 그리다 FileNotFoundError — 돈이 헛나갔다. 글꼴부터 확인하고 AI를 부른다
    fonts = find_fonts(font_dir)
    if meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        doc = _with_judge(m["doc"], f)
        if not (pdf.exists() and pptx.exists()):
            to_pdf(doc, f, writer.model, data.basis, pdf, fonts)
            to_pptx(doc, f, writer.model, data.basis, pptx)
        return DocResult(f.region, dong, writer.model, doc, pdf, pptx, m["dropped"], True)
    doc = writer.write(f)
    bad = problems(doc, f)
    if bad:
        note = "\n".join(f"- {x} ({' · '.join(w)})" for x, w in bad.items())
        doc = writer.write(f, note)
        bad = problems(doc, f)
    if bad:
        # 【판단】 두 번 써도 걸린 줄은 뺀다(틀린 줄을 결재 문서에 남기지 않는다)
        doc = {
            "summary": [x for x in doc["summary"] if x not in bad],
            "sections": [
                {"heading": s["heading"], "bullets": [b for b in s["bullets"] if b not in bad]}
                for s in doc["sections"]
            ],
        }
        doc["sections"] = [s for s in doc["sections"] if s["bullets"]]
    doc = {"title": f"{f.region} {dong} 동 상황 문서", **doc}
    meta.write_text(
        json.dumps(
            {"doc": doc, "dropped": bad, "model": writer.model}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    doc = _with_judge(doc, f)
    to_pdf(doc, f, writer.model, data.basis, pdf, fonts)
    to_pptx(doc, f, writer.model, data.basis, pptx)
    return DocResult(f.region, dong, writer.model, doc, pdf, pptx, bad)


# ── 글꼴 ──
FONT_DIRS = (
    "C:/Windows/Fonts",
    "/usr/share/fonts/truetype/nanum",  # 우분투 fonts-nanum
    "/usr/share/fonts/nanum",
    "/Library/Fonts",
)


def find_fonts(font_dir: str = "") -> tuple[str, str]:
    """나눔고딕(보통 · 굵게) 경로. 설정(doc_font_dir) → 흔한 위치 순서로 찾는다."""
    # 【판단】 10-27: 구글 폰트 공식 파일 이름(NanumGothic-Regular · -Bold.ttf)도 받는다
    names = (
        ("NanumGothic.ttf", "NanumGothicBold.ttf"),
        ("NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"),
    )
    for d in ([font_dir] if font_dir else []) + list(FONT_DIRS):
        for r, b in names:
            reg, bold = os.path.join(d, r), os.path.join(d, b)
            if os.path.exists(reg) and os.path.exists(bold):
                return reg, bold
    raise FileNotFoundError(
        "나눔고딕(NanumGothic.ttf · NanumGothicBold.ttf)을 찾지 못했다. "
        ".env 의 DOC_FONT_DIR 에 글꼴 폴더를 적거나 fonts-nanum 을 설치한다"
    )


# ── PDF ──
# 나눔고딕에 없는 글자 → 같은 뜻의 글자(10-27 fontTools로 확인: ㎡ ℃ ㎞ ㎜ ㎝ ㎏ ㏊ ∼ ①②③ 없음)
PDF_SUBST = str.maketrans(
    {
        "㎡": "m²",
        "℃": "°C",
        "㎞": "km",
        "㎜": "mm",
        "㎝": "cm",
        "㎏": "kg",
        "㏊": "ha",
        "∼": "~",
        **{chr(0x2460 + i): f"({i + 1})" for i in range(20)},  # ① ~ ⑳
    }
)


def pdf_text(text: object) -> object:
    return text.translate(PDF_SUBST) if isinstance(text, str) else text


GREEN, GRAY, INK = (46, 92, 70), (110, 110, 110), (30, 30, 30)


def to_pdf(
    doc: dict, f: DocFacts, model: str, basis: str, path: Path, fonts: tuple[str, str]
) -> None:
    from fpdf import FPDF

    class Doc(FPDF):
        # 【판단】 10-27: 나눔고딕에 없는 단위 글자(㎡ · ℃ · ㎞ · ①…)는 PDF에서 빈칸이 된다
        #        (fpdf2 'missing the following glyphs') → 그릴 때만 같은 뜻의 글자로 바꾼다
        def cell(self, w=None, h=None, text="", *a, **k):  # type: ignore[override]
            return super().cell(w, h, pdf_text(text), *a, **k)

        def multi_cell(self, w, h=None, text="", *a, **k):  # type: ignore[override]
            return super().multi_cell(w, h, pdf_text(text), *a, **k)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("ng", "", 8)
            self.set_text_color(*GRAY)
            self.cell(
                0,
                5,
                f"취약 돌보미 AI 비서 · 동 상황 문서 · {f.region} {f.dong} · {self.page_no()}쪽",
                align="C",
            )

    pdf = Doc(format="A4")

    def head(t: str) -> None:
        pdf.ln(2)
        pdf.set_font("ng", "B", 12)
        pdf.set_text_color(*GREEN)
        pdf.multi_cell(0, 7, t, new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.set_draw_color(200, 200, 200)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(1.5)

    def items(xs: list[str], size: float = 10.5) -> None:
        pdf.set_font("ng", "", size)
        pdf.set_text_color(*INK)
        for x in xs:
            pdf.set_x(pdf.l_margin)
            pdf.cell(5, 6, "·")
            pdf.multi_cell(0, 6, x, new_x="LMARGIN", new_y="NEXT", align="L")

    pdf.add_font("ng", "", fonts[0])
    pdf.add_font("ng", "B", fonts[1])
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, 16)
    pdf.add_page()
    pdf.set_font("ng", "B", 17)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 9, doc["title"], new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.set_font("ng", "", 9)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(
        0,
        5,
        f"기준 {basis} · 공개 자료 · 숫자는 공개 자료에서 코드가 꺼냈고, "
        f"글은 AI({model})가 그 숫자로만 썼습니다.",
        new_x="LMARGIN",
        new_y="NEXT",
        align="L",
    )
    head("한눈에")
    pdf.set_font("ng", "", 10)
    pdf.set_text_color(*INK)
    with pdf.table(
        col_widths=(62, 112),
        line_height=7,
        text_align=("LEFT", "LEFT"),
        first_row_as_headings=False,
    ) as table:
        for k, v in f.figures:
            row = table.row()
            row.cell(k)
            row.cell(v)
    head("요약")
    items(doc["summary"])
    for s in doc["sections"]:
        head(s["heading"])
        items(s["bullets"])
    head("자료 출처")
    items(f.sources, 9)
    pdf.output(str(path))


# ── PPTX ──
def _ko(run) -> None:
    """글자에 한국어 표시를 단다. 없으면 PowerPoint가 낱말 가운데서 줄을 바꾼다(10-12 시험)."""
    from pptx.oxml.ns import qn

    rpr = run._r.get_or_add_rPr()
    rpr.set("lang", "ko-KR")
    rpr.set("altLang", "en-US")
    if rpr.find(qn("a:ea")) is None:
        rpr.append(rpr.makeelement(qn("a:ea"), {"typeface": "NanumGothic"}))


def to_pptx(doc: dict, f: DocFacts, model: str, basis: str, path: Path) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    name = "NanumGothic"
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]
    foot = f"{f.region} {f.dong} · 기준 {basis} · 공개 자료"

    def text(slide, s, x, y, w, h, size, bold=False, color=INK):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        r = tf.paragraphs[0].add_run()
        r.text = s
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, name
        _ko(r)
        r.font.color.rgb = RGBColor(*color)

    def bullets(slide, xs, size):
        tb = slide.shapes.add_textbox(Inches(0.7), Inches(1.45), Inches(11.9), Inches(5.3))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, s in enumerate(xs):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(14)
            r = p.add_run()
            r.text = "· " + s
            r.font.size, r.font.name = Pt(size), name
            _ko(r)
            r.font.color.rgb = RGBColor(*INK)

    def page(title):
        s = prs.slides.add_slide(blank)
        text(s, title, 0.6, 0.35, 12, 0.7, 26, True, GREEN)
        line = s.shapes.add_connector(1, Inches(0.6), Inches(1.1), Inches(12.7), Inches(1.1))
        line.line.color.rgb = RGBColor(200, 200, 200)
        text(s, foot, 0.6, 6.95, 12, 0.4, 10, color=GRAY)
        return s

    s = prs.slides.add_slide(blank)
    text(s, doc["title"], 0.8, 2.2, 11.7, 1.8, 34, True, GREEN)
    text(s, foot, 0.8, 4.1, 11.7, 0.6, 18, color=GRAY)
    text(
        s,
        f"숫자는 공개 자료에서 코드가 꺼냈고, 글은 AI({model})가 그 숫자로만 썼습니다",
        0.8,
        6.4,
        11.7,
        0.5,
        12,
        color=GRAY,
    )
    s = page("한눈에")
    rows = len(f.figures)
    tbl = s.shapes.add_table(
        rows, 2, Inches(0.7), Inches(1.5), Inches(11.9), Inches(min(0.7 * rows, 5.3))
    ).table
    tbl.first_row = tbl.horz_banding = False
    tbl.columns[0].width, tbl.columns[1].width = Inches(4.6), Inches(7.3)
    for i, (k, v) in enumerate(f.figures):
        for j, val in enumerate((k, v)):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(*((232, 240, 235) if j == 0 else (250, 250, 250)))
            cell.text = val
            run = cell.text_frame.paragraphs[0].runs[0]
            run.font.size, run.font.name, run.font.bold = Pt(17), name, j == 0
            _ko(run)
            run.font.color.rgb = RGBColor(*(GREEN if j == 0 else INK))
    bullets(page("요약"), doc["summary"], 20)
    for sec in doc["sections"]:
        bs = sec["bullets"]
        k = -(-len(bs) // 7)  # 한 장에 7줄까지, 넘으면 고르게 나눈다
        per = -(-len(bs) // k)
        for i in range(0, len(bs), per):
            bullets(
                page(sec["heading"] + (" (이어서)" if i else "")),
                bs[i : i + per],
                20 if per <= 5 else 18,
            )
    bullets(
        page("자료 출처 · 만든 방식"),
        f.sources
        + [
            "숫자 · 순위 · 늘었나 줄었나는 코드가 공개 자료에서 꺼내 계산했습니다",
            f"글은 AI({model})가 그 숫자로만 썼고, 자료에 없는 숫자 · 반대 방향 · "
            "쓰지 않기로 한 말을 코드가 검사했습니다",
        ],
        14,
    )
    prs.save(str(path))
