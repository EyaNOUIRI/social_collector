"""
Module de logging centralisé.
Fournit un logger configuré avec handlers console et fichier.
"""
import logging
import sys
from config.settings import settings


def get_logger(name: str) -> logging.Logger:
    """
    Retourne un logger configuré pour le module donné.

    Args:
        name: Nom du module (typiquement __name__)

    Returns:
        Logger configuré avec handler console et fichier.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler fichier
    try:
        file_handler = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        logger.warning(f"Impossible de créer le fichier de log: {e}")

    return logger
