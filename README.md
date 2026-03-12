#  Social Media Collector — Facebook & Instagram

> Collecteur modulaire de posts (textes, images, commentaires) depuis Facebook et Instagram
> via la **Meta Graph API**, avec stockage persistant dans **MongoDB**.



##  Structure du projet


social_collector/
│
├── config/
│   ├── __init__.py
│   └── settings.py              #  Configuration centralisée (.env)
│
├── collectors/
│   ├── __init__.py
│   ├── base_collector.py        #  Classe abstraite commune (HTTP, pagination, retry)
│   ├── facebook_collector.py    #  Collecteur Facebook (posts, images, commentaires)
│   └── instagram_collector.py  #  Collecteur Instagram (hashtags, médias, commentaires)
│
├── storage/
│   ├── __init__.py
│   └── mongodb_storage.py       #   Couche de persistance MongoDB
│
├── utils/
│   ├── __init__.py
│   ├── image_downloader.py      #   Téléchargement & encodage base64 des images
│   └── logger.py                #  Logging centralisé (console + fichier)
│
├── tests/
│   ├── __init__.py
│   └── test_collectors.py       #  Tests unitaires pytest (sans appels réseau)
│
├── main.py                      #  Point d'entrée CLI (argparse)
├── requirements.txt
├── .env
└── README.md




##  Architecture & modularité

Le projet est conçu selon le principe de **séparation des responsabilités** :
chaque couche est indépendante, remplaçable et testable isolément.

### 1. `config/settings.py` — Configuration unique

Toutes les variables d'environnement sont chargées **en un seul endroit** via `python-dotenv`.
Aucun fichier source ne contient de valeur en dur : token, URI MongoDB, IDs de comptes —
tout passe par le fichier `.env`.

python
# Exemple : changer de base MongoDB sans toucher au code
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB_NAME=social_collector_prod




### 2. `collectors/base_collector.py` — Socle commun réutilisable

Classe abstraite `BaseCollector` dont héritent Facebook et Instagram.
Elle centralise les comportements partagés :

- **Session HTTP robuste** avec retry automatique (`urllib3.Retry`) sur les codes
  `429`, `500`, `502`, `503`, `504` — backoff exponentiel entre tentatives
- **Gestion du rate limiting** Meta : détection du header `Retry-After` et mise en attente
- **Pagination transparente** via la méthode `_paginate()` — parcourt automatiquement
  toutes les pages de résultats de l'API Graph sans code dupliqué
- **Méthode abstraite** `collect()` : chaque sous-classe implémente sa propre logique


# Ajouter une nouvelle source (ex: Twitter/X) : hériter et implémenter collect()
class TwitterCollector(BaseCollector):
    def collect(self, subject: str, limit: int) -> List[Dict]:
        ...
```

---

### 3. `collectors/facebook_collector.py` — Collecteur Facebook

Collecte depuis une **Page Facebook** via l'endpoint `/posts` :

- Récupère texte, image principale (`full_picture`), albums d'images (`attachments`)
- Collecte les **commentaires** associés à chaque post
- **Filtrage par mots-clés** : seuls les posts mentionnant le sujet sont retenus
- Comptage des **réactions** (likes, love, etc.)

---

### 4. `collectors/instagram_collector.py` — Collecteur Instagram

Double stratégie de collecte pour maximiser la couverture :

1. **Recherche par hashtags** générés automatiquement depuis le sujet :
   `"Jacques Chirac décès"` → `#jacqueschirac`, `#chirac`, `#deces`
   (suppression des accents et des mots vides : *le, la, du, des…*)
2. **Médias du compte** filtrés par mots-clés dans la caption

Gère les types `IMAGE`, `VIDEO` (thumbnail) et `CAROUSEL_ALBUM`.

---

### 5. `storage/mongodb_storage.py` — Persistance MongoDB

- **Index unique** sur `(post_id, source)` : les doublons sont silencieusement ignorés,
  permettant de relancer la collecte sans corrompre la base
- **Index texte full-text** sur `message` et `subject` pour des recherches rapides
- **Index de tri** sur `created_time` (DESC) pour récupérer les posts les plus récents
- Méthode `save_posts_bulk()` avec rapport détaillé `{inserted, duplicates, errors}`
- Utilisation comme **context manager** (`with MongoDBStorage() as storage:`)
  pour garantir la fermeture de connexion même en cas d'exception

**Exemple de document stocké dans MongoDB :**

```json
{
  "post_id": "123456789_987654321",
  "source": "facebook",
  "subject": "Jacques Chirac décès",
  "message": "C'est avec une grande tristesse que nous apprenons le décès de Jacques Chirac...",
  "permalink_url": "https://www.facebook.com/permalink/...",
  "created_time": "2019-09-26T16:00:00",
  "images": [
    {
      "url": "https://external.fbcdn.net/...",
      "format": "jpeg",
      "width": 1200,
      "height": 630,
      "size_bytes": 98432,
      "md5": "a1b2c3d4e5f6...",
      "data_b64": "/9j/4AAQSkZJRgAB...",
      "content_type": "image/jpeg"
    }
  ],
  "comments": [
    {
      "comment_id": "987654321_111",
      "message": "Repose en paix, Monsieur le Président.",
      "created_time": "2019-09-26T17:30:00",
      "author_name": "Marie Dupont",
      "like_count": 42
    }
  ],
  "stats": {
    "reaction_count": 15420,
    "comment_count": 3,
    "image_count": 1
  },
  "collected_at": "2024-01-15T10:22:31.445Z"
}
```

---

