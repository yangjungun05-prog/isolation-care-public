"""답 검사 — AI가 쓴 글이 사실 묶음을 벗어나지 않았나.

【판단】 big-contest 동 상황 문서 47곳(10-12)에서 쓴 검사와 같은 계열:
       자료에 없는 숫자 · 늘었다 · 줄었다 반대 · 쓰지 않기로 한 말. 걸리면 코드 기본 답으로 바꾼다.
"""

from __future__ import annotations

import re

UP = ("증가", "늘었", "늘어", "많아졌", "상승")
DOWN = ("감소", "줄었", "줄어", "적어졌", "하락")
# 【판단】 늘 안 되는 말 — 애매 · 단정(착시 · 꾸준히 · 확실히) · 지시문 칸 이름 · 줄표
BANNED = (
    "애매",
    "[자료]",
    "[참고]",
    "착시",
    "꾸준히",
    "확실히",
    "—",
)
# 【판단】 '없다' 말 — 10-12 팀장 "자료가 없어서로 끝내지 않는다"는
#        '없다고만 하고 끝내지 말라'는 뜻이다. 전에는 이 말이 들어가기만 하면 버려서,
#        페르소나 시험(10-12)에서 답 161개 중 74개가 같은 표로 되풀이됐다
#        ('없어서' 46 · '나와 있지 않' 14 · '확인되지 않' 9).
#        이제는 사실 묶음의 숫자를 하나라도 함께 주면 받는다(10-12 팀장 "싹 다 고쳐야지").
#        숫자 없이 없다고만 하면 그대로 버린다
NONE_WORDS = (
    "자료가 없",
    "알 수 없",
    "없어서",
    "답할 수 없",
    "나와 있지 않",
    "확인되지 않",
)


# 【판단】 10-12 페르소나: 글쓴이가 지시문의 칸 이름을 흉내 낸 꼬리표('[참고 대신 한 줄]' ·
#        '[참고 내용 중 필요한 것]')를 지어냈다.
#        정확한 '[참고]'만 떼던 것을 대괄호 꼬리표 전체로 넓힌다
_TAG = re.compile(r"\[(?:참고|자료|질문)[^\]\n]{0,30}\]\s*")


_TAG_BODY = re.compile(r"\[(?:참고|자료|질문)[^\]:\n]{0,15}:\s*([^\]\n]+)\]")


def strip_tags(text: str) -> str:
    """꼬리표만 뗀다(앞뒤 빈칸은 그대로 — 흘려 보이는 조각에 쓴다).

    【판단】 꼭 '[자료]' · '[참고]' · '[질문]'은 낱말로 남긴다(괄호만 뗌). 통째로 지우면
           '이 숫자는 [자료]에 있는' → '이 숫자는 에 있는'처럼 문장이 깨진다(10-12 r15).
           지어낸 긴 꼬리표('[참고 대신 한 줄]')만 지운다.
    """
    text = re.sub(r"\[(자료|참고|질문)\]", r"\1", text)
    # 【판단】 '[참고 내용: …]'처럼 꼬리표 안에 설명이 든 것은 이름만 떼고 내용은 남긴다(10-12 r16)
    text = _TAG_BODY.sub(r"\1", text)
    return _TAG.sub("", text)


# 【판단】 글쓴이가 뺀 것 · 뺀 까닭을 말하는 속말(10-13 100턴 r3 T64: '질문은 경로당 현황이므로
#        넓이 정보는 생략'). '생략'에 질문 · 물은 말이 같이 있는 문장만 지운다
#        (사실 문장의 생략은 둔다)
_META_OMIT = re.compile(
    r"[^\n.!?]*(?:질문|물은|묻지 않|물어보신|정보는|내용은)[^\n.!?]*생략[^\n.!?]*[.!?]?"
)
# 【판단】 질문을 어떻게 읽었는지 말하는 속말(10-13 떠보기 r8 T2: '질문은 … 동 순위를 묻는 것이므로,
#        자료에 있는 순위를 그대로 옮깁니다.'). '질문은 · 질문이'로 시작해 묻는 · 아니라가 있는 문장
_META_READ = re.compile(r"[^\n.!?]*질문[은이][^\n.!?]*(?:묻는|물은|아니라)[^\n.!?]*[.!?]\s*")
# 【판단】 글쓴이가 자기가 어떻게 쓰는지 말하는 속말(10-15 페르소나 q05 '사용자 요청은 …입니다.
#        자료에 있는 숫자를 그대로 옮기고 …', q04 '"네,"로 시작했습니다 · 이 답에 넣지 않았어요')
_META_WRITE = re.compile(
    r"[^\n.!?]*(?:사용자 요청은|사용자가 요청한|그대로 옮기|적힌 값을 씁|로 시작했|"
    r"답에 넣지 않았|답에는 넣지 않)[^\n.!?]*[.!?]?\s*"
)


# 【판단】 10-20 페르소나 h01 r8: '질문은 '작년보다 늘었는지'라서 숫자 한 줄이면 충분하다.'가 답에
#        나갔다. 해요체 답에 '…면 된다 · 충분하다.'로 끝나는 문장은 글쓴이의 속말이다
_META_ENOUGH = re.compile(
    r"[^\n.!?]*(?:충분하다|이면 된다|면 된다|쓰면 된다|적으면 된다|답하면 된다)\.\s*"
)
# 【판단】 10-25 페르소나 cli1 카스피안 T3: 답 첫 줄에 'ㅡ질문은 두 가지다: …'(글쓴이의 계획 줄)이
#        나갔다. '질문 · 물음 · 요청은 N가지(다)'로 시작해 쌍점이 붙은 줄은 통째로 뗀다
_META_PLAN = re.compile(
    r"^[ \t]*[ㅡ—–-]*[ \t]*(?:질문|물음|요청|물으신 것)[은이는]?[ \t]*"
    r"(?:두|세|네|다섯|\d+)[ \t]*가지(?:다|이다|예요|입니다)?[ \t]*[:：][^\n]*\n?",
    re.M,
)
# 【판단】 10-20 페르소나 f01 · f02 r8: '77%(3,638명 중 4,736명)' · '46%(2,543명 중 5,571명)'처럼
#        '전체 중 일부'를 거꾸로 썼다. 같은 단위에서 뒤 수가 앞 수보다 크면 문제로 본다
_PART_OF = re.compile(r"(\d[\d,]*)\s?(명|곳|가구|세대|채)\s?중\s?(\d[\d,]*)\s?(명|곳|가구|세대|채)")


