"""
Utilitaire de téléchargement et d'encodage d'images.
Télécharge les images depuis les URLs et les encode en base64
pour stockage dans MongoDB.
"""
import base64
import hashlib
import io
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import requests
from PIL import Image

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class ImageDownloader:
    """Gère le téléchargement et le traitement des images."""

    SUPPORTED_FORMATS = {"JPEG", "PNG", "GIF", "WEBP"}
    MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

    def __init__(self, timeout: int = settings.REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "SocialMediaCollector/1.0"})

    def download(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Télécharge une image depuis une URL.

        Args:
            url: URL de l'image à télécharger.

        Returns:
            Dictionnaire contenant les métadonnées et données de l'image,
            ou None en cas d'erreur.
        """
        if not url or not self._is_valid_url(url):
            logger.warning(f"URL invalide: {url}")
            return None

        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            content_length = int(response.headers.get("Content-Length", 0))
            if content_length > self.MAX_SIZE_BYTES:
                logger.warning(f"Image trop grande ({content_length} bytes): {url}")
                return None

            raw_bytes = response.content
            return self._process_image(raw_bytes, url)

        except requests.exceptions.Timeout:
            logger.error(f"Timeout lors du téléchargement: {url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur téléchargement {url}: {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue pour {url}: {e}")

        return None

    def _process_image(self, raw_bytes: bytes, url: str) -> Optional[Dict[str, Any]]:
        """
        Traite les bytes d'une image: validation, métadonnées, encodage.

        Args:
            raw_bytes: Bytes bruts de l'image.
            url: URL source (pour les métadonnées).

        Returns:
            Dictionnaire avec métadonnées et données base64.
        """
        try:
            img = Image.open(io.BytesIO(raw_bytes))

            if img.format not in self.SUPPORTED_FORMATS:
                logger.warning(f"Format non supporté: {img.format}")
                return None

            md5_hash = hashlib.md5(raw_bytes).hexdigest()
            b64_data = base64.b64encode(raw_bytes).decode("utf-8")

            return {
                "url": url,
                "format": img.format.lower(),
                "width": img.width,
                "height": img.height,
                "size_bytes": len(raw_bytes),
                "md5": md5_hash,
                "data_b64": b64_data,
                "content_type": f"image/{img.format.lower()}",
            }

        except Exception as e:
            logger.error(f"Erreur traitement image: {e}")
            return None

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Vérifie qu'une URL est bien formée."""
        try:
            result = urlparse(url)
            return result.scheme in {"http", "https"} and bool(result.netloc)
        except ValueError:
            return False

    def close(self) -> None:
        """Ferme la session HTTP."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
