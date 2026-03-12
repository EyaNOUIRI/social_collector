"""
Configuration centralisée du projet.
Charge les variables depuis le fichier .env.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Paramètres de configuration globaux."""

    # --- Meta Graph API ---
    META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
    META_APP_ID: str = os.getenv("META_APP_ID", "")
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    META_API_VERSION: str = "v18.0"
    META_BASE_URL: str = f"https://graph.facebook.com/v18.0"

    # --- Comptes cibles ---
    FACEBOOK_PAGE_ID: str = os.getenv("FACEBOOK_PAGE_ID", "")
    INSTAGRAM_BUSINESS_ACCOUNT_ID: str = os.getenv(
        "INSTAGRAM_BUSINESS_ACCOUNT_ID", ""
    )

    # --- MongoDB ---
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "social_media_collector")
    COLLECTION_POSTS: str = "posts"
    COLLECTION_MEDIA: str = "media"

    # --- Collecte ---
    DEFAULT_LIMIT: int = int(os.getenv("DEFAULT_LIMIT", "50"))
    IMAGE_DOWNLOAD: bool = os.getenv("IMAGE_DOWNLOAD", "true").lower() == "true"
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3

    # --- Logging ---
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = "collector.log"

    def validate(self) -> None:
        """Vérifie que les paramètres critiques sont définis."""
        if not self.META_ACCESS_TOKEN:
            raise ValueError(
                "META_ACCESS_TOKEN manquant. Vérifiez votre fichier .env"
            )
        if not self.MONGODB_URI:
            raise ValueError("MONGODB_URI manquant.")


settings = Settings()
