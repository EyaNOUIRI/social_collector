"""
Classe abstraite de base pour tous les collecteurs de réseaux sociaux.
Définit l'interface commune et les utilitaires partagés.
"""
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class BaseCollector(ABC):
    """
    Classe abstraite définissant l'interface commune des collecteurs.

    Chaque sous-classe implémente la logique spécifique à sa plateforme
    (Facebook ou Instagram) tout en réutilisant les utilitaires communs:
    session HTTP avec retry, gestion des erreurs, pagination.
    """

    def __init__(self, access_token: str = settings.META_ACCESS_TOKEN):
        self.access_token = access_token
        self.base_url = settings.META_BASE_URL
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        """
        Construit une session HTTP avec retry automatique.

        Retry sur les erreurs 429 (rate limit), 500, 502, 503, 504.
        Backoff exponentiel entre les tentatives.
        """
        session = requests.Session()

        retry_strategy = Retry(
            total=settings.MAX_RETRIES,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Effectue une requête GET vers l'API Graph.

        Args:
            endpoint: Chemin de l'endpoint (ex: "me/posts").
            params: Paramètres de requête supplémentaires.

        Returns:
            Données JSON de la réponse, ou None en cas d'erreur.
        """
        url = f"{self.base_url}/{endpoint}"
        request_params = {"access_token": self.access_token}
        if params:
            request_params.update(params)

        try:
            response = self.session.get(
                url,
                params=request_params,
                timeout=settings.REQUEST_TIMEOUT,
            )

            if response.status_code == 429:
                # Rate limit: attendre avant retry
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limit atteint. Attente {retry_after}s...")
                time.sleep(retry_after)
                return self._make_request(endpoint, params)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            error_data = {}
            try:
                error_data = e.response.json()
            except Exception:
                pass

            error_msg = error_data.get("error", {}).get("message", str(e))
            error_code = error_data.get("error", {}).get("code", "unknown")
            logger.error(
                f"HTTP {e.response.status_code} [{error_code}] "
                f"pour {endpoint}: {error_msg}"
            )
            return None

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Erreur de connexion pour {endpoint}: {e}")
            return None

        except requests.exceptions.Timeout:
            logger.error(f"Timeout pour {endpoint}")
            return None

        except Exception as e:
            logger.error(f"Erreur inattendue pour {endpoint}: {e}")
            return None

    def _paginate(
        self,
        initial_data: Dict[str, Any],
        max_items: int,
        collected: List[Dict],
        item_processor,
    ) -> List[Dict[str, Any]]:
        """
        Gère la pagination de l'API Graph.

        Args:
            initial_data: Données de la première page.
            max_items: Nombre maximum d'items à collecter.
            collected: Liste dans laquelle ajouter les résultats.
            item_processor: Fonction appelée pour chaque item brut.

        Returns:
            Liste complète des items collectés.
        """
        data = initial_data

        while data and len(collected) < max_items:
            items = data.get("data", [])

            for item in items:
                if len(collected) >= max_items:
                    break
                processed = item_processor(item)
                if processed:
                    collected.append(processed)

            # Vérifier si une page suivante existe
            paging = data.get("paging", {})
            next_url = paging.get("next")

            if not next_url or len(collected) >= max_items:
                break

            # Fetch la page suivante directement via l'URL "next"
            try:
                response = self.session.get(
                    next_url, timeout=settings.REQUEST_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()
                logger.debug(
                    f"Page suivante chargée, total collecté: {len(collected)}"
                )
            except Exception as e:
                logger.error(f"Erreur pagination: {e}")
                break

        return collected

    @abstractmethod
    def collect(self, subject: str, limit: int) -> List[Dict[str, Any]]:
        """
        Collecte des posts relatifs au sujet donné.

        Args:
            subject: Sujet de recherche (ex: "Jacques Chirac décès").
            limit: Nombre maximum de posts à collecter.

        Returns:
            Liste de posts structurés prêts pour MongoDB.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Ferme la session HTTP."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
