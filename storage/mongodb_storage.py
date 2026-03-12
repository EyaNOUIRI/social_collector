"""
Couche de persistance MongoDB.
Gère la connexion, l'insertion et la récupération des posts collectés.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import (
    ConnectionFailure,
    DuplicateKeyError,
    ServerSelectionTimeoutError,
)

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class MongoDBStorage:
    """
    Gère le stockage des posts et médias dans MongoDB.

    Usage:
        with MongoDBStorage() as storage:
            storage.save_post(post_data)
    """

    def __init__(
        self,
        uri: str = settings.MONGODB_URI,
        db_name: str = settings.MONGODB_DB_NAME,
    ):
        self.uri = uri
        self.db_name = db_name
        self.client: Optional[MongoClient] = None
        self.db = None

    def connect(self) -> None:
        """Établit la connexion à MongoDB et crée les index."""
        try:
            self.client = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            # Test de connexion
            self.client.admin.command("ping")
            self.db = self.client[self.db_name]
            self._create_indexes()
            logger.info(f"Connecté à MongoDB: {self.db_name}")
        except ServerSelectionTimeoutError as e:
            logger.error(f"Impossible de joindre MongoDB: {e}")
            raise ConnectionFailure(f"MongoDB non disponible: {e}")

    def _create_indexes(self) -> None:
        """Crée les index pour optimiser les recherches."""
        posts_col = self.db[settings.COLLECTION_POSTS]

        posts_col.create_index(
            [("post_id", ASCENDING), ("source", ASCENDING)],
            unique=True,
            name="idx_post_id_source",
        )
        posts_col.create_index([("subject", ASCENDING)], name="idx_subject")
        posts_col.create_index([("created_time", DESCENDING)], name="idx_created_time")
        posts_col.create_index(
            [("message", "text"), ("subject", "text")],
            name="idx_text_search",
        )
        logger.debug("Index MongoDB créés.")

    def save_post(self, post: Dict[str, Any]) -> Optional[str]:
        """
        Insère un post dans la collection MongoDB.
        Ignore les doublons (même post_id + source).

        Args:
            post: Dictionnaire représentant le post avec ses métadonnées.

        Returns:
            L'ID MongoDB inséré (str) ou None si doublon/erreur.
        """
        if self.db is None:
            raise RuntimeError("Non connecté à MongoDB. Appelez connect().")

        post["collected_at"] = datetime.utcnow()

        try:
            result = self.db[settings.COLLECTION_POSTS].insert_one(post)
            logger.debug(
                f"Post sauvegardé: {post.get('post_id')} [{post.get('source')}]"
            )
            return str(result.inserted_id)

        except DuplicateKeyError:
            logger.debug(f"Post déjà existant (doublon ignoré): {post.get('post_id')}")
            return None

        except Exception as e:
            logger.error(f"Erreur insertion MongoDB: {e}")
            return None

    def save_posts_bulk(self, posts: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Insère plusieurs posts en une seule opération.

        Returns:
            Dictionnaire {inserted: N, duplicates: N, errors: N}
        """
        stats = {"inserted": 0, "duplicates": 0, "errors": 0}

        for post in posts:
            result = self.save_post(post)
            if result:
                stats["inserted"] += 1
            else:
                stats["duplicates"] += 1

        logger.info(
            f"Bulk insert: {stats['inserted']} insérés, "
            f"{stats['duplicates']} doublons"
        )
        return stats

    def get_posts_by_subject(
        self,
        subject: str,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Récupère les posts par sujet de collecte."""
        query: Dict[str, Any] = {"subject": subject}
        if source:
            query["source"] = source

        cursor = (
            self.db[settings.COLLECTION_POSTS]
            .find(query, {"_id": 0})
            .sort("created_time", DESCENDING)
            .limit(limit)
        )
        return list(cursor)

    def count_posts(self, subject: Optional[str] = None) -> int:
        """Retourne le nombre de posts, filtré par sujet si fourni."""
        query = {"subject": subject} if subject else {}
        return self.db[settings.COLLECTION_POSTS].count_documents(query)

    def close(self) -> None:
        """Ferme la connexion MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Connexion MongoDB fermée.")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