### 6. `utils/image_downloader.py` — Images robustes

- Validation de l'URL avant tout appel réseau
- Vérification du format (`JPEG`, `PNG`, `GIF`, `WEBP` uniquement)
- Limite de taille à **10 MB** pour éviter les téléchargements abusifs
- Calcul du **hash MD5** pour déduplication côté stockage
- Encodage **base64** pour stockage binaire natif dans MongoDB

---

### 7. `utils/logger.py` — Logging structuré

Logger configuré avec deux handlers simultanés :

- **Console** (stdout) pour le suivi en temps réel
- **Fichier** `collector.log` pour l'historique persistant

Format lisible : `2024-01-15 10:22:31 | INFO     | collectors.facebook | 12 posts collectés`

---

##  Tests unitaires avec pytest

Les tests sont situés dans `tests/test_collectors.py` et couvrent les composants critiques
**sans aucun appel réseau réel** grâce aux mocks (`unittest.mock`).

### Lancer les tests

```bash
pytest tests/ -v
```

### Ce qui est testé

| Classe testée | Cas de test |
|---|---|
| `FacebookCollector` | Retour vide sans `page_id`, filtrage par mots-clés, parsing de date, détection de sujet |
| `InstagramCollector` | Génération de hashtags, suppression des mots vides, retour vide sans account ID |
| `ImageDownloader` | Validation d'URL, retour `None` sur erreur HTTP |
| `MongoDBStorage` | Exception si non connecté, création des index |

### Exemple de test

```python
def test_collect_filters_by_subject(self, mock_session, mock_downloader):
    """Seuls les posts contenant les mots-clés du sujet sont retournés."""
    # L'API retourne 2 posts : un sur Chirac, un sur la météo
    # Seul le post sur Chirac doit être dans le résultat
    result = collector.collect("Chirac", limit=10)
    assert len(result) == 1
    assert "chirac" in result[0]["message"].lower()
```

---

##  Installation et utilisation

### Prérequis

- Python 3
- MongoDB (local ou [Atlas](https://www.mongodb.com/atlas))
- Application Meta approuvée avec un **Page Access Token**

### Installation

```bash
git clone <repo>
cd social_collector
pip install -r requirements.txt
cp .env .env
# Éditer .env avec vos credentials
```

### Configuration `.env`

```env
META_ACCESS_TOKEN=EAAxxxxxxxxxxxxxxx
FACEBOOK_PAGE_ID=123456789
INSTAGRAM_BUSINESS_ACCOUNT_ID=987654321
MONGODB_URI=mongodb://localhost:27017/
MONGODB_DB_NAME=social_media_collector
IMAGE_DOWNLOAD=true
DEFAULT_LIMIT=50
```

### Commandes

```bash
# Collecter depuis Facebook ET Instagram
python main.py --subject "Jacques Chirac décès" --source both --limit 50

# Facebook uniquement
python main.py --subject "Jacques Chirac" --source facebook --limit 100

# Instagram uniquement
python main.py --subject "Chirac" --source instagram --limit 30

# Sans téléchargement d'images (plus rapide)
python main.py --subject "Chirac" --source both --no-images

# Tester sans écrire dans MongoDB
python main.py --subject "Chirac" --source both --dry-run
```

### Résultat en console

```
============================================================
RÉSUMÉ DE LA COLLECTE
============================================================
Posts Facebook    : 18
Posts Instagram   : 27
Total posts       : 45
Total images      : 61
Total commentaires: 312
Insérés MongoDB   : 43
Doublons ignorés  : 2
============================================================
```

---

##  Dépendances

| Package | Version | Rôle |
|---|---|---|
| `requests` | 2.31.0 | Appels HTTP vers l'API Graph |
| `pymongo` | 4.6.1 | Connexion et opérations MongoDB |
| `python-dotenv` | 1.0.0 | Chargement des variables `.env` |
| `Pillow` | 10.2.0 | Validation et traitement des images |
| `pytest` | 7.4.4 | Framework de tests unitaires |
| `pytest-mock` | 3.12.0 | Mocks pour les tests |

---

##  Statut des tests & données réelles

> **Ce projet a été testé avec de vraies APIs Meta et une vraie base MongoDB.**

Les collecteurs Facebook et Instagram ont été validés sur des données réelles :
posts publics, images téléchargées et encodées en base64, commentaires récupérés,
documents correctement insérés dans MongoDB avec déduplication fonctionnelle.

```
  Les tokens et IDs utilisés pour tester le projet sont des informations
    personnelles. Ils ont été supprimés et masqués avant le partage du projet.
    Remplacez-les par vos propres credentials dans le fichier .env.
```

Les variables sensibles suivantes ont été retirées pour la sécurité :

| Variable | Description |
|---|---|
| `META_ACCESS_TOKEN` | Token d'accès Meta Graph API (personnel) |
| `META_APP_ID` / `META_APP_SECRET` | Identifiants de l'application Meta |
| `FACEBOOK_PAGE_ID` | ID de la Page Facebook testée |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | ID du compte Instagram Business testé |
| `MONGODB_URI` | URI de connexion MongoDB (avec credentials) |

Pour reproduire les résultats, configurez votre propre fichier `.env`
à partir du modèle fourni `.env`.

---

##  Notes légales

Ce projet utilise l'**API officielle Meta Graph API** — aucun scraping.
L'accès aux données requiert une application approuvée par Meta.
Respectez les [Conditions d'utilisation de Meta](https://developers.facebook.com/terms/)
et le **RGPD** lors de toute collecte et conservation de données personnelles.