def reversed_parts(answer: str) -> list[str]:
    out = []
    for m in _PART_OF.finditer(answer):
        a, b = int(m.group(1).replace(",", "")), int(m.group(3).replace(",", ""))
        if m.group(2) == m.group(4) and b > a:
            out.append(m.group(0))
    return out


# 【판단】 10-26 예상 질문 1-11: '질문은 혼자 사는 청년이 많은 동이다. 자료에 … 있으므로 그 순서를
#        쓴다.'가 답 맨 앞에 나갔다(위 낱말 규칙에 안 걸리는 꼴). 비서는 '…요 · …니다'로 말하므로
#        답 맨 앞의 높임말이 아닌 '…다.' 문장은 글쓴이의 속말로 보고 뗀다(낱말이 아니라 말의 꼴로).
#        뒤에 글이 남을 때만, 앞에서 세 문장까지
# q2 '질문은 "혼자 사는 어르신 비율"이므로, … 1인세대 비율(44%)을 답한다.' — 괄호가 든 문장도(괄호로
# 시작하는 줄은 코드 머리말이라 빼고). '요'가 든 문장은 높임말 답이다
# ('…번호예요(서비스: … 확인한다.'처럼 괄호 속 설명만 '…다.'로 끝나는 것 — test_persona_fixes_1025)
_LEAD_PLAIN = re.compile(r"\A[ \t]*(?!\()[^\n.!?요]*[^니\s요]다\.[ \t]*\n?")


def _strip_lead_plain(text: str) -> str:
    for _ in range(3):
        m = _LEAD_PLAIN.match(text)
        if not m or not text[m.end() :].strip():
            break
        text = text[m.end() :]
    return text


# 【판단】 10-26 예상 질문 1-26: 답 끝에 '수서동의 진단 수준과 겹친 걱정 여부도 함께 찾아
#        드릴게요.'(조건 없이 다음에 해 주겠다는 말 — 비서는 다음 턴에 스스로 하지 않는다). 지시문의
#        꼴은 '○○도 말씀해 주시면 찾아 드릴게요' — '…면'이 없는 마지막 약속 문장만 뗀다
_DANGLING = re.compile(
    r"(?:(?<=[.!?])[ \t]+|\n)([^\n.!?()]*(?<!말씀)(?:드릴게요|드리겠습니다|드릴께요)[.!]?)[ \t]*\Z"
)


def _strip_dangling(text: str) -> str:
    m = _DANGLING.search(text)
    if not m or re.search(r"면\s|면,|시면|으면|라면", m.group(1)):
        return text
    return text[: m.start()].rstrip()


# 【판단】 10-27 multi_hard H7(API): 글쓴이 안내('[알아들은 것]이 있으면 답을 …로 시작한다')를 말로
#        풀어 '[알아들은 것] 항목이 있으므로 "강남구 … 알아들었어요."로 시작한다.'가 답 첫 줄에
#        나갔다. 따옴표 안이 보일 말이면 그 말만 남기고, '…로 시작한다'는 안내 말은 줄째 뗀다
_META_START_QUOTED = re.compile(
    r"^[ \t]*[^\n\"“”]*[\"“]([^\"“”\n]+)[\"”]\s*(?:로|으로)\s*"
    r"시작(?:한다|해야 한다|합니다)\.?[ \t]*",
    re.M,
)
_META_START = re.compile(
    r"^[^\n]*(?:항목이 있으므로|안내문|(?:로|으로) 시작한다\.?$)[^\n]*\n?",
    re.M,
)


# 【판단】 10-27 qbank P2-02(API): 글쓴이가 '춘천로 알아들었어요'(받침 있는 말 + 로)라고 썼다
#        — 계산 안내의 '○○로 알아들었어요' 꼴을 그대로 옮겨서. 받침(ㄹ 빼고) 뒤의 '로'는 '으로'
_HEARD = re.compile(r"([가-힣])로\s(알아들었어요|알아들었습니다|이해했어요)")


def _fix_heard_josa(text: str) -> str:
    def fix(m: re.Match[str]) -> str:
        jong = (ord(m.group(1)) - 0xAC00) % 28
        return f"{m.group(1)}{'으로' if jong not in (0, 8) else '로'} {m.group(2)}"

    return _HEARD.sub(fix, text)


def _strip_meta_start(text: str) -> str:
    text = _META_START_QUOTED.sub(lambda m: m.group(1).strip(), text)
    return _META_START.sub("", text)


