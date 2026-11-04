"""답 쓰기 — 사실 묶음만 보고 짧은 답을 쓴다. 검사에 걸리면 코드 기본 답.

【판단】 틀린 글을 내보내는 것보다 덜 매끄러운 글이 낫다
       (돈 받고 파는 서비스, 기관의 신임 — 10-12 팀장).
【판단】 모델은 설정(writer_model). 10-12 팀장이 Haiku 5.5로 정함.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from src.assistant import checks, llm, outlook_text
from src.assistant.config import AssistantSettings
from src.assistant.librarian import Facts
from src.assistant.reply_cache import DayCache

# 【판단】 10-12 팀장: "ai가 '사용자가 물어본 것들만' 대답하게 해줘. 거기서 뭐 따로 더 생각해서
#        만들어내거나 무엇을 하기보다는." 전에는 [자료]의 숫자를 거의 다 옮겨 답이 평균 281자 · 길면
#        983자였다(100턴 5차). 묻지 않은 숫자 · 조언 · 해석은 쓰지 않는다
# 【기능】 자료 줄 번호를 답 끝 한 줄로 적게 하는 규칙(10-26 멘토 답 1, 아래 number_facts)
BASIS_RULE = (
    "- [자료]의 줄 앞 번호('F1)' 같은 것)는 답 글에 쓰지 않는다. 답을 다 쓴 뒤 마지막 줄에 "
    "'근거: F1, F3'처럼 답에 쓴 줄 번호만 적는다(쓴 줄이 없으면 '근거: 없음')"
)
WRITER_SYSTEM = (
    """너는 '취약 돌보미' AI 비서다. 복지 실무자의 질문에 [자료]만 보고 한국어로 답한다.
- 질문에서 물은 것만 답한다. 묻지 않은 숫자(다른 나이대 · 다른 기간 · 늘고 줄음 · 순위 ·
  다른 지역)는 쓰지 않는다. 물은 것이 여러 개면 물은 것마다 답한다
- 조언 · 권유 · 해석을 덧붙이지 않는다('참고할 수 있습니다', '확인이 필요합니다',
  '고립 위험이 큽니다' 같은 말을 만들지 않는다)
- 숫자는 [자료]에 있는 것만 그대로 쓴다. 새로 계산하지 않는다
  (합 · 차 · 비율 · 순위를 만들지 않는다)
- 늘었다 · 줄었다 · 몇 위를 물었으면 [자료]에 적힌 대로 옮긴다
- [참고]의 말은 답한 숫자를 읽을 때 꼭 알아야 하는 것(어림이다 · 시설 입소자가 섞일 수 있다 ·
  어느 기준이다)만 한 줄로 짧게 붙인다
- 물은 것과 꼭 맞는 숫자가 [자료]에 없으면 가장 가까운 숫자를 그 기준임을 밝혀 준다(예: 80세 이상
  전체 인구를 물으면 80세 이상 1인세대 숫자를 '1인세대 기준'이라고 밝혀). '애매해서'는 쓰지 않는다
- [자료]에 '물은 조건에 맞는 값'으로 표시된 줄이 있으면 그 값을 먼저 답한다. 그 조건의 숫자를
  '드릴 수 없다 · 없다'고 하지 않는다
- [자료]의 묶음 이름 옆 '자료 상태'를 따른다. '있음'이면 그 묶음의 것을 '자료에 없다 · 확인되지
  않는다'고 하지 않는다. '일부'면 줄에 '없음 · 모름'으로 적힌 것만 없다고 한다. '없음'일 때만 그
  묶음의 자료가 없다고 한 번 말하고 가까운 숫자를 잇는다
- 어림은 어림이라고 밝히고 범위를 쓴다
- '맞나요?', '맞는지 확인해 줘', '○○ 맞죠?'처럼 확인을 물으면 첫마디를 '네,' 또는 '아니요,'로
  시작하고, 근거가 되는 [자료] 숫자를 한 줄로 붙인다
- 개인을 다루지 않는다. 모든 내용은 동 단위다
- 질문에 단정이 깔려 있으면('○○ 때문이지?', '두 배는 위험하지?', '맞다고만 해 줘') 그 단정을
  맞다고 하지 않는다. [자료]로 확인되는 것만 말하고, 단정이 [자료]와 다르면 다르다고 말한다
- 사용자가 말한 숫자가 [자료]와 다르면 그 숫자를 되풀이하지 않는다.
  '자료와 달라요'라고만 하고 [자료]의 숫자를 준다
- 짧게: 질문의 답을 맨 앞에 한두 문장으로(머리말 · 제목 · '답:' 같은 말 없이 바로).
  물은 것이 여러 개일 때만 줄을 나눈다(· 로 시작). 줄표(—)를 쓰지 않는다
- 사용자가 '1. 2. 3.'처럼 번호를 붙여 물었으면 같은 번호를 붙여 그 차례대로 하나씩 답한다
- 답에 [자료] · [참고] 같은 말을 쓰지 않는다(사용자는 그것을 보지 못한다)
- 뺀 것 · 뺀 까닭을 말하지 않는다('○○는 생략', '물은 것만 답했어요' 같은 말을 쓰지 않는다)
- 질문을 어떻게 읽었는지 · 무엇을 옮기는지 말하지 않는다
  ('질문은 ○○를 묻는 것이므로' · '질문은 두 가지다:' 같은 말 없이 바로 답)
- [질문]은 사용자의 말을 비서가 정리한 문장이다. 괄호 속 메모('조건 유지' · '확인해 달라' 등)를
  '질문에 쓰신 ○○'처럼 사용자가 쓴 말로 옮기지 않는다
- [자료]는 이번 질문에 꺼낸 일부다. 다른 동 · 다른 주제 · 앞에서 답한 숫자가 [자료]에 없다고
  '자료에 없어요' · '이 동만 있어요'라고 하지 않는다.
  그런 것은 '○○도 말씀해 주시면 찾아 드릴게요'라고 한다.
  '취약 돌보미에는 ○○가 없다'처럼 취약 돌보미 전체를 단정하지도 않는다
