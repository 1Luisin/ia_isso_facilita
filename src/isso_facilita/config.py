from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    enabled_marketplaces: str = "demo"
    publisher: str = "console"
    dry_run: bool = True
    scan_interval_minutes: int = Field(default=30, ge=0)
    min_discount_percent: float = Field(default=20, ge=0, le=100)
    include_non_promotional_products: bool = True
    max_offers_per_run: int = Field(default=5, ge=1, le=50)
    database_path: Path = Path("data/offers.db")
    bot_api_token: str = ""

    ai_curation_enabled: bool = False
    ai_provider: Literal["ollama", "openai"] = "ollama"
    ai_relevance_threshold: int = Field(default=75, ge=0, le=100)
    max_ai_evaluations_per_run: int = Field(default=6, ge=1, le=30)
    brand_identity_path: Path = Path("config/brand_identity.json")
    editorial_feedback_path: Path = Path("config/editorial_feedback.json")
    max_product_price_brl: float = Field(default=500, gt=0)
    ollama_model: str = "qwen3-vl:2b-instruct"
    ollama_use_product_images: bool = True
    ollama_api_url: str = "http://127.0.0.1:11434"
    ollama_timeout_seconds: float = Field(default=180, ge=10, le=600)
    openai_api_key: str = ""
    openai_model: str = "gpt-6-luna"
    openai_api_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = Field(default=45, ge=5, le=180)

    shopee_app_id: str = ""
    shopee_secret: str = ""
    shopee_api_url: str = "https://open-api.affiliate.shopee.com.br/graphql"

    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    aliexpress_tracking_id: str = ""
    aliexpress_api_url: str = "https://api-sg.aliexpress.com/sync"
    aliexpress_keywords: str = (
        "mechanical gaming keyboard,magnetic rapid trigger keyboard,anime keycaps,"
        "genshin impact keycaps,wireless gaming mouse,cute deskmat,pastel deskmat,"
        "cinnamoroll mouse pad,aesthetic anime mousepad,wireless gaming controller,"
        "8bitdo controller,monitor light bar,monitor arm,notebook stand,usb hub,"
        "usb condenser microphone desk,bluetooth headphones,gan charger,ssd nvme 1tb,"
        "portable monitor,cute keyboard cleaning kit,cute phone stand,"
        "anime action figure 25cm,vocaloid action figure,"
        "hatsune miku figure,sanrio desk accessory,solo leveling figure,dandadan figure,"
        "my hero academia figure,demon slayer figure,wuthering waves figure,"
        "genshin impact figure,hollow knight silksong figure,clair obscur figure"
    )

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

    @property
    def ai_model(self) -> str:
        return self.ollama_model if self.ai_provider == "ollama" else self.openai_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