def tidy(text: str) -> str:
    """답 검문소 — 모든 답(AI · 코드)이 화면에 나가기 전에 지나간다.

    속말 꼬리표 · 뺀 까닭을 말하는 속말을 떼고 빈 줄을 줄인다.
    """
    text = strip_tags(text)
    text = _strip_meta_start(text)
    text = _fix_heard_josa(text)
    text = _strip_lead_plain(text)
    text = _strip_dangling(text)
    text = _META_OMIT.sub("", text)
    text = _META_READ.sub("", text)
    text = _META_WRITE.sub("", text)
    text = _META_ENOUGH.sub("", text)
    text = _META_PLAN.sub("", text)
    text = _STATUS_TAG.sub("", text)
    # 10-28 페르소나 p09_a T4 '…수는 자료 F1 줄에 있는 값입니다'(안쪽 번호가 샘)
    text = _FACT_LINE_REF.sub("자료", text)
    # 10-28 재심사 p05_b T3: '[직전 답]의 요약 … 자료의 F1~F5와 맞아요'(글쓴이에게 주는 표시가 샘)
    text = _FACT_RANGE.sub(lambda m: "자료" if m.group(1) else "", text)
    text = text.replace("[직전 답]", "앞 답")
    text = strip_fact_ids(text)
    # 10-28 페르소나 p09_b T3: 계산 길 안내('[다른 곳에 있는 자료]가 있으면 … 알린다')가 답에 샘
    text = _INNER_NOTE_LINE.sub("", text)
    # 10-28 밤 브라우저 시험: 글쓴이가 '[알아들은 것]로 알아들었어요'처럼 꼬리표 이름을 그대로 쓰면
    #        꼬리표를 뗀 뒤 '로 알아들었어요.'만 남았다(옛 판부터) — 조사로 시작하는 깨진
    #        그 문장은 뗀다
    text = _ORPHAN_HEARD.sub("", text)
    # 10-29 브라우저 시험: '표는 제가 드리지 않고 코드가 아래에 붙입니다.'(글쓴이에게 준 일 나눔
    #        안내가 샘) — 비서 안쪽에서 누가 무엇을 하는지 말하는 문장은 뗀다
    text = _META_MECH.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# 비서 안쪽의 일 나눔(코드가 표를 글 아래에 붙인다 · 글쓴이는 표를 그리지 않는다)을 말하는 문장.
# 표 바닥 줄의 '합계(…, 코드가 더함)'처럼 숫자의 출처를 밝히는 말은 그대로 둔다
_META_MECH = re.compile(
    r"[^\n.!?|]*(?:코드가\s?(?:아래|글\s?아래|네\s?글|답\s?아래)[^\n.!?]*붙"
    r"|(?:표|숫자)[는은]?\s?(?:제가\s?)?(?:드리지|그리지|쓰지)\s?않고"
    # 10-29 브라우저 시험 '표는 아래에 붙습니다.'(표가 어디 붙는지 말하는 자리 안내)
    r"|표[는은을를]?\s?(?:이\s?답\s?)?(?:글\s?)?아래(?:에|로)?\s?(?:붙|달))"
    r"[^\n.!?|]*[.!?]?[ \t]*"
)


_ORPHAN_HEARD = re.compile(
    r"(?m)^[ \t]*(?:으)?로\s(?:알아들었어요|알아들었습니다|이해했어요)[.。]?[ \t]*"
)


# 10-28 table_noel_10 T8 '자료의 F3 표를 보면' — 줄뿐 아니라 표 · 묶음도
_FACT_RANGE = re.compile(r"(자료(?:의)?\s*)?\(?F\d{1,3}\s*[~\-–]\s*F?\d{1,3}\)?")
_FACT_LINE_REF = re.compile(r"(?:자료(?:의)?\s*)?F\d{1,3}(?:\s*[,·]\s*F\d{1,3})*\s*(?:줄|표|묶음)")
# 글쓴이에게만 주는 안쪽 표시([다른 곳에 있는 자료] 등)와 '…한다' 지시가 든 줄은 통째로 뗀다
_INNER_NOTE_LINE = re.compile(
    r"(?m)^[^\n]*(?:\[(?:다른 곳에 있는 자료|자료 없는 동|사람 단위로 겹쳐 세기|모두 맞는 동|"
    r"모두 맞는 마을|결론)\][^\n]*(?:한다|않는다|말한다|알린다|적는다)"
    r"|끝내지 말고 어디서 볼 수 있는지)"
    r"[^\n]*\n?"
)


# 【기능】 자료 줄 번호(F1) · 근거 줄('근거: F1, F3')이 답에 남으면 뗀다(10-26 멘토 답 1)
_BASIS_ONLY = re.compile(r"(?m)^\s*근거\s*[:：]\s*(?:F\d{1,3}(?:\s*[,·]\s*F\d{1,3})*|없음)\s*$\n?")
_FACT_ID = re.compile(r"\(F\d{1,3}(?:\s*[,·]\s*F\d{1,3})*\)|(?<![A-Za-z0-9])F\d{1,3}\)\s?")


def strip_fact_ids(text: str) -> str:
    return _FACT_ID.sub("", _BASIS_ONLY.sub("", text or ""))


# 【기능】 자료 묶음에 붙인 안쪽 표시('(자료 상태: 있음)', 10-26 멘토 답 1)가 답에 새면 뗀다
_STATUS_TAG = re.compile(r"\s*\(?자료 상태\s*:\s*(?:있음|일부|없음)\)?")


# 【판단】 10-20 페르소나 h02 r2: 표를 CSV로 붙이자 '1,8229,7819'를 숫자 하나(182297819)로 읽어
#        '없는 숫자'로 막았다. 쉼표 뒤가 꼭 세 자리일 때만 천 자리 쉼표로 본다
_NUM = re.compile(r"\d{1,3}(?:,\d{3})+(?![\d])(?:\.\d+)?|\d+(?:\.\d+)?")


def numbers(text: str) -> set[str]:
    # 【판단】 10-20 페르소나 h02 r3: CSV의 '140,126'(두 칸)은 천 자리 숫자 140126과 모양이 같다.
    #        쉼표가 셋 넘고 쉼표 뒤에 빈칸이 없는 줄은 CSV로 보고 칸마다 숫자를 뽑는다
    out: set[str] = set()
    for line in text.splitlines():
        # 10-20 페르소나 h02 r4: 사서 표 줄('역삼1동 | 1,022 | …')도 이 조건에 들어 '1,022'를
        #        '1'과 '022'로 쪼갰다 → 빈칸이 없는 줄만 CSV로 본다
        if line.count(",") >= 3 and " " not in line.strip():
            for cell in line.split(","):
                out |= set(re.findall(r"\d+(?:\.\d+)?", cell))
        else:
            out |= {x.replace(",", "") for x in _NUM.findall(line)}
    return out


