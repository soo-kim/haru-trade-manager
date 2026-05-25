from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "haru-trade-manager"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://haru:haru@localhost:6432/haru_trade"
    enable_background_loops: bool = False
    trading_mode: str = "paper"
    server_timezone: str = "Asia/Seoul"
    kiwoom_base_url: str = "https://api.kiwoom.com"
    kiwoom_app_key: str = ""
    kiwoom_app_secret: str = ""
    kiwoom_account_no: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


settings = Settings()
