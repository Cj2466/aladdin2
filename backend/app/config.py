from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    finnhub_api_key: str = ""
    database_url: str = "sqlite:///./aladdin2.db"
    cookie_secure: bool = False  # set true once served over https

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