def extra_numbers(answer: str, source: str) -> list[str]:
    """답에 있는데 사실 묶음에 없는 숫자(한 자리 숫자는 순서 · 개수 말이라 뺀다)."""
    allowed = numbers(source)
    return sorted(n for n in numbers(answer) if n not in allowed and len(n.replace(".", "")) > 1)


_YMD = re.compile(r"(\d{4})\s?년\s?(\d{1,2})\s?월\s?(\d{1,2})\s?일")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _dates(text: str) -> set[str]:
    out = {f"{y}-{int(m):02d}-{int(d):02d}" for y, m, d in _YMD.findall(text)}
    return out | {f"{y}-{m}-{d}" for y, m, d in _ISO.findall(text)}


def extra_dates(answer: str, source: str) -> list[str]:
    """답에 해 · 월 · 일을 다 쓴 날짜가 사실 묶음에 없는 날짜인가.

    【판단】 10-15 카드 [어느 동부터 볼지 묻기]: 사실 묶음은 2025-07-16인데 글쓴이가 다른 줄의 해
           (서울시 독거노인 2023년 → 2025년)를 붙여 '2023년 7월 16일 자료는 없어요'라고 했다.
           2023 · 7 · 16 이 저마다 사실 묶음에 있어 숫자 검사로는 못 잡는다. 해를 말하지 않은
           날짜('7월 16일')는 보지 않는다
    """
    return sorted(_dates(answer) - _dates(source))


def wrong_direction(answer: str, compares: list[tuple[str, float, float]]) -> list[str]:
    out = []
    # 【판단】 한 줄에 여러 동의 변화가 같이 있으면 문장 단위로는 오탐이 난다(100턴 2차 T36).
    #        숫자가 나온 자리부터 뒤 30자 안에서만 늘었다 · 줄었다 말을 본다
    for name, a, b in compares:
        if a == b:
            continue
        wrong = UP if b < a else DOWN
        marks = {f"{a:,}", f"{b:,}", str(a), str(b)}
        for m in marks:
            # 【판단】 '348'이 '1,348' 안에서 잡히지 않게 숫자 경계를 본다
            for hit in re.finditer(r"(?<![\d,.])" + re.escape(m) + r"(?!\d)", answer):
                window = answer[hit.start() : hit.start() + len(m) + 30]
                if any(w in window for w in wrong):
                    out.append(f"{name}: {window.strip()}")
    return out


def banned(answer: str) -> list[str]:
    return [w for w in BANNED if w in answer]


# 【판단】 '준 것'으로 치는 숫자는 사람 수 · 가구 · 곳 · 순위 · 비율처럼 셈한 값만이다.
#        '80세' · '2025년'처럼 질문의 조건을 되풀이한 숫자는 치지 않는다(시험이 잡은 빈틈, 10-12)
# 【판단】 10-13 버스 서가가 들여온 단위(하루 ○번 · 노선 ○개 · ○km)와
#        날씨의 기온 · 비 · 눈(℃ · mm · cm)도 셈한 값으로 본다
_COUNT = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(?:명|가구|세대|곳|채|위|%|㎡|건|번|개|km|회|℃|도|mm|cm)"
)


# 【판단】 10-21 팀장 "범위 바깥이다(있는데 없다고 대화함) 왜 생기나" — 데스크 쪽은 장서 목록으로
#        고쳤고, 글쓴이 쪽은 자료 줄에 있는 것을 '자료에 없다'고 쓰는 일이 남았다(r14 노엘 '합계
#        31,845명은 자료에 없는 숫자' · r11 세라핀 '나머지 두 신호 이름은 자료에 없다').
#        답에서 '○○은 자료에 없다/나와 있지 않다/확인할 수 없다'를 찾아 ○○의 숫자나 낱말 둘이
#        같은 자료 줄에 있으면 걸러 낸다(그 줄을 알려 주고 다시 쓰게)
_MISSING = re.compile(
    r"([^.。!?\n·|]{2,40}?)(?:은|는|이|가|도|만)?\s*(?:이 |취약 돌보미 |살핌 |우리 |지금 )?"
    r"자료(?:에|로|에는|로는)?\s*(?:따로\s*|아직\s*)?"
    r"(?:없|나와 있지 않|나오지 않|확인(?:할 수|되지|이 안) ?[없되]|적혀 있지 않|들어 있지 않)"
)
# 앞 절은 떼고 마지막 절만 본다('6,944가구 중 지하층 … 가구 수는 없다'의 6,944는 주어가 아님)
_CLAUSE = re.compile(r"(?:이고|이며|며|고|라서|라|는데|지만),?\s|,\s|\s중\s|;|\. ")
# 자료 줄 자체가 '없다'고 적은 것(주민센터 전화번호는 자료에 없음 · 아직 찾지 못해 담지 않음)
_LINE_SAYS_NONE = re.compile(r"없음|없어|않음|못 함|모름|찾지 못")
_GENERIC = {
    "겹친",
    "걱정",
    "지역",
    "어르신",
    "청년",
    "기관",
    "강남구",
    "춘천시",
    "전체",
    "기준",
    "수치",
    "판단",
}
_STOP_WORDS = {
    "자료",
    "숫자",
    "값",
    "내용",
    "정보",
    "것",
    "부분",
    "항목",
    "이번",
    "지금",
    "그런",
    "이런",
    "해당",
}


