"""공개 전 검사 — 대회 자료 · 응답자 줄 · 비밀 값 · 개인 메일이 저장소에 없는지 본다.

    uv run python scripts/check_public.py            # git 이 추적하는 파일을 검사
    uv run python scripts/check_public.py --self-test # 일부러 넣은 나쁜 파일을 잡는지 확인

통과하면 PUBLIC_CHECK_OK 를 찍고, 걸리면 파일과 까닭을 찍고 1 로 끝난다.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = "scripts/check_public.py"
BAD_NAMES = re.compile(
    r"(flow_month|dong_alert_month|respondents\.csv|weights\.csv|빅콘테스트_제공|\.sas7bdat$|"
    r"(^|/)\.env$|\.ipynb$|\.auth_secret$|ledger_.*\.jsonl$)"
)
# 【판단】 대회 표의 칸 이름 · 건강조사 원자료 칸 이름은 그 자료가 섞였다는 신호다
BAD_TEXT = {
    "대회 카드 표 칸": re.compile(r"\bage_group,industry_group,time_band,n,amount,raw\b"),
    "SKT 표 칸": re.compile(r"\bold_idx\b|\brel_idx\b"),
    "건강조사 원자료 칸": re.compile(r"\b(enb_0[123]z1|fma_19z3|fma_04z1|wt_p)\b"),
    "API 키": re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,}"),
    "비밀 키 파일": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "개인 메일": re.compile(r"[A-Za-z0-9._-]{4,}@(gmail|naver|daum)\.[a-z]+"),
}
ALLOWED_MAIL = {"anyone@gmail.com"}
ALLOWED_TEXT = {SELF}


def check(root: Path, files: list[str]) -> list[str]:
    problems = []
    for name in files:
        if BAD_NAMES.search(name):
            problems.append(f"{name}: 올리면 안 되는 파일 이름")
        path = root / name
        if name in ALLOWED_TEXT or not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for why, pat in BAD_TEXT.items():
            for m in pat.finditer(text):
                if m.group(0) not in ALLOWED_MAIL:
                    problems.append(f"{name}: {why}")
                    break
    # 【판단】 동 카드에 SKT 경보가 다시 들어오면 안 된다 — 칸은 있어도 비어 있어야 한다
    card = root / "data/derived_public/dong_card.csv"
    if card.exists():
        import pandas as pd

        t = pd.read_csv(card, encoding="utf-8-sig")
        if t["alert_grade"].notna().any() or t["alert_why"].notna().any():
            problems.append("data/derived_public/dong_card.csv: SKT 경보 값이 들어 있음")
    table = root / "data/derived_public/card_pay_day.csv"
    if table.exists():
        import pandas as pd

        t = pd.read_csv(table)
        if set(t["time_band"]) != {"all"} or set(t["age_group"]) != {"60대", "70대 이상"}:
            problems.append("data/derived_public/card_pay_day.csv: 공개판 모양이 아님")
    if card.exists():
        import pandas as pd

        if "n_iso" in pd.read_csv(card, encoding="utf-8-sig", nrows=1).columns:
            problems.append("data/derived_public/dong_card.csv: 응답자 수 칸이 들어 있음")
    cells = root / "data/derived_public/sim_inputs/cells.csv"
    if cells.exists():
        import pandas as pd

        if pd.read_csv(cells)["n"].min() < 30:
            problems.append("cells.csv: 응답자 30명 미만 칸")
    return problems


def self_test() -> int:
    # 【기능】 대조군 — 나쁜 파일을 넣으면 반드시 걸려야 한다. 깨끗한 파일은 걸리면 안 된다
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        cases = {
            "data/flow_month.csv": "x",
            "a.txt": "old_idx,rel_idx",
            "b.txt": "fma_19z3",
            "c.txt": "sk-ant-" + "a" * 20,
            "d.txt": "someone" + "@gmail.com",
            "n.ipynb": "{}",
        }
        for name, body in cases.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(body, encoding="utf-8")
            if not check(root, [name]):
                print("못 잡음:", name)
                return 1
        (root / "ok.txt").write_text("공개 자료", encoding="utf-8")
        if check(root, ["ok.txt"]):
            print("오탐: ok.txt")
            return 1
    print("SELF_TEST_OK", len(cases))
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    files = out.stdout.splitlines()
    problems = check(ROOT, files)
    for p in problems:
        print(p)
    if problems:
        return 1
    print("PUBLIC_CHECK_OK", len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
