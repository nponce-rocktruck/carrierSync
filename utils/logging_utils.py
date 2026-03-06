"""
Configuración de logging para CarrierSync API.
"""

import logging
import os


def configure_logging() -> None:
    """Configura logging global para la API."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    logging.basicConfig(level=level, handlers=[console_handler])