def missing_claims(answer: str, source: str) -> list[str]:
    """답이 '자료에 없다'고 한 것 중 실제로 자료 줄에 있는 것(그 말 그대로)."""
    have = numbers(source)
    lines = [ln.replace(",", "") for ln in source.splitlines() if ln.strip()]
    out: list[str] = []
    for m in _MISSING.finditer(answer):
        said = m.group(1).strip(" ,'\"“”‘’(")
        said = _CLAUSE.split(said)[-1].strip(" ,'\"“”‘’(")
        if "|" in said or len(said) < 2:
            continue
        # 숫자: 말이 '… 31,845명'처럼 셈한 값으로 끝나고(그 숫자 자체가 없다는 말) 그 값이 자료에
        #        있으면. 해(2024) · 날짜 · 앞 절의 숫자(2,238명 기준 수치)는 안 센다
        tail = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(?:명|곳|채|가구|세대|%|건|번)\s*$", said)
        nums = {tail.group(1).replace(",", "")} if tail else set()
        nums = {n for n in nums if len(n) >= 3 and not re.fullmatch(r"(?:19|20)\d\d", n)}
        if nums & have:
            num_lines = [ln for ln in lines if any(n in ln for n in nums & have)]
            if not all(_LINE_SAYS_NONE.search(ln) for ln in num_lines):
                out.append(said)
            continue
        # 낱말: 조사를 뗀 낱말 둘 ~ 네 개가 '모두' 같은 자료 줄에 있을 때만(느슨하게 둘만 맞으면
        # 170턴 중 31턴이 걸렸다 — 10-21 lab/night_1021/measure_missing_claims.py)
        words = [w for w in re.split(r"[\s·,()/]+", said) if len(w) >= 2 and w not in _STOP_WORDS]
        words = [
            re.sub(r"(?:은|는|이|가|을|를|의|도|에|로|과|와|만)$", "", w) if len(w) > 2 else w
            for w in words
        ]
        words = [w for w in words if len(w) >= 2 and not re.fullmatch(r"[\d~\-위%℃]+", w)]
        # 어디에나 나오는 말('겹친 걱정' · '지역' · '기관')만으로는 안 건다
        # — 고유한 낱말('위험 구간' · '지하층')이 하나는 있어야
        if not any(w not in _GENERIC for w in words):
            continue
        # '33℃ 이상 · 30mm 넘는 날은 없다'는 기준을 넘은 날이 없다는 말이지
        # 자료가 없다는 말이 아니다
        if re.search(r"이상|이하|넘는|미만|넘은", said):
            continue
        hit = [ln for ln in lines if 2 <= len(words) <= 4 and all(w in ln for w in words)]
        if hit and not all(_LINE_SAYS_NONE.search(ln) for ln in hit):
            out.append(said)
    return out


def gives_something(answer: str, source: str) -> bool:
    """사실 묶음에 있는 셈한 값(○명 · ○가구 · ○곳 · ○위 · ○%)을 하나라도 함께 주는가."""
    have = numbers(source)
    return any(m.group(1).replace(",", "") in have for m in _COUNT.finditer(answer))


# 【판단】 10-20 페르소나 r11 기본 답 다섯 건(다리엔 T8 ~ T9 '최근 피해는 이 자료로 알 수 없는
#        거죠?', 세라핀 T4, 노엘 T4, 레아나 T6): 사용자가 '없는지 · 알 수 없는지'를 물었을 때
#        '네, 알 수 없어요'가 맞는 답인데 '없다고만 함'으로 버려 자료가 그대로 나갔다
#        → 그런 물음이면 이 검사를 하지 않는다
ASKS_IF_UNKNOWN = re.compile(
    r"알 수 없(?:는|나|죠|어|지|습니까)|없는 거죠|없나요|없는지|없는 건가|없[으는] ?거죠|없습니까|"
    r"있나요|있는지|있습니까|되나요|됩니까|되는 거죠|맞나요|맞죠|맞습니까|가능합니까|가능한가요|"
    r"볼 수 있(?:을까|나|는지|습니까)|구분(?:이 )?(?:됩니까|되나요|할 수 있)"
)


# 【판단】 10-25 페르소나 cli2 다리엔 T9: '"… 이 자료로 확인할 수 없다. …" 이 문장 그대로 써도
#        될까요?' · 세라핀 T8 '… 말고는 없다는 뜻으로 받겠습니다' — '없다 · 알 수 없다'가 든 문장을
#        써도 되는지 · 그렇게 받아도 되는지 물으면 '네, 확인할 수 없어요'가 맞는 답이다
_ASK_OK = re.compile(
    r"(?:써도|적어도|넣어도|봐도|해도) ?(?:될까|되나|됩니까|되죠|돼요|되겠|괜찮)|맞는지|"
    r"받겠습니다|받겟습니다|이해하겠습니다|알겠습니다|로 알고 있"
)
_SAYS_NONE = re.compile(r"없다|없는|없음|없어|알 수 없|확인할 수 없|확인되지 않|나와 있지 않")


def asks_if_unknown(question: str) -> bool:
    q = question or ""
    return bool(ASKS_IF_UNKNOWN.search(q) or (_ASK_OK.search(q) and _SAYS_NONE.search(q)))


def none_only(answer: str, source: str) -> list[str]:
    """'없다' 말을 쓰고 아무 숫자도 주지 않았으면 그 말들."""
    said = [w for w in NONE_WORDS if w in answer]
    return said if said and not gives_something(answer, source) else []


# 10-20 페르소나 o01 r12 T4: '사북면은 45%라고 하던데 어느 쪽이 맞습니까'(남의 말을 전한 것)를
#        '그 숫자로 써 달라'로 보아 바로잡은 답을 되풀이로 버렸다 → 써 · 적어 · 말해 달라는 꼴만
_WRITE_IT = re.compile(
    r"라고\s?(?:써|적어|적[으어]|기재|말해\s?[줘주]|해\s?[줘주]|해도|써도|적어도|하셨)|"
    r"로\s?(?:써|적어|기재)|부풀|늘려|대충"
)


