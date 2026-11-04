"""판단 층 따로 시험지에 쓸 '사용자 말'을 다른 AI(Sonnet)가 만든다(10-26).

    uv run python evals/gen_route_msgs.py --env-file <.env> --out <파일>

【판단】 판단 층 규칙을 만든 쪽(Claude 세션)이 시험 말까지 쓰면 규칙에 맞는 말만 쓰기 쉽다
       (route_50 r1 → 고친 뒤 route_hold_32 에서 18/32로 떨어짐). 규칙을 모르는 AI에게 자료
       목록과 사용자 모습만 주고 말을 만들게 한 뒤, 정답 길은 사람 쪽이 AI 결과를 보기 전에 적는다
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.assistant import llm  # noqa: E402
from src.assistant.config import AssistantSettings  # noqa: E402

SYSTEM = """너는 복지 현장 사용자 흉내 내는 사람이다. 동 단위 공개 자료로 답하는 AI 비서(서울 강남구
22개 동 · 강원 춘천시 25개 읍면동)에게 실제 사용자가 보낼 만한 말을 만든다.

비서가 가진 자료(동마다): 주민 · 65세 이상 · 80세 이상 인구, 혼자 사는 65세 이상 · 80세
이상(주민등록 1인세대)과 1년 새 증감, 혼자 사는 비율, 서울시 독거노인 현황(강남만: 남녀 ·
80세 이상 · 기초수급 · 2년 새 증감), 기초생활수급자(춘천만), 빈집(춘천 일부), 승강기 없는
낡은 계단 집 · 반지하 건물, 경로당 · 무료급식소 · 약국 · 의원 · 방문요양 기관 · 요양원 수,
약국까지 거리, 청년 인구 · 혼자 사는 청년과 증감 · 집에만 있는 청년 어림, 돌봄 자원 공백,
먼저 볼 동 순위 · 위험 구간 · 진단 신호, 날씨 예보와 특보, 춘천 시골 버스 횟수 · 정류장
거리, 지원 기관 연락처, 동 상황 문서(PDF). 없는 자료: 개인 정보, 우울 · 소득 · 질병, 동보다
작은 단위(아파트 · 통반), 다른 시군.

사용자: 동 주민센터 복지 담당, 구청 · 시청 노인 · 청년 정책 담당, 보건소 방문간호사, 복지관
사례관리자, 민간 단체 활동가, 기자, 도청 점검 담당. 말투는 섞는다 — 아주 짧은 말, 오타 ·
띄어쓰기 틀림, 사투리, 반말, 화난 말, 공문서 같은 긴 말, 두세 가지를 한꺼번에 묻는 말,
조건을 꼬아서 말하는 것.

만들 것(모두 {n}개, 이 비율로 섞어서 순서는 뒤섞어라):
- 4할: 자료 여러 개를 묶어 계산해 달라는 실무 요구(조건 여럿으로 동 고르기, 구 · 시 평균과
  견주기, 합계, 몇 명당, 동 몇 곳을 지표 여럿으로 나란히, 앞에서 받은 결과 안에서 다시
  거르기, 공모 · 지침 기준 맞추기 등). 그런 말이라는 티를 내지 말고 실제 사람이 하듯이
- 3할: 자료 하나만 꺼내면 되는 말(동 하나의 숫자, 한 가지로 줄 세우기, 말뜻 · 기준 · 출처
  질문, 문서, 날씨, 버스, 기관 안내). 이 가운데 반은 자료 이름이 여럿 나오지만 실제로는
  설명을 묻는 말
- 2할: 앞 대화를 되짚는 말(앞에서 들은 숫자 확인, 앞뒤 답이 다르다고 따짐, 지금까지 요약)
- 1할: 인사 · 고맙다는 말 · 개인 정보를 캐는 말 · 자료 밖 질문
앞 대화가 있어야 뜻이 서는 말은 prev_user(사용자가 바로 앞에 한 말)와 prev_bot(비서가 바로
앞에 한 답, 두세 문장)을 함께 만든다. 없으면 빈 문자열.

JSON 배열 하나만 낸다: [{{"say": "...", "region": "강남구"|"춘천시", "prev_user": "",
"prev_bot": "", "who": "누가 · 어떤 상황(짧게)"}}]"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=45)
    a = ap.parse_args()
    load_dotenv(a.env_file, override=False)
    s = AssistantSettings(_env_file=a.env_file)  # pyright: ignore[reportCallIssue]
    r = llm.call(
        s.anthropic_api_key,
        llm.Usage(),
        model="claude-sonnet-5-5",
        max_tokens=16000,
        system=[{"type": "text", "text": SYSTEM.format(n=a.n)}],
        messages=[{"role": "user", "content": f"{a.n}개를 만들어 줘."}],
    )
    text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
    start, end = text.find("["), text.rfind("]")
    items = json.loads(text[start : end + 1])
    Path(a.out).write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(items), a.out)


if __name__ == "__main__":
    main()
