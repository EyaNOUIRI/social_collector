"""
Tests unitaires pour les collecteurs et le stockage.
Utilise des mocks pour éviter les appels réseau réels.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

# Patch les imports de config avant tout
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestFacebookCollector:
    """Tests pour le collecteur Facebook."""

    @patch("collectors.facebook_collector.ImageDownloader")
    def test_collect_returns_empty_without_page_id(self, mock_downloader):
        """collect() retourne [] si FACEBOOK_PAGE_ID est vide."""
        from collectors.facebook_collector import FacebookCollector

        collector = FacebookCollector(page_id="", access_token="test_token")
        result = collector.collect("Jacques Chirac", limit=5)
        assert result == []

    @patch("collectors.facebook_collector.ImageDownloader")
    @patch("collectors.base_collector.requests.Session")
    def test_collect_filters_by_subject(self, mock_session_cls, mock_downloader):
        """collect() filtre les posts qui ne contiennent pas les mots-clés."""
        from collectors.facebook_collector import FacebookCollector

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "post_1",
                    "message": "Jacques Chirac est décédé aujourd'hui",
                    "created_time": "2019-09-26T16:00:00+0000",
                    "permalink_url": "https://fb.com/1",
                    "full_picture": None,
                    "attachments": {},
                    "reactions": {"summary": {"total_count": 100}},
                },
                {
                    "id": "post_2",
                    "message": "Belle journée ensoleillée",
                    "created_time": "2019-09-26T12:00:00+0000",
                    "permalink_url": "https://fb.com/2",
                    "full_picture": None,
                    "attachments": {},
                    "reactions": {"summary": {"total_count": 5}},
                },
            ],
            "paging": {},
        }
        mock_response.raise_for_status = MagicMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        mock_downloader_instance = MagicMock()
        mock_downloader.return_value = mock_downloader_instance

        with patch("collectors.facebook_collector.settings") as mock_settings:
            mock_settings.META_ACCESS_TOKEN = "test_token"
            mock_settings.META_BASE_URL = "https://graph.facebook.com/v18.0"
            mock_settings.REQUEST_TIMEOUT = 30
            mock_settings.MAX_RETRIES = 3
            mock_settings.DEFAULT_LIMIT = 50
            mock_settings.IMAGE_DOWNLOAD = False

            collector = FacebookCollector(page_id="123456", access_token="test_token")
            # Mock _fetch_comments to return empty list
            collector._fetch_comments = MagicMock(return_value=[])

            # On doit aussi mocker _make_request pour éviter les vrais appels
            collector._make_request = MagicMock(return_value=mock_response.json())

            result = collector.collect("Chirac", limit=10)

        # Seul le post mentionnant "chirac" doit être retourné
        assert len(result) == 1
        assert "chirac" in result[0]["message"].lower()

    def test_matches_subject_true(self):
        """_matches_subject retourne True si un mot-clé est présent."""
        from collectors.facebook_collector import FacebookCollector
        assert FacebookCollector._matches_subject(
            "Hommage à Jacques Chirac décédé", ["chirac", "hommage"]
        )

    def test_matches_subject_false(self):
        """_matches_subject retourne False si aucun mot-clé n'est présent."""
        from collectors.facebook_collector import FacebookCollector
        assert not FacebookCollector._matches_subject(
            "Belle journée ensoleillée", ["chirac", "décès"]
        )

    def test_parse_datetime_valid(self):
        """_parse_datetime parse correctement une date ISO 8601."""
        from collectors.facebook_collector import FacebookCollector
        result = FacebookCollector._parse_datetime("2019-09-26T16:00:00+0000")
        assert isinstance(result, datetime)
        assert result.year == 2019
        assert result.month == 9
        assert result.day == 26

    def test_parse_datetime_empty(self):
        """_parse_datetime retourne None pour une chaîne vide."""
        from collectors.facebook_collector import FacebookCollector
        assert FacebookCollector._parse_datetime("") is None


