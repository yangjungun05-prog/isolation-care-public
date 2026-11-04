from src.auth import rules
from src.auth.secrets_util import check_password, hash_password, sign, unsign


def test_password_rules_follow_storyboard():
    # COM-140 ③: 9~20자 · 영문 · 숫자 · 특수문자 · 아이디 없음 · 같은 글자 3번 연속 없음
    assert all(rules.password_checks("Salpim#2026", "hong07").values())
    assert not rules.password_checks("ab1!", "")["length"]
    assert not rules.password_checks("abcdefgh12", "")["kinds"]  # 특수문자 없음
    assert not rules.password_checks("hong07#abc1", "hong07")["no_id"]
    assert not rules.password_checks("abc111#xyz", "")["no_repeat"]
    assert (
        rules.password_problem("abcdefgh12")
        == "비밀번호에 영문 · 숫자 · 특수문자를 모두 넣어 주세요."
    )


def test_login_id_rules_and_mask():
    assert rules.login_id_problem("hong07") is None
    assert rules.login_id_problem("Hong07") is not None  # 대문자로 시작
    assert rules.login_id_problem("ab") is not None
    assert rules.mask_login_id("hong07") == "ho***7"  # COM-161 예


def test_password_hash_and_signed_ticket():
    h = hash_password("Salpim#2026")
    assert h.startswith("scrypt$") and len(h) <= 200 and "Salpim" not in h
    assert check_password("Salpim#2026", h) and not check_password("salpim#2026", h)
    t = sign("signup", {"email": "a@b.kr"}, 5)
    assert unsign("signup", t)["email"] == "a@b.kr"
    assert unsign("reset", t) is None  # 쓰임이 다르면 못 쓴다
    assert unsign("signup", t[:-1] + ("0" if t[-1] != "0" else "1")) is None  # 고친 표
