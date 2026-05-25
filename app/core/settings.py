from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "haru-trade-manager"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://haru:haru@localhost:6432/haru_trade"
    enable_background_loops: bool = False
    enable_auto_backtest: bool = False
    auto_backtest_run_hour: int = 16
    trading_mode: str = "paper"
    server_timezone: str = "Asia/Seoul"
    kiwoom_base_url: str = "https://api.kiwoom.com"
    kiwoom_app_key: str = ""
    kiwoom_app_secret: str = ""
    kiwoom_account_no: str = ""
    telegram_token: str = ""
    telegram_chat_id: str = ""


settings = Settings()
