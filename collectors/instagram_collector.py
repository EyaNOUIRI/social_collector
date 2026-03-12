"""
Collecteur Instagram via Meta Graph API.

Collecte les médias (photos, vidéos) d'un compte Instagram Business/Creator
en filtrant par hashtag ou mots-clés. Nécessite un compte Instagram Business
lié à une Page Facebook et un token avec la permission instagram_basic.

Endpoints utilisés:
  - /{ig_user_id}/media             : Médias du compte
  - /{ig_user_id}/tags              : Posts où le compte est tagué
  - /ig_hashtag_search              : Recherche par hashtag
  - /{hashtag_id}/recent_media      : Médias récents du hashtag
  - /{media_id}/comments            : Commentaires d'un média
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

from config.settings import settings
from collectors.base_collector import BaseCollector
from utils.image_downloader import ImageDownloader
from utils.logger import get_logger

logger = get_logger(__name__)


class InstagramCollector(BaseCollector):
    """
    Collecteur de posts Instagram via l'API Graph.

    Fonctionnalités:
    - Recherche par hashtag (nécessite compte Business)
    - Collecte des médias (image_url, caption, timestamp)
    - Téléchargement et encodage des images en base64
    - Collecte des commentaires
    """

    # Champs demandés pour chaque média
    MEDIA_FIELDS = (
        "id,caption,media_type,media_url,thumbnail_url,"
        "permalink,timestamp,like_count,comments_count"
    )

    # Champs demandés pour les commentaires
    COMMENT_FIELDS = "id,text,timestamp,username,like_count"

    def __init__(
        self,
        ig_account_id: str = settings.INSTAGRAM_BUSINESS_ACCOUNT_ID,
        access_token: str = settings.META_ACCESS_TOKEN,
    ):
        super().__init__(access_token=access_token)
        self.ig_account_id = ig_account_id
        self.image_downloader = (
            ImageDownloader() if settings.IMAGE_DOWNLOAD else None
        )

    def collect(
        self, subject: str, limit: int = settings.DEFAULT_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Collecte les posts Instagram relatifs au sujet donné.

        Stratégie:
        1. Extraire les hashtags du sujet
        2. Rechercher par chaque hashtag via l'API
        3. Compléter avec les médias du compte si nécessaire

        Args:
            subject: Sujet (ex: "Jacques Chirac décès").
            limit: Nombre maximum de posts à retourner.

        Returns:
            Liste de documents structurés pour MongoDB.
        """
        if not self.ig_account_id:
            logger.error("INSTAGRAM_BUSINESS_ACCOUNT_ID non configuré.")
            return []

        logger.info(
            f"Démarrage collecte Instagram | sujet='{subject}' | limit={limit}"
        )

        collected: List[Dict[str, Any]] = []
        seen_ids = set()

        # Stratégie 1: Recherche par hashtags
        hashtags = self._subject_to_hashtags(subject)
        for hashtag in hashtags:
            if len(collected) >= limit:
                break
            posts = self._collect_by_hashtag(hashtag, subject, limit - len(collected))
            for post in posts:
                if post["post_id"] not in seen_ids:
                    collected.append(post)
                    seen_ids.add(post["post_id"])

        # Stratégie 2: Médias du compte (filtrage par mots-clés)
        if len(collected) < limit:
            account_posts = self._collect_account_media(
                subject, limit - len(collected)
            )
            for post in account_posts:
                if post["post_id"] not in seen_ids:
                    collected.append(post)
                    seen_ids.add(post["post_id"])

        logger.info(
            f"Collecte Instagram terminée: {len(collected)} posts pour '{subject}'"
        )
        return collected[:limit]

    def _collect_by_hashtag(
        self, hashtag: str, subject: str, limit: int
    ) -> List[Dict[str, Any]]:
        """
        Collecte les médias récents pour un hashtag donné.

        Args:
            hashtag: Hashtag sans le '#' (ex: "jacqueschirac").
            subject: Sujet de collecte (pour les métadonnées).
            limit: Nombre maximum de médias à retourner.

        Returns:
            Liste de posts structurés.
        """
        # Étape 1: Obtenir l'ID du hashtag
        hashtag_data = self._make_request(
            endpoint="ig_hashtag_search",
            params={
                "user_id": self.ig_account_id,
                "q": hashtag,
            },
        )

        if not hashtag_data or not hashtag_data.get("data"):
            logger.warning(f"Hashtag introuvable: #{hashtag}")
            return []

        hashtag_id = hashtag_data["data"][0].get("id")
        if not hashtag_id:
            return []

        logger.debug(f"Hashtag #{hashtag} -> ID: {hashtag_id}")

        # Étape 2: Récupérer les médias récents du hashtag
        media_data = self._make_request(
            endpoint=f"{hashtag_id}/recent_media",
            params={
                "user_id": self.ig_account_id,
                "fields": self.MEDIA_FIELDS,
                "limit": min(limit, 50),
            },
        )

        if not media_data:
            return []

        collected = []

        def process_media(raw_media: Dict) -> Optional[Dict]:
            return self._process_media(raw_media, subject, hashtag=hashtag)

        self._paginate(media_data, limit, collected, process_media)
        return collected

    def _collect_account_media(
        self, subject: str, limit: int
    ) -> List[Dict[str, Any]]:
        """
        Collecte les médias du compte Instagram et filtre par mots-clés.

        Args:
            subject: Sujet pour le filtrage.
            limit: Nombre maximum de médias.

        Returns:
            Liste de posts filtrés.
        """
        media_data = self._make_request(
            endpoint=f"{self.ig_account_id}/media",
            params={
                "fields": self.MEDIA_FIELDS,
                "limit": min(limit * 3, 100),  # Surcharge pour compenser le filtrage
            },
        )

        if not media_data:
            return []

        keywords = [kw.lower() for kw in subject.split()]
        collected = []

        def process_and_filter(raw_media: Dict) -> Optional[Dict]:
            caption = raw_media.get("caption", "") or ""
            if not any(kw in caption.lower() for kw in keywords):
                return None
            return self._process_media(raw_media, subject)

        self._paginate(media_data, limit, collected, process_and_filter)
        return collected

    def _process_media(
        self,
        raw_media: Dict[str, Any],
        subject: str,
        hashtag: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Transforme un média brut de l'API en document MongoDB.

        Args:
            raw_media: Données brutes depuis l'API Graph.
            subject: Sujet de collecte.
            hashtag: Hashtag source (facultatif).

        Returns:
            Document structuré ou None.
        """
        media_id = raw_media.get("id")
        if not media_id:
            return None

        media_type = raw_media.get("media_type", "IMAGE")

        # Télécharger l'image
        images = []
        image_url = raw_media.get("media_url")
        if media_type in ("IMAGE", "CAROUSEL_ALBUM") and image_url:
            img_data = self._download_image(image_url)
            if img_data:
                images.append(img_data)
        elif media_type == "VIDEO":
            # Pour les vidéos, télécharger la thumbnail
            thumb_url = raw_media.get("thumbnail_url")
            if thumb_url:
                img_data = self._download_image(thumb_url)
                if img_data:
                    img_data["is_thumbnail"] = True
                    images.append(img_data)

        # Collecter les commentaires
        comments = self._fetch_comments(media_id)

        return {
            "post_id": media_id,
            "source": "instagram",
            "subject": subject,
            "message": raw_media.get("caption", ""),
            "permalink_url": raw_media.get("permalink", ""),
            "created_time": self._parse_datetime(raw_media.get("timestamp", "")),
            "media_type": media_type,
            "images": images,
            "comments": comments,
            "hashtag_source": hashtag,
            "stats": {
                "like_count": raw_media.get("like_count", 0),
                "comment_count": raw_media.get("comments_count", 0),
                "image_count": len(images),
            },
            "ig_account_id": self.ig_account_id,
        }

    def _fetch_comments(self, media_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les commentaires d'un média Instagram.

        Args:
            media_id: ID du média Instagram.

        Returns:
            Liste des commentaires structurés.
        """
        data = self._make_request(
            endpoint=f"{media_id}/comments",
            params={
                "fields": self.COMMENT_FIELDS,
                "limit": 50,
            },
        )

        if not data:
            return []

        comments = []
        for raw_comment in data.get("data", []):
            comment = {
                "comment_id": raw_comment.get("id"),
                "message": raw_comment.get("text", ""),
                "created_time": self._parse_datetime(
                    raw_comment.get("timestamp", "")
                ),
                "author_name": raw_comment.get("username", ""),
                "like_count": raw_comment.get("like_count", 0),
            }
            comments.append(comment)

        return comments

    def _download_image(self, url: str) -> Optional[Dict[str, Any]]:
        """Télécharge une image si le téléchargement est activé."""
        if not self.image_downloader:
            return {"url": url}
        return self.image_downloader.download(url)

    @staticmethod
    def _subject_to_hashtags(subject: str) -> List[str]:
        """
        Convertit un sujet en liste de hashtags candidats.

        Ex: "Jacques Chirac décès" -> ["jacqueschirac", "chirac", "deces"]

        Args:
            subject: Sujet en langage naturel.

        Returns:
            Liste de hashtags (sans '#', en minuscules, sans accents).
        """
        import unicodedata

        def remove_accents(text: str) -> str:
            return "".join(
                c for c in unicodedata.normalize("NFD", text)
                if unicodedata.category(c) != "Mn"
            )

        words = subject.lower().split()
        # Supprimer les articles et mots courts
        stop_words = {"le", "la", "les", "de", "du", "des", "un", "une", "et", "ou"}
        words = [remove_accents(w) for w in words if w not in stop_words and len(w) > 2]

        hashtags = []
        # Hashtag composé (ex: jacqueschirac)
        if len(words) >= 2:
            hashtags.append("".join(words))
        # Hashtags individuels
        hashtags.extend(words)

        logger.debug(f"Hashtags générés pour '{subject}': {hashtags}")
        return hashtags

    @staticmethod
    def _parse_datetime(dt_str: str) -> Optional[datetime]:
        """Parse une date ISO 8601 depuis l'API Instagram."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S+%f")
            except ValueError:
                logger.debug(f"Format de date non reconnu: {dt_str}")
                return None

    def close(self) -> None:
        """Ferme les ressources."""
        super().close()
        if self.image_downloader:
            self.image_downloader.close()