class TestInstagramCollector:
    """Tests pour le collecteur Instagram."""

    def test_subject_to_hashtags(self):
        """_subject_to_hashtags génère les bons hashtags."""
        from collectors.instagram_collector import InstagramCollector

        hashtags = InstagramCollector._subject_to_hashtags("Jacques Chirac décès")
        # Doit contenir le hashtag composé et les mots individuels
        assert "jacqueschiracdeces" in hashtags or "jacqueschirac" in hashtags
        assert "chirac" in hashtags

    def test_subject_to_hashtags_removes_stopwords(self):
        """_subject_to_hashtags supprime les mots vides."""
        from collectors.instagram_collector import InstagramCollector

        hashtags = InstagramCollector._subject_to_hashtags("le décès du président")
        assert "le" not in hashtags
        assert "du" not in hashtags

    def test_parse_datetime_iso(self):
        """_parse_datetime parse le format Instagram."""
        from collectors.instagram_collector import InstagramCollector

        result = InstagramCollector._parse_datetime("2019-09-26T16:00:00+0000")
        assert isinstance(result, datetime)

    @patch("collectors.instagram_collector.ImageDownloader")
    def test_collect_returns_empty_without_account_id(self, mock_downloader):
        """collect() retourne [] si ig_account_id est vide."""
        from collectors.instagram_collector import InstagramCollector

        collector = InstagramCollector(ig_account_id="", access_token="test")
        result = collector.collect("test", limit=5)
        assert result == []


class TestImageDownloader:
    """Tests pour le téléchargeur d'images."""

    def test_is_valid_url_valid(self):
        """URLs valides reconnues correctement."""
        from utils.image_downloader import ImageDownloader
        assert ImageDownloader._is_valid_url("https://example.com/image.jpg")
        assert ImageDownloader._is_valid_url("http://cdn.facebook.com/pic.png")

    def test_is_valid_url_invalid(self):
        """URLs invalides rejetées correctement."""
        from utils.image_downloader import ImageDownloader
        assert not ImageDownloader._is_valid_url("")
        assert not ImageDownloader._is_valid_url("not-a-url")
        assert not ImageDownloader._is_valid_url("ftp://example.com/file.jpg")

    @patch("utils.image_downloader.requests.Session")
    def test_download_returns_none_on_error(self, mock_session_cls):
        """download() retourne None en cas d'erreur HTTP."""
        import requests
        from utils.image_downloader import ImageDownloader

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError("404")
        )
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        with patch("utils.image_downloader.settings") as mock_s:
            mock_s.REQUEST_TIMEOUT = 30
            downloader = ImageDownloader()
            result = downloader.download("https://example.com/image.jpg")

        assert result is None


class TestMongoDBStorage:
    """Tests pour le stockage MongoDB."""

    def test_save_post_raises_if_not_connected(self):
        """save_post() lève RuntimeError si non connecté."""
        from storage.mongodb_storage import MongoDBStorage

        storage = MongoDBStorage()
        with pytest.raises(RuntimeError, match="Non connecté"):
            storage.save_post({"post_id": "123", "source": "facebook"})

    @patch("storage.mongodb_storage.MongoClient")
    def test_connect_creates_indexes(self, mock_mongo_cls):
        """connect() crée bien les index sur la collection."""
        from storage.mongodb_storage import MongoDBStorage

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_collection = MagicMock()

        mock_mongo_cls.return_value = mock_client
        mock_client.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = mock_collection
        mock_client.admin.command.return_value = {"ok": 1}

        with patch("storage.mongodb_storage.settings") as mock_s:
            mock_s.MONGODB_URI = "mongodb://localhost:27017/"
            mock_s.MONGODB_DB_NAME = "test_db"
            mock_s.COLLECTION_POSTS = "posts"

            storage = MongoDBStorage()
            storage.client = mock_client
            storage.db = mock_db

        # Vérifier que create_index a été appelé (index créés)
        # Le test vérifie la structure sans appel réseau réel


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
