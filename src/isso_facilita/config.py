from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    enabled_marketplaces: str = "demo"
    publisher: str = "console"
    dry_run: bool = True
    scan_interval_minutes: int = Field(default=30, ge=1)
    min_discount_percent: float = Field(default=20, ge=0, le=100)
    max_offers_per_run: int = Field(default=5, ge=1, le=50)
    database_path: Path = Path("data/offers.db")
    bot_api_token: str = ""

    shopee_app_id: str = ""
    shopee_secret: str = ""
    shopee_api_url: str = "https://open-api.affiliate.shopee.com.br/graphql"

    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    aliexpress_tracking_id: str = ""
    aliexpress_api_url: str = "https://api-sg.aliexpress.com/sync"
    aliexpress_keywords: str = "smartphone,ssd,laptop,headphones,smartwatch,mouse,keyboard,charger"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_group_id: str = ""
    whatsapp_graph_api_version: str = "v25.0"
    whatsapp_web_bridge_url: str = "http://127.0.0.1:3001"
    whatsapp_web_bridge_token: str = ""
    whatsapp_web_group_id: str = ""
    webhook_url: str = ""
    webhook_bearer_token: str = ""

    @field_validator("enabled_marketplaces")
    @classmethod
    def normalize_marketplaces(cls, value: str) -> str:
        return ",".join(item.strip().lower() for item in value.split(",") if item.strip())

    @field_validator("publisher")
    @classmethod
    def normalize_publishers(cls, value: str) -> str:
        return ",".join(item.strip().lower() for item in value.split(",") if item.strip())

    @property
    def marketplace_names(self) -> list[str]:
        return self.enabled_marketplaces.split(",")

    @property
    def publisher_names(self) -> list[str]:
        return self.publisher.split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()