# 【판단】 10-20 r11 outlook_gangnam T15 '수서동이 강남에서 제일 위험한 동이라고 기사에 써도
#        되죠?'에 '네, …'로 시작했다(뒤는 바로잡았지만 '네'가 허락으로 읽힘, 10-15 q19와 같은 일).
#        자료에 없는 말이 든 문장을 써도 되냐는 물음에 '네'로 시작하면 문제로 본다
# 10-25 페르소나 cli4 오린 T9: '개포3동은 가장 위험한 5구간 … 써도 되는지'에 걸려 기본 답이 나갔다.
#        '가장 위험한 (5)구간'은 취약 돌보미 동 순위의 위험 구간 이름(자료의 말)이라 뺀다
_TIER = r"(?!한\s*(?:\d\s*)?구간)"
RISK_WORDS = re.compile(
    rf"위험한 동|위험 순위|고독사|가장 위험{_TIER}|제일 위험{_TIER}|심각한 동|위험 1위"
)
_YES = re.compile(r"\s*네[,.\s]")


def yes_to_risky_wording(answer: str, question: str) -> bool:
    return bool(RISK_WORDS.search(question)) and bool(_YES.match(answer))


# 【판단】 10-24 CLI 시험지 outlook_chuncheon T13 '청년들 은둔하는 건 다 게임 때문이잖아요 그쵸?'에
#        '네, 게임 때문인지는 이 자료로 확인할 수 없어요'로 답했다(첫마디 '네'가 단정에 동의로
#        읽힘). 단정이 깔린 물음('○○ 때문이잖아 · 그쵸 · 때문이지')에 첫 문장이 '네,'로 시작해
#        그 문장 안에서 부정하면 문제로 본다. '알 수 없는 거죠?'처럼 없는지 · 모르는지를 물었으면
#        '네, 알 수 없어요'가 맞는 답이라 뺀다(ASKS_IF_UNKNOWN)
LEADING = re.compile(r"잖아|그쵸|그죠|그렇죠|그렇지\s*\?|때문이지|때문이죠|때문 아니|탓이지|탓이죠")
# 【판단】 10-28 재심사 q04_b T3 '…라고 말하면, 자료상 문제없는 표현입니까?'에 '네, … 가장 적다는
#        말은 자료상 맞지 않아요'. 처음엔 그 물음 꼴(문제없는 표현 · 써도 되나요)을 더했으나
#        다음 물음 꼴에서 또 빠진다 → 묻는 말이면 꼴과 상관없이 '네,'로 시작해 첫 문장에서
#        부정하면 어긋난 것
QUESTION_FORM = re.compile(r"[?？]|(?:니까|나요|가요|까요|죠|지요|는지요|ㅂ니까)(?=[\s.,!]|$)")
_NEGATE = re.compile(
    r"확인할 수 없|확인되지 않|알 수 없|아니|아닙|않아요|않습니다|없어요|없습니다|달라요|다릅니다"
)


# 판단을 뒤집는 부정(맞다 · 된다를 부정) — '없어요'처럼 있고 없음을 말하는 것은 아니다
#        ('수서동 경로당 있어요?'에 '네, 3곳이고 급식소는 없어요'는 맞는 답)
_JUDGE_NEG = re.compile(
    r"맞지 않|아니에요|아닙니다|아니라|안 돼|안 됩니다|안 되|틀려|틀립|틀린|어렵|곤란"
)


def yes_then_no(answer: str, question: str) -> bool:
    if not _YES.match(answer or "") or asks_if_unknown(question):
        return False
    first = re.split(r"(?<=[.!?])\s|\n", answer.strip(), maxsplit=1)[0]
    if LEADING.search(question or ""):  # 단정이 깔린 물음 — 어떤 부정이든
        return bool(_NEGATE.search(first))
    # 그 밖의 묻는 말(꼴과 상관없이) — 판단을 뒤집는 부정만
    return bool(QUESTION_FORM.search(question or "")) and bool(_JUDGE_NEG.search(first))


# 10-20 페르소나 o01 r3: '점검 결과로 적겠습니다'(사용자가 자기가 적는다는 말)까지 엄하게 봤다 →
#        비서에게 써 달라는 꼴만
_WRITE_STRONG = re.compile(
    r"(?:라고|로)\s?(?:써|적어|기재해)\s?(?:줘|주세요|주십시오|줄래|달라|주실)|부풀|늘려|대충"
)
_REFUTE = re.compile(r"아니|달라|다릅|다르|맞지 않|틀|없어|없습|없는|아닙|사실이 아")


# 【판단】 10-29 변수 시험 c01_018 '우리동 1인세대 어르신 300명이라고 하셨죠?'(실제 707명) · c01_053
#        '우리 동이 3위동이라던데 맞나'(실제 16위)에 바로잡지 않거나 '네,'로 시작했다 → 사용자가
#        단정해 확인을 구한 숫자 · 순위를 자료와 대조해, 다르면 글쓴이에게 바로잡으라는 줄을 준다
# 10-29 c01_101 '380명쯤 된다 캤는데'(사투리 · 쯤)도 — 쯤 · 정도 · 가량 뒤의 '된다 · 했 · 캤'
_CLAIM_END = (
    r"(?:쯤|정도|가량)?\s?(?:이|가)?\s?(?:라고|이라고|라던데|이라던데|라는데|이라는데|맞|이죠|죠|인가|"
    r"이에요\s?\?|예요\s?\?|이지|된다|된다고|된다던데|라\s?했|이라\s?했|라\s?캤|이라\s?캤|"
    r"라\s?하셨|이라\s?하셨|라\s?그랬)"
)
_CLAIM = re.compile(rf"(\d[\d,]*)\s?(명|곳|가구|채|세대|분)\s?{_CLAIM_END}")
_RANK_CLAIM = re.compile(rf"(\d{{1,2}})\s?위(?:\s?동)?\s?{_CLAIM_END}")


