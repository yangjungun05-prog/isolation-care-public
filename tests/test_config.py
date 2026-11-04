from src.assistant.config import AssistantSettings


def test_defaults_without_env(tmp_path, monkeypatch):
    # 【기능】 키가 없어도 설정은 만들어져야 한다(가짜 데스크로 시험을 돌린다)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    s = AssistantSettings()
    assert s.anthropic_api_key == ""
    assert s.desk_model == "claude-haiku-5-5"
    assert s.history_turns > 0


def test_reads_same_env_file(tmp_path, monkeypatch):
    # 【기능】 팀 저장소와 같은 .env 를 읽고, 모르는 이름(DATABASE_URL)은 무시한다
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+psycopg://user:1234@localhost:5432/AgentDB\n"
        "DESK_MODEL=claude-sonnet-5-5\n"
    )
    monkeypatch.chdir(tmp_path)
    assert AssistantSettings().desk_model == "claude-sonnet-5-5"
