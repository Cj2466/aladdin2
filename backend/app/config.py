from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    finnhub_api_key: str = ""
    database_url: str = "sqlite:///./aladdin2.db"
    cookie_secure: bool = False  # set true once served over https
    risk_free_rate: float = 0.04  # static annualized rate used for Sharpe ratio, not fetched live
    alert_check_interval_seconds: int = 300
    resend_api_key: str = ""
    alert_email_from: str = "onboarding@resend.dev"  # Resend's shared sandbox sender

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
