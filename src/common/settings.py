# 【기능】 .env 에 적힌 값을 읽어 코드에서 settings.database_url 처럼 쓰게 한다
# 【판단】 os.getenv 를 여기저기 쓰면 이름 오타가 조용히 None 이 된다.
#        한곳에 모으면 빠진 값이 프로그램 시작하자마자 오류로 드러난다
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 【문법】 model_config 는 pydantic 이 읽는 설정 칸. env_file=".env" = "이 파일에서 값을 읽어라"
    # 【문법】 extra="ignore" = .env 에 아래 없는 이름이 있어도 오류 내지 말라
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 【문법】 기본값이 없으면 필수 칸.
    # .env 의 대문자 DATABASE_URL 이 소문자 이름에 들어간다(대소문자 무시)
    database_url: str
    # 【판단】 키가 아직 없는 사람도 있으니 빈 문자열을 기본값으로 — 쓰는 곳에서 비었는지 확인
    gemini_api_key: str = ""
    data_go_kr_service_key: str = ""


# 【기능】 다른 파일에서는 from src.common.settings import settings 로 가져다 쓴다
# 【판단】 값은 .env 에서 채워지는데 검사기(Pylance)는 그걸 몰라 "인자 빠짐"으로 본다 → 이 줄만 끔
settings = Settings()  # pyright: ignore[reportCallIssue]
