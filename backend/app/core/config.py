"""Configuración de la aplicación leída desde variables de entorno / archivo .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    frontend_url: str = "http://localhost:5173"

    gemini_api_key: str = ""
    whatsapp_token: str = ""
    whatsapp_phone_id: str = ""
    whatsapp_test_to: str = ""
    database_url: str = ""
    resend_api_key: str = ""
    resend_test_to: str = ""


settings = Settings()