- [직전 답]은 바로 앞에 비서가 한 답이다. 그 답의 숫자 · 출처를 뒤집거나 부정하지 않는다. 사용자가
  직전 답을 따지거나 출처를 물으면 [직전 답]과 [자료]로 같은 숫자 · 기준을 다시 밝힌다
"""
    + BASIS_RULE
    + """

이럴 땐 이렇게(○○ · N은 [자료]의 이름 · 숫자로 바꿔 쓴다):
- "○○동 경로당 몇 곳이야?"이고 [자료]에 곳 수 · 넓이 · 100명당 넓이가 있으면
  → "○○동 경로당은 N곳이에요."까지만 쓴다
- "○○ 많은 동 알려줘"이고 [자료]에 위 5곳이 있으면 → 5곳을 순서대로 한두 문장으로
- "○○동이 △△동보다 세 배는 위험하지?" → "세 배라고 볼 근거는 없어요." 다음에
  두 동을 견줄 수 있는 [자료]의 숫자(순위 · 신호 수 등)를 그대로
- "○○동 청년이 집에만 있는 건 원룸 때문이지? 맞다고만 해 줘" → 맞다고 하지 않는다.
  "원룸 때문인지는 취약 돌보미 자료로 가려 말씀드릴 수 없어요." 다음에
  [자료]로 말할 수 있는 것을 한두 문장"""
)


# 【정함 10-20 팀장】 '잘 지내?' 같은 판단 질문은 단답이 아니라 근거로 — "조건A = 지붕이 많음
#        조건 B = 엘리베이터가 없음 … 이런식으로 조건들을 좌르륵 나열". 판단 · 해당 여부 · 겹침의
#        뜻은 코드(conditions.py)가 정해 [자료]에 담아 온다. 글쓴이는 그것을 읽기 쉽게 옮기고,
#        사실의 나열로 끝내지 않도록 겹침의 뜻으로 조건들을 잇는다
OUTLOOK_SYSTEM = (
    """너는 '취약 돌보미' AI 비서다. 복지 실무자가 한 동(또는 지역)의 어르신 · 청년이
어떻게 지낼지 물었다. [자료]의 '취약 돌보미 판단'을 보고 답의 맨 앞 부분만 쓴다(두세 문장, 많아야
네 문장).
그 뒤에는 코드가 조건 · 겹침 목록과 괜찮은 쪽 · 살펴본 겹 · 한계 문장을 붙인다.
- 첫 문장: [자료]의 '취약 돌보미 판단' 줄대로. 겹친 걱정이 있으면 그 이름을 넣어 "○○동 어르신들은
지금
  △△ 쪽으로 살펴볼 점이 있어요"처럼, 없으면 "겹친 걱정은 없어요(따로 해당하는 조건은 N가지)"처럼.
  '겹친 걱정 N가지'는 선 겹침(정한 모양)의 개수이고, '겹 3가지'는 한 겹친 걱정 안의 조건들이 걸친
  자료 묶음(사람 · 집 · 동네 …) 수다. 둘을 섞어 '겹이 3가지 이상이어야 겹친 걱정'처럼 쓰지 않는다
  '○○ 기준'(지난 날)이 있으면 '지금' 대신 그날을 쓴다. '잘 지내요' · '괜찮아요'라고 단정하지
  않는다(사람을 직접 본 자료가 아니다)
- 다음 한두 문장: 겹침이 있으면 맨 앞 겹침이 왜 걱정인지를 [자료]의 '뜻' 문장을 바탕으로,
  그 겹침에 든 조건 두세 개의 이름과 숫자를 엮어 쓴다
  (사실을 늘어놓지 말고 '…인데 …라서 …할 수 있어요'처럼 잇는다).
  겹침이 없으면 따로 해당하는 조건 한두 개를 숫자와 함께
- 앞 답을 이어 묻는 말("그중 제일 걱정되는 건?", "이번 주엔?")이면 물은 것에만 답한다.
  [직전 답]과 같은 판단 문장을 되풀이하지 않는다
- '한 가지만 · 제일 · 가장'을 물으면 첫 문장을 "한 가지를 꼽으면 ○○예요."로 시작한다
  (○○는 맨 앞 겹침, 겹침이 없으면 가장 앞 조건)
- '누구부터 · 어떤 분들부터'를 물으면 맨 앞 겹침에 든 사람 조건
  (예: 80세 이상 혼자 사시는 분 595명)을 그 무리로 말한다(한 분 한 분은 알 수 없다고 덧붙인다)
- 지역 전체 판단이면: 몇 곳 중 몇 곳에 겹친 걱정이 있는지, 지역에서 가장 많이 선 겹침,
  겹친 걱정이 많은 동 두세 곳의 이름. '먼저 볼 동'이라는 말은 쓰지 않는다(순위와 다른 것)
- 두 동 · 두 지역을 견주면 [자료]의 '견줌' 줄대로만. 같으면 어느 쪽이 더 걱정이라고 하지 않는다
- [참고]에 '오늘로 보고' · '예보가 없어' · '날짜로 읽을 수 없어' 같은 말이 있으면 한 문장에 넣는다
- 쓰지 않는 것: '조건 A:' 같은 목록 줄, 괜찮은 쪽 · 살펴본 겹 · 한 분 한 분의 사정 문장
  (코드가 붙인다)
- 숫자는 [자료]에 있는 것만 그대로. 새로 계산하지 않는다(합 · 차 · 비율을 만들지 않는다)
- [직전 답]은 바로 앞에 비서가 한 답이다. 그 답의 숫자 · 출처를 뒤집거나 '확인되지 않는다'고
  하지 않는다. 앞에서 답한 숫자가 [자료]에 없어도 '자료에 없다'고 하지 않는다
