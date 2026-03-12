"""
Point d'entrée principal du collecteur social media.

Usage:
    python main.py --subject "Jacques Chirac décès" --source both --limit 50
    python main.py --subject "Chirac" --source facebook --limit 100
    python main.py --subject "Chirac" --source instagram --limit 30
"""
import argparse
import sys
from typing import List, Dict, Any

from config.settings import settings
from collectors.facebook_collector import FacebookCollector
from collectors.instagram_collector import InstagramCollector
from storage.mongodb_storage import MongoDBStorage
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Collecteur de posts Facebook/Instagram avec stockage MongoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python main.py --subject "Jacques Chirac décès" --source both --limit 50
  python main.py --subject "Chirac" --source facebook --limit 100
  python main.py --subject "Chirac" --source instagram --limit 30
        """,
    )
    parser.add_argument(
        "--subject",
        type=str,
        required=True,
        help='Sujet de collecte (ex: "Jacques Chirac décès")',
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["facebook", "instagram", "both"],
        default="both",
        help="Source de collecte (default: both)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=settings.DEFAULT_LIMIT,
        help=f"Nombre maximum de posts (default: {settings.DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Désactiver le téléchargement des images",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collecter sans sauvegarder dans MongoDB",
    )
    return parser.parse_args()


def collect_facebook(subject: str, limit: int) -> List[Dict[str, Any]]:
    """Lance la collecte Facebook."""
    logger.info("=== Collecte Facebook ===")
    with FacebookCollector() as collector:
        posts = collector.collect(subject=subject, limit=limit)
    logger.info(f"Facebook: {len(posts)} posts collectés")
    return posts


def collect_instagram(subject: str, limit: int) -> List[Dict[str, Any]]:
    """Lance la collecte Instagram."""
    logger.info("=== Collecte Instagram ===")
    with InstagramCollector() as collector:
        posts = collector.collect(subject=subject, limit=limit)
    logger.info(f"Instagram: {len(posts)} posts collectés")
    return posts


def save_to_mongodb(posts: List[Dict[str, Any]]) -> Dict[str, int]:
    """Sauvegarde les posts dans MongoDB."""
    if not posts:
        return {"inserted": 0, "duplicates": 0}

    logger.info(f"Sauvegarde de {len(posts)} posts dans MongoDB...")
    with MongoDBStorage() as storage:
        stats = storage.save_posts_bulk(posts)

    logger.info(
        f"MongoDB: {stats['inserted']} insérés, "
        f"{stats['duplicates']} doublons ignorés"
    )
    return stats


def print_summary(posts: List[Dict[str, Any]], mongo_stats: Dict[str, int]) -> None:
    """Affiche un résumé de la collecte."""
    fb_posts = [p for p in posts if p.get("source") == "facebook"]
    ig_posts = [p for p in posts if p.get("source") == "instagram"]

    total_images = sum(len(p.get("images", [])) for p in posts)
    total_comments = sum(len(p.get("comments", [])) for p in posts)

    print("\n" + "=" * 60)
    print("RÉSUMÉ DE LA COLLECTE")
    print("=" * 60)
    print(f"Posts Facebook    : {len(fb_posts)}")
    print(f"Posts Instagram   : {len(ig_posts)}")
    print(f"Total posts       : {len(posts)}")
    print(f"Total images      : {total_images}")
    print(f"Total commentaires: {total_comments}")
    print(f"Insérés MongoDB   : {mongo_stats.get('inserted', 0)}")
    print(f"Doublons ignorés  : {mongo_stats.get('duplicates', 0)}")
    print("=" * 60)


def main() -> int:
    """Fonction principale. Retourne 0 si succès, 1 si erreur."""
    args = parse_args()

    # Désactiver le téléchargement d'images si demandé
    if args.no_images:
        settings.IMAGE_DOWNLOAD = False

    # Validation des paramètres
    try:
        settings.validate()
    except ValueError as e:
        logger.error(f"Configuration invalide: {e}")
        return 1

    logger.info(
        f"Démarrage | sujet='{args.subject}' | "
        f"source={args.source} | limit={args.limit}"
    )

    all_posts: List[Dict[str, Any]] = []

    # Collecte Facebook
    if args.source in ("facebook", "both"):
        try:
            posts = collect_facebook(args.subject, args.limit)
            all_posts.extend(posts)
        except Exception as e:
            logger.error(f"Erreur collecte Facebook: {e}")

    # Collecte Instagram
    if args.source in ("instagram", "both"):
        try:
            posts = collect_instagram(args.subject, args.limit)
            all_posts.extend(posts)
        except Exception as e:
            logger.error(f"Erreur collecte Instagram: {e}")

    if not all_posts:
        logger.warning("Aucun post collecté.")
        return 0

    # Sauvegarde MongoDB (sauf dry-run)
    mongo_stats: Dict[str, int] = {"inserted": 0, "duplicates": 0}
    if not args.dry_run:
        try:
            mongo_stats = save_to_mongodb(all_posts)
        except Exception as e:
            logger.error(f"Erreur sauvegarde MongoDB: {e}")
            return 1
    else:
        logger.info("Mode dry-run: les posts ne sont PAS sauvegardés.")

    print_summary(all_posts, mongo_stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
