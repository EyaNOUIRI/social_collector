
---

# Social Media Collector — Facebook & Instagram

> Collecteur modulaire de posts (textes, images, commentaires) depuis Facebook et Instagram via la **Meta Graph API**, avec stockage persistant dans **MongoDB**.

---

## Structure du projet

```
social_collector/
│
├── config/
│   ├── __init__.py
│   └── settings.py              # Configuration centralisée (.env)
│
├── collectors/
│   ├── __init__.py
│   ├── base_collector.py        # Classe abstraite commune (HTTP, pagination, retry)
│   ├── facebook_collector.py    # Collecteur Facebook (posts, images, commentaires)
│   └── instagram_collector.py   # Collecteur Instagram (hashtags, médias, commentaires)
│
├── storage/
│   ├── __init__.py
│   └── mongodb_storage.py       # Couche de persistance MongoDB
│
├── utils/
│   ├── __init__.py
│   ├── image_downloader.py      # Téléchargement & encodage base64 des images
│   └── logger.py                # Logging centralisé (console + fichier)
│
├── tests/
│   ├── __init__.py
│   └── test_collectors.py       # Tests unitaires pytest (sans appels réseau)
│
├── main.py                      # Point d'entrée CLI (argparse)
├── requirements.txt
├── .env
└── README.md
```

---

## Architecture & modularité

Le projet est conçu selon le principe de **séparation des responsabilités** :
chaque couche est indépendante, remplaçable et testable isolément.

### 1. `config/settings.py` — Configuration unique

Toutes les variables d'environnement sont chargées **en un seul endroit** via `python-dotenv`.
Aucun fichier source ne contient de valeur en dur : token, URI MongoDB, IDs de comptes — tout passe par le fichier `.env`.

```python
# Exemple : changer de base MongoDB sans toucher au code
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB_NAME=social_collector_prod
```

### 2. `collectors/base_collector.py` — Socle commun réutilisable

Classe abstraite `BaseCollector` dont héritent Facebook et Instagram.
Elle centralise les comportements partagés :

* **Session HTTP robuste** avec retry automatique (`urllib3.Retry`) sur les codes `429`, `500`, `502`, `503`, `504`
* **Gestion du rate limiting** Meta via `Retry-After`
* **Pagination transparente** via `_paginate()`
* **Méthode abstraite** `collect()` à implémenter dans chaque sous-classe

```python
# Ajouter une nouvelle source (ex: Twitter/X) :
class TwitterCollector(BaseCollector):
    def collect(self, subject: str, limit: int) -> List[Dict]:
        ...
```

### 3. `collectors/facebook_collector.py` — Collecteur Facebook

* Récupère texte, image principale (`full_picture`), albums (`attachments`)
* Collecte les **commentaires** de chaque post
* **Filtrage par mots-clés** pour le sujet
* Comptage des **réactions** (likes, love…)

### 4. `collectors/instagram_collector.py` — Collecteur Instagram

Double stratégie :

1. **Recherche par hashtags** depuis le sujet (`"Jacques Chirac décès"` → `#jacqueschirac`, `#chirac`, `#deces`)
2. **Médias du compte** filtrés par mots-clés dans la caption

Gère `IMAGE`, `VIDEO` et `CAROUSEL_ALBUM`.

### 5. `storage/mongodb_storage.py` — Persistance MongoDB

* **Index unique** `(post_id, source)`
* **Index texte full-text** sur `message` et `subject`
* **Index tri** sur `created_time`
* Méthode `save_posts_bulk()` avec rapport `{inserted, duplicates, errors}`
* Utilisation comme **context manager** (`with MongoDBStorage() as storage:`)

```json
{
  "post_id": "123456789_987654321",
  "source": "facebook",
  "subject": "Jacques Chirac décès",
  "message": "C'est avec une grande tristesse...",
  "permalink_url": "https://www.facebook.com/permalink/...",
  "created_time": "2019-09-26T16:00:00",
  "images": [
    {"url": "...", "format": "jpeg", "data_b64": "..."}
  ],
  "comments": [{"comment_id": "...", "message": "..."}],
  "stats": {"reaction_count": 15420, "comment_count": 3},
  "collected_at": "2024-01-15T10:22:31.445Z"
}
```

### 6. `utils/image_downloader.py` — Images robustes

* Validation URL
* Formats acceptés : `JPEG`, `PNG`, `GIF`, `WEBP`
* Limite taille 10 MB
* Hash MD5 pour déduplication
* Encodage **base64** pour MongoDB

### 7. `utils/logger.py` — Logging structuré

* **Console** + **fichier collector.log**
* Format : `2024-01-15 10:22:31 | INFO | collectors.facebook | 12 posts collectés`

---

## Tests unitaires avec pytest

```bash
pytest tests/ -v
```

* **FacebookCollector** : filtre sujet, parsing date
* **InstagramCollector** : génération hashtags, suppression mots vides
* **ImageDownloader** : validation URL, gestion erreur
* **MongoDBStorage** : création index, exceptions

---

## Installation & utilisation

```bash
git clone https://github.com/EyaNOUIRI/social_collector
cd social_collector
pip install -r requirements.txt
cp .env .env
# Modifier .env avec vos credentials
```

### Commandes

```bash
python main.py --subject "Jacques Chirac décès" --source both --limit 50
python main.py --subject "Chirac" --source facebook --limit 100
python main.py --subject "Chirac" --source instagram --limit 30
python main.py --subject "Chirac" --source both --no-images
python main.py --subject "Chirac" --source both --dry-run
```

---

## Dépendances principales

| Package       | Version | Rôle                  |
| ------------- | ------- | --------------------- |
| requests      | 2.31.0  | Appels HTTP API Graph |
| pymongo       | 4.6.1   | MongoDB               |
| python-dotenv | 1.0.0   | Variables `.env`      |
| Pillow        | 10.2.0  | Traitement images     |
| pytest        | 7.4.4   | Tests unitaires       |
| pytest-mock   | 3.12.0  | Mocks                 |

---

## Lien GitHub

 [Social Media Collector — Facebook & Instagram](https://github.com/EyaNOUIRI/social_collector)

---

## Notes

* Projet testé sur **vraies APIs Meta** et MongoDB.
* Tokens et IDs personnels **supprimés** pour le partage.
* Respecter [conditions Meta](https://developers.facebook.com/terms/) et **RGPD**.