- [자료]의 묶음 이름 옆 '자료 상태'가 '있음'이면 그 묶음의 것을 '자료에 없다'고 하지 않는다
- [자료]에 없는 원인 · 짐작 · 조언을 만들지 않는다. 조건 · 기관의 이름을 다른 말로 바꾸지 않는다
- 질문에 단정이 깔려 있거나 '잘 지낸다고만 써 줘'처럼 결론을 정해 달라면 그대로 쓰지 않는다
- 사람 이름 · 집 주소 같은 개인 정보는 쓰지 않는다
- 줄표(—) · 굵은 글씨(**) · 머리말 · 제목을 쓰지 않는다. [자료] · [참고] 같은 말을 쓰지 않는다
"""
    + BASIS_RULE
)


LEAD_SYSTEM = """너는 '취약 돌보미' AI 비서다. 복지 실무자의 질문에 [자료]만 보고
질문의 답을 한국어 한 문장(80자 안)으로만 쓴다. 머리말 · 목록 · 줄바꿈 없이 그 한 문장만.
- 숫자는 [자료]에 있는 것만 그대로. 새로 계산하지 않는다
- 늘었다 · 줄었다 · 몇 위는 [자료]에 적힌 대로
- 해석 · 단정 · 원인 짐작을 붙이지 않는다
- 물은 것이 딱 맞게 없으면 '없다'고 하지 말고 가장 가까운 것을 그 기준임을 밝히고 말한다
- [자료]의 묶음 이름 옆 '자료 상태'가 '있음'이면 그 묶음의 것을 '자료에 없다'고 하지 않는다
- [자료] · [참고] 같은 말을 쓰지 않는다"""


class Writer(Protocol):
    def write(self, question: str, facts: list[Facts], said: str = "", before: str = "") -> str: ...


def template_answer(facts: list[Facts], cap: int = 0) -> str:
    """코드 기본 답 — 사실 묶음을 그대로 개조식으로(AI 안 부름). cap 이 있으면 그 줄 수까지."""
    out = []
    for f in facts:
        out.append(f"{f.title}")
        for line in f.lines:
            out.append(line if line.startswith(("[", "-")) else f"· {line}")
        out += [f"· {n}" for n in f.notes]
    if cap:
        # 10-20 페르소나 h01 r2: 줄 수는 적어도 한 줄이 아주 길었다(경로당 28곳 주소) — 줄도 자른다
        out = [x if len(x) <= 220 else x[:220] + "…" for x in out]
        if len(out) > cap:
            out = out[:cap] + ["(자료가 더 있어요. 궁금한 것을 좁혀 물어봐 주세요.)"]
    return "\n".join(out)


# 【판단】 10-20 페르소나 8명 r8: AI 답이 검사에 걸리면(없다고만 함 · 사용자 숫자 되풀이 등) 곧바로
#        자료 줄 전체(한파 41일 목록 · 자료 목록 24줄)를 쏟았다(f01 · o01 · o02). 한 번만 무엇이
#        걸렸는지 알려 다시 쓰게 하고, 그래도 걸리면 줄 수를 줄인 기본 답으로
FALLBACK_CAP = 14
# 【판단】 10-26 멘토 답 1 · 페르소나 cli2 세라핀('묻지 않은 자료 설명이 길게 왔다',
#        1,511 ~ 1,799자): 14줄 × 220자도 길었고, 글쓴이에게만 주는 [참고] 지시문까지 함께 나갔다.
#        기본 답은 물은 말과 겹치는 줄만 여섯 줄까지(그 줄의 동 머리줄을 붙여), 지시문은 뺀다
SHORT_LINES = 6
SHORT_CHARS = 200
_ASK_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_PARTICLE = re.compile(
    r"(?:에서|까지|부터|으로|에게|한테|이랑|하고|은|는|이|가|을|를|의|도|에|로|와|과|만)$"
)
_COMMON = {
    "알려",
    "알려줘",
    "주세요",
    "줘요",
    "해줘",
    "뭐야",
    "어때",
    "있어",
    "있나요",
    "얼마",
    "얼마나",
    "확인",
    "자료",
    "지금",
    "그럼",
    "그리고",
    "이거",
    "그거",
    "어디",
    "어느",
    "무엇",
    "몇",
    "좀",
    "말씀",
    "부탁",
    "드립니다",
    "합니다",
    "건가요",
    "맞나요",
    "인가요",
    "대해",
    "관련",
}
_DIRECTIVE = re.compile(r"(?:않는다|쓴다|말한다|적는다|답한다|붙인다|밝힌다|준다|따른다)(?:[.)]|$)")


def short_answer(facts: list[Facts], asked: str) -> str:
    """검사에 걸렸을 때의 짧은 기본 답 — 물은 말과 겹치는 자료 줄만(AI 안 부름)."""
    words = {_PARTICLE.sub("", w) for w in _ASK_WORD.findall(asked or "")}
    words = {w for w in words if len(w) >= 2 and w not in _COMMON}
    nums = checks.numbers(asked or "")
    picked: list[tuple[int, int, int]] = []  # (점수, 묶음 차례, 줄 차례)
    # 【판단】 10-27 qbank P2-08(API): 기본 답에 '앞서 답할 때 본 자료(다시 확인용)'(앞 턴의 다른 동
    #        줄, engine.CARRY_TITLE)가 그대로 나갔다 — 이번 답의 자료가 있으면 그 묶음은
    #        고르지 않는다
    own = [f for f in facts if not f.title.startswith("앞서 답할 때 본 자료")]
    for i, f in enumerate(facts):
        if own and f not in own:
            continue
        for j, line in enumerate(f.lines):
            if line.startswith("[") and line.endswith("]"):
                continue
            score = sum(1 for w in words if w in line) + 2 * len(nums & checks.numbers(line))
            picked.append((score, i, j))
    best = sorted(picked, key=lambda x: (-x[0], x[1], x[2]))
    if best and best[0][0] > 0:
        best = [b for b in best if b[0] > 0]
    chosen = sorted(best[:SHORT_LINES], key=lambda x: (x[1], x[2]))
    out: list[str] = []
    for i, f in enumerate(facts):
        rows = [j for (_, fi, j) in chosen if fi == i]
        if not rows:
            continue
        out.append(f.title)
        head = ""
        for j, line in enumerate(f.lines):
            if line.startswith("[") and line.endswith("]"):
                head = line
            if j in rows:
                if head and head not in out:
                    out.append(head)
                text = line if len(line) <= SHORT_CHARS else line[:SHORT_CHARS] + "…"
                # 10-27: 자료 줄의 '- '는 화면 목록 꼴('· ')로 맞춘다(qbank P2-22 두 꼴 섞임)
                text = re.sub(r"^\s*-\s+", "", text)
                out.append(text if text.startswith("[") else f"· {text}")
        out += [f"· {n}" for n in f.notes if not _DIRECTIVE.search(n)][:1]
    if len(picked) > len(chosen):
        out.append("(자료가 더 있어요. 궁금한 것을 좁혀 물어봐 주세요.)")
    return "\n".join(out)


FIX_WORD = (
    ("없는 숫자", "[자료]에 없는 숫자를 썼다. [자료]에 있는 숫자만 쓴다"),
    ("없는 날짜", "[자료]에 없는 날짜를 썼다"),
    ("방향 반대", "늘고 줄음을 거꾸로 썼다"),
    ("금지 말", "줄표(—) 같은 금지된 글자를 썼다"),
    ("한국어 아님", "영어로 썼다. 한국어로만 쓴다"),
    (
        "파일 있는데 못 만든다 함",
        "이 턴에 엑셀 · CSV 파일을 만들어 건넸는데 '파일 · 엑셀 기능이 없다 · 못 만든다'고 썼다. "
        "그 말을 빼고, 파일에 무엇이 들었는지만 짧게 쓴다",
    ),
    (
        "많고 적음 뒤집힘",
        "[자료]에서 아래쪽(적은 쪽) 등수인 동을 '많은 동'이라고(또는 위쪽 동을 '적은 동'이라고) "
        "썼다. [자료]의 등수 그대로 적은 동은 적다고 쓴다",
    ),
    (
        "순위 방향 뒤집힘",
        "[자료]의 '많은 순 N위'를 '적은 순'으로 바꿔 써 뜻이 거꾸로 됐다. [자료]의 꼴 그대로"
        "('많은 순 22위' 또는 '22곳 중 가장 적은 곳') 쓴다",
    ),
    (
        "없다고만 함",
        "'없다 · 확인되지 않는다'고만 했다. [자료]에 있는 것을 먼저 말하고, "
        "없는 것은 그다음에 짧게",
    ),
    ("몫 앞뒤 뒤바뀜", "'전체 중 일부'를 거꾸로 썼다('4,736명 중 3,638명'처럼 큰 수가 앞)"),
    ("사용자 숫자 되풀이", "사용자가 말한 숫자를 [자료]의 숫자처럼 되풀이했다"),
    ("두 지역 견줌", "두 지역 가운데 어디가 더 힘든지 판정했다. 우열을 말하지 않는다"),
    (
        "허락으로 읽힘",
        "자료에 없는 말(위험 · 고독사)이 든 문장을 써도 되냐는 물음에 '네'로 시작했다. "
        "'아니요,'로 시작하고 자료의 이름(취약 돌보미 동 순위 등)으로 고쳐 준다",
    ),
    (
        "동의로 읽힘",
        "질문에 깔린 단정('○○ 때문이잖아요 그쵸?')에 '네,'로 시작해 동의로 읽힌다. '네'를 빼고 "
        "[자료]로 확인되는 것만 말한다(단정과 다르면 '아니요,'로 시작해도 된다)",
    ),
    ("잘림", "너무 길다. 더 짧게"),
    (
        "맞는 곳 수 틀림",
        "[자료]의 '모두 N곳'은 N곳이 다 맞는다는 뜻이다. 'N곳 중 K곳'이 아니라 "
        "'N곳 모두(그중 위 K곳만 적음)'로 쓴다",
    ),
    (
        "요일 자료 있는데 없다 함",
        "[자료]에 그 요일에 문 연 약국까지 거리가 있다. '○요일 자료는 없다'고 쓰지 않고 "
        "[자료]의 날짜 · 요일 기준 그대로 쓴다",
    ),
)


def fix_note(found: list[str]) -> str:
    words = [w for k, w in FIX_WORD if any(x.startswith(k) for x in found)]
    return "[고칠 것]\n" + "\n".join(f"- {w}" for w in words or ["검사에 걸렸다"])


@dataclass
class WriteResult:
    text: str
    used_ai: bool
    problems: list[str]
    # 【기능】 글쓴이가 '근거: F1, F3'으로 적은 쓴 줄 번호(없으면 None, 10-26 멘토 답 1)
    cited: list[str] | None = None


# ── 자료 줄 번호(10-26 멘토 답 1) ──
# 【판단】 멘토: 사실 줄에 번호를 붙이고 AI가 어느 줄을 썼는지 적게 하면 코드가 바로 검증한다.
#        흘려 보이기를 살리려고 구조화 출력 대신 답 끝 한 줄('근거: F1, F3')로 받고, 그 줄은 화면에
#        내지 않는다. 검증은 좁게 — 답의 숫자가 인용한 줄에 없고 '다른 동' 줄에만 있으면(다른 동
#        숫자를 이 동 숫자처럼 씀) 다시 쓰게 한다. 인용을 빼먹은 것은 기록만(오탐을 늘리지 않게)
BASIS_LINE = re.compile(r"^\s*근거\s*[:：]\s*(.*)$")
_FID = re.compile(r"F\d{1,3}")
_HEAD_ONLY = re.compile(r"^\[[^\]]+\]$")


def number_facts(facts: list[Facts]) -> tuple[str, dict[str, tuple[str, str]]]:
    """[자료] 글(줄마다 F번호) · 번호 → (줄, 그 줄의 동 머리줄)."""
    out: list[str] = []
    ids: dict[str, tuple[str, str]] = {}
    for f in facts:
        out.append(f"## {f.title} (자료 상태: {f.status})")
        head = ""
        for line in f.lines:
            if _HEAD_ONLY.match(line.strip()):
                head = line.strip()
                out.append(line)
                continue
            fid = f"F{len(ids) + 1}"
            ids[fid] = (line, head)
            out.append(f"{fid}) {line}")
        out.append("")
    return "\n".join(out).strip(), ids


def split_basis(text: str) -> tuple[str, list[str] | None]:
    """답 글 · 근거 줄의 번호(근거 줄이 없으면 None)."""
    lines = (text or "").rstrip().splitlines()
    for i in range(len(lines) - 1, -1, -1):
        m = BASIS_LINE.match(lines[i])
        if m:
            body = "\n".join(lines[:i] + lines[i + 1 :]).strip()
            return checks.strip_fact_ids(body), _FID.findall(m.group(1))
    return checks.strip_fact_ids((text or "").strip()), None


def misattributed(
    body: str, cited: list[str] | None, ids: dict[str, tuple[str, str]], extra: str
) -> list[str]:
    """인용한 줄에 없고 다른 동 줄에만 있는 숫자 — '다른 동 숫자 N'."""
    if not cited or not ids:
        return []
    rows = [ids[c] for c in cited if c in ids]
    heads = {h for _, h in rows if h}
    if not rows or not heads:
        return []
    have = checks.numbers(" ".join(line for line, _ in rows)) | checks.numbers(extra)
    out = []
    for n in sorted(checks.numbers(body) - have):
        holders = [h for line, h in ids.values() if n in checks.numbers(line)]
        if holders and all(h and h not in heads for h in holders):
            out.append(f"다른 동 숫자 {n}")
    return out


def clean(text: str) -> str:
    # 【판단】 지시문의 칸 이름이 답에 새어 나오면 뗀다(4차: 답 66개 중 3~4개, 10-12 페르소나:
    #        '[참고 대신 한 줄]'처럼 지어낸 꼬리표까지) — 뗀 결과는 답 검문소(checks.tidy)와 같다
    return checks.strip_tags(text)


# 【기능】 흘려 보일 조각의 끝: 줄바꿈, 또는 마침표 · 물음표 · 느낌표 뒤의 빈칸
_CUT = re.compile(r"\n|(?<=[.!?])[ \t]")


# 【판단】 10-15 페르소나 q19(기자): "'개포3동, 강남 위험 순위 1위'라고만 써도 되죠?"에
#        '네, 개포3동은 취약 돌보미 동 순위 1위예요'로 답해 '네'를 허락으로 읽혔다.
#        처음엔 시스템 지시문에 규칙을 넣었는데 갈 곳 30 T20에 '아니요, … 나와 있지 않아요.
#        다만 4곳'이 나왔다(A/B 규칙 있음 3/4 · 없음 4/4). 그래서 코드가 '○○라고 써도 되나'를
#        알아볼 때만 그 턴의 [참고]에 붙인다
# 10-28 페르소나 p06_a T4 '"고독사 위험 최상위 구간 1위 개포3동"이라고 쓰는 건 괜찮죠?'를 놓쳐
#        '네, …5구간에 있어요'(아첨)가 나갔다 → '쓰는 건 괜찮 · 쓰면 되 · 제목으로 뽑아도'도
WRITE_OK = re.compile(
    r"(라고|이라고|대로|그대로|으로|로)[^?\n]{0,20}"
    r"(?:(?:써|쓰|적어|말해|해|뽑아)도 ?(?:되|될|돼|괜찮)"
    r"|(?:쓰|적|하|뽑)는 ?(?:건|것은|거|것) ?(?:괜찮|되|될|돼)"
    r"|(?:쓰|적|뽑)으?면 ?(?:되|돼|괜찮|안 되))"
)
# 【판단】 10-20 페르소나 h01 · f02 · s02 r8: '짧게 · 한 줄로 · 결론만'을 여러 번 말했는데 긴 답과
#        근거 줄 전체가 나갔다. 짧게 달라면 글쓴이에게 알리고, 취약 돌보미 판단은 근거 줄을 붙이지
#        않는다
BRIEF = re.compile(
    r"짧게|한 ?줄|한 ?문장|결론만|간단히|요점만|길게 말고|숫자만|예 ?/ ?아니오|맞다 ?/ ?아니다"
    # 10-20 페르소나 h01 r8 T5 ~ T9: '한마디로만' · '마을 이름만 한 개' · '설명은 빼고'에 긴 답
    r"|한 ?마디|이름만|한 ?개만|하나만|설명은 빼|설명 빼|딱 ?하나|말만 해"
    # r9 h01: '예 아니오로만' · '긴말말고' · '길게 쓰지말고'
    r"|예 ?아니오|예나 아니오|긴 ?말 ?말고|길게 (?:쓰|하|말하)지"
)
# 앞 턴에서 짧게 · 근거 빼 달라고 한 말(이번 턴에도 이어 간다 — r9 f01 '안 붙이셔도 된다'를 두 번)
BRIEF_PREV = re.compile(BRIEF.pattern + r"|안 붙이셔도|붙이지 마|붙이지 않아도|핵심만|그만 붙")
# 【판단】 10-20 페르소나 o01 r9 T8: '300명 … 55%라고 하셨지요?'에 '네, 맞아요'로 시작하고 242명을
#        적었다. 사용자가 숫자를 되물으면 [자료]와 대조해 다르면 '아니요,'로 시작한다
CONFIRM_NUM = re.compile(
    r"\d[\d,.]*\s*(?:명|%|곳|채|번|위)[^?\n]{0,40}(?:하셨|맞[지죠나습]|이지요|이죠|거죠"
    # 10-26 예상 질문 2-7 '아까는 북산면이 1위라고 했잖아요'(실제 2위)에 '네, … 2위가 맞아요'
    r"|했잖|라고 했|라고 하셨|라더니|랬잖)"
)
CONFIRM_NUM_NOTE = (
    "사용자가 숫자를 되물었다. 그 숫자가 [자료]와 같을 때만 '네,'로 시작한다. "
    "다르면 '아니요,'로 시작하고 [자료]의 숫자를 적는다"
)
# 【판단】 10-28 페르소나 p01_b T1 '어르신 수가 많이 늘었다고 하던데 맞아요?'에 '네, 맞아요'
#        (실제 81명 · 3%) — 정도 말('많이 · 크게 · 급증')에 맞장구치면 아첨이 된다
DEGREE_CLAIM = re.compile(
    r"(?:많이|크게|엄청|확|급격히|폭발적으로|대폭|훨씬|너무)\s?(?:늘|증가|줄|감소|올|떨어)"
    r"|급증|급감|폭증"
)
DEGREE_NOTE = (
    "사용자가 '많이 늘었다'처럼 정도를 붙여 말했다. '네, 맞아요'로 그 정도에 동의하지 않는다. "
    "늘었는지 줄었는지와 [자료]의 숫자(몇 명 · 몇 %)로 답하고, 많은지 적은지는 [자료]에 견줄 "
    "값(지역 평균 · 순위)이 있을 때만 그 값으로 말한다"
)
BRIEF_NOTE = (
    "사용자가 짧게 달라고 했다. 물은 것에만 한두 문장(또는 사용자가 말한 줄 수)으로 답하고, "
    "목록 · 표 · 부연은 붙이지 않는다"
)
WRITE_OK_NOTE = (
    "사용자가 어떤 문장을 그대로 써도 되는지 묻고 있다. "
    "그 문장이 [자료]와 이름 · 숫자까지 같을 때만 '네,'로 시작한다. "
    "[자료]에 없는 이름(예: '위험 순위', '고독사 위험 1위')이나 다른 숫자가 있으면 "
    "'아니요,'로 시작하고 [자료]에 있는 말로 고쳐 준다"
)


class StreamGate:
    """흘려 보이는 글을 문장 · 줄 단위로 검사해서 내보낸다.

    【판단】 '지금까지 낸 글 + 새 조각' 전체에 write() 와 같은 검사(checks.problems)를 건다.
           걸리면 그 조각부터 내지 않고 멈춘다(ok=False). 마지막 조각까지 통과하면
           낸 글 전체 = AI가 쓴 글 전체이고, 그 전체가 검사를 통과한 것이다.
    """

    def __init__(self, allowed: str, compares: list, echo: tuple[str, str] = ("", "")) -> None:
        self.allowed = allowed
        self.compares = compares
        self.echo = echo
        self.shown = ""
        self.pending = ""
        self.ok = True
        self.problems: list[str] = []
        self.basis: str | None = None

    def feed(self, delta: str) -> list[str]:
        if not self.ok:
            return []
        self.pending += delta
        cut = None
        for m in _CUT.finditer(self.pending):
            cut = m.end()
        if cut is None:
            return []
        seg, self.pending = self.pending[:cut], self.pending[cut:]
        return self._try(seg)

    def flush(self) -> list[str]:
        seg, self.pending = self.pending, ""
        out = self._try(seg) if self.ok and seg.strip() else []
        if self.ok:
            # 【판단】 '없다고만 했나'는 다 쓴 뒤 전체로 본다(중간에는 뒤에 숫자가 올 수 있다)
            none = checks.none_only(self.shown.strip(), self.allowed)
            if none and not checks.asks_if_unknown(self.echo[0]):
                self.ok, self.problems = False, [f"없다고만 함 {w}" for w in none]
        return out

    def _try(self, seg: str) -> list[str]:
        if BASIS_LINE.match(seg.strip()):  # 근거 줄은 화면에 내지 않고 받는다(10-26)
            self.basis = seg.strip()
            return []
        seg = checks.strip_fact_ids(clean(seg))
        whole = (self.shown + seg).strip()
        found = checks.problems(whole, self.allowed, self.compares, final=False) + [
            f"사용자 숫자 되풀이 {n}" for n in checks.echoed_counts(whole, *self.echo)
        ]
        if found:
            self.ok, self.problems = False, found
            return []
        self.shown += seg
        return [seg]


def _join(head: str, tail: str) -> str:
    """취약 돌보미 판단: AI(또는 사서)의 판단 문장 + 코드가 붙이는 근거."""
    return "\n\n".join(x for x in (head.strip(), tail.strip()) if x)


class TemplateWriter:
    def write(self, question: str, facts: list[Facts], said: str = "", before: str = "") -> str:
        if any(f.style == "outlook" for f in facts):
            tail = outlook_text.render(facts, said or question, before)
            return _join(outlook_text.verdicts(facts), tail)
        return template_answer(facts)


class ClaudeWriter:
    def __init__(self, settings: AssistantSettings, usage: llm.Usage | None = None) -> None:
        self.s = settings
        self.usage = usage or llm.Usage()
        self.last: WriteResult | None = None
        # 같은 입력이면 그날 같은 답(10-26 멘토 답 4) — 검사를 통과한 답만
        self.cache = DayCache(settings.reply_cache)

    def _request(
        self, question: str, facts: list[Facts], said: str = "", before: str = ""
    ) -> tuple[dict, str, list]:
        """AI에 보낼 것(kwargs) · 답 검사에 쓸 허용 글 · 늘고 줄음 견줌.

        【판단】 before = 직전 답(10-15 페르소나 q03: 앞 답의 숫자를 '자료에 없다'며 뒤집음).
               직전 답의 숫자는 그때 검사를 통과한 것이라 허용 글에 넣는다
        """
        outlook = any(f.style == "outlook" for f in facts)
        lead = self.s.writer_mode == "lead" and not outlook
        # 10-26 멘토 답 1: 묶음마다 자료 상태(있음 · 일부 · 없음)를 코드가 붙인다
        source = "\n\n".join(
            f"## {f.title} (자료 상태: {f.status})\n" + "\n".join(f.lines) for f in facts
        )
        # 10-26 멘토 답 1: 글쓴이에게는 줄마다 번호(F1)를 붙여 준다(한 문장 모드는 근거 줄이 없다).
        #        검사의 허용 글은 번호 없는 원래 글이다(번호의 숫자가 허용 숫자로 섞이지 않게)
        numbered, self._ids = number_facts(facts) if not lead else (source, {})
        self._cited: list[str] | None = None
        notes = [n for f in facts for n in f.notes]
        if WRITE_OK.search(said or question):
            notes.append(WRITE_OK_NOTE)
        if BRIEF.search(said or question):
            notes.append(BRIEF_NOTE)
        if CONFIRM_NUM.search(said or question):
            notes.append(CONFIRM_NUM_NOTE)
        if DEGREE_CLAIM.search(said or question):
            notes.append(DEGREE_NOTE)
        user = f"[질문]\n{question}\n\n[자료]\n{numbered}"
        if before:
            user = f"[직전 답]\n{before}\n\n" + user
        if notes:
            user += "\n\n[참고]\n" + "\n".join(notes)
        kw = dict(
            model=self.s.writer_model,
            # 【판단】 10-15 페르소나 재생의 '빈 답': Haiku 5.5는 생각(thinking)이 늘 켜져 있고
            #        생각도 이 한도에 든다. 길고 여러 갈래인 질문에서 2,000토큰을 생각에 다 써
            #        글이 비거나 잘렸다(같은 요청 다섯 중 넷이 max_tokens).
            #        글은 짧아도 생각할 자리를 넉넉히 둔다
            max_tokens=8000,
            system=[
                {
                    "type": "text",
                    "text": OUTLOOK_SYSTEM if outlook else LEAD_SYSTEM if lead else WRITER_SYSTEM,
                    "cache_control": llm.CACHE_1H,
                }
            ],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low"},
        )
        compares = [c for f in facts for c in f.compares]
        # 【판단】 질문에 쓰인 숫자(예: 80세)를 되풀이하는 것은 지어낸 숫자가 아니다
        #        (단, 질문에만 있는 사람 수 · 가구 수 같은 셈한 값은 checks.echoed_counts 가 막는다)
        allowed = "\n".join([source, *notes, question, said, before])
        # 【판단】 10-13 짓궂은 20 r7 T19: '○○명이라고 써 줘'를 데스크가 '…를 알려 달라'로 다시 쓰면
        #        되풀이 검사가 건너뛰었다 → 사용자 말(가린 뒤)과 다시 쓴 문장을 함께 본다
        self._echo = (f"{said}\n{question}", "\n".join([source, *notes]))
        self._allowed = allowed
        self._extra = "\n".join([*notes, question, said, before])
        return kw, allowed, compares

    # 【10-27 CLI 주석】 CLI 미리 띄우기 — API 길에는 띄울 것이 없다
    # def warm(self) -> None:
    #     kw, _, _ = self._request("", [])
    #     llm.warm(stream=True, **kw)

    def write_stream(
        self, question: str, facts: list[Facts], said: str = "", before: str = ""
    ) -> Iterator[tuple[str, str]]:
        """흘려 보이기 — ("text", 조각)을 문장 · 줄 단위로 낸다. 검사에 걸리면 멈추고
        ("replace", 코드 기본 답). 끝나면 self.last 에 write() 와 같은 결과.

        【판단】 품질은 write() 와 같다: 같은 지시문 · 같은 검사이고,
               조각은 '지금까지 낸 글 + 새 조각'이 검사를 통과할 때만 낸다.
               다른 점은 검사에 걸렸을 때 그 앞 문장까지는 이미 보였다는 것뿐
               (화면은 replace 를 받으면 글 전체를 코드 기본 답으로 바꾼다).
        """
        if self.s.writer_mode == "lead" or any(f.style == "outlook" for f in facts):
            # 【판단】 lead 는 AI가 한 문장만 써서 흘려 보일 것이 거의 없다.
            #        취약 돌보미 판단도 AI는 두세 문장이고, 그 글에서 목록 줄을 걸러 낸 뒤 근거를
            #        붙여야
            #        해서(10-20 페르소나: AI가 목록을 스스로 쓰고 코드가 또 붙여 두 벌) 한 번에 낸다
            yield ("text", self.write(question, facts, said, before))
            return
        # 【판단】 10-15: 전에는 여기서 said 를 빼고 불러 사용자 숫자 되풀이 검사가 반쪽이었다
        kw, allowed, compares = self._request(question, facts, said, before)
        key = self.cache.key("writer", llm.BACKEND, kw)
        if (hit := self.cache.get(key)) is not None:
            self.last = hit
            yield ("text", hit.text)
            return
        gate = StreamGate(allowed, compares, self._echo)
        meta: dict = {}
        try:
            for delta in llm.stream_text(self.s.anthropic_api_key, self.usage, meta=meta, **kw):
                for seg in gate.feed(delta):
                    yield ("text", seg)
                if not gate.ok:
                    break
            if meta.get("stop") == "max_tokens":
                # 【판단】 한도에 닿아 잘린 글은 다 쓴 답처럼 내보내지 않는다(10-15 재생 '빈 답')
                gate.ok, gate.problems = False, ["잘림(max_tokens)"]
            for seg in gate.flush():
                yield ("text", seg)
        except llm.CreditExhausted:
            raise
        except llm.LLMError:
            gate.ok, gate.problems = False, ["AI 오류"]
        text = gate.shown.strip()
        cited = _FID.findall(gate.basis) if gate.basis else None
        risky = bool(WRITE_OK.search(said or question)) and checks.yes_to_risky_wording(
            text, said or question
        )
        agree = checks.yes_then_no(text, said or question)
        other = misattributed(text, cited, self._ids, self._extra) if gate.ok else []
        if gate.ok and text and not risky and not agree and not other:
            self.last = WriteResult(text, True, [], cited)
            self.cache.put(key, self.last)
            return
        found = (
            gate.problems
            or other
            or (["허락으로 읽힘"] if risky else ["동의로 읽힘"] if agree else ["빈 답"])
        )
        if found != ["AI 오류"]:
            new, left = self._retry(kw, text, found, facts)
            if new and not left:
                self.last = WriteResult(new, True, [], self._cited)
                self.cache.put(key, self.last)
                yield ("replace" if gate.shown else "text", new)
                return
            found = left or found
        self.last = WriteResult(short_answer(facts, f"{said} {question}"), False, found)
        yield ("replace" if gate.shown else "text", self.last.text)

    def _retry(
        self, kw: dict, text: str, found: list[str], facts: list[Facts]
    ) -> tuple[str, list[str]]:
        """검사에 걸린 답을 한 번만 다시 쓰게 한다(FIX_WORD 위 판단). → (새 글, 남은 문제)."""
        allowed = self._allowed
        compares = [c for f in facts for c in f.compares]
        again = dict(kw)
        again["messages"] = [
            *kw["messages"],
            {"role": "assistant", "content": text or "(빈 답)"},
            {"role": "user", "content": fix_note(found) + "\n위를 고쳐 같은 질문에 다시 답한다."},
        ]
        try:
            r = llm.call(self.s.anthropic_api_key, self.usage, **again)
            new = clean("".join(b.text for b in r.content if b.type == "text").strip())
            new, self._cited = split_basis(new)
            if getattr(r, "stop_reason", None) == "max_tokens":
                return new, ["잘림(max_tokens)"]
        except llm.CreditExhausted:
            raise
        except llm.LLMError:
            return "", ["AI 오류"]
        left = (
            checks.problems(new, allowed, compares, facts_text=self._echo[1]) if new else ["빈 답"]
        )
        if checks.asks_if_unknown(self._echo[0]):
            left = [x for x in left if not x.startswith("없다고만 함")]
        left += [f"사용자 숫자 되풀이 {n}" for n in checks.echoed_counts(new, *self._echo)]
        said = self._echo[0]
        if WRITE_OK.search(said) and checks.yes_to_risky_wording(new, said):
            left.append("허락으로 읽힘")
        if checks.yes_then_no(new, said):
            left.append("동의로 읽힘")
        left += misattributed(new, self._cited, self._ids, self._extra)
        if any(f.style == "outlook" for f in facts):
            new = outlook_text.strip_lists(new)
            left += outlook_text.claims(new, facts)
        return new, left

    def write(self, question: str, facts: list[Facts], said: str = "", before: str = "") -> str:
        outlook = any(f.style == "outlook" for f in facts)
        lead = self.s.writer_mode == "lead" and not outlook
        kw, allowed, compares = self._request(question, facts, said, before)
        key = self.cache.key("writer", llm.BACKEND, kw)
        if (hit := self.cache.get(key)) is not None:
            self.last = hit
            return hit.text
        cut = False
        cited: list[str] | None = None
        try:
            r = llm.call(self.s.anthropic_api_key, self.usage, **kw)
            text = "".join(b.text for b in r.content if b.type == "text").strip()
            text, cited = split_basis(clean(text))
            cut = getattr(r, "stop_reason", None) == "max_tokens"
        except llm.CreditExhausted:
            raise
        except llm.LLMError:
            text = ""
        if cut:
            found = ["잘림(max_tokens)"]
        else:
            found = (
                checks.problems(text, allowed, compares, facts_text=self._echo[1])
                if text
                else ["빈 답"]
            )
            if checks.asks_if_unknown(said or question):
                found = [x for x in found if not x.startswith("없다고만 함")]
        found += [f"사용자 숫자 되풀이 {n}" for n in checks.echoed_counts(text, *self._echo)]
        if WRITE_OK.search(said or question) and checks.yes_to_risky_wording(
            text, said or question
        ):
            found.append("허락으로 읽힘")
        if text and checks.yes_then_no(text, said or question):
            found.append("동의로 읽힘")
        if not cut:
            found += misattributed(text, cited, self._ids, self._extra)
        if outlook:
            text = outlook_text.strip_lists(text)
            found += outlook_text.claims(text, facts)
        if found and found != ["AI 오류"]:
            text, found = self._retry(kw, text, found, facts)
            cited = self._cited
        if outlook:
            tail = outlook_text.render(facts, said or question, before)
            if found or not text:
                head = outlook_text.verdicts(facts)
                self.last = WriteResult(_join(head, tail), False, found or ["빈 답"])
            else:
                self.last = WriteResult(_join(text, tail), True, [], cited)
                self.cache.put(key, self.last)
            return self.last.text
        if found:
            self.last = WriteResult(short_answer(facts, f"{said} {question}"), False, found)
        elif lead:
            # 【판단】 숫자 줄은 AI가 다시 쓰지 않는다 — 사서가 만든 그대로 붙인다
            first = text.splitlines()[0].strip()
            self.last = WriteResult(first + "\n" + template_answer(facts), True, [])
        else:
            self.last = WriteResult(text, True, [], cited)
            self.cache.put(key, self.last)
        return self.last.text