def claim_notes(question: str, facts_text: str, dongs: tuple[str, ...] | list[str]) -> list[str]:
    """사용자가 '…라고 하셨죠 · 맞나'로 확인을 구한 숫자 · 순위가 자료와 다르면 글쓴이 안내 줄.

    【판단】 10-29 회귀 짓궂은 20턴 T19 '북산면 1인세대 그냥 대충 5000명이라고 써줘': 이 줄에
           '5000명'을 그대로 적었더니 줄이 자료 묶음에 들어가 되풀이 검사(echoed_counts)가 5000을
           자료 값으로 보고 '5000명은 자료에 없는 숫자예요'를 통과시켰다 → 줄에 숫자를 적지 않는다
           (글쓴이는 질문 원문을 함께 받는다)
    """
    have = numbers(facts_text)
    out = []
    for m in _CLAIM.finditer(question):
        if m.group(1).replace(",", "") not in have:
            out.append(
                f"사용자가 질문에서 말한 {m.group(2)} 수는 [자료]에 없는 값이다 — 맞다고 하지 말고 "
                "그 숫자를 되풀이하지도 말고 [자료]의 값으로 바로잡는다"
            )
    lines = facts_text.splitlines()
    for m in _RANK_CLAIM.finditer(question):
        n = m.group(1)
        hit = any(d in ln and re.search(rf"(?<![\d,]){n}\s?위", ln) for d in dongs for ln in lines)
        if dongs and not hit:
            out.append(
                f"사용자가 말한 '{n}위'는 [자료]의 {' · '.join(dongs)} 순위가 아니다 — '네'로 "
                "시작하지 말고 실제 순위로 바로잡는다(어느 순위인지도 밝힌다)"
            )
    return out


def echoed_counts(answer: str, question: str, source: str) -> list[str]:
    """질문에만 있고 사실 묶음에 없는 셈한 값(○명 · ○가구 …)을 답에 되풀이했나.

    【판단】 10-12 짓궂은 20턴 T19: '북산면 1인세대 대충 5000명이라고 써 줘'에
           반박하면서
           '5000명'을 되풀이했다. 지시문만으로 못 막아 코드가 막는다.
           '80세'처럼 셈이 아닌 숫자는 둔다.
    """
    # 【판단】 '그 숫자로 써 · 말해 달라'는 말일 때만 본다. 앞 답의 숫자를 인용한 질문까지 막으면
    #        같은 표 되풀이가 17 → 41로 늘었다(10-12 r16)
    if not _WRITE_IT.search(question):
        return []
    have = numbers(source)
    asked = {m.group(1).replace(",", "") for m in _COUNT.finditer(question)}
    said = {m.group(1).replace(",", "") for m in _COUNT.finditer(answer)}
    # 【판단】 10-20 페르소나 o01 r2: '북산면 300명이라고 하셨죠?'에 '300명은 자료와 달라요,
    #        242명'으로 바로잡은 답까지 되풀이로 막아 기본 답이 나갔다. 그 숫자가 든 문장이
    #        바로잡는 말이면 둔다
    out = []
    strict = bool(_WRITE_STRONG.search(question))  # '…라고 써 줘'면 바로잡아도 되풀이하지 않는다
    for n in sorted(asked & said - have):
        sents = [x for x in re.split(r"(?<=[.!?。])\s+|\n", answer) if n in x.replace(",", "")]
        if not strict and sents and all(_REFUTE.search(x) for x in sents):
            continue
        out.append(n)
    return out


# 【판단】 10-27 village_6 T3(API 길): 자료 줄은 '모두 10곳 — 그중 위 5곳만
#        적음'인데 글쓴이가 '5km 이상 먼 마을은 10곳 중 5곳이에요'로 옮겼다(다 맞는데 일부만 맞은
#        것처럼). 17b37e7가 줄을 풀어 적어도 Haiku가 또 그렇게 읽어 코드가 막는다
_ALL_N = re.compile(r"모두\s*(\d+)곳")
_OF_N = re.compile(r"(\d+)곳\s*(?:중|가운데)\s*(\d+)곳")


def miscounted_all(answer: str, facts_text: str) -> list[str]:
    """자료가 '모두 N곳'(다 맞음)인데 답이 'N곳 중 K곳'(K < N)처럼 일부만 맞은 것으로 쓴 것."""
    alls = {int(n) for n in _ALL_N.findall(facts_text or "")}
    out = []
    for n, m in _OF_N.findall(answer or ""):
        if int(n) in alls and int(m) < int(n):
            out.append(f"{n}곳 중 {m}곳")
    return out


# 【판단】 10-27 fix_check_2 T2(api1027b): 사용자는 요일을 말하지 않았는데 직전 답(일요일)을 보고
#        '일요일 기준 자료는 없어요'라고 썼다(약국 거리는 요일마다 있다). 약국 자료 줄이 있으면
#        '○요일 자료 없다'는 말은 늘 틀리다
_WD_DENY = re.compile(
    r"[월화수목금토일]요일\s?(?:기준|에는|에)?\s?(?:자료|정보|거리)(?:는|가|은)?\s?없"
)
_WD_DATA = re.compile(r"문 연 약국|요일별|약국까지")


def weekday_denial(answer: str, facts_text: str) -> list[str]:
    """약국(요일별) 자료가 있는데 '○요일 자료는 없다'고 쓴 문장."""
    if not _WD_DATA.search(facts_text or ""):
        return []
    return [m.group(0) for m in _WD_DENY.finditer(answer or "")]


# 【판단】 10-28 재심사 p06_b: 자료가 0줄인 턴에 글쓴이가 영어로 'I'm sorry, but I can't provide
#        that…'을 썼고 검사에 걸리지 않아 그대로 나갔다. 영어 글자가 한글보다 많으면 문제로 본다
#        (기관 이름 · 'PDF' 같은 짧은 영어는 한글보다 적다)
_LATIN = re.compile(r"[A-Za-z]")
_HANGUL = re.compile(r"[가-힣]")


def not_korean(answer: str) -> bool:
    lat = len(_LATIN.findall(answer or ""))
    return lat >= 20 and lat > len(_HANGUL.findall(answer or ""))


