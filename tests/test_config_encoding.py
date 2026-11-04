"""설정 파일 인코딩 — 한국어 Windows(cp949)에서도 `uv run alembic upgrade head` 가 돈다."""

import configparser
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_alembic_ini_is_ascii():
    # 【판단】 alembic · logging.config 는 alembic.ini 를 OS 기본 인코딩으로 읽는다
    #   (10-26 cp949 에서 멈춤)
    #   → 한글이 한 글자라도 들어오면 한국어 Windows 에서 UnicodeDecodeError
    bad = [
        (n, line)
        for n, line in enumerate(ROOT.joinpath("alembic.ini").read_bytes().splitlines(), 1)
        if not line.isascii()
    ]
    assert bad == [], f"alembic.ini 에 ASCII 가 아닌 줄: {bad}"


def test_alembic_ini_reads_with_cp949():
    # 한국어 Windows 와 같은 조건 — cp949 로 읽어도 깨지지 않고 설정 값이 나온다
    c = configparser.ConfigParser()
    c.read(ROOT / "alembic.ini", encoding="cp949")
    # 【문법】 raw=True = '%(here)s' 같은 자리 표시를 풀지 않고 적힌 글자 그대로 읽는다
    assert c.get("alembic", "script_location", raw=True).endswith("migrations")


def test_alembic_config_loads_in_korean_locale():
    # 실제 경로 — 기본 인코딩을 EUC-KR 로 바꾼 파이썬에서 alembic Config · fileConfig 를 연다
    code = (
        "import locale; assert locale.getpreferredencoding(False).lower().replace('-', '')"
        " in ('euckr', 'cp949'), locale.getpreferredencoding(False);"
        "from alembic.config import Config; from logging.config import fileConfig;"
        "c = Config('alembic.ini'); fileConfig(c.config_file_name);"
        "print(c.get_main_option('script_location'))"
    )
    env = {**os.environ, "LC_ALL": "ko_KR.eucKR", "PYTHONUTF8": "0"}
    r = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True
    )
    if "AssertionError" in r.stderr:
        import pytest

        pytest.skip("이 컴퓨터에 ko_KR.eucKR 로케일이 없음")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().endswith("migrations")
