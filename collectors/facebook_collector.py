"""
Collecteur Facebook via Meta Graph API.

Collecte les posts (texte, images, commentaires) depuis une Page Facebook
en filtrant par sujet (mots-clés). Nécessite un Page Access Token.

Endpoints utilisés:
  - /{page_id}/posts       : Posts publiés sur la page
  - /{post_id}/comments    : Commentaires d'un post
  - /{post_id}/attachments : Médias attachés (images, vidéos)
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

from config.settings import settings
from collectors.base_collector import BaseCollector
from utils.image_downloader import ImageDownloader
from utils.logger import get_logger

logger = get_logger(__name__)


class FacebookCollector(BaseCollector):
    """
    Collecteur de posts Facebook via l'API Graph.

    Fonctionnalités:
    - Collecte les posts d'une Page par mots-clés
    - Télécharge et encode les images en base64
    - Collecte les commentaires associés à chaque post
    - Retourne des documents structurés pour MongoDB
    """

    # Champs demandés pour chaque post
    POST_FIELDS = (
        "id,message,story,created_time,permalink_url,"
        "full_picture,attachments,reactions.summary(true)"
    )

    # Champs demandés pour les commentaires
    COMMENT_FIELDS = "id,message,created_time,from,like_count"

    def __init__(
        self,
        page_id: str = settings.FACEBOOK_PAGE_ID,
        access_token: str = settings.META_ACCESS_TOKEN,
    ):
        super().__init__(access_token=access_token)
        self.page_id = page_id
        self.image_downloader = (
            ImageDownloader() if settings.IMAGE_DOWNLOAD else None
        )

    def collect(self, subject: str, limit: int = settings.DEFAULT_LIMIT) -> List[Dict[str, Any]]:
        """
        Collecte les posts Facebook relatifs au sujet donné.

        Args:
            subject: Mots-clés du sujet (ex: "Jacques Chirac décès").
            limit: Nombre maximum de posts à retourner.

        Returns:
            Liste de documents structurés pour MongoDB.
        """
        if not self.page_id:
            logger.error("FACEBOOK_PAGE_ID non configuré.")
            return []

        logger.info(
            f"Démarrage collecte Facebook | sujet='{subject}' | limit={limit}"
        )

        # Récupération des posts de la page
        raw_data = self._make_request(
            endpoint=f"{self.page_id}/posts",
            params={
                "fields": self.POST_FIELDS,
                "limit": min(limit, 100),  # API max = 100 par page
            },
        )

        if not raw_data:
            logger.warning("Aucune donnée reçue de l'API Facebook.")
            return []

        collected: List[Dict[str, Any]] = []

        def process_post(raw_post: Dict) -> Optional[Dict]:
            return self._process_post(raw_post, subject)

        self._paginate(raw_data, limit, collected, process_post)

        # Filtrer par mots-clés du sujet
        keywords = [kw.lower() for kw in subject.split()]
        filtered = [
            post for post in collected
            if self._matches_subject(post.get("message", ""), keywords)
        ]

        logger.info(
            f"Collecte terminée: {len(collected)} posts récupérés, "
            f"{len(filtered)} correspondent au sujet '{subject}'"
        )
        return filtered

    def _process_post(
        self, raw_post: Dict[str, Any], subject: str
    ) -> Optional[Dict[str, Any]]:
        """
        Transforme un post brut de l'API en document MongoDB.

        Args:
            raw_post: Données brutes du post depuis l'API Graph.
            subject: Sujet de collecte (pour métadonnées).

        Returns:
            Document structuré ou None si traitement impossible.
        """
        post_id = raw_post.get("id")
        if not post_id:
            return None

        message = raw_post.get("message") or raw_post.get("story", "")

        # Extraire les images
        images = self._extract_images(raw_post)

        # Collecter les commentaires
        comments = self._fetch_comments(post_id)

        # Compter les réactions
        reactions = raw_post.get("reactions", {})
        reaction_count = reactions.get("summary", {}).get("total_count", 0)

        return {
            "post_id": post_id,
            "source": "facebook",
            "subject": subject,
            "message": message,
            "permalink_url": raw_post.get("permalink_url", ""),
            "created_time": self._parse_datetime(
                raw_post.get("created_time", "")
            ),
            "images": images,
            "comments": comments,
            "stats": {
                "reaction_count": reaction_count,
                "comment_count": len(comments),
                "image_count": len(images),
            },
            "page_id": self.page_id,
        }

    def _extract_images(self, raw_post: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extrait toutes les images d'un post (photo principale + attachments).

        Args:
            raw_post: Données brutes du post.

        Returns:
            Liste de dictionnaires d'images avec données base64.
        """
        images = []
        seen_urls = set()

        # Image principale (full_picture)
        main_pic_url = raw_post.get("full_picture")
        if main_pic_url and main_pic_url not in seen_urls:
            img_data = self._download_image(main_pic_url)
            if img_data:
                images.append(img_data)
                seen_urls.add(main_pic_url)

        # Images depuis les attachments
        attachments = raw_post.get("attachments", {})
        for attachment in attachments.get("data", []):
            # Sous-attachments (albums)
            for sub in attachment.get("subattachments", {}).get("data", []):
                media = sub.get("media", {})
                img_url = media.get("image", {}).get("src")
                if img_url and img_url not in seen_urls:
                    img_data = self._download_image(img_url)
                    if img_data:
                        images.append(img_data)
                        seen_urls.add(img_url)

            # Attachment direct (image unique)
            media = attachment.get("media", {})
            img_url = media.get("image", {}).get("src")
            if img_url and img_url not in seen_urls:
                img_data = self._download_image(img_url)
                if img_data:
                    images.append(img_data)
                    seen_urls.add(img_url)

        return images

    def _download_image(self, url: str) -> Optional[Dict[str, Any]]:
        """Télécharge une image si le téléchargement est activé."""
        if not self.image_downloader:
            return {"url": url}
        return self.image_downloader.download(url)

    def _fetch_comments(self, post_id: str) -> List[Dict[str, Any]]:
        """
        Récupère les commentaires d'un post.

        Args:
            post_id: ID du post Facebook.

        Returns:
            Liste des commentaires structurés.
        """
        data = self._make_request(
            endpoint=f"{post_id}/comments",
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
                "message": raw_comment.get("message", ""),
                "created_time": self._parse_datetime(
                    raw_comment.get("created_time", "")
                ),
                "author_name": raw_comment.get("from", {}).get("name", ""),
                "author_id": raw_comment.get("from", {}).get("id", ""),
                "like_count": raw_comment.get("like_count", 0),
            }
            comments.append(comment)

        return comments

    @staticmethod
    def _matches_subject(text: str, keywords: List[str]) -> bool:
        """
        Vérifie si un texte contient au moins un mot-clé du sujet.

        Args:
            text: Texte du post.
            keywords: Liste de mots-clés (en minuscules).

        Returns:
            True si au moins un mot-clé est trouvé.
        """
        if not text:
            return False
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)

    @staticmethod
    def _parse_datetime(dt_str: str) -> Optional[datetime]:
        """Parse une date ISO 8601 depuis l'API Graph."""
        if not dt_str:
            return None
        try:
            # Format: "2019-09-26T16:00:00+0000"
            return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%S+%f")
        except ValueError:
            try:
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            except ValueError:
                logger.debug(f"Format de date non reconnu: {dt_str}")
                return None

    def close(self) -> None:
        """Ferme les ressources (session HTTP, image downloader)."""
        super().close()
        if self.image_downloader:
            self.image_downloader.close()
