"""Configuración de la aplicación leída desde variables de entorno / archivo .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    frontend_url: str = "http://localhost:5173"
    backend_public_url: str = ""

    gemini_api_key: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_test_to: str = ""
    database_url: str = ""
    resend_api_key: str = ""
    resend_test_to: str = ""
    telegram_bot_token: str = ""
    telegram_test_chat_id: str = ""
    whatsapp_verify_token: str = ""
    telegram_webhook_secret: str = ""
    whatsapp_provider: str = "ycloud"
    ycloud_api_key: str = ""
    ycloud_whatsapp_from: str = ""
    ycloud_webhook_secret: str = ""
    ycloud_allow_unsigned_webhooks: bool = False
    ycloud_webhook_tolerance_seconds: int = 300
    affiliate_csv_path: str = ""


settings = Settings()
