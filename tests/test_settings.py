from src.common.settings import Settings


def test_env_file_is_read(tmp_path, monkeypatch):
    # 【문법】 tmp_path = pytest 가 테스트마다 만들어 주는 빈 폴더
    #        monkeypatch = 테스트 동안만 환경을 바꿨다가 끝나면 되돌려 주는 도구
    # 【기능】 터미널에 같은 이름의 값이 있으면 .env 보다 우선하니 테스트 동안 지운다
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=postgresql+psycopg://salpim:salpim@localhost:5432/salpim\n")
    # 【기능】 작업 폴더를 빈 폴더로 옮겨, 내 진짜 .env 대신 방금 만든 .env 를 읽게 한다
    monkeypatch.chdir(tmp_path)

    s = Settings()  # pyright: ignore[reportCallIssue]
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.gemini_api_key == ""