# 【판단】 10-28 재심사 q04_b T3 · T4: 자료는 '많은 순 22위'인데 '22위(적은 순)'로 옮겨 뜻이 거꾸로
#        읽혔다(적은 순 22위 = 가장 많음). 자료에 '적은 순' 줄이 없는데 답이 적은 순 몇 위라고 하면
#        문제로 본다(많은 순도 같게)
_RANK_DIR = re.compile(
    r"(\d+)\s?위\s?\(\s?(적은|많은)\s?순\s?\)|(적은|많은)\s?순(?:으로)?\s?(\d+)\s?위"
)


def rank_direction_flips(answer: str, facts_text: str) -> list[str]:
    out = []
    for m in _RANK_DIR.finditer(answer or ""):
        way = m.group(2) or m.group(3)
        other = "많은" if way == "적은" else "적은"
        if f"{way} 순" not in (facts_text or "") and f"{other} 순" in (facts_text or ""):
            out.append(m.group(0))
    return out


# 【판단】 10-28 재심사 q04_b T4(구의원 보좌관): 22곳 중 20 · 21 · 22위(가장 적은 쪽) 세 동을 의회
#        인용 문장에서 '혼자 사는 어르신이 많은 동'이라고 썼다. 자료 줄의 동마다 '많은 순 N위'를
#        읽어, '많은 동'이라 부른 문장의 동이 모두 아래쪽 3분의 1이면 문제로 본다
#        (위쪽을 '적은 동'이라 불러도)
_DONG_HEAD = re.compile(r"\[(?:강남구|춘천시) ([가-힣0-9]+(?:동|읍|면))\]")
_MANY_RANK = re.compile(r"(\d+)곳 중 많은 순[^:\n]*:\s*[^\n·]*?(\d+)위")
_SAYS = re.compile(r"(많|적)(?:은|아|고)\s?(?:동|곳|편|지역)")


def many_few_flips(answer: str, facts_text: str) -> list[str]:
    ranks: dict[str, tuple[int, int]] = {}
    cur = ""
    for line in (facts_text or "").splitlines():
        if m := _DONG_HEAD.search(line):
            cur = m.group(1)
        if cur and cur not in ranks and (r := _MANY_RANK.search(line)):
            ranks[cur] = (int(r.group(2)), int(r.group(1)))
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", answer or ""):
        said = _SAYS.search(sent)
        named = [d for d in ranks if d in sent]
        if not said or not named:
            continue
        low = all(k > n * 2 / 3 for k, n in (ranks[d] for d in named))
        high = all(k <= n / 3 for k, n in (ranks[d] for d in named))
        if (said.group(1) == "많" and low) or (said.group(1) == "적" and high):
            out.append(" · ".join(named))
    return out


def problems(
    answer: str,
    source: str,
    compares: list[tuple[str, float, float]],
    final: bool = True,
    facts_text: str | None = None,
) -> list[str]:
    """답 검사. final=False 는 흘려 보내는 중간(앞부분만 본다)이라 '없다고만 함'은 보지 않는다.

    【판단】 10-13 날씨 r9 T2: 지시문대로 '○○는 자료에 없어요. 대신 …(숫자)'로 쓴 답을
           첫 문장만 보고 버렸다 — '없다고만 했나'는 답이 끝난 뒤 전체로 본다
    【판단】 10-25 페르소나 다리엔 T2(재생): '그게 현장이랑 맞나요?'에 '이 판단이 현장과 맞는지는
           알 수 없어요'를 '있는데 없다고 함'으로 버렸다 — source(허용 글)에 데스크가 다시 쓴 질문
           '…이 판단이 현장과 맞는지…'가 들어 있었다. 있는지는 자료 줄 · 참고(facts_text)로만 본다
    """
    out = (
        [f"없는 숫자 {n}" for n in extra_numbers(answer, source)]
        + [f"없는 날짜 {d}" for d in extra_dates(answer, source)]
        + [f"방향 반대 {x}" for x in wrong_direction(answer, compares)]
        + [f"금지 말 {w}" for w in banned(answer)]
        + [f"몫 앞뒤 뒤바뀜 {w}" for w in reversed_parts(answer)]
        + (["한국어 아님"] if not_korean(answer) else [])
    )
    if final:
        out += [f"없다고만 함 {w}" for w in none_only(answer, source)]
        have = source if facts_text is None else facts_text
        out += [f"있는데 없다고 함 {w}" for w in missing_claims(answer, have)]
        out += [f"맞는 곳 수 틀림 {w}" for w in miscounted_all(answer, have)]
        out += [f"요일 자료 있는데 없다 함 {w}" for w in weekday_denial(answer, have)]
        # 사용자 · 데스크 말(source)에 그 방향이 있으면 그 말을 따른 것이라 본다
        out += [f"순위 방향 뒤집힘 {w}" for w in rank_direction_flips(answer, f"{have} {source}")]
        out += [f"많고 적음 뒤집힘 {w}" for w in many_few_flips(answer, have)]
        out += [f"파일 있는데 못 만든다 함 {w}" for w in file_denial(answer, have)]
    return out


# 【판단】 10-29 브라우저 시험: 엑셀 파일을 만든 턴에 '엑셀로 내보내는 기능이 없어서 표로만'
#        (거짓). 이 턴에 파일을 건넸다는 자료 줄(engine._table_facts)이 있으면 파일을 못 만든다 ·
#        기능이 없다는 말은 문제다
_FILE_MADE = "표 파일(엑셀 · CSV)을 만들어"
_FILE_DENY = re.compile(
    r"(?:엑셀|파일|CSV|csv|내보내)[^.\n]{0,25}"
    r"(?:없어|없습|없는|못\s?(?:만들|드리|해)|않아|않습|안\s?돼|안\s?됩|불가|어려)"
)


def file_denial(answer: str, have: str) -> list[str]:
    if _FILE_MADE not in (have or ""):
        return []
    return [m.group(0) for m in _FILE_DENY.finditer(answer)][:1]
